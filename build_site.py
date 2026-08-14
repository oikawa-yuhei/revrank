"""
build_site.py — RevRank 静的サイトジェネレーター
各ジャンルごとに docs/{slug}/index.html を生成し、
docs/index.html（トップ）と docs/sitemap.xml も作る。

使い方:
    python build_site.py                  # 全ジャンル
    python build_site.py running_shoes    # 1ジャンルのみ（デバッグ用）
"""

import base64, hashlib, json, math, os, re, sqlite3, sys, time
import urllib.request
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))
from ichiba.config import DB_PATH, GENRES

# ── サイト設定 ──────────────────────────────────────────────
SITE_NAME   = "RevRank"
BASE_URL    = "https://oikawa-yuhei.github.io/revrank"
DOCS_DIR    = Path(__file__).parent / "docs"
CACHE_DIR   = Path(__file__).parent / "data" / "img_cache"
APP_ID      = os.environ.get("RAKUTEN_ICHIBA_APP_ID", "")
DOCS_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ── ジャンルメタ ─────────────────────────────────────────────
GENRE_META = {
    "running_shoes":   {"slug":"running-shoes","label":"ランニングシューズ","emoji":"👟",
        "kw":"ランニングシューズ おすすめ",
        "desc":"楽天市場のランニングシューズを口コミ件数×評価点の独自スコアで並べた本当のランキング。売れ筋とは違う、本当に評価された一足を探せます。",
        "related":["running_watch"]},
    "running_watch":   {"slug":"running-watch","label":"ランニングウォッチ・GPS","emoji":"⌚",
        "kw":"ランニングウォッチ GPS おすすめ",
        "desc":"GPSランニングウォッチの口コミ評価ランキング。ガーミン・アップルウォッチなど人気モデルを実際の購入者レビューで比較。",
        "related":["running_shoes"]},
    "golf_club":       {"slug":"golf-club","label":"ゴルフクラブ","emoji":"⛳",
        "kw":"ゴルフクラブ おすすめ ランキング",
        "desc":"ゴルフクラブの口コミ評価ランキング。実際のゴルファーの口コミスコアで選ぶ一本。",
        "related":["golf_ball","golf_shoes","golf_bag"]},
    "golf_ball":       {"slug":"golf-ball","label":"ゴルフボール","emoji":"⛳",
        "kw":"ゴルフボール おすすめ",
        "desc":"ゴルフボールの口コミ評価ランキング。購入者レビューが多い信頼性の高い製品を厳選。",
        "related":["golf_club","golf_shoes"]},
    "golf_shoes":      {"slug":"golf-shoes","label":"ゴルフシューズ","emoji":"⛳",
        "kw":"ゴルフシューズ おすすめ",
        "desc":"ゴルフシューズの口コミ評価ランキング。実際のゴルファーから高評価を得た一足。",
        "related":["golf_club","golf_bag"]},
    "golf_bag":        {"slug":"golf-bag","label":"ゴルフバッグ","emoji":"⛳",
        "kw":"ゴルフバッグ おすすめ キャディバッグ",
        "desc":"キャディバッグの口コミ評価ランキング。収納力・デザイン・耐久性を購入者が評価。",
        "related":["golf_club","golf_shoes"]},
    "treadmill":       {"slug":"treadmill","label":"ランニングマシン","emoji":"🏃",
        "kw":"ランニングマシン おすすめ 家庭用",
        "desc":"家庭用ランニングマシンの口コミ評価ランキング。静音性・折りたたみなど実用性を購入者が評価。",
        "related":["fitness_bike","stepper"]},
    "fitness_bike":    {"slug":"fitness-bike","label":"フィットネスバイク","emoji":"🚴",
        "kw":"フィットネスバイク おすすめ 家庭用",
        "desc":"家庭用フィットネスバイク・エアロバイクの口コミ評価ランキング。購入者レビューで比較。",
        "related":["treadmill","stepper"]},
    "stepper":         {"slug":"stepper","label":"ステッパー","emoji":"🏋️",
        "kw":"ステッパー おすすめ ながら運動",
        "desc":"ステッパーの口コミ評価ランキング。テレワーク中の運動不足解消に人気の製品を実際の口コミで比較。",
        "related":["treadmill","fitness_bike"]},
    "dumbbell":        {"slug":"dumbbell","label":"ダンベル","emoji":"🏋️",
        "kw":"ダンベル おすすめ 可変式",
        "desc":"ダンベルの口コミ評価ランキング。可変式・固定式を問わず、ホームジム派から高評価の製品を紹介。",
        "related":["barbell","kettlebell"]},
    "barbell":         {"slug":"barbell","label":"バーベル","emoji":"🏋️",
        "kw":"バーベル おすすめ セット",
        "desc":"バーベルセットの口コミ評価ランキング。ホームジム構築に実際に購入して高評価をつけた製品を厳選。",
        "related":["dumbbell","kettlebell"]},
    "kettlebell":      {"slug":"kettlebell","label":"ケトルベル","emoji":"🏋️",
        "kw":"ケトルベル おすすめ 重さ",
        "desc":"ケトルベルの口コミ評価ランキング。重量・素材・グリップを購入者が評価した製品を比較。",
        "related":["dumbbell","barbell"]},
    "tent":            {"slug":"tent","label":"テント","emoji":"⛺",
        "kw":"テント おすすめ ソロ キャンプ",
        "desc":"キャンプ用テントの口コミ評価ランキング。実際のキャンパーから高評価を得た一幕。",
        "related":["tarp","outdoor_bedding","camp_chair"]},
    "tarp":            {"slug":"tarp","label":"タープ","emoji":"⛺",
        "kw":"タープ おすすめ キャンプ",
        "desc":"タープの口コミ評価ランキング。ヘキサ・レクタ・ウィングなど購入者が評価した製品を紹介。",
        "related":["tent","camp_chair"]},
    "outdoor_bedding": {"slug":"outdoor-bedding","label":"アウトドア用寝具","emoji":"🏕️",
        "kw":"シュラフ 寝袋 おすすめ キャンプ",
        "desc":"シュラフ・キャンプ用マットなどアウトドア寝具の口コミ評価ランキング。",
        "related":["tent","tarp"]},
    "camp_chair":      {"slug":"camp-chair","label":"キャンプチェア・テーブル","emoji":"🪑",
        "kw":"キャンプ チェア テーブル おすすめ",
        "desc":"キャンプ用チェア・テーブルの口コミ評価ランキング。実際のキャンパーが評価した製品を紹介。",
        "related":["tent","bonfire"]},
    "bbq_grill":       {"slug":"bbq-grill","label":"バーベキューコンロ","emoji":"🔥",
        "kw":"バーベキューコンロ おすすめ",
        "desc":"バーベキューコンロの口コミ評価ランキング。購入者が評価した製品を比較。",
        "related":["bonfire","camp_stove","camp_chair"]},
    "camp_stove":      {"slug":"camp-stove","label":"キャンプバーナー","emoji":"🔥",
        "kw":"キャンプ バーナー シングル おすすめ",
        "desc":"キャンプ用バーナーの口コミ評価ランキング。火力・収納サイズ・コスパを購入者が評価。",
        "related":["bonfire","tent"]},
    "bonfire":         {"slug":"bonfire","label":"焚き火台","emoji":"🔥",
        "kw":"焚き火台 おすすめ ソロ",
        "desc":"焚き火台の口コミ評価ランキング。組み立て・収納のしやすさを実際のキャンパーが評価した製品。",
        "related":["bbq_grill","camp_stove","camp_chair"]},
    "ski_board":       {"slug":"ski","label":"スキー板","emoji":"⛷️",
        "kw":"スキー板 おすすめ 初心者 中級者",
        "desc":"スキー板の口コミ評価ランキング。購入者から高評価を得たスキー板を紹介。",
        "related":["ski_boots","snowboard"]},
    "ski_boots":       {"slug":"ski-boots","label":"スキーブーツ","emoji":"⛷️",
        "kw":"スキーブーツ おすすめ",
        "desc":"スキーブーツの口コミ評価ランキング。フィット感・保温性を購入者が実際に評価した製品を比較。",
        "related":["ski_board","snowboard_boots"]},
    "snowboard":       {"slug":"snowboard","label":"スノーボード","emoji":"🏂",
        "kw":"スノーボード おすすめ 板",
        "desc":"スノーボードの口コミ評価ランキング。購入者が評価した板を紹介。",
        "related":["snowboard_boots","ski_board"]},
    "snowboard_boots": {"slug":"snowboard-boots","label":"スノーボードブーツ","emoji":"🏂",
        "kw":"スノーボード ブーツ おすすめ",
        "desc":"スノーボードブーツの口コミ評価ランキング。フィット感・フレックスを購入者が評価した製品を比較。",
        "related":["snowboard","ski_boots"]},
    "mattress":        {"slug":"mattress","label":"マットレス","emoji":"🛏️",
        "kw":"マットレス おすすめ 腰痛",
        "desc":"マットレスの口コミ評価ランキング。腰痛対策・高反発・低反発など、実際の購入者が評価した製品を紹介。",
        "related":["bed_frame","leg_mattress"]},
    "bed_frame":       {"slug":"bed-frame","label":"ベッドフレーム","emoji":"🛌",
        "kw":"ベッドフレーム おすすめ すのこ",
        "desc":"ベッドフレームの口コミ評価ランキング。すのこ・収納付き・フロアベッドなど購入者が評価した製品。",
        "related":["mattress","leg_mattress"]},
    "leg_mattress":    {"slug":"leg-mattress","label":"脚付きマットレス","emoji":"🛌",
        "kw":"脚付きマットレス おすすめ",
        "desc":"脚付きマットレスの口コミ評価ランキング。一人暮らしに人気の製品をコスパ・寝心地で比較。",
        "related":["mattress","bed_frame"]},
    "stroller":        {"slug":"stroller","label":"ベビーカー","emoji":"👶",
        "kw":"ベビーカー おすすめ 軽量",
        "desc":"ベビーカーの口コミ評価ランキング。実際のパパ・ママが評価した製品を紹介。",
        "related":["child_seat"]},
    "child_seat":      {"slug":"child-seat","label":"チャイルドシート","emoji":"🚗",
        "kw":"チャイルドシート おすすめ 新生児",
        "desc":"チャイルドシートの口コミ評価ランキング。安全性・使いやすさを購入者が評価した製品を比較。",
        "related":["stroller"]},
    "climbing_shoes":  {"slug":"climbing-shoes","label":"登山・クライミングシューズ","emoji":"🧗",
        "kw":"登山靴 クライミングシューズ おすすめ",
        "desc":"登山靴・クライミングシューズの口コミ評価ランキング。購入者が評価した一足。",
        "related":["tent","outdoor_bedding"]},
    "e_bike":          {"slug":"e-bike","label":"電動アシスト自転車","emoji":"🚲",
        "kw":"電動アシスト自転車 おすすめ",
        "desc":"電動アシスト自転車の口コミ評価ランキング。通勤・子乗せ・折りたたみなど購入者が評価した一台。",
        "related":["treadmill","fitness_bike"]},
}

# ── DB ──────────────────────────────────────────────────────
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

latest_date = conn.execute(
    "SELECT MAX(fetched_date) FROM item_rankings"
).fetchone()[0]

# ── クリーニング ─────────────────────────────────────────────
_PROMO_IN_BRACKET = re.compile(
    r'(?:\d+[倍%]|OFF|%引き?|限定|クーポン|ランキング|\d+位|まで|迄|'
    r'\d+円|セール|特価|送料|あす楽|無料|期間|先着|\bSALE\b|受注|予約|'
    r'今だけ|特典|割引|引き|相当|ポイント|P\d+|\bLINE\b|SNS|友達|'
    r'再入荷|入荷待ち|キャンペーン|楽天\d+位|楽天一位|'
    r'正規品|公式|全品|先行|お盆|夏休み|冬休み|春休み|リニューアル情報)',
    re.IGNORECASE
)

def _is_promo_bracket(content):
    if _PROMO_IN_BRACKET.search(content):
        return True
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

# ── 画像 ────────────────────────────────────────────────────
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

# ── データ取得 ──────────────────────────────────────────────
def load_genre(key):
    rows = conn.execute("""
        SELECT rank, item_code, item_name, item_price,
               review_count, review_average, item_url, affiliate_url,
               image_url, shop_name, item_caption
        FROM item_rankings
        WHERE genre_key=? AND fetched_date=?
        ORDER BY rank LIMIT 30
    """, (key, latest_date)).fetchall()
    items = [dict(r) for r in rows]
    for item in items:
        history = conn.execute("""
            SELECT fetched_date, rank, review_count, review_average
            FROM item_rankings WHERE genre_key=? AND item_code=?
            ORDER BY fetched_date
        """, (key, item["item_code"])).fetchall()
        hist = []
        for h in history:
            rc = h["review_count"] or 0; ra = h["review_average"] or 0
            hist.append({"d": h["fetched_date"], "r": h["rank"],
                         "s": round(math.log10(rc+1)*ra, 2)})
        item["history"] = hist
        old = conn.execute("""
            SELECT review_count FROM item_rankings
            WHERE genre_key=? AND item_code=? AND fetched_date <= date(?, '-7 days')
            ORDER BY fetched_date DESC LIMIT 1
        """, (key, item["item_code"], latest_date)).fetchone()
        if not old:
            old = conn.execute("""
                SELECT review_count FROM item_rankings
                WHERE genre_key=? AND item_code=?
                ORDER BY fetched_date ASC LIMIT 1
            """, (key, item["item_code"])).fetchone()
        item["delta_rc"] = max(0, (item["review_count"] or 0) - ((old["review_count"] if old else None) or 0))
    for item in items:
        rc = item["review_count"] or 0; ra = item["review_average"] or 0
        delta = item.get("delta_rc", 0) or 0
        item["community_score"] = math.log10(rc+1)*ra*(1+math.log10(delta+1))
        item["rakuten_rank"]    = item["rank"]
        item["item_name"]       = clean_name(item["item_name"])
        item["item_caption"]    = clean_caption(item.get("item_caption") or "")
        item["shop_name"]       = item.get("shop_name") or ""
    reviewed  = [i for i in items if i["review_count"] > 0]
    no_review = [i for i in items if i["review_count"] == 0]
    reviewed.sort(key=lambda i: i["community_score"], reverse=True)
    for idx, item in enumerate(reviewed): item["rank"] = idx + 1
    return reviewed + no_review

def prefetch_images(items, label):
    for i, item in enumerate(items):
        url = (item.get("image_url") or "").replace("_ex=64x64", "_ex=128x128")
        cached = url and (CACHE_DIR / hashlib.md5(url.encode()).hexdigest()).exists()
        item["img"] = fetch_datauri(item.get("image_url") or "")
        if not cached: time.sleep(0.12)
        print(f"  [{i+1}/{len(items)}] {'C' if cached else 'F'} {label} #{item['rakuten_rank']}", file=sys.stderr)

# ── チャート生成 ─────────────────────────────────────────────
CHART_COLORS = ["#2563EB","#16A34A","#DC2626","#D97706","#7C3AED",
                "#0891B2","#BE185D","#059669","#B45309","#4F46E5"]

def _fmt_price(p):
    if p >= 100000: return f"¥{p//10000}万"
    if p >= 10000:  return f"¥{p/10000:.1f}万"
    if p >= 1000:   return f"¥{p//1000}千"
    return f"¥{p}"

def render_bubble_chart(items):
    """価格 × 口コミスコア バブルチャート (SVG)"""
    scored = [i for i in items if i["review_count"] > 0 and i.get("item_price")]
    if len(scored) < 3: return ""

    W, H = 680, 320
    PT, PR, PB, PL = 24, 24, 48, 58
    iW, iH = W-PL-PR, H-PT-PB

    prices = [i["item_price"] for i in scored]
    scores = [i["community_score"] for i in scored]
    revs   = [i["review_count"] for i in scored]
    min_p, max_p = min(prices), max(prices)
    max_s = max(scores) * 1.12
    max_r = max(revs)
    p_range = max(max_p - min_p, 1)

    def cx(p): return PL + (p - min_p) / p_range * iW
    def cy(s): return H - PB - s / max_s * iH
    def cr(r): return max(6, min(26, math.sqrt(r / max_r) * 26))

    # grid
    lines = []
    for t in [0.25, 0.5, 0.75, 1.0]:
        y = cy(max_s * t); sv = f"{max_s*t:.1f}"
        lines.append(f'<line x1="{PL}" y1="{y:.1f}" x2="{W-PR}" y2="{y:.1f}" stroke="currentColor" opacity=".07" stroke-dasharray="4,3"/>')
        lines.append(f'<text x="{PL-6}" y="{y+3.5:.1f}" text-anchor="end" font-size="9" fill="currentColor" opacity=".35">{sv}</text>')
    for t in [0, 0.25, 0.5, 0.75, 1.0]:
        x = cx(min_p + p_range * t)
        lines.append(f'<text x="{x:.1f}" y="{H-PB+16:.1f}" text-anchor="middle" font-size="9" fill="currentColor" opacity=".35">{_fmt_price(min_p + p_range*t)}</text>')

    # quadrant labels (median split)
    med_p = sorted(prices)[len(prices)//2]; med_s = sorted(scores)[len(scores)//2]
    qx_l = cx(min_p + (med_p-min_p)*0.45); qx_r = cx(med_p + (max_p-med_p)*0.55)
    qy_t = cy(med_s + (max_s-med_s)*0.55); qy_b = cy(med_s*0.45)
    quads = [
        (qx_l, qy_t, "コスパ優秀"), (qx_r, qy_t, "プレミアム"),
        (qx_l, qy_b, "要検討"),     (qx_r, qy_b, "高価格低評価"),
    ]
    qlabels = "".join(
        f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="middle" font-size="10" fill="currentColor" opacity=".12" font-weight="700">{lbl}</text>'
        for x, y, lbl in quads
    )

    # bubbles (draw small→large for z-order)
    order = sorted(scored, key=lambda i: i["review_count"])
    bubbles = []
    for i, item in enumerate(order):
        x = cx(item["item_price"]); y = cy(item["community_score"]); r = cr(item["review_count"])
        c = CHART_COLORS[item["rank"] % len(CHART_COLORS)]
        esc = item["item_name"].replace('"', '&quot;').replace('<', '&lt;')
        bubbles.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{c}" opacity=".72" '
            f'class="bc" data-n="{esc[:28]}" data-p="¥{item["item_price"]:,}" '
            f'data-s="{item["community_score"]:.1f}" data-r="{item["rank"]}" '
            f'data-c="{item["review_count"]:,}"/>'
        )

    # rank labels for top 3
    rlabels = []
    for item in scored[:3]:
        x = cx(item["item_price"]); y = cy(item["community_score"]); r = cr(item["review_count"])
        rlabels.append(f'<text x="{x:.1f}" y="{y-r-5:.1f}" text-anchor="middle" font-size="10" font-weight="700" fill="currentColor" opacity=".6">{item["rank"]}位</text>')

    axis = (f'<text x="{W/2:.0f}" y="{H-1}" text-anchor="middle" font-size="11" fill="currentColor" opacity=".4">価格</text>'
            f'<text x="12" y="{H/2:.0f}" text-anchor="middle" font-size="11" fill="currentColor" opacity=".4" transform="rotate(-90,12,{H/2:.0f})">口コミスコア</text>')

    return (f'<svg id="chart-bubble" viewBox="0 0 {W} {H}" width="100%" preserveAspectRatio="xMidYMid meet" class="cr-chart">'
            + "".join(lines) + qlabels + "".join(bubbles) + "".join(rlabels) + axis + "</svg>")


def render_ts_chart(items):
    """スコア推移 折れ線グラフ (SVG)"""
    top5 = [i for i in items if i["review_count"] > 0 and len(i.get("history", [])) >= 2][:5]
    if not top5: return ""
    all_dates = sorted(set(h["d"] for i in top5 for h in i["history"]))
    if len(all_dates) < 2: return ""

    W, H = 680, 260
    PT, PR, PB, PL = 16, 16, 36, 48
    iW, iH = W-PL-PR, H-PT-PB

    all_s = [h["s"] for i in top5 for h in i["history"]]
    max_s = max(all_s) * 1.1 or 1; min_s = min(all_s) * 0.9
    s_range = max_s - min_s or 1
    n = len(all_dates)

    def px(i): return PL + i / (n-1) * iW
    def py(s): return H - PB - (s - min_s) / s_range * iH

    grid = []
    for t in [0.25, 0.5, 0.75, 1.0]:
        s = min_s + s_range * t; y = py(s)
        grid.append(f'<line x1="{PL}" y1="{y:.1f}" x2="{W-PR}" y2="{y:.1f}" stroke="currentColor" opacity=".07" stroke-dasharray="4,3"/>')
        grid.append(f'<text x="{PL-6}" y="{y+3:.1f}" text-anchor="end" font-size="9" fill="currentColor" opacity=".35">{s:.1f}</text>')

    show_dates = [all_dates[0]] + [d for d in all_dates[1:-1] if all_dates.index(d) % max(1, n//5) == 0] + [all_dates[-1]]
    for d in show_dates:
        i = all_dates.index(d); x = px(i)
        grid.append(f'<text x="{x:.1f}" y="{H-PB+14:.1f}" text-anchor="middle" font-size="9" fill="currentColor" opacity=".35">{d[5:]}</text>')

    series = []
    legend = []
    for ci, item in enumerate(top5):
        c = CHART_COLORS[ci]
        smap = {h["d"]: h["s"] for h in item["history"]}
        pts  = [(px(i), py(smap[d])) for i, d in enumerate(all_dates) if d in smap]
        if len(pts) < 2: continue
        poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        # area fill
        area = f"M {pts[0][0]:.1f} {H-PB} " + " ".join(f"L {x:.1f} {y:.1f}" for x, y in pts) + f" L {pts[-1][0]:.1f} {H-PB} Z"
        series.append(f'<path d="{area}" fill="{c}" opacity=".08"/>')
        series.append(f'<polyline points="{poly}" fill="none" stroke="{c}" stroke-width="2" stroke-linejoin="round" opacity=".9"/>')
        lx, ly = pts[-1]
        series.append(f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="4" fill="{c}"/>')
        name = item["item_name"][:18] + ("…" if len(item["item_name"]) > 18 else "")
        legend.append(f'<div class="ts-leg-item"><span style="background:{c}" class="ts-dot"></span><span>{name}</span></div>')

    return (f'<svg id="chart-ts" viewBox="0 0 {W} {H}" width="100%" preserveAspectRatio="xMidYMid meet" class="cr-chart">'
            + "".join(grid) + "".join(series) + "</svg>"
            + f'<div class="ts-legend">{"".join(legend)}</div>')


# ── 時系列分析 ─────────────────────────────────────────────────

def get_genre_dates(key):
    rows = conn.execute("""
        SELECT DISTINCT fetched_date FROM item_rankings
        WHERE genre_key=? ORDER BY fetched_date
    """, (key,)).fetchall()
    return [r[0] for r in rows]


def get_rank_matrix(key, codes, dates):
    if not codes: return {}
    ph = ",".join("?" * len(codes))
    rows = conn.execute(f"""
        SELECT item_code, fetched_date, rank FROM item_rankings
        WHERE genre_key=? AND item_code IN ({ph})
    """, (key, *codes)).fetchall()
    matrix = {c: {} for c in codes}
    for r in rows:
        matrix[r[0]][r[1]] = r[2]
    return matrix


def compute_trends(key, scored):
    result = []
    for item in scored:
        hist = item.get("history", [])
        n = len(hist)
        ref_rank  = hist[max(0, n - 7)]["r"] if n >= 2 else item["rank"]
        ref_score = hist[max(0, n - 7)]["s"] if n >= 2 else item["community_score"]
        result.append({
            **item,
            "rank_change":  ref_rank - item["rank"],
            "score_change": round(item["community_score"] - ref_score, 2),
            "first_date":   hist[0]["d"] if hist else (latest_date or ""),
            "top3_days":    sum(1 for h in hist if h["r"] <= 3),
            "days_tracked": n,
        })
    return result


def render_hero_ts(scored, trends_data):
    """Hero section time-series chart with 📈👑🆕 badge annotations on line endpoints."""
    top5 = [i for i in scored if len(i.get("history", [])) >= 2][:5]
    if len(top5) < 2: return "", {}, {}
    all_dates = sorted(set(h["d"] for i in top5 for h in i["history"]))
    if len(all_dates) < 2: return "", {}, {}

    color_map = {item["item_code"]: CHART_COLORS[ci] for ci, item in enumerate(top5)}

    # Assign trend badges to chart items
    badge_map = {}
    assigned  = set()
    rising    = sorted([t for t in trends_data if t["rank_change"] > 0],
                       key=lambda t: t["rank_change"], reverse=True)
    newcomers = ([t for t in sorted(trends_data, key=lambda t: t["first_date"], reverse=True)
                  if t["days_tracked"] <= 7]
                 or sorted(trends_data, key=lambda t: t["first_date"], reverse=True))
    stable    = sorted([t for t in trends_data if t["top3_days"] > 0],
                       key=lambda t: t["top3_days"], reverse=True)

    def assign(candidates, badge):
        for t in candidates:
            if t["item_code"] not in assigned and t["item_code"] in color_map:
                badge_map[t["item_code"]] = badge
                assigned.add(t["item_code"])
                return
    assign(rising,    "📈")
    assign(stable,    "👑")
    assign(newcomers, "🆕")

    W, H = 760, 200
    PT, PR, PB, PL = 12, 180, 32, 50
    iW, iH = W - PL - PR, H - PT - PB
    n = len(all_dates)

    all_s = [h["s"] for i in top5 for h in i["history"]]
    max_s = max(all_s) * 1.12 or 1
    min_s = min(all_s) * 0.9
    s_rng = max_s - min_s or 1

    def px(i): return PL + i / (n - 1) * iW if n > 1 else PL + iW / 2
    def py(s): return H - PB - (s - min_s) / s_rng * iH

    parts = []
    # grid
    for t in [0.25, 0.5, 0.75, 1.0]:
        s = min_s + s_rng * t; y = py(s)
        parts.append(f'<line x1="{PL}" y1="{y:.1f}" x2="{W-PR}" y2="{y:.1f}" stroke="currentColor" opacity=".07" stroke-dasharray="3,4"/>')
        parts.append(f'<text x="{PL-5}" y="{y+3:.1f}" text-anchor="end" font-size="9" fill="currentColor" opacity=".28">{s:.1f}</text>')
    # date labels
    show_idx = sorted({0, n - 1} | ({n // 2} if n > 4 else set()))
    for di in show_idx:
        if 0 <= di < n:
            parts.append(f'<text x="{px(di):.1f}" y="{H-PB+12:.1f}" text-anchor="middle" font-size="9" fill="currentColor" opacity=".28">{all_dates[di][5:]}</text>')

    # series
    raw_labels = []
    for ci, item in enumerate(top5):
        c    = color_map[item["item_code"]]
        smap = {h["d"]: h["s"] for h in item["history"]}
        pts  = [(px(i), py(smap[d])) for i, d in enumerate(all_dates) if d in smap]
        if len(pts) < 2: continue
        poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        area = (f"M {pts[0][0]:.1f} {H-PB} "
                + " ".join(f"L {x:.1f} {y:.1f}" for x, y in pts)
                + f" L {pts[-1][0]:.1f} {H-PB} Z")
        parts.append(f'<path d="{area}" fill="{c}" opacity=".07"/>')
        badge = badge_map.get(item["item_code"], "")
        sw = "3" if badge else "2"
        parts.append(f'<polyline points="{poly}" fill="none" stroke="{c}" stroke-width="{sw}" stroke-linejoin="round" opacity=".88"/>')
        lx, ly = pts[-1]
        r = "5.5" if badge else "4"
        parts.append(f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="{r}" fill="{c}"/>')
        if badge:
            parts.append(f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="10" fill="{c}" opacity=".18"/>')
        raw_labels.append((ly, c, badge, item["item_name"]))

    # right-side labels with collision avoidance
    raw_labels.sort(key=lambda x: x[0])
    used_ys = []
    for ly, c, badge, name in raw_labels:
        ay = float(ly)
        for uy in used_ys:
            if abs(ay - uy) < 15: ay = uy + 15
        used_ys.append(ay)
        lx  = W - PR + 8
        nm  = name[:14] + ("…" if len(name) > 14 else "")
        bdg = (badge + " ") if badge else ""
        fw  = "700" if badge else "400"
        parts.append(f'<circle cx="{lx-4}" cy="{ay:.1f}" r="3" fill="{c}"/>')
        parts.append(f'<text x="{lx+4}" y="{ay+3.5:.1f}" font-size="10" font-weight="{fw}" fill="currentColor" opacity=".75">{bdg}{nm}</text>')

    svg = f'<svg viewBox="0 0 {W} {H}" width="100%" class="hero-chart">' + "".join(parts) + "</svg>"
    return svg, color_map, badge_map


def render_trend_dashboard(trends, color_map=None):
    rising    = sorted([t for t in trends if t["rank_change"] > 0],
                       key=lambda t: t["rank_change"], reverse=True)[:3]
    newcomers = sorted(trends, key=lambda t: t["first_date"], reverse=True)
    newcomers = [t for t in newcomers if t["days_tracked"] <= 7][:3] or newcomers[:3]
    stable    = sorted([t for t in trends if t["top3_days"] > 0],
                       key=lambda t: (t["top3_days"], -t["rank"]), reverse=True)[:3]

    cm = color_map or {}

    def mini_card(item, extra):
        img = (f'<img src="{item["img"]}" alt="" style="width:40px;height:40px;object-fit:cover;border-radius:6px;flex-shrink:0">'
               if item.get("img") else
               f'<div style="width:40px;height:40px;display:flex;align-items:center;justify-content:center;font-size:22px;background:var(--bg);border-radius:6px;flex-shrink:0">📦</div>')
        nm = item["item_name"][:22] + ("…" if len(item["item_name"]) > 22 else "")
        cc = cm.get(item["item_code"], "")
        dot = (f'<span class="td-chart-dot" style="background:{cc}" title="チャートに表示"></span>' if cc else "")
        return (f'<a class="td-card" href="{item["affiliate_url"] or item["item_url"]}" '
                f'target="_blank" rel="noopener sponsored">{dot}{img}'
                f'<div class="td-info"><div class="td-name">{nm}</div>{extra}</div></a>')

    def panel(icon, title, items_list, extra_fn):
        if not items_list:
            return f'<div class="td-panel"><div class="td-ptitle">{icon} {title}</div><p class="td-empty">データ収集中...</p></div>'
        return (f'<div class="td-panel"><div class="td-ptitle">{icon} {title}</div>'
                + "".join(mini_card(it, extra_fn(it)) for it in items_list) + '</div>')

    p1 = panel("📈", "急上昇中", rising,
               lambda t: f'<div class="td-stat up">ランク +{t["rank_change"]} → 現在{t["rank"]}位</div>')
    p2 = panel("🆕", "今週の新顔", newcomers,
               lambda t: f'<div class="td-stat">初登場 {t["first_date"]} &nbsp; {t["rank"]}位</div>')
    p3 = panel("👑", "安定王者", stable,
               lambda t: f'<div class="td-stat">{t["top3_days"]}日間 TOP3 → {t["rank"]}位</div>')

    return (f'<div class="trend-sec"><div class="trend-in">'
            f'<div class="trend-hd">今週この市場で何が起きているか</div>'
            f'<div class="trend-grid">{p1}{p2}{p3}</div></div></div>')


def render_heatmap(key, scored):
    top_items = scored[:12]
    dates = get_genre_dates(key)
    if len(dates) < 2 or len(top_items) < 3: return ""
    codes  = [i["item_code"] for i in top_items]
    matrix = get_rank_matrix(key, codes, dates)

    CW, CH, LW, DH = 30, 26, 136, 38
    W = LW + len(dates) * CW + 14
    H = DH + len(top_items) * CH + 6

    def color(r):
        if r is None: return "var(--bdr)"
        return f"rgba(37,99,235,{0.12 + (1 - (r-1)/29.0) * 0.82:.2f})"

    parts = []
    for di, d in enumerate(dates):
        x = LW + di * CW + CW // 2
        parts.append(f'<text x="{x}" y="{DH-5}" text-anchor="middle" '
                     f'font-size="9" fill="currentColor" opacity=".38"'
                     f' transform="rotate(-45,{x},{DH-5})">{d[5:]}</text>')
    for ri, item in enumerate(top_items):
        y  = DH + ri * CH
        nm = item["item_name"][:13] + ("…" if len(item["item_name"]) > 13 else "")
        parts.append(f'<text x="{LW-5}" y="{y+CH//2+4}" text-anchor="end" '
                     f'font-size="10" fill="currentColor" opacity=".65">{nm}</text>')
        for di, d in enumerate(dates):
            rk   = matrix.get(item["item_code"], {}).get(d)
            col  = color(rk)
            cx2  = LW + di * CW
            parts.append(f'<rect x="{cx2+1}" y="{y+1}" width="{CW-2}" height="{CH-2}" fill="{col}" rx="2"/>')
            if rk:
                parts.append(f'<text x="{cx2+CW//2}" y="{y+CH//2+4}" text-anchor="middle" '
                              f'font-size="9" font-weight="700" fill="white" opacity=".9">{rk}</text>')

    return (f'<div style="overflow-x:auto"><svg viewBox="0 0 {W} {H}" '
            f'width="{W}" height="{H}" class="cr-chart" style="min-width:{min(W,320)}px">'
            + "".join(parts) + "</svg></div>")


def render_velocity_bar(scored):
    by_vel = sorted([i for i in scored if (i.get("delta_rc") or 0) > 0],
                    key=lambda i: i["delta_rc"], reverse=True)[:8]
    if not by_vel: return ""
    max_d = max(i["delta_rc"] for i in by_vel) or 1
    BH, GAP, LW2, BMAX = 26, 8, 128, 340
    W2 = LW2 + BMAX + 80
    H2 = len(by_vel) * (BH + GAP)
    parts = []
    for i, item in enumerate(by_vel):
        y  = i * (BH + GAP)
        bw = max(4, item["delta_rc"] / max_d * BMAX)
        nm = item["item_name"][:15] + ("…" if len(item["item_name"]) > 15 else "")
        parts.append(f'<text x="{LW2-28}" y="{y+BH//2+4}" text-anchor="end" '
                     f'font-size="9" fill="var(--acc)" opacity=".7" font-family="monospace">{item["rank"]}位</text>')
        parts.append(f'<text x="{LW2-5}" y="{y+BH//2+4}" text-anchor="end" '
                     f'font-size="10" fill="currentColor" opacity=".65">{nm}</text>')
        parts.append(f'<rect x="{LW2}" y="{y+2}" width="{bw:.1f}" height="{BH-4}" '
                     f'fill="var(--acc)" opacity=".72" rx="3"/>')
        parts.append(f'<text x="{LW2+bw+7}" y="{y+BH//2+4}" '
                     f'font-size="10" font-weight="700" fill="currentColor" opacity=".55">+{item["delta_rc"]:,}件</text>')
    return (f'<svg viewBox="0 0 {W2} {H2}" width="100%" class="cr-chart" style="min-width:280px">'
            + "".join(parts) + "</svg>")


def render_animation(key, scored):
    candidates = [i for i in scored if i.get("item_price") and i["review_count"] > 0]
    if len(candidates) < 3: return "", ""
    all_dates = get_genre_dates(key)
    if len(all_dates) < 2: return "", ""

    codes = [i["item_code"] for i in candidates]
    ph = ",".join("?" * len(codes))
    rows = conn.execute(f"""
        SELECT item_code, fetched_date, review_count, review_average, item_price
        FROM item_rankings WHERE genre_key=? AND item_code IN ({ph}) ORDER BY fetched_date
    """, (key, *codes)).fetchall()

    score_map = {c: {} for c in codes}
    for r in rows:
        rc = r[2] or 0; ra = r[3] or 0
        score_map[r[0]][r[1]] = {"rc": rc, "ra": ra,
                                  "s": round(math.log10(rc + 1) * ra, 2), "p": r[4] or 0}

    names   = {i["item_code"]: i["item_name"][:18] for i in candidates}
    cmap    = {i["item_code"]: CHART_COLORS[idx % len(CHART_COLORS)]
               for idx, i in enumerate(candidates)}
    frames  = []
    for d in all_dates:
        frame = [{"c": code, "p": sd["p"], "s": sd["s"], "rc": sd["rc"], "n": names[code]}
                 for code in codes if (sd := score_map[code].get(d)) and sd["p"] > 0]
        frames.append({"d": d, "items": frame})

    fj = json.dumps(frames,  ensure_ascii=False, separators=(",", ":"))
    cj = json.dumps(cmap,    ensure_ascii=False, separators=(",", ":"))

    ctrl = (
        '<div class="anim-ctrl">'
        '<button class="anim-btn" id="anim-play" onclick="animToggle()">▶ 再生</button>'
        f'<input type="range" id="anim-slider" min="0" max="{len(all_dates)-1}" value="0" '
        'style="flex:1;min-width:80px" oninput="animGoto(+this.value)">'
        f'<span class="anim-date" id="anim-date">{all_dates[0]}</span>'
        '</div>'
        '<svg id="anim-svg" viewBox="0 0 680 300" width="100%" class="cr-chart"></svg>'
        '<div id="anim-leg" class="ts-legend" style="margin-top:10px"></div>'
    )

    js = (
        "(function(){"
        f"var F={fj},CM={cj};"
        "var svg=document.getElementById('anim-svg');if(!svg)return;"
        "var NS='http://www.w3.org/2000/svg';"
        "var W=680,H=300,PL=58,PR=24,PT=18,PB=44,iW=W-PL-PR,iH=H-PT-PB;"
        "var aP=F.flatMap(function(f){return f.items.map(function(i){return i.p})});"
        "var aS=F.flatMap(function(f){return f.items.map(function(i){return i.s})});"
        "var aR=F.flatMap(function(f){return f.items.map(function(i){return i.rc})});"
        "if(!aP.length)return;"
        "var mnP=Math.min.apply(null,aP),mxP=Math.max.apply(null,aP);"
        "var mxS=Math.max.apply(null,aS)*1.12||1,mxR=Math.max.apply(null,aR)||1;"
        "function cx(p){return PL+(p-mnP)/(mxP-mnP||1)*iW}"
        "function cy(s){return H-PB-s/mxS*iH}"
        "function cr(r){return Math.max(7,Math.min(28,Math.sqrt(r/mxR)*28))}"
        "function fP(p){return p>=10000?'¥'+Math.round(p/1000)/10+'万':'¥'+p.toLocaleString('ja-JP')}"
        "function el(t,a){var e=document.createElementNS(NS,t);for(var k in a)e.setAttribute(k,a[k]);return e}"
        "function tx(t,a,s){var e=el(t,a);e.textContent=s;return e}"
        "var gG=el('g',{});svg.appendChild(gG);"
        "[.25,.5,.75,1].forEach(function(t){"
        "var y=cy(mxS*t);"
        "gG.appendChild(el('line',{x1:PL,y1:y,x2:W-PR,y2:y,stroke:'currentColor',opacity:.07,'stroke-dasharray':'4,3'}));"
        "gG.appendChild(tx('text',{x:PL-5,y:y+3,'text-anchor':'end','font-size':9,fill:'currentColor',opacity:.35},(mxS*t).toFixed(1)));"
        "});"
        "[0,.25,.5,.75,1].forEach(function(t){"
        "var p=mnP+(mxP-mnP)*t,x=cx(p);"
        "gG.appendChild(tx('text',{x:x,y:H-PB+14,'text-anchor':'middle','font-size':9,fill:'currentColor',opacity:.35},fP(p)));"
        "});"
        "gG.appendChild(tx('text',{x:W/2,y:H,'text-anchor':'middle','font-size':11,fill:'currentColor',opacity:.4},'価格'));"
        "gG.appendChild(tx('text',{x:12,y:H/2,'text-anchor':'middle','font-size':11,fill:'currentColor',opacity:.4,transform:'rotate(-90,12,'+(H/2)+')'},'口コミスコア'));"
        "var codes=[],seen={};"
        "F.forEach(function(f){f.items.forEach(function(i){if(!seen[i.c]){seen[i.c]=1;codes.push(i.c)}})});"
        "var gB=el('g',{});svg.appendChild(gB);"
        "var bubbles={};"
        "codes.forEach(function(c){"
        "var b=el('circle',{r:7,fill:CM[c]||'#2563EB',opacity:.75});"
        "b.style.transition='cx .6s ease,cy .6s ease,r .6s ease';"
        "gB.appendChild(b);bubbles[c]=b;"
        "});"
        "var leg=document.getElementById('anim-leg');"
        "if(leg)leg.innerHTML=codes.slice(0,10).map(function(c){"
        "var nm=F.flatMap(function(f){return f.items}).find(function(i){return i.c===c});"
        "return '<div class=\"ts-leg-item\"><span class=\"ts-dot\" style=\"background:'+(CM[c]||'#2563EB')+'\"></span><span>'+(nm?nm.n:c)+'</span></div>';"
        "}).join('');"
        "var cur=0,playing=false,timer=null;"
        "function drawFrame(n){"
        "var frame=F[n];if(!frame)return;"
        "var present={};"
        "frame.items.forEach(function(item){"
        "present[item.c]=1;"
        "var b=bubbles[item.c];if(!b)return;"
        "b.setAttribute('cx',cx(item.p).toFixed(1));"
        "b.setAttribute('cy',cy(item.s).toFixed(1));"
        "b.setAttribute('r',cr(item.rc).toFixed(1));"
        "b.style.display='';"
        "});"
        "codes.forEach(function(c){if(!present[c]&&bubbles[c])bubbles[c].style.display='none'});"
        "var dEl=document.getElementById('anim-date');if(dEl)dEl.textContent=frame.d;"
        "var sl=document.getElementById('anim-slider');if(sl)sl.value=n;"
        "cur=n;"
        "}"
        "window.animToggle=function(){"
        "var btn=document.getElementById('anim-play');"
        "if(playing){clearInterval(timer);playing=false;if(btn)btn.textContent='▶ 再生';}"
        "else{if(cur>=F.length-1)cur=0;playing=true;if(btn)btn.textContent='⏸ 停止';"
        "timer=setInterval(function(){cur++;if(cur>=F.length){clearInterval(timer);playing=false;if(btn)btn.textContent='▶ 再生';return;}drawFrame(cur);},900);"
        "}"
        "};"
        "window.animGoto=function(n){"
        "if(playing){clearInterval(timer);playing=false;var btn=document.getElementById('anim-play');if(btn)btn.textContent='▶ 再生';}"
        "drawFrame(n);"
        "};"
        "drawFrame(0);"
        "})();"
    )
    return ctrl, js


# ── バッジ ──────────────────────────────────────────────────
HOT_THRESHOLD = 30   # 7日間 delta_rc がこれ以上 = 急上昇

def badges(item):
    out = []
    if item.get("delta_rc", 0) >= HOT_THRESHOLD:
        out.append('<span class="badge-hot">🔥 急上昇</span>')
    return "".join(out)

# ── カードレンダリング ────────────────────────────────────────
def _stars_html(avg, cnt, cls="", code=""):
    pct = f"{avg/5*100:.1f}"
    c = code
    ra_a = f' data-live-ra="{c}"' if c else ""
    rc_a = f' data-live-rc="{c}"' if c else ""
    sf_a = f' data-live-sf="{c}"' if c else ""
    return (f'<div class="stars-row{" "+cls if cls else ""}">'
            f'<span class="sw"><span class="sb">★★★★★</span>'
            f'<span class="sf"{sf_a} style="width:{pct}%">★★★★★</span></span>'
            f'<span class="sn"{ra_a}>{avg:.2f}</span>'
            f'<span class="sc"{rc_a}>{cnt:,}件</span></div>')

def _spark(history):
    if not history or len(history) < 7: return ""
    ranks = [h["r"] for h in history]
    W, H = 100, 18
    mn, mx = min(ranks), max(ranks); rng = mx-mn or 1
    pts = " ".join(f"{i/(len(ranks)-1)*W:.1f},{(r-mn)/rng*H:.1f}" for i, r in enumerate(ranks))
    return (f'<div class="spark"><svg viewBox="0 0 {W} {H}" preserveAspectRatio="none">'
            f'<polyline points="{pts}" fill="none" stroke="rgba(255,255,255,.85)" stroke-width="1.5" stroke-linejoin="round"/>'
            f'</svg></div>')

def _rk(item):
    diff = item["rakuten_rank"] - item["rank"]
    if diff > 0:   return f'楽天{item["rakuten_rank"]}位→<span class="up">↑{diff}</span>'
    elif diff < 0: return f'楽天{item["rakuten_rank"]}位→<span class="dn">↓{abs(diff)}</span>'
    else:          return f'楽天{item["rakuten_rank"]}位（同順）'

def render_podium(item, rank_label, emoji):
    img = (f'<img src="{item["img"]}" alt="" loading="eager">'
           if item.get("img") else f'<div class="pfallback">{emoji}</div>')
    nc  = {1:"pn1",2:"pn2",3:"pn3"}.get(item["rank"],"")
    num = f'<div class="pnum {nc}">{rank_label}</div>'
    stars = _stars_html(item["review_average"], item["review_count"], code=item["item_code"]) if item["review_count"] > 0 else ""
    desc  = f'<p class="pdesc">{item["item_caption"]}</p>' if item.get("item_caption") else ""
    shop  = f'<p class="pshop">🏪 {item["shop_name"]}</p>' if item.get("shop_name") else ""
    rk    = f'<span class="prk">{_rk(item)}</span>' if item["review_count"] > 0 else ""
    price = f'¥{item["item_price"]:,}' if item.get("item_price") else ""
    bdg   = badges(item)
    return f"""<a class="pcard{'  p1' if item['rank']==1 else ''}"
   href="{item['affiliate_url'] or item['item_url']}" target="_blank" rel="noopener sponsored"
   data-code="{item['item_code']}">
  <div class="pimg">{img}{num}{_spark(item["history"])}</div>
  <div class="pbody">
    <p class="pname">{item['item_name']}</p>
    {bdg}{stars}{desc}{shop}
    <div class="pfoot">
      <span class="pprice" data-live="{item['item_code']}">{price}</span>
      {rk}
    </div>
  </div>
</a>"""

def render_card(item, emoji):
    img   = (f'<img src="{item["img"]}" alt="" loading="lazy">'
             if item.get("img") else f'<div class="cfallback">{emoji}</div>')
    num   = f'<div class="cnum">{item["rank"]}位</div>' if item["review_count"] > 0 else ""
    stars = (_stars_html(item["review_average"], item["review_count"], "sm", item["item_code"])
             if item["review_count"] > 0 else '<span class="no-rev">レビューなし</span>')
    desc  = f'<p class="cdesc">{item["item_caption"]}</p>' if item.get("item_caption") else ""
    shop  = f'<p class="cshop">🏪 {item["shop_name"]}</p>' if item.get("shop_name") else ""
    rk    = f'<span class="crk">{_rk(item)}</span>' if item["review_count"] > 0 else ""
    price = f'¥{item["item_price"]:,}' if item.get("item_price") else ""
    bdg   = badges(item)
    return f"""<a class="card{'  no-data' if not item['review_count'] else ''}"
   href="{item['affiliate_url'] or item['item_url']}" target="_blank" rel="noopener sponsored">
  <div class="cimg">{img}{num}{_spark(item["history"])}</div>
  <div class="cbody">
    <p class="cname">{item['item_name']}</p>
    {bdg}{stars}{desc}{shop}
    <div class="cfoot">
      <span class="cprice" data-live="{item['item_code']}">{price}</span>
      {rk}
    </div>
  </div>
</a>"""

# ── CSS ─────────────────────────────────────────────────────
CSS = """
:root {
  --bg:#F4F6FB; --sur:#FFF; --ink:#0F172A; --ink2:#475569; --ink3:#94A3B8;
  --acc:#2563EB; --bdr:#E2E8F0; --gold:#F59E0B; --up:#16A34A; --dn:#DC2626;
  --shd:0 1px 3px rgba(0,0,0,.07),0 4px 16px rgba(0,0,0,.05);
  --r:10px; --sans:-apple-system,'Hiragino Kaku Gothic ProN','Hiragino Sans',sans-serif;
  --mono:'SF Mono',Consolas,monospace;
}
@media(prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#0B1120;--sur:#111827;--ink:#F1F5F9;--ink2:#94A3B8;--ink3:#475569;
  --acc:#60A5FA;--bdr:#1E293B;--gold:#FCD34D;--up:#4ADE80;--dn:#F87171;
  --shd:0 1px 3px rgba(0,0,0,.3),0 4px 16px rgba(0,0,0,.25);
}}
:root[data-theme="dark"]{
  --bg:#0B1120;--sur:#111827;--ink:#F1F5F9;--ink2:#94A3B8;--ink3:#475569;
  --acc:#60A5FA;--bdr:#1E293B;--gold:#FCD34D;--up:#4ADE80;--dn:#F87171;
  --shd:0 1px 3px rgba(0,0,0,.3),0 4px 16px rgba(0,0,0,.25);
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--ink);font-family:var(--sans);font-size:15px;line-height:1.6;min-height:100vh}
a{color:inherit;text-decoration:none} img{display:block;max-width:100%}
button{cursor:pointer;border:none;background:none;font:inherit;color:inherit}

/* NAV */
.nav{background:var(--sur);border-bottom:1px solid var(--bdr);position:sticky;top:0;z-index:100}
.nav-in{max-width:1080px;margin:0 auto;padding:0 20px;height:52px;display:flex;align-items:center;gap:12px}
.nav-logo{font-size:16px;font-weight:900;letter-spacing:-.03em;color:var(--acc)}
.nav-logo span{color:var(--ink2);font-weight:400;font-size:12px;margin-left:4px}
.nav-sep{width:1px;height:16px;background:var(--bdr);flex-shrink:0}
.nav-genre{font-size:13px;font-weight:700;color:var(--ink2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.nav-date{margin-left:auto;font-family:var(--mono);font-size:11px;color:var(--ink3);white-space:nowrap}
.nav-live{display:inline-flex;align-items:center;gap:4px;font-size:10px;font-weight:700;
  color:var(--acc);font-family:var(--mono);margin-left:6px}
.nav-live::before{content:'';width:6px;height:6px;border-radius:50%;background:var(--acc);
  animation:pulse 1.8s ease-in-out infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}

/* BREADCRUMB */
.bc{max-width:1080px;margin:0 auto;padding:12px 20px 0;font-size:12px;color:var(--ink3);display:flex;gap:6px}
.bc a{color:var(--acc)}.bc-sep{opacity:.4}

/* HERO */
.hero{background:var(--sur);border-bottom:1px solid var(--bdr);padding:40px 20px 36px}
.hero-in{max-width:1080px;margin:0 auto}
.eyebrow{font-size:11px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--acc);margin-bottom:10px}
.h1{font-size:32px;font-weight:900;letter-spacing:-.04em;line-height:1.15;margin-bottom:8px}
.h1 em{font-style:normal;color:var(--acc)}
.hero-sub{font-size:14px;color:var(--ink2);max-width:560px;line-height:1.7}
.hero-badges{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}
.hbadge{display:inline-flex;align-items:center;gap:5px;font-size:11px;font-weight:600;
  padding:4px 10px;border-radius:99px;border:1px solid var(--bdr);color:var(--ink2);background:var(--bg)}
.hbadge.a{border-color:var(--acc);color:var(--acc);background:rgba(37,99,235,.07)}
.hbadge.m{font-family:var(--mono)}

/* FORMULA BAND */
.fband{background:linear-gradient(135deg,rgba(37,99,235,.07),rgba(37,99,235,.02));
  border:1px solid rgba(37,99,235,.18);border-radius:var(--r);
  padding:14px 18px;margin-top:22px;display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.fform{font-family:var(--mono);font-size:13px;color:var(--acc);font-weight:700;white-space:nowrap}
.fdesc{font-size:12px;color:var(--ink2);line-height:1.5}

/* CHART SECTION */
.chart-sec{max-width:1080px;margin:32px auto 0;padding:0 20px}
.chart-hdr{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;flex-wrap:wrap;gap:8px}
.chart-ttl{font-size:14px;font-weight:700;color:var(--ink2)}
.chart-note{font-size:11px;color:var(--ink3);font-family:var(--mono)}
.chart-sub{font-size:11px;color:var(--ink3);font-family:var(--mono);margin-bottom:10px;padding:6px 10px;background:var(--bg);border-radius:6px;display:inline-block}
.chart-tabs{display:flex;gap:4px}
.ctab{padding:5px 14px;border-radius:99px;font-size:12px;font-weight:600;
  border:1px solid var(--bdr);color:var(--ink3);cursor:pointer;transition:all .12s}
.ctab.on{border-color:var(--acc);color:var(--acc);background:rgba(37,99,235,.08)}
.chart-box{background:var(--bg);border:1px solid var(--bdr);border-radius:var(--r);
  padding:18px;overflow-x:auto;position:relative}
.cr-chart{display:block;min-width:300px}
.bc{cursor:pointer;transition:opacity .1s,r .1s}
.bc:hover{opacity:1 !important}
.ts-legend{display:flex;flex-wrap:wrap;gap:10px;margin-top:10px}
.ts-leg-item{display:flex;align-items:center;gap:5px;font-size:11px;color:var(--ink2)}
.ts-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}

/* BUBBLE TOOLTIP */
#btip{position:fixed;pointer-events:none;display:none;z-index:999;
  background:var(--sur);border:1px solid var(--bdr);border-radius:10px;
  padding:10px 14px;font-size:12px;box-shadow:var(--shd);max-width:220px;line-height:1.6}

/* BEST3 SECTION */
.best3-sec{max-width:1080px;margin:28px auto 0;padding:0 20px}
.best3-hd{font-size:13px;font-weight:700;color:var(--ink2);letter-spacing:.05em;
  text-transform:uppercase;display:flex;align-items:center;gap:10px;margin-bottom:14px}
.best3-hd::after{content:'';flex:1;height:1px;background:var(--bdr)}
.best3-hd .live-tag{font-size:9px;font-weight:700;color:var(--acc);font-family:var(--mono);
  border:1px solid var(--acc);border-radius:3px;padding:0 4px;letter-spacing:.05em}

/* PODIUM */
.podium{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px}
@media(max-width:600px){.podium{grid-template-columns:1fr}}
.pcard{background:var(--sur);border:1px solid var(--bdr);border-radius:var(--r);
  overflow:hidden;display:flex;flex-direction:column;box-shadow:var(--shd);
  transition:transform .15s,box-shadow .15s}
.pcard:hover{transform:translateY(-3px);box-shadow:0 8px 30px rgba(0,0,0,.12)}
.pcard.p1{border-color:var(--gold);box-shadow:0 0 0 1.5px var(--gold),var(--shd)}
.pimg{position:relative;aspect-ratio:1/1;background:var(--bg);overflow:hidden;
  display:flex;align-items:center;justify-content:center}
.pimg img{width:100%;height:100%;object-fit:cover}
.pfallback{font-size:56px;line-height:1}
.pnum{position:absolute;top:10px;left:10px;font-family:var(--mono);font-size:12px;
  font-weight:700;color:#fff;padding:3px 8px;border-radius:5px;line-height:1.4}
.pn1{background:var(--gold);color:#1a1200;font-size:14px}
.pn2{background:var(--acc)}
.pn3{background:#60A5FA}
.pbody{padding:14px 14px 16px;flex:1;display:flex;flex-direction:column;gap:5px}
.pname{font-size:13px;font-weight:700;line-height:1.4;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.pdesc{font-size:11px;color:var(--ink2);line-height:1.5;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.pshop{font-size:11px;color:var(--ink3)}
.pfoot{display:flex;align-items:baseline;justify-content:space-between;
  margin-top:auto;padding-top:8px;gap:8px}
.pprice{font-family:var(--mono);font-size:16px;font-weight:700}
.pprice.live-ok::after{content:'LIVE';font-size:8px;font-weight:700;
  color:var(--acc);margin-left:4px;vertical-align:super}
.sc.live-rc{transition:color .3s}
.sc.live-rc-flash{color:var(--up)}
.pprice.live-loading{opacity:.5}
.prk{font-family:var(--mono);font-size:10px;color:var(--ink3)}

/* GRID */
.sec{max-width:1080px;margin:32px auto 0;padding:0 20px}
.sec-hd{font-size:13px;font-weight:700;color:var(--ink2);letter-spacing:.05em;
  text-transform:uppercase;display:flex;align-items:center;gap:10px;margin-bottom:14px}
.sec-hd::after{content:'';flex:1;height:1px;background:var(--bdr)}
.cgrid{display:grid;grid-template-columns:repeat(5,1fr);gap:12px}
@media(max-width:960px){.cgrid{grid-template-columns:repeat(4,1fr)}}
@media(max-width:680px){.cgrid{grid-template-columns:repeat(3,1fr);gap:8px}}
@media(max-width:440px){.cgrid{grid-template-columns:repeat(2,1fr)}}
.card{background:var(--sur);border:1px solid var(--bdr);border-radius:var(--r);
  overflow:hidden;display:flex;flex-direction:column;
  transition:transform .15s,box-shadow .15s,border-color .15s}
.card:hover{transform:translateY(-2px);box-shadow:var(--shd);border-color:var(--acc)}
.card.no-data{opacity:.45}
.cimg{position:relative;aspect-ratio:1/1;background:var(--bg);overflow:hidden;
  display:flex;align-items:center;justify-content:center}
.cimg img{width:100%;height:100%;object-fit:cover}
.cfallback{font-size:36px;line-height:1}
.cnum{position:absolute;top:7px;left:7px;font-family:var(--mono);font-size:11px;
  font-weight:700;color:#fff;padding:2px 6px;border-radius:4px;background:rgba(15,23,42,.5)}
.cbody{padding:9px 10px 11px;display:flex;flex-direction:column;gap:3px;flex:1}
.cname{font-size:11px;font-weight:600;line-height:1.45;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.cdesc{font-size:10px;color:var(--ink2);line-height:1.4;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.cshop{font-size:10px;color:var(--ink3);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cfoot{margin-top:auto;padding-top:4px;display:flex;flex-direction:column;gap:1px}
.cprice{font-family:var(--mono);font-size:13px;font-weight:700}
.crk{font-family:var(--mono);font-size:10px;color:var(--ink3)}

/* STARS */
.stars-row{display:flex;align-items:center;gap:5px}
.stars-row.sm{gap:3px}
.sw{position:relative;display:inline-block;font-size:14px;line-height:1;letter-spacing:2px}
.stars-row.sm .sw{font-size:11px;letter-spacing:1px}
.sb{color:var(--bdr)}
.sf{position:absolute;top:0;left:0;overflow:hidden;white-space:nowrap;color:var(--gold);letter-spacing:2px}
.stars-row.sm .sf{letter-spacing:1px}
.sn{font-family:var(--mono);font-size:12px;font-weight:700;color:var(--ink2)}
.stars-row.sm .sn{font-size:10px}
.sc{font-family:var(--mono);font-size:11px;color:var(--ink3)}
.stars-row.sm .sc{font-size:10px}
.no-rev{font-size:10px;color:var(--ink3);font-family:var(--mono)}

/* SPARK */
.spark{position:absolute;bottom:0;left:0;right:0;height:24px;
  background:linear-gradient(transparent,rgba(0,0,0,.3))}
.spark svg{display:block;width:100%;height:20px;margin-top:4px}

/* BADGES */
.badge-hot{display:inline-flex;align-items:center;gap:3px;
  font-size:9px;font-weight:700;padding:1px 6px;border-radius:3px;
  background:#FEF3C7;color:#92400E;border:1px solid #FDE68A;margin-bottom:2px}

/* UP/DOWN */
.up{color:var(--up);font-weight:700}.dn{color:var(--dn);font-weight:700}

/* HERO CHART */
.hero-chart{display:block;width:100%}
.hc-tabs{display:flex;gap:4px;flex-wrap:wrap;margin-top:20px;margin-bottom:10px}
.hctab{padding:5px 14px;border-radius:99px;font-size:12px;font-weight:600;
  border:1px solid var(--bdr);color:var(--ink3);cursor:pointer;
  transition:all .12s;background:none;font-family:var(--sans)}
.hctab.on{border-color:var(--acc);color:var(--acc);background:rgba(37,99,235,.08)}
.hero-chart-box{background:var(--bg);border:1px solid var(--bdr);border-radius:var(--r);
  padding:14px;overflow-x:auto}
.hero-chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.hchip{display:inline-flex;align-items:center;gap:6px;font-size:11px;font-weight:600;
  padding:4px 12px 4px 8px;border-radius:99px;background:var(--bg);
  border:1px solid var(--bdr);color:var(--ink2)}
.hchip-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}

/* TREND DASHBOARD */
.trend-sec{background:var(--sur);border-top:1px solid var(--bdr);border-bottom:1px solid var(--bdr);padding:22px 20px}
.trend-in{max-width:1080px;margin:0 auto}
.trend-hd{font-size:11px;font-weight:700;letter-spacing:.09em;text-transform:uppercase;color:var(--ink2);
  display:flex;align-items:center;gap:10px;margin-bottom:12px}
.trend-hd::after{content:'';flex:1;height:1px;background:var(--bdr)}
.trend-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
@media(max-width:680px){.trend-grid{grid-template-columns:1fr}}
.td-panel{background:var(--bg);border:1px solid var(--bdr);border-radius:var(--r);padding:14px 14px 10px;display:flex;flex-direction:column;gap:0}
.td-ptitle{font-size:12px;font-weight:700;color:var(--ink2);margin-bottom:8px}
.td-card{display:flex;align-items:center;gap:9px;padding:7px 0;border-bottom:1px solid var(--bdr);transition:opacity .1s}
.td-card:last-child{border-bottom:none;padding-bottom:0}
.td-card:hover{opacity:.78}
.td-info{min-width:0;flex:1}
.td-name{font-size:11px;font-weight:600;color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.td-stat{font-size:10px;font-family:var(--mono);color:var(--ink3);margin-top:1px}
.td-stat.up{color:var(--up);font-weight:700}
.td-empty{font-size:11px;color:var(--ink3);padding:10px 0;text-align:center;font-family:var(--mono)}
.td-chart-dot{width:7px;height:7px;border-radius:50%;flex-shrink:0;margin-right:2px;opacity:.85}

/* ANIMATION */
.anim-ctrl{display:flex;align-items:center;gap:10px;margin-bottom:12px;flex-wrap:wrap}
.anim-btn{padding:5px 18px;border-radius:99px;font-size:12px;font-weight:700;
  border:1.5px solid var(--acc);color:var(--acc);background:rgba(37,99,235,.07);
  cursor:pointer;transition:background .12s}
.anim-btn:hover{background:rgba(37,99,235,.16)}
.anim-date{font-family:var(--mono);font-size:12px;color:var(--ink3);white-space:nowrap;flex-shrink:0}
input[type=range]{accent-color:var(--acc)}

/* RELATED */
.related{max-width:1080px;margin:36px auto 0;padding:0 20px 60px}
.rel-hd{font-size:13px;font-weight:700;color:var(--ink2);letter-spacing:.05em;
  text-transform:uppercase;display:flex;align-items:center;gap:10px;margin-bottom:14px}
.rel-hd::after{content:'';flex:1;height:1px;background:var(--bdr)}
.rel-grid{display:flex;flex-wrap:wrap;gap:8px}
.rpill{display:inline-flex;align-items:center;gap:6px;padding:8px 16px;
  border-radius:99px;font-size:13px;font-weight:600;border:1px solid var(--bdr);
  color:var(--ink2);background:var(--sur);transition:border-color .12s,color .12s,background .12s}
.rpill:hover{border-color:var(--acc);color:var(--acc);background:rgba(37,99,235,.06)}

/* NO-REV DIVIDER */
.norev-hd{margin:24px 0 12px;font-size:12px;font-weight:600;color:var(--ink3);
  display:flex;align-items:center;gap:8px}
.norev-hd::before,.norev-hd::after{content:'';flex:1;height:1px;background:var(--bdr)}

/* FOOTER */
.footer{background:var(--sur);border-top:1px solid var(--bdr);padding:24px 20px;
  text-align:center;font-size:11px;color:var(--ink3);line-height:2}
.footer a{color:var(--acc)}

@media(max-width:480px){.h1{font-size:24px}.podium{grid-template-columns:1fr}.fband{flex-direction:column;align-items:flex-start}}
"""

# ── ジャンルページ ───────────────────────────────────────────
def build_genre_page(key, items):
    m     = GENRE_META[key]
    slug  = m["slug"]; label = m["label"]; emoji = m["emoji"]
    desc  = m["desc"]; kw    = m["kw"]
    page_url = f"{BASE_URL}/{slug}/"
    year  = date.today().year

    scored   = [i for i in items if i["review_count"] > 0]
    no_rev   = [i for i in items if i["review_count"] == 0]
    top3     = scored[:3]; rest = scored[3:]
    rc_total = sum(i["review_count"] for i in scored)

    # JSON-LD
    ld_items = []
    for item in scored[:10]:
        li = {"@type":"ListItem","position":item["rank"],"item":{
            "@type":"Product","name":item["item_name"],"url":item["item_url"],
            "offers":{"@type":"Offer","price":str(item["item_price"] or 0),
                      "priceCurrency":"JPY","availability":"https://schema.org/InStock"},
            "aggregateRating":{"@type":"AggregateRating",
                               "ratingValue":str(item["review_average"]),
                               "reviewCount":str(item["review_count"])},
        }}
        if item.get("item_caption"): li["item"]["description"] = item["item_caption"]
        ld_items.append(li)
    jsonld = json.dumps({"@context":"https://schema.org","@type":"ItemList",
        "name":f"{label} 口コミランキング","description":desc,"url":page_url,
        "numberOfItems":len(scored),"itemListElement":ld_items},
        ensure_ascii=False, indent=2)

    # charts
    trends_data        = compute_trends(key, scored)
    hero_svg, color_map, badge_map = render_hero_ts(scored, trends_data)
    trend_html         = render_trend_dashboard(trends_data, color_map) if scored else ""
    hm_svg             = render_heatmap(key, scored)
    vel_svg            = render_velocity_bar(scored)
    anim_ctrl, anim_js = render_animation(key, scored)
    bubble             = render_bubble_chart(scored)

    # Hero chart annotation chips
    BADGE_LABEL = {"📈": "急上昇", "🆕": "今週の新顔", "👑": "安定王者"}
    hero_chips = ""
    if hero_svg and badge_map:
        chips = []
        for code, badge in badge_map.items():
            item = next((i for i in scored if i["item_code"] == code), None)
            if item and code in color_map:
                c  = color_map[code]
                nm = item["item_name"][:16] + ("…" if len(item["item_name"]) > 16 else "")
                chips.append(
                    f'<span class="hchip">'
                    f'<span class="hchip-dot" style="background:{c}"></span>'
                    f'{badge} {BADGE_LABEL.get(badge, "")} — {nm}'
                    f'</span>'
                )
        if chips:
            hero_chips = f'<div class="hero-chips" id="hc-chips">{"".join(chips)}</div>'

    # All charts bundled into hero section via tabs
    _hc_tabs, _hc_bodies = [], []
    if hero_svg:
        _hc_tabs.append('<button class="hctab on" id="hct-ts" onclick="switchHeroChart(\'ts\')">スコア推移</button>')
        _hc_bodies.append(f'<div id="hc-ts">{hero_svg}</div>')
    if hm_svg:
        _hc_tabs.append('<button class="hctab" id="hct-hm" onclick="switchHeroChart(\'hm\')">ランク動向</button>')
        _hc_bodies.append(f'<div id="hc-hm" style="display:none">{hm_svg}</div>')
    if vel_svg:
        _hc_tabs.append('<button class="hctab" id="hct-vel" onclick="switchHeroChart(\'vel\')">口コミ勢い</button>')
        _hc_bodies.append(f'<div id="hc-vel" style="display:none">{vel_svg}</div>')
    if anim_ctrl:
        _hc_tabs.append('<button class="hctab" id="hct-anim" onclick="switchHeroChart(\'anim\')">市場推移</button>')
        _hc_bodies.append(f'<div id="hc-anim" style="display:none">{anim_ctrl}</div>')
    if bubble:
        _hc_tabs.append('<button class="hctab" id="hct-bb" onclick="switchHeroChart(\'bb\')">価格マップ</button>')
        _hc_bodies.append(
            f'<div id="hc-bb" style="display:none">'
            f'<p class="chart-sub">縦軸:口コミスコア ｜ 横軸:価格 ｜ ○の大きさ:口コミ件数</p>'
            f'{bubble}</div>'
        )
    hero_tabs_html   = f'<div class="hc-tabs">{"".join(_hc_tabs)}</div>' if _hc_tabs else ""
    hero_bodies_html = "".join(_hc_bodies)
    chart_html = ""  # all charts are now inside the hero section

    # podium
    rank_labels = ["🥇 1位", "🥈 2位", "🥉 3位"]
    podium_html = "".join(render_podium(i, rank_labels[i["rank"]-1], emoji) for i in top3)

    # grid
    rest_html  = "".join(render_card(i, emoji) for i in rest)
    norev_html = (f'<div class="norev-hd">評価データなし（{len(no_rev)}件）</div>'
                  f'<div class="cgrid">{"".join(render_card(i,emoji) for i in no_rev)}</div>') if no_rev else ""

    # related
    rel_pills = "".join(
        f'<a class="rpill" href="../{GENRE_META[k]["slug"]}/">{GENRE_META[k]["emoji"]} {GENRE_META[k]["label"]}</a>'
        for k in m.get("related",[]) if k in GENRE_META
    ) + f'<a class="rpill" href="../">🏠 全ジャンル一覧</a>'

    # item_codes for live price fetch (top 10)
    live_codes = json.dumps([i["item_code"] for i in scored[:10]], ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{label} 口コミランキング {year}年 | {SITE_NAME}</title>
<meta name="description" content="{desc}">
<meta name="robots" content="index,follow">
<link rel="canonical" href="{page_url}">
<meta property="og:type" content="website">
<meta property="og:title" content="{label} 口コミランキング {year}年 | {SITE_NAME}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{page_url}">
<script type="application/ld+json">{jsonld}</script>
<style>{CSS}</style>
</head>
<body>

<nav class="nav">
  <div class="nav-in">
    <a class="nav-logo" href="../">{SITE_NAME}<span>口コミスコアランキング</span></a>
    <div class="nav-sep"></div>
    <span class="nav-genre">{emoji} {label}</span>
    <span class="nav-date" id="upd">{latest_date}</span>
    <span class="nav-live" id="live-ind" style="display:none">LIVE</span>
  </div>
</nav>

<div class="bc"><a href="../">トップ</a><span class="bc-sep">/</span><span>{label}</span></div>

<header class="hero">
  <div class="hero-in">
    <p class="eyebrow">{SITE_NAME} — 独自口コミスコアランキング</p>
    <h1 class="h1">{emoji} {label}<br><em>口コミランキング</em> {year}年版</h1>
    <p class="hero-sub">{desc}</p>
    <div class="hero-badges">
      <span class="hbadge">{len(scored)}製品を分析</span>
      <span class="hbadge">{rc_total:,}件のレビューを集計</span>
      <span class="hbadge a">楽天公式とは別集計</span>
      <span class="hbadge m" id="upd-badge">{latest_date} 更新</span>
    </div>
    {hero_tabs_html}
    <div class="hero-chart-box">{hero_bodies_html}</div>
    {hero_chips}
    <div class="fband">
      <span class="fform">📊 独自スコア：口コミ件数が多く・評価が高く・最近注目されている製品ほど上位</span>
      <span class="fdesc">楽天の売れ筋順位とは別に、<strong>口コミの量・質・勢い</strong>の3つで計算した独自ランキングです。</span>
    </div>
  </div>
</header>

{"<div class='best3-sec'><div class='best3-hd'>リアルタイム ベスト3<span class='live-tag'>LIVE</span></div><div class='podium'>" + podium_html + "</div></div>" if top3 else ""}

{trend_html}

{"<div class='sec'><div class='sec-hd'>4位以下 — 口コミスコア順</div><div class='cgrid'>" + rest_html + "</div>" + norev_html + "</div>" if rest else ""}

<nav class="related"><div class="rel-hd">関連ジャンル</div><div class="rel-grid">{rel_pills}</div></nav>

<footer class="footer">
  <p>楽天市場のレビューデータをもとに独自スコアで並べ替えたランキングです。楽天の売れ筋順位とは異なります。</p>
  <p>価格は随時更新されます。本ページには<a href="https://affiliate.rakuten.co.jp/" rel="noopener">楽天アフィリエイト</a>リンクが含まれます。</p>
  <p>© {year} {SITE_NAME}</p>
</footer>

<div id="btip"></div>

<script>
// ── ヒーローチャート切り替え ──
function switchHeroChart(t) {{
  ['ts','hm','vel','anim','bb'].forEach(function(k){{
    var w=document.getElementById('hc-'+k);
    var b=document.getElementById('hct-'+k);
    if(w) w.style.display=k===t?'':'none';
    if(b) b.className=k===t?'hctab on':'hctab';
  }});
  var chips=document.getElementById('hc-chips');
  if(chips) chips.style.display=t==='ts'?'':'none';
}}

// ── バブルチャートツールチップ ──
(function() {{
  const tip = document.getElementById('btip');
  if (!tip) return;
  document.querySelectorAll('.bc').forEach(el => {{
    el.addEventListener('mouseenter', () => {{
      tip.innerHTML = '<strong style="font-size:11px;line-height:1.5">' + el.dataset.n + '</strong><br>'
        + '<span style="font-family:monospace;font-size:14px;font-weight:700">' + el.dataset.p + '</span><br>'
        + '<span style="color:var(--ink3);font-size:11px">スコア ' + el.dataset.s
        + ' &nbsp;|&nbsp; ' + el.dataset.r + '位 &nbsp;|&nbsp; ' + el.dataset.c + '件</span>';
      tip.style.display = 'block';
    }});
    el.addEventListener('mousemove', e => {{
      tip.style.left = (e.clientX + 16) + 'px';
      tip.style.top  = (e.clientY - 10) + 'px';
    }});
    el.addEventListener('mouseleave', () => {{ tip.style.display = 'none'; }});
  }});
}})();

// ── リアルタイムデータ取得（価格・口コミ件数・評価）──
(function() {{
  const APP_ID = '{APP_ID}';
  const CODES  = {live_codes};
  if (!APP_ID || !CODES.length) return;

  async function fetchLiveData(code) {{
    const url = 'https://app.rakuten.co.jp/services/api/IchibaItem/Search/20170706'
      + '?format=json&applicationId=' + APP_ID
      + '&itemCode=' + encodeURIComponent(code) + '&hits=1';
    const d = await (await fetch(url)).json();
    const it = d.Items?.[0]?.Item;
    if (!it) return null;
    return {{ p: it.itemPrice, rc: it.reviewCount, ra: it.reviewAverage }};
  }}

  function animCount(el, from, to) {{
    if (from === to) return;
    const dur = Math.min(1200, Math.abs(to - from) * 40);
    const start = Date.now();
    el.classList.add('live-rc');
    (function tick() {{
      const t = Math.min((Date.now() - start) / dur, 1);
      const ease = 1 - Math.pow(1 - t, 3);
      el.textContent = Math.round(from + (to - from) * ease).toLocaleString('ja-JP') + '件';
      if (t < 1) requestAnimationFrame(tick);
      else {{
        el.classList.add('live-rc-flash');
        setTimeout(function() {{ el.classList.remove('live-rc-flash'); }}, 600);
      }}
    }})();
  }}

  function applyLive(code, d) {{
    const prEl = document.querySelector('[data-live="' + code + '"]');
    if (prEl && d.p != null) {{
      prEl.textContent = '¥' + d.p.toLocaleString('ja-JP');
      prEl.classList.add('live-ok');
    }}
    const rcEl = document.querySelector('[data-live-rc="' + code + '"]');
    if (rcEl && d.rc != null) {{
      const from = parseInt(rcEl.textContent.replace(/[^0-9]/g, ''), 10) || d.rc;
      animCount(rcEl, from, d.rc);
    }}
    const raEl = document.querySelector('[data-live-ra="' + code + '"]');
    if (raEl && d.ra != null) raEl.textContent = d.ra.toFixed(2);
    const sfEl = document.querySelector('[data-live-sf="' + code + '"]');
    if (sfEl && d.ra != null) sfEl.style.width = (d.ra / 5 * 100).toFixed(1) + '%';
  }}

  async function run() {{
    const ind = document.getElementById('live-ind');
    for (const code of CODES.slice(0, 3)) {{
      const prEl = document.querySelector('[data-live="' + code + '"]');
      if (prEl) prEl.classList.add('live-loading');
      try {{
        const d = await fetchLiveData(code);
        if (d) applyLive(code, d);
      }} catch(e) {{}}
      if (prEl) prEl.classList.remove('live-loading');
      await new Promise(r => setTimeout(r, 400));
    }}
    if (ind) ind.style.display = '';
    if ('requestIdleCallback' in window) {{
      requestIdleCallback(async function() {{
        for (const code of CODES.slice(3)) {{
          try {{ const d = await fetchLiveData(code); if (d) applyLive(code, d); }} catch(e) {{}}
          await new Promise(r => setTimeout(r, 500));
        }}
      }});
    }}
  }}

  run().catch(function() {{}});
}})();
{anim_js}
</script>

</body>
</html>"""

# ── トップページ ────────────────────────────────────────────
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
        sections.append(
            f'<div class="icat"><h2 class="ich">{cat}</h2><div class="igrid">{cards}</div></div>'
        )

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{SITE_NAME} — 口コミスコアで選ぶ、本当のランキング</title>
<meta name="description" content="楽天市場の口コミ件数と評価点から独自スコアを算出し、売れ筋とは異なる本当の評価ランキングを29ジャンルで提供。">
<meta name="robots" content="index,follow">
<link rel="canonical" href="{BASE_URL}/">
<style>
{CSS}
.top-hero{{background:var(--sur);border-bottom:1px solid var(--bdr);
  padding:72px 20px 60px;text-align:center}}
.top-in{{max-width:680px;margin:0 auto}}
.top-logo{{font-size:48px;font-weight:900;letter-spacing:-.06em;color:var(--acc);margin-bottom:6px}}
.top-sub{{font-size:16px;color:var(--ink2);line-height:1.7;margin-bottom:22px}}
.idx{{max-width:1080px;margin:40px auto 60px;padding:0 20px}}
.icat{{margin-bottom:36px}}
.ich{{font-size:13px;font-weight:700;color:var(--ink2);letter-spacing:.06em;text-transform:uppercase;
  display:flex;align-items:center;gap:10px;margin-bottom:14px}}
.ich::after{{content:'';flex:1;height:1px;background:var(--bdr)}}
.igrid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:10px}}
.ic{{background:var(--sur);border:1px solid var(--bdr);border-radius:var(--r);
  padding:16px;display:flex;flex-direction:column;gap:4px;
  transition:border-color .12s,box-shadow .12s,transform .12s}}
.ic:hover{{border-color:var(--acc);box-shadow:var(--shd);transform:translateY(-2px)}}
.ie{{font-size:28px;line-height:1;margin-bottom:2px}}
.il{{font-size:13px;font-weight:700;color:var(--ink);line-height:1.3}}
.in{{font-size:11px;color:var(--ink3);font-family:var(--mono)}}
</style>
</head>
<body>
<nav class="nav"><div class="nav-in">
  <span class="nav-logo">{SITE_NAME}<span>口コミスコアランキング</span></span>
  <span class="nav-date">{latest_date} 更新</span>
</div></nav>
<header class="top-hero"><div class="top-in">
  <div class="top-logo">{SITE_NAME}</div>
  <p class="top-sub">「ランキング1位！」「送料無料！」ではなく、<br>
  <strong>口コミの質と量</strong>だけで並べた本当のランキング。</p>
  <div class="hero-badges" style="justify-content:center">
    <span class="hbadge a">29ジャンル収録</span>
    <span class="hbadge">楽天公式とは別集計</span>
    <span class="hbadge m">{latest_date} 更新</span>
  </div>
</div></header>
<main class="idx">{"".join(sections)}</main>
<footer class="footer">
  <p>楽天市場のレビューデータをもとに独自スコアで並べ替えたランキングです。本ページには楽天アフィリエイトリンクが含まれます。</p>
  <p>© {year} {SITE_NAME}</p>
</footer>
</body>
</html>"""

def build_sitemap(built):
    urls = [f'  <url><loc>{BASE_URL}/</loc><changefreq>hourly</changefreq><priority>1.0</priority></url>']
    for key in built:
        if key in GENRE_META:
            urls.append(f'  <url><loc>{BASE_URL}/{GENRE_META[key]["slug"]}/</loc><changefreq>hourly</changefreq><priority>0.8</priority></url>')
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{chr(10).join(urls)}\n</urlset>'

# ── メイン ──────────────────────────────────────────────────
def main():
    target = sys.argv[1] if len(sys.argv) > 1 else None
    keys   = [target] if target else list(GENRE_META.keys())
    genre_counts = {}; built = []

    for key in keys:
        if key not in GENRE_META:
            print(f"Unknown: {key}", file=sys.stderr); continue
        m = GENRE_META[key]
        print(f"\n── {m['label']} ──", file=sys.stderr)
        items = load_genre(key)
        if not items:
            print(f"  No data, skipping", file=sys.stderr); continue
        prefetch_images(items, m["label"])
        genre_counts[key] = len([i for i in items if i["review_count"] > 0])
        html = build_genre_page(key, items)
        out  = DOCS_DIR / m["slug"]
        out.mkdir(parents=True, exist_ok=True)
        (out / "index.html").write_text(html, encoding="utf-8")
        print(f"  → docs/{m['slug']}/index.html ({len(html):,} bytes)", file=sys.stderr)
        built.append(key)

    if not target:
        idx = build_index(genre_counts)
        (DOCS_DIR / "index.html").write_text(idx, encoding="utf-8")
        print(f"\n→ docs/index.html ({len(idx):,} bytes)", file=sys.stderr)
        sm = build_sitemap(built)
        (DOCS_DIR / "sitemap.xml").write_text(sm, encoding="utf-8")
        print(f"→ docs/sitemap.xml", file=sys.stderr)

    print(f"\n✓ Built {len(built)} pages → {DOCS_DIR}", file=sys.stderr)

if __name__ == "__main__":
    main()
