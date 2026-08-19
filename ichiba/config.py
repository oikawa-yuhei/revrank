from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH  = BASE_DIR / "data" / "ichiba_ranking.db"

RANKING_URL      = "https://openapi.rakuten.co.jp/ichibaranking/api/IchibaItem/Ranking/20220601"
GENRE_URL        = "https://openapi.rakuten.co.jp/ichiba/api/IchibaGenre/Search/20140222"
REQUEST_INTERVAL = 1.2
MAX_RETRIES      = 3
RETRY_BACKOFF    = 5

PAGE_SIZE        = 30
PAGES_PER_GENRE  = 3

# ガチ勢向けランニングギア 12ジャンル
# genre_id: 楽天市場ジャンルID。tools/find_genre.py で検索できる。
# id=0 はプレースホルダー（未確認）。fetch_ranking.py は自動でスキップする。
#
# 公開優先順位 (Phase 2-3 基準: 30日分データ・15商品・ガイド完成):
#   最優先: running_watch, running_shoes, power_meter
#   次点:   recovery, ultra_gear, compression_wear, running_sunglass, waterproof_jacket
#   後回し: training_gear, race_pouch, nutrition, cap
GENRES = {
    # ── 確認済み ──────────────────────────────────────────────────────────────
    "running_watch":    {"id": 565769, "label": "GPSランニングウォッチ",
                         "priority": 1, "price_floor": 15000},
    "running_shoes":    {"id": 565768, "label": "厚底カーボンシューズ",
                         "priority": 1, "price_floor": 15000},

    # ── 要確認: python tools/find_genre.py <キーワード> で ID を検索 ───────────
    "power_meter":      {"id": 0, "label": "ランニングパワーメーター",
                         "priority": 1, "price_floor": 20000},
    "recovery":         {"id": 0, "label": "回復管理ギア（リカバリーデバイス・スマートリング）",
                         "priority": 2, "price_floor": 30000},
    "ultra_gear":       {"id": 0, "label": "ウルトラ装備（ハイドレーションベスト・ランニングポール）",
                         "priority": 2, "price_floor": 10000},
    "compression_wear": {"id": 0, "label": "高機能タイツ・コンプレッションウェア",
                         "priority": 2, "price_floor": 8000},
    "running_sunglass": {"id": 0, "label": "ランニング用サングラス",
                         "priority": 2, "price_floor": 10000},
    "waterproof_jacket":{"id": 0, "label": "防水防寒ジャケット（Gore-Tex系）",
                         "priority": 2, "price_floor": 15000},
    "training_gear":    {"id": 0, "label": "トレーニング用品（高地マスク・フォームローラー）",
                         "priority": 3, "price_floor": 5000},
    "race_pouch":       {"id": 0, "label": "レース用サコッシュ・ランニングポーチ",
                         "priority": 3, "price_floor": 3000},
    "nutrition":        {"id": 0, "label": "補給食・行動食",
                         "priority": 3, "price_floor": 500},
    "cap":              {"id": 0, "label": "帽子・キャップ（速乾・UVカット）",
                         "priority": 3, "price_floor": 3000},
}
