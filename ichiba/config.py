from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH  = BASE_DIR / "data" / "ichiba_ranking.db"

RANKING_URL     = "https://openapi.rakuten.co.jp/ichibaranking/api/IchibaItem/Ranking/20220601"
REQUEST_INTERVAL = 1.2
MAX_RETRIES     = 3
RETRY_BACKOFF   = 5

PAGE_SIZE       = 30
PAGES_PER_GENRE = 3

GENRES = {
    # ── ランニング ──
    "running_shoes":   {"id": 565768, "label": "ランニングシューズ"},
    "running_watch":   {"id": 565769, "label": "ランニングウォッチ・GPS"},

    # ── ゴルフ ──
    "golf_club":       {"id": 565751, "label": "ゴルフクラブ"},
    "golf_ball":       {"id": 204964, "label": "ゴルフボール"},
    "golf_shoes":      {"id": 565750, "label": "ゴルフシューズ"},
    "golf_bag":        {"id": 201775, "label": "ゴルフバッグ"},

    # ── フィットネスマシン ──
    "treadmill":       {"id": 205052, "label": "ランニングマシン"},
    "fitness_bike":    {"id": 201867, "label": "フィットネスバイク"},
    "stepper":         {"id": 204690, "label": "ステッパー"},

    # ── ウェイトトレーニング ──
    "dumbbell":        {"id": 503299, "label": "ダンベル"},
    "barbell":         {"id": 201866, "label": "バーベル"},
    "kettlebell":      {"id": 565860, "label": "ケトルベル"},

    # ── アウトドア ──
    "tent":            {"id": 302373, "label": "テント"},
    "tarp":            {"id": 201876, "label": "タープ"},
    "outdoor_bedding": {"id": 201887, "label": "アウトドア用寝具"},
    "camp_chair":      {"id": 201883, "label": "チェア・テーブル"},
    "bbq_grill":       {"id": 402220, "label": "バーベキューコンロ"},
    "camp_stove":      {"id": 565799, "label": "キャンプバーナー"},
    "bonfire":         {"id": 208072, "label": "焚き火台"},

    # ── ウィンタースポーツ ──
    "ski_board":       {"id": 205002, "label": "スキー板"},
    "ski_boots":       {"id": 205003, "label": "スキーブーツ"},
    "snowboard":       {"id": 205015, "label": "スノーボード"},
    "snowboard_boots": {"id": 205016, "label": "スノーボードブーツ"},

    # ── 寝具 ──
    "mattress":        {"id": 508183, "label": "マットレス"},
    "bed_frame":       {"id": 400482, "label": "ベッドフレーム"},
    "leg_mattress":    {"id": 505107, "label": "脚付きマットレス"},

    # ── 子育て ──
    "stroller":        {"id": 401151, "label": "ベビーカー"},
    "child_seat":      {"id": 203056, "label": "チャイルドシート"},

    # ── 登山 ──
    "climbing_shoes":  {"id": 302384, "label": "登山・クライミングシューズ"},

    # ── 自転車 ──
    "e_bike":          {"id": 302202, "label": "電動アシスト自転車"},
}
