# CrowdCast 需要天気図

楽天トラベルAPIを毎日呼び出して全国35エリアのホテル空室率・価格統計を収集し、
「観測日 × 宿泊日までの残日数」のヒートマップ（需要天気図）として可視化するシステム。

**このシステムの価値は現在の価格ではなく、毎日積み上がる時系列データにある。**
ホテル個別の情報は保存せず、エリア単位の集計統計のみを蓄積する。

---

## 目次

1. [ディレクトリ構成](#ディレクトリ構成)
2. [セットアップ](#セットアップ)
3. [日次自動収集](#日次自動収集)
4. [ヒートマップ生成](#ヒートマップ生成)
5. [分析ツール](#分析ツール)
6. [データモデル](#データモデル)
7. [対象エリア一覧](#対象エリア一覧)
8. [APIクライアントの仕様](#apiクライアントの仕様)
9. [既知の制約・注意事項](#既知の制約注意事項)
10. [エリアの追加方法](#エリアの追加方法)
11. [トラブルシューティング](#トラブルシューティング)

---

## ディレクトリ構成

```
CrowdCast_claudecode/
│
├── demand_weather/            # コアパッケージ
│   ├── config.py              # エリア定義・定数（AREAS, FORECAST_DAYS, DB_PATH 等）
│   ├── db.py                  # SQLiteスキーマ作成・upsert
│   ├── rakuten_client.py      # 楽天トラベルAPIクライアント
│   └── csv_export.py          # エリア別CSVアペンド書き込み
│
├── data/
│   ├── demand_weather.db      # SQLiteデータベース（本体。毎晩自動更新）
│   ├── events.csv             # 手動登録イベント（異常値の原因付け用）
│   └── csv/                   # エリア別CSV（naha.csv, shinjuku.csv 等）
│
├── output/                    # 生成されたヒートマップPNG（70+枚）
│
├── docs/rakuten_api/
│   ├── FIELDS.md              # 楽天トラベルAPI全フィールド調査結果
│   ├── area_hotel_counts.json # エリア選定時のホテル数調査結果
│   └── samples/               # 各エンドポイントのレスポンスサンプルJSON
│
├── fetch_demand.py            # 日次バッチ（エントリポイント）
├── heatmap.py                 # ヒートマップPNG生成
├── detect_events.py           # 異常値検知＋祝日・イベント自動紐付け
├── detect_anomalies.py        # 簡易異常値スキャン（旧版）
├── plot_stay_date_trend.py    # 斜め切り：1宿泊日を観測日方向に追う
├── plot_residual_curve.py     # 縦切り：1観測日のスナップショット
├── plot_lead_time_series.py   # 横切り：残日数固定でカレンダー方向に展開
│
├── discover_area_codes.py     # エリアコード検索ヘルパー（初期設定用）
├── rank_areas_by_hotel_count.py  # エリア選定調査スクリプト（初期設定用）
├── research_rakuten_api.py    # APIフィールド調査スクリプト（初期設定用）
│
├── sim_step1〜5_*.py          # シミュレーション（実データなしで動作確認用）
│
├── .env                       # API認証情報（gitignore済）
├── .env.example               # 認証情報のテンプレート
├── API.txt                    # API認証情報の控え（gitignore済）
└── requirements.txt
```

---

## セットアップ

### 1. 依存パッケージのインストール

```
pip install -r requirements.txt
```

### 2. 楽天ウェブサービスのアプリ登録

https://webservice.rakuten.co.jp/ でアプリを登録し、以下を取得する。

- **Application ID**（UUID形式: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`）
- **Access Key**（`pk_` で始まる文字列）
- **許可されたWebサイト**（登録時に入力したドメイン。`http://localhost` 等でよい）

> **注意:** 2026年2月の楽天API移行により、Application ID + Access Key に加えて
> Origin/Refererヘッダーが必須になった。登録ドメインと一致しないとリクエストが拒否される。

現在のAPI認証情報は `API.txt` に記載。アプリ有効期限: **2027-06-20**。

### 3. `.env` の設定

```
cp .env.example .env
```

`.env` を編集して認証情報を入力する。

```
RAKUTEN_APP_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
RAKUTEN_ACCESS_KEY=pk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
RAKUTEN_ORIGIN=http://localhost
```

`RAKUTEN_ORIGIN` は楽天アプリ登録時の「許可されたWebサイト」と完全一致させること。

### 4. Windowsタスクスケジューラの登録

毎日0時に `fetch_demand.py` が自動実行されるよう登録済み。

- **タスク名:** `CrowdCast_FetchDemand`
- **スケジュール:** 毎日 00:00
- **コマンド:** `python fetch_demand.py`
- **実行時間上限:** 3時間（現在の実行時間は約3時間。上限に近いため注意）

新規PCへの移行時は以下でタスクを再登録する。

```powershell
schtasks /create /tn "CrowdCast_FetchDemand" /tr "python C:\path\to\fetch_demand.py" /sc daily /st 00:00 /ru SYSTEM
```

実行状況の確認:

```powershell
schtasks /query /tn "CrowdCast_FetchDemand" /fo LIST
```

---

## 日次自動収集

### 動作の流れ

毎日0:00に `fetch_demand.py` が起動し、以下を35エリア分繰り返す。

1. `SimpleHotelSearch` でエリア内の登録ホテル総数を取得（1コール）
2. 今日〜89日後の各宿泊日について `VacantHotelSearch` で空室統計・価格を取得（3コール/日）
3. SQLite の `area_daily_stats` テーブルに upsert
4. `data/csv/<area_key>.csv` に追記
5. `output/<area_key>_vacancy_ratio.png` と `output/<area_key>_median_price.png` を再生成

**合計: 約9,500 APIコール/日、所要時間: 約3時間**

### 手動実行

```
python fetch_demand.py
```

特定エリアのみ:

```
python fetch_demand.py --areas naha shinjuku
```

### 価格取得の仕組み（3コール法）

全件取得せず、ソート+順位指定で min/median/max を3コールで取得している。

| コール | sort | rank | 取得値 |
|--------|------|------|--------|
| 1 | `+roomCharge`（安い順） | 1位 | min_price、vacant_count |
| 2 | `+roomCharge`（安い順） | (count+1)//2 位 | median_price |
| 3 | `-roomCharge`（高い順） | 1位 | max_price |

> **重要:** ソートキーは `roomInfo.dailyCharge.total`（代表プランの料金）であり、
> `hotelBasicInfo.hotelMinCharge`（全プランの最安値）ではない。実機検証済み。
> そのため取得価格は「そのホテルの絶対的最安値」ではなく「代表プランの価格」。

---

## ヒートマップ生成

### 自動生成

`fetch_demand.py` がエリアごとの収集完了後に自動でPNGを生成する。

### 手動での全エリア再生成

```
python heatmap.py --metric vacancy_ratio
python heatmap.py --metric median_price
```

特定エリアのみ:

```
python heatmap.py --areas naha shinjuku --metric median_price
```

### カラーマップのレンジ

| メトリクス | レンジ | カラーマップ |
|-----------|--------|------------|
| vacancy_ratio | 0〜100%（固定） | Blues_r（青：空室あり、白：満室） |
| median_price / min_price / max_price | DBの全エリア実データのmin〜max（自動） | Reds（赤：高価格、白：低価格） |

価格系は全エリア共通レンジのため、エリア間で色の濃さを直接比較できる。

---

## 分析ツール

### 異常値検知（推奨）

```
python detect_events.py
```

エリア×曜日の平常値からz-scoreを計算し、異常な宿泊日を検出する。
検出した日付を `data/events.csv` の手動登録イベント・祝日・慣習的連休と自動照合する。

原因不明の異常が見つかったら `data/events.csv` に1行追記すれば次回から反映される。

```csv
date,name
2026-08-11,山の日振替
```

### 縦断的な可視化

| スクリプト | 使い方 | 意味 |
|-----------|--------|------|
| `plot_stay_date_trend.py` | `python plot_stay_date_trend.py naha 2026-08-15` | 1つの宿泊日が観測日とともにどう変化したか（斜め切り） |
| `plot_residual_curve.py` | `python plot_residual_curve.py naha` | ある観測日時点での「残日数vs空室率」スナップショット（縦切り） |
| `plot_lead_time_series.py` | `python plot_lead_time_series.py naha 7` | 残7日時点の空室率をカレンダー順に並べた時系列（横切り） |

---

## データモデル

### テーブル: `area_daily_stats`

主キー: `(observation_date, stay_date, detail_class)`

| カラム | 型 | 内容 |
|--------|-----|------|
| observation_date | TEXT | 観測日（YYYY-MM-DD） |
| stay_date | TEXT | 宿泊日（YYYY-MM-DD） |
| detail_class | TEXT | エリアキー（`shinjuku`, `naha` 等） |
| days_until_stay | INTEGER | 宿泊日までの残日数 |
| observed_hotel_count | INTEGER | エリア内の登録ホテル総数 |
| vacant_hotel_count | INTEGER | 空室ホテル件数 |
| vacancy_ratio | REAL | vacant / observed |
| min_price | INTEGER | 代表プランの最安値（円） |
| median_price | INTEGER | 代表プランの中央値（円） |
| max_price | INTEGER | 代表プランの最高値（円） |

upsertは `INSERT OR REPLACE` のため同日に再実行しても重複しない。

### CSVファイル（`data/csv/<area_key>.csv`）

DBと同一内容をエリア別にCSV形式でも保持。日付チェックにより同日の重複追記を防いでいる。

---

## 対象エリア一覧

35エリア。主要5都市（札幌・東京23区・名古屋・京都・大阪）は `detailClass` 単位で細分化。

| エリアキー | ラベル |
|-----------|--------|
| sapporo_a | 札幌（札幌・新札幌・琴似） |
| sapporo_b | 札幌（大通公園・時計台・狸小路） |
| sapporo_c | 札幌（すすきの・中島公園） |
| sendai | 仙台 |
| tokyo23_a | 東京（東京駅・銀座・秋葉原） |
| tokyo23_b | 東京（新橋・汐留・お台場） |
| tokyo23_c | 東京（赤坂・六本木・霞ヶ関） |
| tokyo23_d | 東京（渋谷・恵比寿・目黒） |
| tokyo23_e | 東京（品川・蒲田・羽田空港） |
| shinjuku | 新宿（新宿・中野・荻窪・四谷） |
| tokyo23_g | 東京（池袋・赤羽・大塚） |
| tokyo23_h | 東京（東京ドーム・飯田橋・御茶ノ水） |
| tokyo23_i | 東京（上野・浅草・錦糸町） |
| yokohama | 横浜 |
| kanazawa | 金沢 |
| nagoya_a | 名古屋（名古屋駅・伏見・丸の内） |
| nagoya_b | 名古屋（栄・錦・名古屋城） |
| nagoya_c | 名古屋（金山・熱田・千種） |
| kyoto_a | 京都（嵐山・嵯峨野・太秦・高雄） |
| kyoto_b | 京都（河原町・四条烏丸・二条城） |
| kyoto_c | 京都（祇園・東山・北白川） |
| kyoto_d | 京都（京都駅） |
| kyoto_e | 京都（大原・鞍馬・貴船）※欠損あり |
| kobe | 神戸 |
| osaka_a | 大阪（新大阪・江坂） |
| osaka_umeda | 大阪（梅田・ユニバーサルシティ） |
| osaka_c | 大阪（京橋・本町・ベイエリア） |
| osaka_d | 大阪（なんば・心斎橋・天王寺） |
| hiroshima | 広島 |
| takamatsu | 高松 |
| matsuyama | 松山（松山・道後） |
| fukuoka_hakata | 福岡（博多・太宰府） |
| fukuoka_tenjin | 福岡（天神・中洲・福岡ドーム） |
| kumamoto | 熊本 |
| naha | 那覇 |

---

## APIクライアントの仕様

### 使用エンドポイント（`demand_weather/rakuten_client.py`）

| 関数 | エンドポイント | 用途 |
|------|--------------|------|
| `get_observed_hotel_count` | SimpleHotelSearch | エリア内登録ホテル総数の取得 |
| `get_price_stats` | VacantHotelSearch | 空室数・min/median/max価格の取得 |

### レート制限対応

- API呼び出し間隔: 1.1秒スリープ
- ネットワークエラー時: 最大3回リトライ、3秒待機

### 認証ヘッダー（2026年2月移行後）

```
applicationId: <APP_ID>
accessKey: <ACCESS_KEY>
Origin: <RAKUTEN_ORIGIN>
Referer: <RAKUTEN_ORIGIN>
```

---

## 既知の制約・注意事項

### 実行時間が上限に近い

現在の実行時間は約3時間で、タスクスケジューラの制限（3時間）に近い。
エリアを追加する前に実行時間の余裕を確認すること。

### kyoto_e の欠損

`kyoto_e`（大原・鞍馬・貴船）はホテル数が約20件と少なく、
楽天APIが `not_found: Data Not Found` を返すことがある。
再取得しても再発するため、エリア固有の特性として受け入れている（特別処理なし）。

### 価格は「代表プランの価格」

取得している価格は `hotelBasicInfo.hotelMinCharge` ではなく
`roomInfo.dailyCharge.total`（レスポンス内の代表プラン料金）に基づく。
ソート順も同フィールド基準であることを実機検証済み。

### 日本語フォント（Windowsのみ）

matplotlib の日本語フォントに `Yu Gothic`, `MS Gothic`, `Meiryo` を指定。
Linux/Macで動かす場合はフォント設定の変更が必要。

### 分析・予測機能はまだない

現時点では蓄積と可視化のみ。将来的な予測モデル構築のためのデータ収集フェーズ。

---

## エリアの追加方法

1. エリアコードを調べる

   ```
   python discover_area_codes.py <キーワード>
   ```

   例: `python discover_area_codes.py 博多`

2. `demand_weather/config.py` の `AREAS` に追記する

   ```python
   "new_area": {
       "label": "エリア表示名",
       "area_codes": [
           {"largeClassCode": "japan", "middleClassCode": "...", "smallClassCode": "..."},
       ],
   },
   ```

3. 実行時間が増加するため（1エリア追加で約16分増）、タスクスケジューラの制限内に収まるか確認する。

---

## トラブルシューティング

### タスクが途中で止まっている

```powershell
schtasks /query /tn "CrowdCast_FetchDemand" /fo LIST
```

Status が `Ready`（実行終了）なのに進捗が途中なら途中停止。
`output/` フォルダの最終更新PNGファイルのエリアまでが完了している。

手動で続きを実行:

```
python fetch_demand.py --areas <続きのエリアキー>
```

### API認証エラー（401/403）

- `.env` の `RAKUTEN_ORIGIN` が楽天アプリ登録時の「許可されたWebサイト」と一致しているか確認
- アプリの有効期限（2027-06-20）を確認し、期限切れなら楽天ウェブサービスで更新

### データベースが壊れた

SQLiteはWALモードを使っていないため、強制終了時にファイルが破損することがある。
`data/demand_weather.db` を削除して `fetch_demand.py` を実行すれば再作成される（過去データは失われる）。
重要なデータは `data/csv/` にも同一内容が残っているため、CSVからの復元も可能（復元スクリプトは未実装）。

### ヒートマップの価格色が薄い・見にくい

全エリア共通のグローバルレンジ（DBのmin〜max）を使用しているため、
外れ値が1件でもあるとレンジが広がり、中間の値が白に近くなることがある。
その場合は `heatmap.py` の `get_global_price_range` が返す値を確認し、
`plot_heatmap` 呼び出し時に `vmin`/`vmax` を明示的に指定して調整する。
