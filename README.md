# RevRank

楽天市場の口コミ件数・評価点・最近の話題性から独自スコアを算出し、売れ筋とは異なる**本当の評価ランキング**を29ジャンルで提供する静的サイト。

**公開URL:** https://oikawa-yuhei.github.io/revrank/

---

## ジャンル一覧

ランニング / ゴルフ / フィットネスマシン / ウェイトトレーニング / アウトドア / ウィンタースポーツ / 寝具 / 子育て / 登山 / 自転車（計29ジャンル）

---

## 仕組み

1. **データ収集** (`fetch_ranking.py`) — 楽天市場ランキングAPIで各ジャンルのTOP90件を取得、SQLiteに保存
2. **スコア計算** (`build_site.py`) — 口コミ件数・評価点・7日間の口コミ増加数から独自スコアを算出
3. **サイト生成** (`build_site.py`) — ジャンルごとに `docs/{slug}/index.html` を生成
4. **自動更新** (GitHub Actions) — 毎時0分に収集→ビルド→pushを自動実行

---

## セットアップ

### 1. 依存パッケージ

```
pip install -r requirements.txt
```

### 2. 楽天ウェブサービス アプリ登録

https://webservice.rakuten.co.jp/ でアプリを登録し、以下を取得する。

- **Application ID**
- **Access Key**
- **許可されたWebサイト**（GitHub PagesのURL: `https://oikawa-yuhei.github.io`）

### 3. `.env` の設定

```
cp .env.example .env
```

```
RAKUTEN_ICHIBA_APP_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
RAKUTEN_ICHIBA_ACCESS_KEY=pk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
RAKUTEN_ORIGIN=https://oikawa-yuhei.github.io
```

### 4. 手動ビルド

```
python fetch_ranking.py        # データ収集（初回）
python build_site.py           # 全ジャンルをビルド
python build_site.py mattress  # 1ジャンルのみ（デバッグ用）
```

---

## GitHub Actions 自動更新

`.github/workflows/update.yml` で毎時自動実行される。

**Secrets 設定（Settings → Secrets → Actions）:**

| Secret名 | 内容 |
|---|---|
| `RAKUTEN_ICHIBA_APP_ID` | Application ID |
| `RAKUTEN_ICHIBA_ACCESS_KEY` | Access Key |
| `RAKUTEN_ORIGIN` | 許可されたWebサイトURL |

---

## ディレクトリ構成

```
revrank/
├── build_site.py          # 静的サイトジェネレーター
├── fetch_ranking.py       # 楽天APIデータ収集
├── ichiba/
│   ├── config.py          # ジャンル定義（29ジャンル）
│   ├── client.py          # APIクライアント
│   └── db.py              # SQLiteスキーマ・クエリ
├── docs/                  # 生成された静的サイト（GitHub Pages公開）
│   ├── index.html         # トップページ
│   └── {slug}/index.html  # 各ジャンルページ
├── data/
│   ├── ichiba_ranking.db  # SQLiteデータベース（gitignore）
│   └── img_cache/         # 商品画像キャッシュ
└── .github/workflows/
    └── update.yml         # 毎時自動更新ワークフロー
```
