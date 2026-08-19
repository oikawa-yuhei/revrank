"""BuySignal 設定。媒体重み・スパイク閾値・RSSフィード定義。"""

# ── 媒体別重み ────────────────────────────────────────────────────────────────
MEDIA_WEIGHTS: dict[str, float] = {
    "rss_youtube": 2.0,   # 専門YouTubeチャンネル（1件あたりの情報量が大きい）
    "rss_blog":    1.5,   # はてなブックマーク / 独自ブログ長文レビュー
    "note_hashtag": 1.5,  # note.com ハッシュタグ記事
    "reddit":      1.3,   # Reddit (英語圏ランナー)
    "runnet":      1.2,   # RUNNET 知恵袋
    "chiebukuro":  1.2,   # Yahoo!知恵袋
}

# ── スパイク判定 ──────────────────────────────────────────────────────────────
SPIKE_Z_THRESHOLD = 2.0   # z > 2.0 をスパイクと判定
SPIKE_WINDOW_DAYS = 14    # 移動平均の計算窓（日）

# ── 価格取得 ──────────────────────────────────────────────────────────────────
FIXED_PRICE_CHECK_TOP_N = 20  # スパイク有無に関わらず常時価格監視する上位N商品

# ── はてなブックマーク 検索RSS ─────────────────────────────────────────────────
# 人気ブログ記事を無料・無制限で取得できる。Per-Media設計の要。
HATENA_QUERIES: list[str] = [
    "ランニングシューズ レビュー",
    "カーボンシューズ おすすめ",
    "厚底シューズ 比較",
    "ガーミン ランニング",
    "ランニングウォッチ レビュー",
    "トレイルランニング シューズ",
    "マラソン シューズ 比較",
]
HATENA_RSS_TEMPLATE = "https://b.hatena.ne.jp/search/text?q={query}&mode=rss&sort=recent"

# ── YouTube チャンネル RSS ───────────────────────────────────────────────────
# YouTube Studio → 設定 → チャンネル → チャンネルID を確認し追加する。
# フォーマット: "チャンネル名": "UCxxxxxxxxxxxxxxxxxx"
YOUTUBE_CHANNELS: dict[str, str] = {
    # 設定例:
    # "ランニングチャンネル名": "UCxxxxxxxxxxxxxxxxxxxxxx",
}
YOUTUBE_RSS_TEMPLATE = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

# ── 独自RSSフィード (WordPressブログ等) ──────────────────────────────────────
CUSTOM_RSS_FEEDS: list[str] = [
    # "https://example-running-blog.com/feed/",
]
