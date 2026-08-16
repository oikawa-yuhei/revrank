"""build_site.py v2 — RevRank 静的サイトジェネレーター
3指標 (口コミランク / コスパランク / バズランク) + RevRankスコアによる製品カード表示。

使い方:
    python build_site.py                  # 全ジャンル
    python build_site.py running_shoes    # 1ジャンルのみ（デバッグ用）
"""

import base64, hashlib, json, math, os, re, sqlite3, sys, time
from html import escape as _he
import urllib.request
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))
from ichiba.config import DB_PATH, GENRES

# ── サイト設定 ──────────────────────────────────────────────
SITE_NAME    = "RevRank"
BASE_URL     = "https://oikawa-yuhei.github.io/revrank"
DOCS_DIR     = Path(__file__).parent / "docs"
CACHE_DIR    = Path(__file__).parent / "data" / "img_cache"
APP_ID       = os.environ.get("RAKUTEN_ICHIBA_APP_ID", "")
WORKER_URL   = os.environ.get("ANALYTICS_WORKER_URL", "")  # Cloudflare Worker URL
DOCS_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# 製品カラーパレット (上位5製品)
PCOLS = ["#d4922a", "#3b6fe0", "#059669", "#9333ea", "#9ca3af"]

# スコア計算の最低データ日数
MIN_DAYS_COSPA = 14
MIN_DAYS_BUZZ  = 14

# ── ジャンルメタ ─────────────────────────────────────────────
GENRE_META = {
    "running_shoes": {"slug":"running-shoes","label":"ランニングシューズ","emoji":"👟",
        "kw":"ランニングシューズ おすすめ",
        "desc":"楽天市場のランニングシューズを口コミ件数×評価点の独自スコアで並べた本当のランキング。売れ筋とは違う、本当に評価された一足を探せます。",
        "guide":"選ぶ視点は「足幅」「ドロップ高」「クッション素材」の3点。同じサイズでもメーカーによって足幅の設計が大きく異なり、フィット感が長距離の快適性を左右する。楽天の売れ筋はキャンペーン商品やセール品が上位に入りやすいが、RevRankの口コミ評価は月100km以上走るユーザーの本音の声を件数と評価点で統計補正したスコア。「買って1年、まだ現役」という長期レビューが多い商品が自然と上位に浮かび上がる。",
        "related":["running_watch"]},
    "running_watch": {"slug":"running-watch","label":"ランニングウォッチ・GPS","emoji":"⌚",
        "kw":"ランニングウォッチ GPS おすすめ",
        "desc":"GPSランニングウォッチの口コミ評価ランキング。ガーミン・アップルウォッチなど人気モデルを実際の購入者レビューで比較。",
        "guide":"GPS精度・バッテリー持ち・心拍計の精度が三大比較ポイント。スマートウォッチとの兼用を求めるか、ランニング特化にするかで選択肢が変わる。高価格帯モデルが売れ筋上位を占める傾向があるが、価格と満足度は必ずしも一致しない。「ガーミンから乗り換えて正解」「バッテリーが思ったより持たない」といった走り込んだランナーの生の声がRevRankに集約され、本当に走りに使えるウォッチが上位に来る。",
        "related":["running_shoes"]},
    "golf_club": {"slug":"golf-club","label":"ゴルフクラブ","emoji":"⛳",
        "kw":"ゴルフクラブ おすすめ ランキング",
        "desc":"ゴルフクラブの口コミ評価ランキング。実際のゴルファーの口コミスコアで選ぶ一本。",
        "guide":"クラブ選びで最も個人差が出るのがシャフトの硬さ（フレックス）と重量。スイングスピードに合わないシャフトは飛距離ロスに直結する。楽天の売れ筋は入門者向けセットが上位に入りやすいが、ゴルファーの口コミは「打感」「弾道の安定性」「実際の飛距離」を具体的に語る。スペック表では見えない〝手に伝わる感覚〟の評価こそが、RevRankで長く高得点を維持する商品の証明だ。",
        "related":["golf_ball","golf_shoes","golf_bag"]},
    "golf_ball": {"slug":"golf-ball","label":"ゴルフボール","emoji":"⛳",
        "kw":"ゴルフボール おすすめ",
        "desc":"ゴルフボールの口コミ評価ランキング。購入者レビューが多い信頼性の高い製品を厳選。",
        "guide":"スピン量・飛距離・フィーリングの三軸で選ぶのが基本。アマチュアはディスタンス系から、スコアが安定してきたらスピン系への移行が定番。ブランドの知名度よりも「実際のコースでどう飛ぶか」「アプローチの止まり方」を評価した口コミの蓄積がRevRankの根拠。同じ価格帯で比べると口コミ評価の差は意外に大きく、隠れた高コスパボールが見つかることも多い。",
        "related":["golf_club","golf_shoes"]},
    "golf_shoes": {"slug":"golf-shoes","label":"ゴルフシューズ","emoji":"⛳",
        "kw":"ゴルフシューズ おすすめ",
        "desc":"ゴルフシューズの口コミ評価ランキング。実際のゴルファーから高評価を得た一足。",
        "guide":"18ホールを4〜5時間歩き続ける道具だからこそ「快適さの持続性」が最重要。防水性・グリップ力は雨のラウンドで真価が問われる。カタログの見た目よりも「雨の日でも滑らなかった」「足が痛くならなかった」という複数ラウンド後の口コミが本当の品質を語る。RevRankはそうした使い込んだゴルファーの評価を統計的に補正したスコアで順位を決める。",
        "related":["golf_club","golf_bag"]},
    "golf_bag": {"slug":"golf-bag","label":"ゴルフバッグ","emoji":"⛳",
        "kw":"ゴルフバッグ おすすめ キャディバッグ",
        "desc":"キャディバッグの口コミ評価ランキング。収納力・デザイン・耐久性を購入者が評価。",
        "guide":"収納力・重量・耐久性の三点が購入後の満足度を決める。スタンド型かカートバッグかで用途が分かれるが、どちらも「実際にコースで使い続けた」ユーザーの長期評価が品質の信頼度を証明する。デザインは初見で判断できても、チャックの耐久性やポケットの使いやすさは使い込まないとわからない。RevRankは数十件以上の口コミが積み上がった製品を正当に評価する。",
        "related":["golf_club","golf_shoes"]},
    "treadmill": {"slug":"treadmill","label":"ランニングマシン","emoji":"🏃",
        "kw":"ランニングマシン おすすめ 家庭用",
        "desc":"家庭用ランニングマシンの口コミ評価ランキング。静音性・折りたたみなど実用性を購入者が評価。",
        "guide":"家庭用ランニングマシンで見落とされがちなのが「騒音」と「振動の階下への影響」。スペック上の最大速度より、日常使いする速度域での静粛性の方が継続使用に直結する。折りたたみ機能の操作性も購入後に初めてわかる要素。「近所トラブルにならなかった」「半年で使わなくなった」というリアルな口コミがRevRankに集積され、本当に続けられる一台を示す。",
        "related":["fitness_bike","stepper"]},
    "fitness_bike": {"slug":"fitness-bike","label":"フィットネスバイク","emoji":"🚴",
        "kw":"フィットネスバイク おすすめ 家庭用",
        "desc":"家庭用フィットネスバイク・エアロバイクの口コミ評価ランキング。購入者レビューで比較。",
        "guide":"負荷調整のなめらかさ・シート高の調整範囲・ペダルの回転の滑らかさが選択の核心。テレワーク中のながら運動として使うなら静音性が最優先。購入直後は満足しても3ヶ月後にガタつきや異音が出る製品も少なくない。RevRankの口コミ評価は長期使用者のレビューが自然に加重されるため、「半年後も快調」という声が多い製品が上位に浮かび上がる。",
        "related":["treadmill","stepper"]},
    "stepper": {"slug":"stepper","label":"ステッパー","emoji":"🏋️",
        "kw":"ステッパー おすすめ ながら運動",
        "desc":"ステッパーの口コミ評価ランキング。テレワーク中の運動不足解消に人気の製品を実際の口コミで比較。",
        "guide":"毎日踏み続けるからこそ「安定性」と「耐久性」が命。安価なモデルは数ヶ月でガタつきが出ることも多く、踏み台の素材・フレームの強度が長期的な満足度を決める。負荷調整の有無と幅も重要な選択基準。「1年以上使い続けている」「音が気にならない」という口コミの蓄積がRevRankの上位を決める根拠であり、単なる売れ筋との違いはそこにある。",
        "related":["treadmill","fitness_bike"]},
    "dumbbell": {"slug":"dumbbell","label":"ダンベル","emoji":"🏋️",
        "kw":"ダンベル おすすめ 可変式",
        "desc":"ダンベルの口コミ評価ランキング。可変式・固定式を問わず、ホームジム派から高評価の製品を紹介。",
        "guide":"可変式か固定式かで用途が変わる。可変式は省スペースで複数の重量に対応できる反面、重量変更の操作性がトレーニングのテンポに影響する。グリップのローレット加工・プレートのズレにくさ・重量精度がホームジム派が実際に気にするポイント。「プレートがズレて危なかった」「チャックが壊れた」といった問題は口コミにしか出てこない情報だ。RevRankはそこを評価する。",
        "related":["barbell","kettlebell"]},
    "barbell": {"slug":"barbell","label":"バーベル","emoji":"🏋️",
        "kw":"バーベル おすすめ セット",
        "desc":"バーベルセットの口コミ評価ランキング。ホームジム構築に実際に購入して高評価をつけた製品を厳選。",
        "guide":"シャフトのしなり（whip）・スリーブの回転・重量精度の三点が本格派の評価基準。安全性に直結するため、「溶接部の強度」「カラーのかみ合わせ」への口コミは品質判断に不可欠。楽天の売れ筋は低価格帯セットが上位に来やすいが、RevRankでは数百回のトレーニングを重ねた後のレビューが多い製品を正当評価する。価格より安全と耐久性を重視した選択が可能だ。",
        "related":["dumbbell","kettlebell"]},
    "kettlebell": {"slug":"kettlebell","label":"ケトルベル","emoji":"🏋️",
        "kw":"ケトルベル おすすめ 重さ",
        "desc":"ケトルベルの口コミ評価ランキング。重量・素材・グリップを購入者が評価した製品を比較。",
        "guide":"シンプルな鉄の塊だからこそ「仕上げ」「底面の平坦さ」「ハンドルの太さと面粗さ」が品質差を生む。表面塗装の剥がれやすさ、重量のバラつきは安価品によく見られる問題。RevRankでは数十件以上のレビューが積み上がった製品を統計補正して評価するため、「塗装が1ヶ月で剥げた」「表示重量と実重量が違う」という問題を抱えた製品は自然と順位が下がる。品質に正直なランキングだ。",
        "related":["dumbbell","barbell"]},
    "tent": {"slug":"tent","label":"テント","emoji":"⛺",
        "kw":"テント おすすめ ソロ キャンプ",
        "desc":"キャンプ用テントの口コミ評価ランキング。実際のキャンパーから高評価を得た一幕。",
        "guide":"設営のしやすさ・耐風性・通気性が三大評価軸。カタログスペックの耐水圧は目安に過ぎず、縫い目のシームテープ処理や出入口のジッパーの耐久性が実際の雨中キャンプで差を生む。「一人でも10分で設営できた」「強風で一晩粘った」というフィールドの口コミがRevRankに集積され、映えるビジュアルとは別の次元で本当に頼れる一幕を選べる。",
        "related":["tarp","outdoor_bedding","camp_chair"]},
    "tarp": {"slug":"tarp","label":"タープ","emoji":"⛺",
        "kw":"タープ おすすめ キャンプ",
        "desc":"タープの口コミ評価ランキング。ヘキサ・レクタ・ウィングなど購入者が評価した製品を紹介。",
        "guide":"設営バリエーションの豊富さ・防水性・収納時のコンパクトさが選択基準。ポリエステル系は軽量でコスパが高く、TC（ポリコットン）素材は結露しにくく焚き火に強い。素材特性は実際に使ったキャンパーの口コミにしか出てこない情報。「夜露が落ちてこなかった」「強風でも張れた」というリアルな声を集約したRevRankのスコアで、素材とサイズの選択を後押しする。",
        "related":["tent","camp_chair"]},
    "outdoor_bedding": {"slug":"outdoor-bedding","label":"アウトドア用寝具","emoji":"🏕️",
        "kw":"シュラフ 寝袋 おすすめ キャンプ",
        "desc":"シュラフ・キャンプ用マットなどアウトドア寝具の口コミ評価ランキング。",
        "guide":"快適温度域とカタログ記載の使用可能温度域は異なる。メーカー表記の限界温度より10℃高い環境での使用が現実的な目安。ダウンか化繊か、エア・フォーム・インフレータブルかで用途が変わる。「表記の使用可能温度域では寒かった」という口コミはカタログでは知れない重要情報。RevRankはそうした実使用者の厳しい評価を集計し、スペックと実力が一致した製品を上位に出す。",
        "related":["tent","tarp"]},
    "camp_chair": {"slug":"camp-chair","label":"キャンプチェア・テーブル","emoji":"🪑",
        "kw":"キャンプ チェア テーブル おすすめ",
        "desc":"キャンプ用チェア・テーブルの口コミ評価ランキング。実際のキャンパーが評価した製品を紹介。",
        "guide":"座り心地・収納サイズ・重量の三点が選択の核心。チェアはキャンプスタイルを大きく左右するギアだが、実際の使いやすさは「展開・収納のしやすさ」「長時間座った後の体への影響」にかかっている。安価なチェアはフレームの溶接部が早期に破損するケースも多い。「3年使ってもガタつかない」という長期レビューが多い製品こそRevRankが高得点を出す理由だ。",
        "related":["tent","bonfire"]},
    "bbq_grill": {"slug":"bbq-grill","label":"バーベキューコンロ","emoji":"🔥",
        "kw":"バーベキューコンロ おすすめ",
        "desc":"バーベキューコンロの口コミ評価ランキング。購入者が評価した製品を比較。",
        "guide":"着火のしやすさ・火力の均一性・後片付けのしやすさが満足度を決める三要素。網の素材（ステンレス vs 鉄製）は食材への影響と手入れのしやすさを左右する。「炭がよく起きる」「灰の処理がラク」「2〜3年使っても全然問題ない」という繰り返し使ったユーザーの口コミがRevRankに積み上がり、見た目だけでは選べない本物を教える。",
        "related":["bonfire","camp_stove","camp_chair"]},
    "camp_stove": {"slug":"camp-stove","label":"キャンプバーナー","emoji":"🔥",
        "kw":"キャンプ バーナー シングル おすすめ",
        "desc":"キャンプ用バーナーの口コミ評価ランキング。火力・収納サイズ・コスパを購入者が評価。",
        "guide":"火力（出力W）・風への耐性・重量が三大スペック。シングルバーナーはOD缶対応かCB缶対応かで互換性が変わり、使うシーンを先に想定しておく必要がある。「強風でも火が消えなかった」「ゴトクが安定していた」という実フィールドの口コミはカタログスペックでは判断できない情報。RevRankは実際の山・キャンプ場での使用体験を評価した口コミの集積から順位を決める。",
        "related":["bonfire","tent"]},
    "bonfire": {"slug":"bonfire","label":"焚き火台","emoji":"🔥",
        "kw":"焚き火台 おすすめ ソロ",
        "desc":"焚き火台の口コミ評価ランキング。組み立て・収納のしやすさを実際のキャンパーが評価した製品。",
        "guide":"燃焼効率・組み立て・収納のしやすさが選択の核心。ステンレスとチタンでは重量・価格・熱への強さが違い、用途によって最適解が変わる。ゴトク部分の安定性と薪を補充しやすいかどうかも長期的な使いやすさに直結する。「何度使っても変形しない」「ソロ用でも大きい薪が入る」という使い込んだキャンパーの評価がRevRankに蓄積され、焚き火愛好家が本当に信頼できる台を示す。",
        "related":["bbq_grill","camp_stove","camp_chair"]},
    "ski_board": {"slug":"ski","label":"スキー板","emoji":"⛷️",
        "kw":"スキー板 おすすめ 初心者 中級者",
        "desc":"スキー板の口コミ評価ランキング。購入者から高評価を得たスキー板を紹介。",
        "guide":"フレックス・サイドカットのR値・重量が選択の三軸。初心者はソフトフレックスで扱いやすい板を、中〜上級者はターン性能と安定性のバランスで選ぶ。楽天の売れ筋は入門セットが上位に入りやすいが、RevRankでは実際にゲレンデで滑り込んだスキーヤーの「カービングの切れ味」「高速域での安定感」といった具体的な口コミを集計。スキルに合った一本選びをデータでサポートする。",
        "related":["ski_boots","snowboard"]},
    "ski_boots": {"slug":"ski-boots","label":"スキーブーツ","emoji":"⛷️",
        "kw":"スキーブーツ おすすめ",
        "desc":"スキーブーツの口コミ評価ランキング。フィット感・保温性を購入者が実際に評価した製品を比較。",
        "guide":"フィット感・保温性・バックルの調整幅がブーツ選びの肝。同じ26cmでもラスト（足型）の幅がメーカーによって大きく異なる。試し履きなしのネット購入はリスクを伴うが、「同じ足幅の人に合った」「レンタルより全然快適」という口コミはサイズ選びのヒントになる。「半日滑ったら足が痛くなった」という率直なレビューも含め、RevRankは購入者の本音を統計的に反映した評価でブーツ選びをサポートする。",
        "related":["ski_board","snowboard_boots"]},
    "snowboard": {"slug":"snowboard","label":"スノーボード","emoji":"🏂",
        "kw":"スノーボード おすすめ 板",
        "desc":"スノーボードの口コミ評価ランキング。購入者が評価した板を紹介。",
        "guide":"フレックス・シェイプ・ワークが板の乗り心地を決める三要素。グラトリ重視ならソフトフレックスのツインチップ、カービング重視ならミディアム以上のフレックスが基本。楽天の売れ筋はセット商品や入門向けが上位を占めがちだが、RevRankでは実際に雪山で使い込んだライダーの「ターンの切れ」「プレスのしやすさ」「スピード域での安定感」を評価した口コミを集計。次の板選びを数字で根拠づける。",
        "related":["snowboard_boots","ski_board"]},
    "snowboard_boots": {"slug":"snowboard-boots","label":"スノーボードブーツ","emoji":"🏂",
        "kw":"スノーボード ブーツ おすすめ",
        "desc":"スノーボードブーツの口コミ評価ランキング。フィット感・フレックスを購入者が評価した製品を比較。",
        "guide":"ヒールホールド・フレックス・防水インナーの品質がブーツの本質。ボードコントロールはブーツとバインディングの連結精度に依存するため、ブーツ選びはライディングに直結する重要選択だ。「足首が安定してトゥサイドが踏めるようになった」「インナーが濡れた」という使い込んだスノーボーダーの声がRevRankに蓄積され、ビジュアルやブランドに頼らない選択を可能にする。",
        "related":["snowboard","ski_boots"]},
    "mattress": {"slug":"mattress","label":"マットレス","emoji":"🛏️",
        "kw":"マットレス おすすめ 腰痛",
        "desc":"マットレスの口コミ評価ランキング。腰痛対策・高反発・低反発など、実際の購入者が評価した製品を紹介。",
        "guide":"腰への影響・通気性・耐久性が長期的な満足度を決める。高反発・低反発・ポケットコイルそれぞれに合う体型と寝姿勢がある。購入直後は何でも「快適」に感じやすいが、3〜6ヶ月後の「腰が痛くなった」「ヘタリが早かった」という正直な長期レビューが本当の品質を教えてくれる。RevRankはそうした使用期間の長い口コミも自然に評価に組み込み、毎晩使う道具の本当のコスパを示す。",
        "related":["bed_frame","leg_mattress"]},
    "bed_frame": {"slug":"bed-frame","label":"ベッドフレーム","emoji":"🛌",
        "kw":"ベッドフレーム おすすめ すのこ",
        "desc":"ベッドフレームの口コミ評価ランキング。すのこ・収納付き・フロアベッドなど購入者が評価した製品。",
        "guide":"組み立てやすさ・軋み音のなさ・耐荷重が選択の核心。「説明書が不親切で苦労した」「半年でフレームが歪んだ」という購入者の声はスペック表には出てこない。すのこタイプは通気性と湿気対策で優れるが、板の間隔と強度がマットレスの寝心地に影響する。RevRankは組み立てから数ヶ月後の使用感まで含めた口コミの蓄積から順位を決め、後悔しないベッドフレーム選びをサポートする。",
        "related":["mattress","leg_mattress"]},
    "leg_mattress": {"slug":"leg-mattress","label":"脚付きマットレス","emoji":"🛌",
        "kw":"脚付きマットレス おすすめ",
        "desc":"脚付きマットレスの口コミ評価ランキング。一人暮らしに人気の製品をコスパ・寝心地で比較。",
        "guide":"一人暮らしに選ばれる理由は「搬入のしやすさ」と「ベッドフレーム不要の手軽さ」。ただし脚の高さと安定性・マットレス本体の硬さ・張り地の耐久性が長期的な満足度を左右する。「脚がグラついてきた」「生地が毛玉だらけになった」という半年〜1年後の口コミこそが品質の証明。RevRankは購入後の実使用者のリアルな声を統計補正して評価し、コスパと品質が両立した一台を選べるようにする。",
        "related":["mattress","bed_frame"]},
    "stroller": {"slug":"stroller","label":"ベビーカー","emoji":"👶",
        "kw":"ベビーカー おすすめ 軽量",
        "desc":"ベビーカーの口コミ評価ランキング。実際のパパ・ママが評価した製品を紹介。",
        "guide":"走行性・折りたたみの手軽さ・収納バスケットの使いやすさが毎日の使用感を決める。実際に乗せる子どもの月齢・体重とのフィット感も重要。「段差に弱かった」「改札を通りにくい」「雨カバーが別売りだった」という街中での使用体験は実際のパパ・ママの口コミにしか出てこない。RevRankは日常的にベビーカーを使う保護者の本音の評価を集計し、カタログスペックでは見えない使いやすさを数値で示す。",
        "related":["child_seat"]},
    "child_seat": {"slug":"child-seat","label":"チャイルドシート","emoji":"🚗",
        "kw":"チャイルドシート おすすめ 新生児",
        "desc":"チャイルドシートの口コミ評価ランキング。安全性・使いやすさを購入者が評価した製品を比較。",
        "guide":"安全性能（R129/R44適合）・取り付けのしやすさ・子どもの乗り心地の三点が最重要。ISOFIXと通常ベルト固定の違い、回転式かどうかも選択基準になる。命を守る道具だからこそ「取り付けが確実にできるか」「子どもが嫌がらないか」という実使用者の評価が最も信頼できる情報源だ。RevRankは安全性と使いやすさを両立した製品に多くの口コミが集まる構造を活かし、本当に信頼できるシートを上位に出す。",
        "related":["stroller"]},
    "climbing_shoes": {"slug":"climbing-shoes","label":"登山・クライミングシューズ","emoji":"🧗",
        "kw":"登山靴 クライミングシューズ おすすめ",
        "desc":"登山靴・クライミングシューズの口コミ評価ランキング。購入者が評価した一足。",
        "guide":"ダウントゥ（つま先の下がり）・ラバーのスティッキー性・ヒールカップのフィット感が選択の三軸。スラブ系と垂壁・オーバーハング系でも最適なシューズが変わる。「サイズ感が独特でハーフサイズ小さめが正解だった」「ヒールフックがしっかり決まる」という実際にクライミングジムや外岩で使ったクライマーの口コミがRevRankに蓄積され、感覚的な部分も含めた本当の評価がわかる。",
        "related":["tent","outdoor_bedding"]},
    "e_bike": {"slug":"e-bike","label":"電動アシスト自転車","emoji":"🚲",
        "kw":"電動アシスト自転車 おすすめ",
        "desc":"電動アシスト自転車の口コミ評価ランキング。通勤・子乗せ・折りたたみなど購入者が評価した一台。",
        "guide":"アシスト力・バッテリー航続距離・車体重量が電動アシスト自転車の三大選択基準。坂道の多い地域・通勤距離・駐輪スペースによって最適なモデルは変わる。「カタログ上の航続距離より実際は短い」「坂道で急にアシストが切れた」という実使用者の声はスペック表には載らない。RevRankは毎日乗り続けた購入者の長期レビューを統計評価し、用途に合った本当の一台を選ぶデータを提供する。",
        "related":["treadmill","fitness_bike"]},
}

# ── DB ──────────────────────────────────────────────────────
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

latest_date = conn.execute(
    "SELECT MAX(fetched_date) FROM item_rankings"
).fetchone()[0]

# ── テキストクリーニング ─────────────────────────────────────
_PROMO_IN_BRACKET = re.compile(
    r'(?:\d+[倍%]|OFF|%引き?|限定|クーポン|ランキング|\d+位|まで|迄|'
    r'\d+円|セール|特価|送料|あす楽|無料|期間|先着|\bSALE\b|受注|予約|'
    r'今だけ|特典|割引|引き|相当|ポイント|P\d+|\bLINE\b|SNS|友達|'
    r'再入荷|入荷待ち|キャンペーン|楽天\d+位|楽天一位|'
    r'正規品|公式|全品|先行|お盆|夏休み|冬休み|春休み|リニューアル情報)',
    re.IGNORECASE
)

def _is_promo_bracket(content):
    if _PROMO_IN_BRACKET.search(content): return True
    return not re.search(r'[A-Za-z]{4,}', content)

def clean_name(raw):
    s = raw
    def _remove_kaku(text):
        def repl(m):
            inner = m.group(0)[1:-1].strip()
            return ' ' if _is_promo_bracket(inner) else ' ' + inner + ' '
        for _ in range(5):
            prev = text; text = re.sub(r'【[^】]{0,120}】', repl, text)
            if text == prev: break
        return text
    s = _remove_kaku(s)
    for _ in range(3):
        prev = s; s = re.sub(r'[《≪][^》≫]{0,80}[》≫]', ' ', s)
        if s == prev: break
    s = re.sub(r'＜[^＞]{0,80}＞', ' ', s)
    for oc, cc in [('〔','〕'),('〈','〉'),('｢','｣'),(r'\[',r'\]'),('（','）')]:
        for _ in range(3):
            prev = s; s = re.sub(f'{oc}[^{cc}]{{0,100}}{cc}', ' ', s)
            if s == prev: break
    for _ in range(3):
        prev = s; s = re.sub(r'[{｛][^}｝]{0,100}[}｝]', ' ', s)
        if s == prev: break
    def _remove_kagi(text):
        return re.sub(r'「([^」]{0,80})」',
                      lambda m: '' if _PROMO_IN_BRACKET.search(m.group(1)) else m.group(0), text)
    s = _remove_kagi(s)
    s = re.sub(r'\*[^*]{2,60}\*', '', s)
    s = re.sub(r'^[^〉\n]{0,120}〉\s*', '', s)
    for _ in range(3):
        prev = s
        s = re.sub(r'[■□◼◻▽△▼▲◁▷▶◀►◄][^■□◼◻▽△▼▲◁▷▶◀►◄]{0,80}[■□◼◻▽△▼▲◁▷▶◀►◄]', '', s)
        if s == prev: break
    for _ in range(3):
        prev = s
        s = re.sub(r'[＼\\][^＼\\／/]{0,100}[／/]', '', s)
        s = re.sub(r'^[＼\\][^\s　]{0,80}', '', s.lstrip())
        if s == prev: break
    s = re.sub(r'[★☆●◎◆♪♥✨🎁🎉▽△▼▲▶◀►◄＼■□]+', '', s)
    _PROMO = (
        (r'^[¥\￥]\s?\d[\d,]+[円%]?(?:割引|OFF|引き|相当)?[！!]?\s*', ''),
        (r'^\d[\d,]+(?:円|%)?(?:~相当)?(?:割引|OFF|引き)[！!]?\s*', ''),
        (r'^\d+(?:\.\d+)?%\s*[Oo][Ff][Ff][！!]?\s*', ''),
        (r'^最大[^\s　,。！!、\n]{0,30}[！!]?\s*', ''),
        (r'^(?:ポイント|P)\d+[倍%][！!]?[^\s　,。]{0,10}\s*', ''),
        (r'^\d+ヶ月レンタル\s*', ''),
        (r'^(?:送料無料|あす楽|レビュー[特典割引あり]+)[^\s　,。！!]{0,20}[！!]?\s*', ''),
        (r'^(?:期間限定|数量限定|在庫限り|在庫あり|新品)[^\s　,。！!]{0,20}[！!]?\s*', ''),
        (r'^\d{1,2}/\d{1,2}[〜～\-]\d{1,2}(?:/\d{1,2})?[^\s　！!,。]{0,40}[！!]?\s*', ''),
        (r'^\d+%クーポン\d+/\d+[^\s　！!,。]{0,20}[！!]?\s*', ''),
        (r'^(?:楽天|年間|総合|部門|週間|月間|即納楽天総合)?ランキング\d+位[^\s　！!]{0,20}[！!]?\s*', ''),
        (r'^即納[^\s　！!,。]{0,50}[！!]\s*', ''),
        (r'^(?:累計)?\d+(?:万|千)?(?:台|個|枚|本)突破[！!]?(?:[&＆][^\s　]{0,30})?\s*', ''),
        (r'^\d+年連続[^\s　！!,。]{0,30}[！!]?\s*', ''),
        (r'^(?:確かな品質で|お陰様で)[^\s　！!,。〉]{0,50}[！!〉]?\s*', ''),
        (r'^高評価[\d.]+\s*', ''),
        (r'^TV(?:に|で|番組で?)紹介[^\s　！!]{0,15}[！!]?\s*', ''),
        (r'^(?:最小最軽量|最新モデル)[^\s　！!,。]{0,20}\s*', ''),
        (r'^(?:SALE|セール|クリアランス|特価|激安|OUTLET|アウトレット)[^\s　]{0,20}\s*', re.IGNORECASE),
        (r'^[^\s　]{1,10}[/／][^\s　]{1,10}(?:モデル)?追加[！!]\s*', ''),
        (r'^(?:最高|最安|最低価格?|口コミ|みんなの|楽天|ワンランク上の)[^\s　,。！!]{0,20}\s*', ''),
        (r'^(?:全国|一部地域)?都市部一部地域のみお届け自宅送料無料\s*', ''),
        (r'^メーカー直送送料無料[^\s　]{0,15}\s*', ''),
        (r'^※[^※\n]{0,60}※\s*', ''),
        (r'^[！!,、。・\-\/／\|｜　\s]+', ''),
    )
    for _ in range(8):
        before = s
        for pat, flag in _PROMO:
            s = re.sub(pat, flag if isinstance(flag, str) else '', s.lstrip(),
                       flags=(0 if isinstance(flag, str) else flag))
        if s == before: break
    for mid_pat in [r'送料無料', r'あす楽', r'即日発送', r'当日発送']:
        s = re.sub(r'[\s　]*' + mid_pat + r'[\s　]*', ' ', s).strip()
    _SUFFIX = re.compile(
        r'(?:[\s　]+(?:送料無料|あす楽|即日発送|当日発送|翌日発送|'
        r'父の日|母の日|バレンタイン|ホワイトデー|クリスマス|お中元|お歳暮|誕生日|'
        r'ギフト|プレゼント|贈り物|メール便(?:可|対応|OK)?|ネコポス(?:可|対応|OK)?))+\s*$',
        re.IGNORECASE)
    s = _SUFFIX.sub('', s).strip()
    s = re.sub(r'[\s　]+', ' ', s).strip()
    return s if len(s) >= 4 else raw

def clean_caption(raw):
    if not raw: return ""
    s = re.sub(r'<[^>]+>', ' ', raw)
    s = re.sub(r'&(?:amp|lt|gt|quot|apos|nbsp|#\d+;|#x[0-9a-fA-F]+);', ' ', s)
    s = re.sub(r'[\r\n\t]+', ' ', s)
    s = re.sub(r'[ 　]+', ' ', s).strip()
    if len(s) > 100: s = s[:100].rstrip() + '…'
    return s

# ── 画像キャッシュ ────────────────────────────────────────────
def fetch_datauri(url):
    if not url: return ""
    url = url.replace("_ex=64x64", "_ex=128x128")
    key  = hashlib.md5(url.encode()).hexdigest()
    path = CACHE_DIR / key
    if path.exists(): return path.read_text(encoding="utf-8")
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Referer": "https://www.rakuten.co.jp/",
        })
        with urllib.request.urlopen(req, timeout=8) as r:
            raw = r.read()
            ct  = r.headers.get_content_type() or "image/jpeg"
            uri = f"data:{ct};base64,{base64.b64encode(raw).decode()}"
        path.write_text(uri, encoding="utf-8")
        return uri
    except Exception as e:
        print(f"  SKIP {url[:60]} — {e}", file=sys.stderr)
        return ""

# ── 口コミランク (ベイズ平均 → 0-100) ───────────────────────
def compute_kuchikomi(items):
    reviewed = [i for i in items if (i['review_count'] or 0) > 0 and (i['review_average'] or 0) > 0]
    if not reviewed:
        return {i['item_code']: None for i in items}
    avg_rc = sum(i['review_count'] for i in reviewed) / len(reviewed)
    avg_ra = sum(i['review_average'] for i in reviewed) / len(reviewed)
    raw = {}
    for item in items:
        rc = item['review_count'] or 0
        ra = item['review_average'] or 0
        raw[item['item_code']] = None if rc == 0 else (avg_rc * avg_ra + rc * ra) / (avg_rc + rc)
    valid = [v for v in raw.values() if v is not None]
    if not valid:
        return {k: None for k in raw}
    mn, mx = min(valid), max(valid)
    rng = mx - mn or 1
    return {c: round((v - mn) / rng * 100) if v is not None else None for c, v in raw.items()}

# ── コスパランク (90日価格履歴 → 0-100) ─────────────────────
def compute_cospa(key, items, today_str):
    since = (date.fromisoformat(today_str) - timedelta(days=90)).isoformat()
    scores = {}
    for item in items:
        code = item['item_code']
        cur  = item['item_price'] or 0
        if not cur:
            scores[code] = None; continue
        rows = conn.execute("""
            SELECT item_price FROM item_rankings
            WHERE genre_key=? AND item_code=? AND fetched_date >= ? AND item_price > 0
        """, (key, code, since)).fetchall()
        prices = [r[0] for r in rows]
        if len(prices) < MIN_DAYS_COSPA:
            scores[code] = None; continue
        mn, mx = min(prices), max(prices)
        scores[code] = 50 if mx == mn else round((mx - cur) / (mx - mn) * 100)
    return scores

# ── バズランク (楽天ランク変化 + 口コミ速度 → 0-100) ────────
def compute_buzz(key, items, today_str):
    since = (date.fromisoformat(today_str) - timedelta(days=30)).isoformat()
    results = {}
    for item in items:
        code = item['item_code']
        first = conn.execute(
            "SELECT MIN(fetched_date) FROM item_rankings WHERE genre_key=? AND item_code=?",
            (key, code)).fetchone()[0] or today_str
        days = (date.fromisoformat(today_str) - date.fromisoformat(first)).days + 1

        if days < MIN_DAYS_BUZZ:
            label = '初登場' if days <= 3 else f'{days}日目'
            results[code] = (None, label, ''); continue

        old_rank_row = conn.execute("""
            SELECT rank FROM item_rankings
            WHERE genre_key=? AND item_code=? AND fetched_date <= ?
            ORDER BY fetched_date DESC LIMIT 1
        """, (key, code, since)).fetchone()
        old_rank = (old_rank_row[0] if old_rank_row else None) or item['rank']

        old_rc_row = conn.execute("""
            SELECT review_count FROM item_rankings
            WHERE genre_key=? AND item_code=? AND fetched_date <= ?
            ORDER BY fetched_date DESC LIMIT 1
        """, (key, code, since)).fetchone()
        cur_rc  = item['review_count'] or 0
        old_rc  = ((old_rc_row[0] if old_rc_row else None) or cur_rc) or 0
        rc_delta = max(0, cur_rc - old_rc)

        rank_change  = old_rank - item['rank']
        rank_score   = min(100, max(0, 50 + rank_change * 2))
        vel_score    = min(100, rc_delta / max(old_rc, 1) * 300)
        score        = round(rank_score * 0.6 + vel_score * 0.4)

        detail = (f'30日で{rank_change}位↑' if rank_change > 3 else
                  f'+{rc_delta:,}件/30日' if rc_delta > 5 else '')
        results[code] = (score, '', detail)
    return results

# ── RevRankスコア (加重平均、欠損は正規化) ──────────────────
def compute_revrank(k_scores, c_scores, b_results):
    out = {}
    for code in k_scores:
        k = k_scores.get(code)
        c = c_scores.get(code)
        b = (b_results.get(code) or (None, '', ''))[0]
        num = den = 0
        if k is not None: num += k * 0.5; den += 0.5
        if c is not None: num += c * 0.3; den += 0.3
        if b is not None: num += b * 0.2; den += 0.2
        out[code] = (round(num / den), den < 0.99) if den > 0 else (None, True)
    return out

# ── アイテムメタ (バッジ判定) ────────────────────────────────
def get_meta(key, code, today_str):
    first = conn.execute(
        "SELECT MIN(fetched_date) FROM item_rankings WHERE genre_key=? AND item_code=?",
        (key, code)).fetchone()[0] or today_str
    days = (date.fromisoformat(today_str) - date.fromisoformat(first)).days + 1
    gap = None
    recent = conn.execute("""
        SELECT DISTINCT fetched_date FROM item_rankings
        WHERE genre_key=? AND item_code=? ORDER BY fetched_date DESC LIMIT 60
    """, (key, code)).fetchall()
    dates = [r[0] for r in recent]
    for i in range(len(dates) - 1):
        g = (date.fromisoformat(dates[i]) - date.fromisoformat(dates[i+1])).days
        if g > 7: gap = g; break
    return {'is_new': days <= 7, 'days': days, 'gap': gap}

# ── ヒーローチャートSVG (Python生成) ─────────────────────────
def _hero_svg(series_list, invert=False):
    """
    series_list: [(color, thick:bool, name:str, values:list[int|None])]
    values: 0-100スコアのリスト。長さ = データポイント数。
    """
    VW, VH = 240, 100
    PL, PR, PT, PB = 26, 234, 6, 90
    PW, PH = PR - PL, PB - PT

    has = any(vals and sum(1 for v in vals if v is not None) >= 2
              for _, _, _, vals in series_list)

    parts = [f'<svg viewBox="0 0 {VW} {VH}" class="cpanel-svg">']
    if not has:
        parts += [
            f'<text x="{VW//2}" y="44" text-anchor="middle" font-size="9" fill="currentColor" opacity=".35">データ蓄積中</text>',
            f'<text x="{VW//2}" y="57" text-anchor="middle" font-size="8" fill="currentColor" opacity=".22">{MIN_DAYS_COSPA}日後に利用可能</text>',
            '</svg>'
        ]
        return ''.join(parts)

    def xof(i, n): return PL + (i / (n - 1) * PW if n > 1 else PW / 2)
    def yof(v):
        norm = (v or 0) / 100
        return PB - (1 - norm if invert else norm) * PH

    for v in [25, 50, 75, 100]:
        y = yof(v)
        parts.append(
            f'<line x1="{PL}" x2="{PR}" y1="{y:.1f}" y2="{y:.1f}" '
            f'stroke="currentColor" opacity=".08" stroke-width=".7" stroke-dasharray="3,3"/>')
        parts.append(
            f'<text x="{PL-3}" y="{y+3:.1f}" text-anchor="end" font-size="7" '
            f'fill="currentColor" opacity=".28">{v}</text>')

    parts.append(f'<text x="{PL}" y="{PB+9}" text-anchor="start" font-size="7" fill="currentColor" opacity=".28">90日前</text>')
    parts.append(f'<text x="{PR}" y="{PB+9}" text-anchor="end" font-size="7" fill="currentColor" opacity=".28">今日</text>')

    for color, thick, _, vals in series_list:
        if not vals: continue
        valid_pts = [(i, v) for i, v in enumerate(vals) if v is not None]
        if len(valid_pts) < 2: continue
        n  = len(vals)
        sw = "2" if thick else "1"
        so = "1" if thick else ".5"
        fo = ".10" if thick else ".04"
        pts = [(xof(i, n), yof(v)) for i, v in valid_pts]
        area = f"{pts[0][0]:.1f},{PB} " + " ".join(f"{x:.1f},{y:.1f}" for x, y in pts) + f" {pts[-1][0]:.1f},{PB}"
        parts.append(f'<polygon points="{area}" fill="{color}" fill-opacity="{fo}"/>')
        line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        parts.append(f'<polyline points="{line}" fill="none" stroke="{color}" stroke-width="{sw}" stroke-linejoin="round" stroke-opacity="{so}"/>')
        lx, ly = pts[-1]
        r = "2.5" if thick else "1.5"
        parts.append(f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="{r}" fill="{color}" opacity="{so}"/>')

    parts.append('</svg>')
    return ''.join(parts)

def _hero_legend(series_list):
    items = []
    for color, thick, name, vals in series_list:
        has = vals and sum(1 for v in vals if v is not None) >= 2
        op  = "1" if thick else ".5"
        nd  = ' <span style="font-size:9px;color:var(--ink3)">収集中</span>' if not has else ''
        items.append(
            f'<div class="legend-item{" legend-nd" if not has else ""}">'
            f'<span class="legend-dot" style="background:{color};opacity:{op}"></span>'
            f'<span>{name}{nd}</span></div>')
    return '<div class="cpanel-legend">' + ''.join(items) + '</div>'

# ── ヒーローチャートデータ (90日) ────────────────────────────
def load_hero_data(key, top5, today_str):
    since = (date.fromisoformat(today_str) - timedelta(days=90)).isoformat()
    codes = [i['item_code'] for i in top5]
    if not codes: return [], [], []

    ph   = ','.join('?' * len(codes))
    rows = conn.execute(f"""
        SELECT item_code, fetched_date, review_count, review_average, item_price, rank
        FROM item_rankings
        WHERE genre_key=? AND item_code IN ({ph}) AND fetched_date >= ?
        ORDER BY fetched_date
    """, (key, *codes, since)).fetchall()

    hist = {c: [] for c in codes}
    for r in rows:
        hist[r['item_code']].append(dict(r))

    reviewed = [i for i in top5 if (i.get('review_count') or 0) > 0]
    avg_rc = sum(i['review_count'] for i in reviewed) / len(reviewed) if reviewed else 100
    avg_ra = sum(i['review_average'] for i in reviewed) / len(reviewed) if reviewed else 4.0

    all_dates = sorted(set(r['fetched_date'] for recs in hist.values() for r in recs))
    if not all_dates: return [], [], []

    # 口コミランク時系列
    k_raw = []
    for code in codes:
        by_d = {r['fetched_date']: r for r in hist[code]}
        pts  = []
        for d in all_dates:
            r = by_d.get(d)
            if r and (r['review_count'] or 0) > 0 and (r['review_average'] or 0) > 0:
                b = (avg_rc * avg_ra + r['review_count'] * r['review_average']) / (avg_rc + r['review_count'])
                pts.append(b)
            else:
                pts.append(None)
        k_raw.append((code, pts))
    all_k = [v for _, pts in k_raw for v in pts if v is not None]
    if all_k:
        mn, mx = min(all_k), max(all_k); rng = mx - mn or 1
        k_series = [(c, [round((v - mn) / rng * 100) if v is not None else None for v in pts]) for c, pts in k_raw]
    else:
        k_series = k_raw

    # コスパランク時系列 (アイテム個別の90日価格レンジ基準)
    c_series = []
    for code in codes:
        by_d   = {r['fetched_date']: r for r in hist[code]}
        prices = [r['item_price'] for r in hist[code] if r['item_price'] and r['item_price'] > 0]
        if len(prices) < MIN_DAYS_COSPA:
            c_series.append((code, [None] * len(all_dates))); continue
        mn_p, mx_p = min(prices), max(prices)
        pts = []
        for d in all_dates:
            r = by_d.get(d)
            p = r['item_price'] if r and r['item_price'] else None
            if p is None: pts.append(None)
            elif mx_p == mn_p: pts.append(50)
            else: pts.append(round((mx_p - p) / (mx_p - mn_p) * 100))
        c_series.append((code, pts))

    # バズランク時系列 (楽天ランク → 反転スコア)
    b_series = []
    for code in codes:
        by_d  = {r['fetched_date']: r for r in hist[code]}
        ranks = [r['rank'] for r in hist[code] if r['rank']]
        if len(ranks) < 2:
            b_series.append((code, [None] * len(all_dates))); continue
        mn_r, mx_r = min(ranks), max(ranks)
        pts = []
        for d in all_dates:
            r = by_d.get(d)
            rk = r['rank'] if r and r['rank'] else None
            if rk is None: pts.append(None)
            elif mx_r == mn_r: pts.append(50)
            else: pts.append(round((mx_r - rk) / (mx_r - mn_r) * 100))
        b_series.append((code, pts))

    return k_series, c_series, b_series

def render_hero_section(key, top5, today_str):
    k_data, c_data, b_data = load_hero_data(key, top5, today_str)
    if not k_data:
        return ''

    def build_sl(series_data):
        sl = []
        for i, item in enumerate(top5):
            code   = item['item_code']
            color  = PCOLS[i] if i < len(PCOLS) else '#64748b'
            thick  = i < 3
            name   = item['item_name'][:14] + ('…' if len(item['item_name']) > 14 else '')
            vals   = next((pts for c, pts in series_data if c == code), [])
            sl.append((color, thick, name, vals))
        return sl

    sl_k = build_sl(k_data)
    sl_c = build_sl(c_data)
    sl_b = build_sl(b_data)

    svg_k = _hero_svg(sl_k)
    svg_c = _hero_svg(sl_c)
    svg_b = _hero_svg(sl_b)
    legend = _hero_legend(sl_k)

    return f'''<div class="hero-inner">
  <div class="hero-head">
    <div class="hero-title">ランク推移チャート — 上位5商品</div>
    <div class="hero-note">過去90日 · 線の色 = 各カード左帯と対応</div>
  </div>
  <div class="charts-grid">
    <div class="cpanel">
      <div class="cpanel-head">
        <div class="cpanel-title"><span class="kw">口コミ</span>ランク</div>
        <div class="cpanel-period">過去90日</div>
      </div>
      {svg_k}
      {legend}
    </div>
    <div class="cpanel">
      <div class="cpanel-head">
        <div class="cpanel-title"><span class="kw">コスパ</span>ランク</div>
        <div class="cpanel-period">過去90日</div>
      </div>
      {svg_c}
    </div>
    <div class="cpanel">
      <div class="cpanel-head">
        <div class="cpanel-title"><span class="kw">バズ</span>ランク</div>
        <div class="cpanel-period">過去90日</div>
      </div>
      {svg_b}
    </div>
  </div>
</div>'''

# ── スコア色クラス ───────────────────────────────────────────
def _sc(s):
    if s is None: return 'col-mute'
    if s >= 70: return 'col-good'
    if s >= 40: return 'col-warn'
    return 'col-mute'

# ── 製品カード (mvert サイドバー付き) ───────────────────────
RANK_CLS = {1: 'rank-1', 2: 'rank-2', 3: 'rank-3'}

def _rank_diff_html(revrank_pos, rakuten_rank):
    """RevRank順位と楽天順位の差分バッジHTML。|diff| < 3 なら非表示。"""
    diff = rakuten_rank - revrank_pos  # 正 = RevRankが楽天より高評価 (隠れ名品)
    if abs(diff) < 3:
        return '<span class="rank-diff" style="display:none"></span>'
    if diff > 0:
        return f'<span class="rank-diff gem">楽天比 +{diff}↑</span>'
    return f'<span class="rank-diff overr">楽天比 {diff}↓</span>'

_MEDAL = {1: '🥇', 2: '🥈', 3: '🥉'}
_TINT  = {
    1: 'color-mix(in srgb, var(--gold) 6%, transparent)',
    2: 'color-mix(in srgb, var(--silver) 5%, transparent)',
    3: 'color-mix(in srgb, var(--bronze) 5%, transparent)',
}

def render_pcard(rank, color, item, k_sc, c_sc, b_sc, b_label, rv, is_prov, meta):
    rakuten_rank = item.get('rank') or rank
    featured = rank <= 3
    rk_cls   = RANK_CLS.get(rank, 'rank-n')
    emoji    = GENRE_META.get(item.get('genre_key', ''), {}).get('emoji', '📦')
    isize    = 100 if featured else 60
    card_cls = 'pcard pcard-feat' if featured else 'pcard pcard-compact'
    bg_style = f' style="background:{_TINT[rank]}"' if rank in _TINT else ''

    img_html = (
        f'<img src="{item["img"]}" alt="" loading="lazy" style="width:{isize}px;height:{isize}px;object-fit:cover">'
        if item.get('img') else
        f'<div style="width:{isize}px;height:{isize}px;display:flex;align-items:center;justify-content:center;font-size:{28 if featured else 20}px">{emoji}</div>'
    )
    price_html = f'<span class="pcard-price">¥{item["item_price"]:,}</span>' if item.get('item_price') else ''
    stars_html = (
        f'<div class="pcard-stars"><span class="s">★</span>{item["review_average"]:.2f}（{item["review_count"]:,}件）</div>'
        if (item.get('review_count') or 0) > 0 else ''
    )
    new_bdg  = '<span class="mvert-badge">NEW</span>' if meta['is_new'] else ''
    ret_bdg  = (f'<span class="mvert-badge ret">{meta["gap"]}日ぶり復帰</span>' if meta.get('gap') else '')
    medal    = f'<span class="medal">{_MEDAL[rank]}</span>' if rank in _MEDAL else ''
    diff_html = _rank_diff_html(rank, rakuten_rank)

    if rv is None:
        rv_html = '<div class="mvert-total-val col-mute">—</div>'
    elif is_prov:
        rv_html = (f'<div class="mvert-total-val {_sc(rv)}" style="opacity:.72">{rv}'
                   f'<span class="prov">暫定</span></div>')
    else:
        rv_html = f'<div class="mvert-total-val {_sc(rv)}">{rv}</div>'

    def mval(sc, lbl=''):
        if lbl:
            return f'<div class="mvert-val" style="font-size:11px;color:var(--good);font-weight:800">{lbl}</div>'
        if sc is None:
            return '<div class="mvert-val mvert-nd">—</div>'
        return f'<div class="mvert-val {_sc(sc)}">{sc}</div>'

    link = item.get('affiliate_url') or item.get('item_url') or '#'

    return f'''<div class="{card_cls}" data-code="{item["item_code"]}" data-rakuten-rank="{rakuten_rank}"{bg_style}>
  <div class="pcard-body">
    <div class="pcard-accent" style="background:{color}"></div>
    <div class="pcard-rank">
      <span class="rank-num {rk_cls}"><span class="medal">{_MEDAL.get(rank,'')}</span><span class="rank-n-val">{rank}</span></span><span class="rank-lbl">位</span>
      <span class="rank-r">楽天 {rakuten_rank}位</span>
      {diff_html}
    </div>
    <div class="pcard-img">{img_html}</div>
    <div class="pcard-info">
      <div class="pcard-name">{item["item_name"]}</div>
      <div class="pcard-price-row">{price_html} {new_bdg}{ret_bdg}</div>
      {stars_html}
      <a class="btn-r" href="{link}" target="_blank" rel="noopener sponsored">楽天で見る ↗</a>
    </div>
    <div class="mvert">
      <div class="mvert-total">
        <div class="mvert-total-lbl">RevRank</div>
        {rv_html}
      </div>
      <div class="mvert-subs">
        <div class="mvert-item">
          <div class="mvert-lbl"><span class="kw">口コミ</span><span class="sf">ランク</span></div>
          {mval(k_sc)}
        </div>
        <div class="mvert-item">
          <div class="mvert-lbl"><span class="kw">コスパ</span><span class="sf">ランク</span></div>
          {mval(c_sc)}
        </div>
        <div class="mvert-item">
          <div class="mvert-lbl"><span class="kw">バズ</span><span class="sf">ランク</span></div>
          {mval(b_sc, b_label)}
        </div>
      </div>
    </div>
  </div>
</div>'''

# ── CSS ─────────────────────────────────────────────────────
CSS = """
:root {
  --bg:#f0f2f8; --sur:#ffffff; --sur2:#f8f9fc; --bdr:#e1e4ee;
  --ink:#18192a; --ink2:#6a6d86; --ink3:#b0b4cc;
  --acc:#d4922a;
  --good:#059669; --warn:#d97706; --danger:#dc2626; --info:#3b6fe0;
  --gold:#f59e0b; --silver:#9ca3af; --bronze:#b45309;
  --r:12px;
  --sans:-apple-system,BlinkMacSystemFont,'Hiragino Sans','Yu Gothic UI',sans-serif;
  --mono:'SF Mono',Consolas,monospace;
  --p1:#d4922a; --p2:#3b6fe0; --p3:#059669; --p4:#9333ea; --p5:#9ca3af;
}
@media(prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#0a0b15; --sur:#131524; --sur2:#1a1d30; --bdr:#252840;
  --ink:#e2e5f5; --ink2:#8a8eaa; --ink3:#454968;
  --acc:#f5b842; --good:#34d399; --warn:#fbbf24; --danger:#f87171; --info:#5b8af8;
  --gold:#fbbf24; --bronze:#d97706;
  --p1:#f5b842; --p2:#5b8af8; --p3:#34d399; --p4:#c084fc; --p5:#6b7280;
}}
:root[data-theme="dark"]{
  --bg:#0a0b15; --sur:#131524; --sur2:#1a1d30; --bdr:#252840;
  --ink:#e2e5f5; --ink2:#8a8eaa; --ink3:#454968;
  --acc:#f5b842; --good:#34d399; --warn:#fbbf24; --danger:#f87171; --info:#5b8af8;
  --gold:#fbbf24; --bronze:#d97706;
  --p1:#f5b842; --p2:#5b8af8; --p3:#34d399; --p4:#c084fc; --p5:#6b7280;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--ink);font-family:var(--sans);font-size:15px;line-height:1.6;min-height:100vh}
a{color:inherit;text-decoration:none} img{display:block;max-width:100%}
button{cursor:pointer;border:none;background:none;font:inherit;color:inherit}

/* PAGE HEADER */
.page-header{background:var(--sur);border-bottom:1px solid var(--bdr);padding:18px 20px 0;max-width:800px;margin:0 auto}
.site-eye{font-size:10px;font-weight:900;letter-spacing:.12em;color:var(--acc);margin-bottom:10px}
.site-eye span{color:var(--ink2);font-weight:400}
.genre-h{font-size:20px;font-weight:900;color:var(--ink);margin-bottom:3px}
.genre-sub{font-size:12px;color:var(--ink2);margin-bottom:14px}
.tabs{display:flex;border-top:1px solid var(--bdr);margin:0 -20px}
.tab{padding:9px 16px;font-size:12px;font-weight:700;color:var(--ink2);border-bottom:2px solid transparent;cursor:pointer;transition:color .12s,border-color .12s}
.tab:hover{color:var(--ink)}
.tab.active{color:var(--acc);border-bottom-color:var(--acc)}

/* GENRE GUIDE */
.genre-guide{max-width:800px;margin:16px auto 0;padding:0 0}
.genre-guide-inner{background:var(--sur2);border:1px solid var(--bdr);border-radius:var(--r);padding:14px 18px;font-size:13px;line-height:1.8;color:var(--ink2)}
.genre-guide-inner p{margin:0}

/* HERO */
.hero{max-width:800px;margin:0 auto;padding:16px 0 0}
.hero-inner{background:var(--sur);border:1px solid var(--bdr);border-radius:var(--r);overflow:hidden}
.hero-head{padding:14px 18px 12px;border-bottom:1px solid var(--bdr);display:flex;align-items:center;justify-content:space-between}
.hero-title{font-size:12px;font-weight:800;color:var(--ink)}
.hero-note{font-size:11px;color:var(--ink3)}
.charts-grid{display:grid;grid-template-columns:1fr 1fr 1fr}
@media(max-width:600px){.charts-grid{grid-template-columns:1fr}}

/* CHART PANEL */
.cpanel{padding:14px 14px 12px;border-right:1px solid var(--bdr)}
.cpanel:last-child{border-right:none}
@media(max-width:600px){.cpanel{border-right:none;border-bottom:1px solid var(--bdr)}.cpanel:last-child{border-bottom:none}}
.cpanel-head{display:flex;align-items:baseline;justify-content:space-between;margin-bottom:10px}
.cpanel-title{font-size:14px;font-weight:900;line-height:1}
.cpanel-title .kw{color:var(--acc)}
.cpanel-period{font-size:10px;font-weight:700;color:var(--ink3);background:var(--sur2);padding:2px 7px;border-radius:20px}
.cpanel-svg{width:100%;display:block}
.cpanel-legend{margin-top:10px;display:flex;flex-direction:column;gap:4px}
.legend-item{display:flex;align-items:center;gap:6px;font-size:10px;color:var(--ink2)}
.legend-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.legend-nd{opacity:.4}

/* PRODUCT LIST — 2-column grid; featured cards span full width */
.list-wrap{max-width:800px;margin:0 auto;padding:12px 0;display:grid;grid-template-columns:1fr 1fr;gap:10px}
.pcard-feat{grid-column:span 2}
.rank-divider{grid-column:span 2}
@media(max-width:520px){.list-wrap{grid-template-columns:1fr}}

/* PRODUCT CARD — base */
.pcard{background:var(--sur);border:1px solid var(--bdr);border-radius:var(--r);overflow:hidden;display:flex;flex-direction:column;transition:box-shadow .15s,transform .15s}
.pcard:hover{box-shadow:0 4px 20px rgba(0,0,0,.10);transform:translateY(-1px)}
.pcard-body{display:flex;align-items:stretch}
.pcard-accent{width:4px;flex-shrink:0}

/* RANK COLUMN */
.pcard-rank{width:56px;flex-shrink:0;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:1px;padding:0 4px}
.rank-num{font-size:22px;font-weight:900;font-variant-numeric:tabular-nums;line-height:1;display:flex;align-items:center;gap:2px}
.rank-lbl{font-size:8px;font-weight:700;color:var(--ink3);letter-spacing:.06em}
.rank-1{color:var(--gold)} .rank-2{color:var(--silver)} .rank-3{color:var(--bronze)} .rank-n{color:var(--ink3);font-size:16px}
.rank-r{font-size:9px;color:var(--ink3);font-weight:600;margin-top:3px;text-align:center;line-height:1.2}
.rank-diff{font-size:8px;font-weight:800;padding:1px 4px;border-radius:3px;margin-top:2px;text-align:center;line-height:1.4}
.rank-diff.gem{background:color-mix(in srgb,var(--good) 14%,transparent);color:var(--good)}
.rank-diff.overr{background:color-mix(in srgb,var(--ink3) 12%,transparent);color:var(--ink3)}
.medal{font-size:14px;line-height:1}

/* IMAGE COLUMN */
.pcard-img{flex-shrink:0;display:flex;align-items:center;justify-content:center;background:var(--sur2);border-left:1px solid var(--bdr);border-right:1px solid var(--bdr)}

/* INFO COLUMN */
.pcard-info{flex:1;min-width:0;display:flex;flex-direction:column;gap:4px}
.pcard-name{font-weight:700;color:var(--ink);line-height:1.4;display:-webkit-box;-webkit-box-orient:vertical;overflow:hidden}
.pcard-price-row{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.pcard-price{font-weight:900;color:var(--ink);font-variant-numeric:tabular-nums}
.pcard-stars{color:var(--ink2)} .pcard-stars .s{color:var(--gold)}
.btn-r{font-size:11px;font-weight:600;color:var(--ink3);background:none;border:none;cursor:pointer;display:inline-flex;align-items:center;gap:3px;padding:0;letter-spacing:.01em;text-decoration:none}
.btn-r:hover{color:var(--ink2)}

/* FEATURED (rank 1-3) */
.pcard-feat{border-width:1.5px;box-shadow:0 2px 10px rgba(0,0,0,.07)}
.pcard-feat .pcard-rank{width:64px}
.pcard-feat .rank-num{font-size:30px}
.pcard-feat .rank-lbl{font-size:9px}
.pcard-feat .rank-r{font-size:10px}
.pcard-feat .pcard-info{padding:14px 16px;gap:6px}
.pcard-feat .pcard-name{font-size:14px;-webkit-line-clamp:3}
.pcard-feat .pcard-price{font-size:19px}
.pcard-feat .pcard-stars{font-size:12px}

/* COMPACT (rank 4+) */
.pcard-compact .pcard-rank{width:48px}
.pcard-compact .rank-num{font-size:17px}
.pcard-compact .rank-r{font-size:8px;margin-top:2px}
.pcard-compact .rank-diff{font-size:7px;padding:1px 3px}
.pcard-compact .pcard-info{padding:8px 12px;gap:3px}
.pcard-compact .pcard-name{font-size:12px;-webkit-line-clamp:1}
.pcard-compact .pcard-price{font-size:14px}
.pcard-compact .pcard-stars{font-size:10px}
.pcard-compact .mvert-total-val{font-size:24px}
.pcard-compact .mvert-val{font-size:13px}
.pcard-compact .mvert-lbl{font-size:8px}
.pcard-compact .mvert-lbl .sf{font-size:7px}

/* SECTION DIVIDER */
.rank-divider{display:flex;align-items:center;gap:10px;padding:4px 0;color:var(--ink3);font-size:11px;font-weight:700;letter-spacing:.06em}
.rank-divider::before,.rank-divider::after{content:'';flex:1;height:1px;background:var(--bdr)}

/* METRIC SIDEBAR */
.mvert{width:110px;flex-shrink:0;border-left:1px solid var(--bdr);display:flex;flex-direction:column}
.mvert-total{padding:10px 12px 8px;border-bottom:1px solid var(--bdr);text-align:center}
.mvert-total-lbl{font-size:9px;font-weight:800;letter-spacing:.08em;color:var(--acc);text-transform:uppercase;margin-bottom:2px}
.mvert-total-val{font-size:32px;font-weight:900;font-variant-numeric:tabular-nums;line-height:1;color:var(--ink)}
.prov{font-size:9px;color:var(--ink3);vertical-align:middle;margin-left:2px}
.mvert-subs{display:flex;flex-direction:column;flex:1}
.mvert-item{flex:1;display:flex;align-items:center;justify-content:space-between;padding:0 10px;border-bottom:1px solid var(--bdr)}
.mvert-item:last-child{border-bottom:none}
.mvert-lbl{font-size:9px;font-weight:700;line-height:1.3}
.mvert-lbl .kw{color:var(--acc);display:block}
.mvert-lbl .sf{color:var(--ink3);font-size:8px}
.mvert-val{font-size:15px;font-weight:900;font-variant-numeric:tabular-nums;line-height:1}
.mvert-nd{color:var(--ink3) !important;font-size:12px !important}
.mvert-badge{font-size:9px;font-weight:800;padding:1px 5px;border-radius:3px;background:color-mix(in srgb,var(--good) 15%,transparent);color:var(--good)}
.mvert-badge.ret{background:color-mix(in srgb,var(--info) 15%,transparent);color:var(--info)}

/* SCORE COLORS */
.col-good{color:var(--good)} .col-warn{color:var(--warn)} .col-mute{color:var(--ink2)}

/* RELATED */
.related{max-width:800px;margin:16px auto 60px;padding:0 20px}
.rel-hd{font-size:12px;font-weight:700;color:var(--ink3);letter-spacing:.06em;text-transform:uppercase;display:flex;align-items:center;gap:10px;margin-bottom:12px}
.rel-hd::after{content:'';flex:1;height:1px;background:var(--bdr)}
.rel-links{display:flex;flex-wrap:wrap;gap:8px}
.rel-link{display:inline-flex;align-items:center;gap:5px;font-size:12px;font-weight:600;padding:6px 14px;border-radius:99px;border:1px solid var(--bdr);color:var(--ink2);background:var(--sur);transition:border-color .12s,color .12s}
.rel-link:hover{border-color:var(--acc);color:var(--acc)}

/* FOOTER */
.footer{background:var(--sur);border-top:1px solid var(--bdr);padding:24px 20px;text-align:center;font-size:11px;color:var(--ink3);line-height:2;max-width:800px;margin:0 auto}

/* INDEX */
.top-hero{background:var(--sur);border-bottom:1px solid var(--bdr);padding:60px 20px 48px;text-align:center}
.top-in{max-width:640px;margin:0 auto}
.top-logo{font-size:40px;font-weight:900;letter-spacing:-.05em;color:var(--acc);margin-bottom:6px}
.top-sub{font-size:15px;color:var(--ink2);line-height:1.75;margin-bottom:20px}
.top-badges{display:flex;flex-wrap:wrap;gap:8px;justify-content:center}
.top-badge{display:inline-flex;align-items:center;gap:5px;font-size:11px;font-weight:600;padding:4px 10px;border-radius:99px;border:1px solid var(--bdr);color:var(--ink2);background:var(--sur2)}
.top-badge.a{border-color:var(--acc);color:var(--acc);background:color-mix(in srgb,var(--acc) 8%,transparent)}
.idx{max-width:800px;margin:40px auto 60px;padding:0 20px}
.icat{margin-bottom:36px}
.ich{font-size:12px;font-weight:700;color:var(--ink3);letter-spacing:.08em;text-transform:uppercase;display:flex;align-items:center;gap:10px;margin-bottom:14px}
.ich::after{content:'';flex:1;height:1px;background:var(--bdr)}
.igrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}
.ic{background:var(--sur);border:1px solid var(--bdr);border-radius:var(--r);padding:16px;display:flex;flex-direction:column;gap:4px;transition:border-color .12s,box-shadow .12s,transform .12s}
.ic:hover{border-color:var(--acc);box-shadow:0 2px 12px rgba(0,0,0,.08);transform:translateY(-2px)}
.ie{font-size:26px;line-height:1;margin-bottom:2px}
.il{font-size:13px;font-weight:700;color:var(--ink);line-height:1.3}
.in{font-size:11px;color:var(--ink3);font-family:var(--mono)}
"""

# ── カテゴリ順 (インデックス用) ──────────────────────────────
CATEGORY_ORDER = [
    ("ランニング",           ["running_shoes","running_watch"]),
    ("ゴルフ",               ["golf_club","golf_ball","golf_shoes","golf_bag"]),
    ("フィットネスマシン",   ["treadmill","fitness_bike","stepper"]),
    ("ウェイトトレーニング", ["dumbbell","barbell","kettlebell"]),
    ("アウトドア",           ["tent","tarp","outdoor_bedding","camp_chair","bbq_grill","camp_stove","bonfire"]),
    ("ウィンタースポーツ",   ["ski_board","ski_boots","snowboard","snowboard_boots"]),
    ("寝具",                 ["mattress","bed_frame","leg_mattress"]),
    ("子育て",               ["stroller","child_seat"]),
    ("登山",                 ["climbing_shoes"]),
    ("自転車",               ["e_bike"]),
]

# ── ジャンルページ生成 ───────────────────────────────────────
def build_genre_page(key):
    if key not in GENRE_META: return
    m     = GENRE_META[key]
    slug  = m["slug"]
    label = m["label"]
    emoji = m["emoji"]
    year  = date.today().year

    # データ読み込み
    rows = conn.execute("""
        SELECT rank, item_code, item_name, item_price,
               review_count, review_average, item_url, affiliate_url,
               image_url, shop_name
        FROM item_rankings WHERE genre_key=? AND fetched_date=?
        ORDER BY rank LIMIT 90
    """, (key, latest_date)).fetchall()

    if not rows:
        print(f"  [SKIP] {key} — データなし ({latest_date})", file=sys.stderr)
        return

    items = [dict(r) for r in rows]
    for item in items:
        item['item_name']    = clean_name(item['item_name'] or '')
        item['genre_key']    = key

    # スコア計算
    k_scores  = compute_kuchikomi(items)
    c_scores  = compute_cospa(key, items, latest_date)
    b_results = compute_buzz(key, items, latest_date)
    rv_scores = compute_revrank(k_scores, c_scores, b_results)

    # RevRankスコア順ソート
    items.sort(key=lambda i: (
        rv_scores.get(i['item_code'], (None, True))[0] or -1,
        k_scores.get(i['item_code']) or -1
    ), reverse=True)

    # 上位20件の画像をプリフェッチ
    for idx, item in enumerate(items[:20]):
        item['img'] = fetch_datauri(item.get('image_url') or '')
        if idx < 19: time.sleep(0.08)
    for item in items[20:]:
        item['img'] = ''

    # ガイドテキスト
    guide_text = m.get('guide', '')
    guide_html = (
        f'<div class="genre-guide"><div class="genre-guide-inner"><p>{_he(guide_text)}</p></div></div>'
        if guide_text else ''
    )

    # ヒーローチャート (上位5)
    top5      = items[:5]
    hero_html = render_hero_section(key, top5, latest_date)

    # 製品カード (上位20)
    cards_html = []
    for rank, item in enumerate(items[:20], 1):
        code   = item['item_code']
        color  = PCOLS[rank-1] if rank <= len(PCOLS) else '#64748b'
        k_sc   = k_scores.get(code)
        c_sc   = c_scores.get(code)
        b_sc, b_label, _ = b_results.get(code, (None, '', ''))
        rv, is_prov = rv_scores.get(code, (None, True))
        meta   = get_meta(key, code, latest_date)
        if rank == 4:
            cards_html.append('<div class="rank-divider">4位以下</div>')
        cards_html.append(render_pcard(rank, color, item, k_sc, c_sc, b_sc, b_label, rv, is_prov, meta))

    # タブ切替用データ
    items_json = json.dumps([{
        'code': i['item_code'],
        'k':    k_scores.get(i['item_code']),
        'c':    c_scores.get(i['item_code']),
        'b':    (b_results.get(i['item_code']) or (None,))[0],
        'rv':   (rv_scores.get(i['item_code']) or (None,))[0],
    } for i in items[:20]], ensure_ascii=False)

    # 関連リンク
    related = [GENRE_META[k] for k in m.get('related', []) if k in GENRE_META]
    rel_html = (''.join(
        f'<a class="rel-link" href="../{r["slug"]}/">{r["emoji"]} {r["label"]}</a>'
        for r in related
    ) + f'<a class="rel-link" href="../">🏠 全ジャンル</a>')

    # JSON-LD
    reviewed = [i for i in items if (i.get('review_count') or 0) > 0]
    ld_items = [{"@type":"ListItem","position":rank+1,"item":{
        "@type":"Product","name":i["item_name"],"url":i.get("item_url",""),
        "offers":{"@type":"Offer","price":str(i.get("item_price") or 0),"priceCurrency":"JPY"},
        "aggregateRating":{"@type":"AggregateRating",
            "ratingValue":str(i["review_average"]),"reviewCount":str(i["review_count"])},
    }} for rank, i in enumerate(reviewed[:10])]
    jsonld = json.dumps({"@context":"https://schema.org","@type":"ItemList",
        "name":f"{label} RevRankランキング","url":f"{BASE_URL}/{slug}/",
        "itemListElement":ld_items}, ensure_ascii=False, separators=(',',':'))

    page_url = f"{BASE_URL}/{slug}/"
    rc_total = sum(i.get('review_count') or 0 for i in reviewed)

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{label}ランキング {year}年 | RevRank</title>
<meta name="description" content="{m['desc']}">
<meta name="robots" content="index,follow">
<link rel="canonical" href="{page_url}">
<meta property="og:title" content="{label}ランキング {year}年 | RevRank">
<meta property="og:description" content="{m['desc']}">
<meta property="og:url" content="{page_url}">
<script type="application/ld+json">{jsonld}</script>
<style>{CSS}</style>
</head>
<body>

<div class="page-header">
  <div class="site-eye">Rev<span>Rank · {emoji} {label}</span></div>
  <div class="genre-h">{label}ランキング</div>
  <div class="genre-sub">楽天市場の上位製品を口コミ・コスパ・バズの3指標で分析 · {latest_date}更新</div>
  <div class="tabs">
    <div class="tab active" data-sort="rv">総合</div>
    <div class="tab" data-sort="k">口コミ順</div>
    <div class="tab" data-sort="c">コスパ順</div>
    <div class="tab" data-sort="b">急上昇</div>
  </div>
</div>

{guide_html}
<div class="hero">{hero_html}</div>

<div class="list-wrap" id="pcard-list">
  {"".join(cards_html)}
</div>

<div class="related">
  <div class="rel-hd">関連ジャンル</div>
  <div class="rel-links">{rel_html}</div>
</div>

<script>
(function(){{
  if(localStorage.getItem('rrAdmin')) return;
  var w='{WORKER_URL}';
  if(!w) return;
  try{{ fetch(w+'/track',{{method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{p:location.pathname,r:document.referrer}}),keepalive:true}}).catch(function(){{}}); }}catch(e){{}}
}})();
</script>
<footer class="footer">
  <p>楽天市場のレビューデータをもとに独自スコア (RevRank) で並べ替えたランキングです。楽天の売れ筋順位とは異なります。</p>
  <p>本ページには楽天アフィリエイトリンクが含まれます。更新: {latest_date} · {rc_total:,}件のレビューを集計</p>
  <p>© {year} RevRank</p>
</footer>

<script>
(function(){{
  var DATA = {items_json};
  var list = document.getElementById('pcard-list');
  if(!list) return;

  var MEDALS = {{1:'🥇',2:'🥈',3:'🥉'}};
  var TINTS  = {{
    1:'color-mix(in srgb,var(--gold) 6%,transparent)',
    2:'color-mix(in srgb,var(--silver) 5%,transparent)',
    3:'color-mix(in srgb,var(--bronze) 5%,transparent)'
  }};
  var RANK_CLS = ['rank-1','rank-2','rank-3'];

  function updateRanks(){{
    var cards = Array.from(list.querySelectorAll('.pcard'));
    var divider = list.querySelector('.rank-divider');

    // divider を4位の前に移動
    if(divider && cards.length > 3) list.insertBefore(divider, cards[3]);

    cards.forEach(function(card, i){{
      var pos  = i + 1;
      var rr   = parseInt(card.dataset.rakutenRank) || pos;
      var diff = rr - pos;
      var feat = pos <= 3;

      // featured / compact クラス切替
      card.classList.remove('pcard-feat','pcard-compact');
      card.classList.add(feat ? 'pcard-feat' : 'pcard-compact');
      card.style.background = TINTS[pos] || '';

      // メダル + 順位番号
      var medalEl = card.querySelector('.medal');
      var nvalEl  = card.querySelector('.rank-n-val');
      var numEl   = card.querySelector('.rank-num');
      if(medalEl) medalEl.textContent = MEDALS[pos] || '';
      if(nvalEl)  nvalEl.textContent  = pos;
      if(numEl)   numEl.className = 'rank-num ' + (RANK_CLS[i] || 'rank-n');

      // 楽天順位
      var rEl = card.querySelector('.rank-r');
      if(rEl) rEl.textContent = '楽天 ' + rr + '位';

      // 差分バッジ
      var diffEl = card.querySelector('.rank-diff');
      if(diffEl){{
        if(Math.abs(diff) >= 3){{
          diffEl.style.display = '';
          diffEl.className = 'rank-diff ' + (diff > 0 ? 'gem' : 'overr');
          diffEl.textContent = diff > 0 ? '楽天比 +'+diff+'↑' : '楽天比 '+diff+'↓';
        }} else {{
          diffEl.style.display = 'none';
        }}
      }}
    }});
  }}

  document.querySelectorAll('.tab').forEach(function(tab){{
    tab.addEventListener('click', function(){{
      document.querySelectorAll('.tab').forEach(function(t){{t.classList.remove('active');}});
      tab.classList.add('active');
      var key = tab.dataset.sort;
      var sorted = DATA.slice().sort(function(a,b){{return (b[key]??-1)-(a[key]??-1);}});
      sorted.forEach(function(d){{
        var card = list.querySelector('[data-code="'+d.code+'"]');
        if(card) list.appendChild(card);
      }});
      updateRanks();
    }});
  }});
}})();
</script>

</body>
</html>"""

    out = DOCS_DIR / slug
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(html, encoding="utf-8")
    print(f"  [OK] {key} → {slug}/index.html ({len(html):,} bytes)", file=sys.stderr)

# ── トップページ ─────────────────────────────────────────────
def build_index(genre_counts):
    year = date.today().year
    sections = []
    for cat, keys in CATEGORY_ORDER:
        cards = "".join(
            f'<a class="ic" href="{GENRE_META[k]["slug"]}/">'
            f'<span class="ie">{GENRE_META[k]["emoji"]}</span>'
            f'<span class="il">{GENRE_META[k]["label"]}</span>'
            f'<span class="in">{genre_counts.get(k,0)}件収録</span></a>'
            for k in keys if k in GENRE_META
        )
        sections.append(f'<div class="icat"><h2 class="ich">{cat}</h2><div class="igrid">{cards}</div></div>')

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>RevRank — 口コミ・コスパ・バズで選ぶ本当のランキング</title>
<meta name="description" content="楽天市場の製品を口コミランク・コスパランク・バズランクの3指標で独自分析。売れ筋とは違う本当の評価ランキングを31ジャンルで提供。">
<meta name="robots" content="index,follow">
<link rel="canonical" href="{BASE_URL}/">
<style>{CSS}</style>
</head>
<body>
<header class="top-hero">
  <div class="top-in">
    <div class="top-logo">RevRank</div>
    <p class="top-sub">「ランキング1位！」ではなく、<strong>口コミの質・コスパ・話題性</strong>で選ぶ本当のランキング。</p>
    <div class="top-badges">
      <span class="top-badge a">31ジャンル収録</span>
      <span class="top-badge">楽天公式とは別集計</span>
      <span class="top-badge">毎時更新</span>
    </div>
  </div>
</header>
<main class="idx">{"".join(sections)}</main>
<script>
(function(){{
  if(localStorage.getItem('rrAdmin')) return;
  var w='{WORKER_URL}';
  if(!w) return;
  try{{ fetch(w+'/track',{{method:'POST',headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{p:location.pathname,r:document.referrer}}),keepalive:true}}).catch(function(){{}}); }}catch(e){{}}
}})();
</script>
<footer class="footer">
  <p>楽天市場のレビューデータをもとに独自スコアで並べ替えたランキングです。本ページには楽天アフィリエイトリンクが含まれます。</p>
  <p>© {year} RevRank · 更新: {latest_date}</p>
</footer>
</body>
</html>"""

def build_admin():
    """管理ページ生成 (docs/admin/index.html)"""
    year = date.today().year
    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>RevRank Analytics</title>
<meta name="robots" content="noindex,nofollow">
<style>
:root{{
  --bg:#0a0b15;--sur:#131524;--sur2:#1a1d30;--bdr:#252840;
  --ink:#e2e5f5;--ink2:#8a8eaa;--ink3:#454968;
  --acc:#f5b842;--good:#34d399;--warn:#fbbf24;--info:#5b8af8;
  --r:10px;--sans:-apple-system,BlinkMacSystemFont,'Hiragino Sans',sans-serif;
}}
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--ink);font-family:var(--sans);font-size:14px;min-height:100vh}}
a{{color:inherit;text-decoration:none}}
.wrap{{max-width:900px;margin:0 auto;padding:24px 16px}}
.hd{{display:flex;align-items:center;justify-content:space-between;margin-bottom:24px;gap:12px;flex-wrap:wrap}}
.logo{{font-size:20px;font-weight:900;color:var(--acc)}}
.logo span{{color:var(--ink2);font-weight:400;font-size:13px}}
.period-tabs{{display:flex;gap:6px}}
.ptab{{padding:5px 14px;border-radius:99px;border:1px solid var(--bdr);color:var(--ink2);font-size:12px;font-weight:600;cursor:pointer;background:var(--sur)}}
.ptab.active{{border-color:var(--acc);color:var(--acc);background:color-mix(in srgb,var(--acc) 10%,transparent)}}
.kpi-row{{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:10px;margin-bottom:20px}}
.kpi{{background:var(--sur);border:1px solid var(--bdr);border-radius:var(--r);padding:14px 16px}}
.kpi-lbl{{font-size:11px;color:var(--ink2);font-weight:600;letter-spacing:.06em;text-transform:uppercase;margin-bottom:4px}}
.kpi-val{{font-size:28px;font-weight:900;color:var(--acc);font-variant-numeric:tabular-nums}}
.card{{background:var(--sur);border:1px solid var(--bdr);border-radius:var(--r);overflow:hidden;margin-bottom:14px}}
.card-hd{{padding:12px 16px;border-bottom:1px solid var(--bdr);font-size:12px;font-weight:700;color:var(--ink2);letter-spacing:.06em;text-transform:uppercase}}
.chart-wrap{{padding:16px;overflow-x:auto}}
svg.chart{{width:100%;display:block}}
.page-table{{width:100%;border-collapse:collapse}}
.page-table th{{padding:8px 12px;text-align:left;font-size:11px;font-weight:700;color:var(--ink3);letter-spacing:.06em;text-transform:uppercase;border-bottom:1px solid var(--bdr)}}
.page-table td{{padding:8px 12px;border-bottom:1px solid var(--bdr);font-size:13px}}
.page-table tr:last-child td{{border-bottom:none}}
.page-table tr:hover td{{background:var(--sur2)}}
.bar-wrap{{display:flex;align-items:center;gap:8px}}
.bar{{height:6px;background:var(--acc);border-radius:3px;opacity:.7;flex-shrink:0}}
.cnt{{color:var(--ink2);font-size:12px;font-variant-numeric:tabular-nums;white-space:nowrap}}
.recent-list{{padding:0}}
.rl-item{{display:flex;align-items:baseline;gap:10px;padding:7px 16px;border-bottom:1px solid var(--bdr);font-size:12px}}
.rl-item:last-child{{border-bottom:none}}
.rl-page{{color:var(--ink);font-weight:600;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.rl-ref{{color:var(--ink3);font-size:11px;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.rl-time{{color:var(--ink3);font-size:11px;white-space:nowrap}}
.login{{display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:60vh;gap:16px}}
.login-box{{background:var(--sur);border:1px solid var(--bdr);border-radius:var(--r);padding:32px;width:100%;max-width:320px;display:flex;flex-direction:column;gap:12px}}
.login-title{{font-size:16px;font-weight:800;color:var(--acc);text-align:center}}
input[type=text],input[type=password]{{background:var(--sur2);border:1px solid var(--bdr);border-radius:6px;padding:9px 12px;color:var(--ink);font-size:14px;width:100%;outline:none}}
input:focus{{border-color:var(--acc)}}
.btn-login{{background:var(--acc);color:#000;font-weight:800;font-size:14px;border:none;border-radius:6px;padding:10px;cursor:pointer;width:100%}}
.err{{color:var(--warn);font-size:12px;text-align:center}}
#main{{display:none}}
</style>
</head>
<body>
<div class="wrap">
  <div id="login-view" class="login">
    <div class="login-box">
      <div class="login-title">RevRank Analytics</div>
      <input type="password" id="key-input" placeholder="管理キー" autocomplete="current-password">
      <button class="btn-login" onclick="doLogin()">ログイン</button>
      <div class="err" id="err-msg"></div>
    </div>
  </div>

  <div id="main">
    <div class="hd">
      <div class="logo">RevRank <span>Analytics</span></div>
      <div class="period-tabs">
        <div class="ptab active" data-d="7">7日</div>
        <div class="ptab" data-d="30">30日</div>
        <div class="ptab" data-d="90">90日</div>
      </div>
    </div>
    <div class="kpi-row" id="kpi-row"></div>
    <div class="card">
      <div class="card-hd">日別PV</div>
      <div class="chart-wrap" id="day-chart"></div>
    </div>
    <div class="card">
      <div class="card-hd">ページ別PV</div>
      <table class="page-table" id="page-table">
        <thead><tr><th>ページ</th><th>PV</th><th></th></tr></thead>
        <tbody></tbody>
      </table>
    </div>
    <div class="card">
      <div class="card-hd">直近アクセス</div>
      <ul class="recent-list" id="recent-list"></ul>
    </div>
  </div>
</div>

<script>
var WORKER = '{WORKER_URL}';
var adminKey = '';

function doLogin() {{
  var k = document.getElementById('key-input').value.trim();
  if (!k) return;
  adminKey = k;
  load(30);
}}

document.getElementById('key-input').addEventListener('keydown', function(e) {{
  if (e.key === 'Enter') doLogin();
}});

// URL パラメータからキーを自動読み込み
(function() {{
  var p = new URLSearchParams(location.search).get('key');
  if (p) {{ adminKey = p; load(30); }}
}})();

document.querySelectorAll('.ptab').forEach(function(t) {{
  t.addEventListener('click', function() {{
    document.querySelectorAll('.ptab').forEach(function(x) {{ x.classList.remove('active'); }});
    t.classList.add('active');
    load(parseInt(t.dataset.d));
  }});
}});

function load(days) {{
  fetch(WORKER + '/stats?days=' + days + '&key=' + encodeURIComponent(adminKey), {{}})
  .then(function(r) {{
    if (r.status === 401) {{
      document.getElementById('err-msg').textContent = 'キーが違います';
      return null;
    }}
    return r.json();
  }})
  .then(function(d) {{
    if (!d) return;
    // 自己除外フラグをセット
    localStorage.setItem('rrAdmin', '1');
    document.getElementById('login-view').style.display = 'none';
    document.getElementById('main').style.display = 'block';
    renderKpi(d, days);
    renderChart(d.by_day);
    renderPages(d.by_page);
    renderRecent(d.recent);
  }})
  .catch(function(e) {{
    document.getElementById('err-msg').textContent = 'エラー: ' + e.message;
  }});
}}

function renderKpi(d, days) {{
  var byDay = d.by_day || [];
  var today = byDay.length ? byDay[byDay.length-1].count : 0;
  var pages = new Set((d.by_page||[]).map(function(p){{return p.page;}})).size;
  document.getElementById('kpi-row').innerHTML =
    kpiCard('総PV', d.total, '過去' + days + '日') +
    kpiCard('本日PV', today, '今日') +
    kpiCard('ページ数', pages, 'アクセスあり');
}}
function kpiCard(lbl, val, sub) {{
  return '<div class="kpi"><div class="kpi-lbl">'+lbl+'</div><div class="kpi-val">'+(val||0).toLocaleString()+'</div><div style="font-size:11px;color:var(--ink3);margin-top:2px">'+sub+'</div></div>';
}}

function renderChart(byDay) {{
  if (!byDay || !byDay.length) {{ document.getElementById('day-chart').innerHTML='<p style="color:var(--ink3);padding:16px;font-size:12px">データなし</p>'; return; }}
  var W=800, H=120, PL=36, PR=W-8, PT=8, PB=H-20, PW=PR-PL, PH=PB-PT;
  var counts = byDay.map(function(r){{return r.count;}});
  var mx = Math.max.apply(null, counts) || 1;
  function x(i){{ return PL + i/(byDay.length-1||1)*PW; }}
  function y(v){{ return PB - v/mx*PH; }}
  var pts = byDay.map(function(r,i){{return x(i).toFixed(1)+','+y(r.count).toFixed(1);}}).join(' ');
  var area = x(0).toFixed(1)+','+PB+' '+pts+' '+x(byDay.length-1).toFixed(1)+','+PB;
  var ticks = '';
  [0, Math.round(byDay.length/2), byDay.length-1].forEach(function(i){{
    if(byDay[i]) ticks += '<text x="'+x(i).toFixed(1)+'" y="'+(PB+14)+'" text-anchor="middle" font-size="9" fill="var(--ink3)">'+byDay[i].date.slice(5)+'</text>';
  }});
  document.getElementById('day-chart').innerHTML =
    '<svg class="chart" viewBox="0 0 '+W+' '+H+'">' +
    '<polygon points="'+area+'" fill="var(--acc)" fill-opacity=".12"/>' +
    '<polyline points="'+pts+'" fill="none" stroke="var(--acc)" stroke-width="2" stroke-linejoin="round"/>' +
    ticks + '</svg>';
}}

function renderPages(byPage) {{
  if (!byPage || !byPage.length) return;
  var mx = byPage[0].count;
  var rows = byPage.map(function(p, i) {{
    var pct = Math.round(p.count/mx*100);
    var label = p.page.replace(/\\/$/,'').split('/').pop() || 'トップ';
    return '<tr><td>'+label+'<div style="font-size:10px;color:var(--ink3)">'+p.page+'</div></td>' +
      '<td style="font-variant-numeric:tabular-nums">'+p.count.toLocaleString()+'</td>' +
      '<td style="width:120px"><div class="bar-wrap"><div class="bar" style="width:'+pct+'px"></div></div></td></tr>';
  }}).join('');
  document.querySelector('#page-table tbody').innerHTML = rows;
}}

function renderRecent(recent) {{
  if (!recent || !recent.length) return;
  document.getElementById('recent-list').innerHTML = recent.map(function(r) {{
    var t = r.viewed_at ? r.viewed_at.replace('T',' ').slice(0,16) : '';
    var ref = r.referrer ? r.referrer.replace(/^https?:\\/\\/[^\\/]+/,'') || r.referrer : '直接';
    return '<li class="rl-item"><span class="rl-page">'+r.page+'</span><span class="rl-ref">from: '+ref+'</span><span class="rl-time">'+t+'</span></li>';
  }}).join('');
}}
</script>
</body>
</html>"""
    out = DOCS_DIR / "admin"
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(html, encoding="utf-8")
    print(f"→ docs/admin/index.html ({len(html):,} bytes)", file=sys.stderr)

def build_sitemap(built):
    today = date.today().isoformat()
    urls  = [f'  <url><loc>{BASE_URL}/</loc><lastmod>{today}</lastmod><changefreq>hourly</changefreq><priority>1.0</priority></url>']
    for key in built:
        if key in GENRE_META:
            slug = GENRE_META[key]["slug"]
            urls.append(f'  <url><loc>{BASE_URL}/{slug}/</loc><lastmod>{today}</lastmod><changefreq>hourly</changefreq><priority>0.8</priority></url>')
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{chr(10).join(urls)}\n</urlset>'

# ── メイン ───────────────────────────────────────────────────
def main():
    if not latest_date:
        print("DBにデータがありません。先に fetch_ranking.py を実行してください。", file=sys.stderr)
        sys.exit(1)

    target = sys.argv[1] if len(sys.argv) > 1 else None
    keys   = [target] if target else list(GENRE_META.keys())
    built  = []
    genre_counts = {}

    for key in keys:
        if key not in GENRE_META:
            print(f"Unknown: {key}", file=sys.stderr); continue
        print(f"\n── {GENRE_META[key]['label']} ──", file=sys.stderr)
        build_genre_page(key)
        cnt = conn.execute(
            "SELECT COUNT(*) FROM item_rankings WHERE genre_key=? AND fetched_date=?",
            (key, latest_date)).fetchone()[0]
        if cnt > 0:
            genre_counts[key] = cnt
            built.append(key)

    if not target:
        idx = build_index(genre_counts)
        (DOCS_DIR / "index.html").write_text(idx, encoding="utf-8")
        print(f"\n→ docs/index.html ({len(idx):,} bytes)", file=sys.stderr)
        sm = build_sitemap(built)
        (DOCS_DIR / "sitemap.xml").write_text(sm, encoding="utf-8")
        print(f"→ docs/sitemap.xml", file=sys.stderr)
        robots = f"User-agent: *\nAllow: /\nSitemap: {BASE_URL}/sitemap.xml\n"
        (DOCS_DIR / "robots.txt").write_text(robots, encoding="utf-8")
        print(f"→ docs/robots.txt", file=sys.stderr)
        build_admin()
        print(f"→ docs/admin/index.html", file=sys.stderr)

    print(f"\n✓ {len(built)}ジャンル生成完了 → {DOCS_DIR}", file=sys.stderr)

if __name__ == "__main__":
    main()
