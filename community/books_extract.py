"""ランニング関連書籍の言及抽出。

既知書籍タイトルのパターンマッチで product_id = "book/{slug}" を生成する。
アフィリエイトリンクは Amazon Associates (ISBN ベース) で後付けする想定。
"""
import re


# (パターン, 正規タイトル, slug)
_BOOK_PATTERNS: list[tuple[re.Pattern, str, str]] = [

    # ── 定番・入門 ────────────────────────────────────────────────────────
    (re.compile(r'born[\s\-]?to[\s\-]?run|ボーン[\s・]?トゥ[\s・]?ラン|ボーントゥラン', re.I),
     "Born to Run", "born-to-run"),

    (re.compile(r'走ることについて語る|村上春樹.{0,10}ラン|ランニング.{0,10}村上春樹|ノルウェー.{0,10}走', re.I),
     "走ることについて語るときに僕の語ること", "haruki-running"),

    (re.compile(r'ダニエルズ|daniels[\s\-]?(?:running[\s\-]?)?formula', re.I),
     "ダニエルズのランニング・フォーミュラ", "daniels-formula"),

    (re.compile(r'80[\s/／]20[\s\-]?run|エイティ.{0,4}トゥエンティ.{0,4}ラン', re.I),
     "80/20 Running", "80-20-running"),

    (re.compile(r'lore[\s\-]?of[\s\-]?running', re.I),
     "Lore of Running", "lore-of-running"),

    # ── トレーニング理論 ──────────────────────────────────────────────────
    (re.compile(r'ピリオダイゼーション|periodization[\s\-]?(?:for[\s\-]?sport)?', re.I),
     "ピリオダイゼーション", "periodization"),

    (re.compile(r'science[\s\-]?of[\s\-]?running|ランニングの科学', re.I),
     "Science of Running", "science-of-running"),

    (re.compile(r'ランニング革命|running[\s\-]?revolution|ポーズメソッド', re.I),
     "ランニング革命", "running-revolution"),

    (re.compile(r'マフェトン|maffetone[\s\-]?(?:method)?|低心拍.{0,4}トレーニング', re.I),
     "マフェトン理論", "maffetone-method"),

    # ── レース・超長距離 ─────────────────────────────────────────────────
    (re.compile(r'ウルトラマラソン.{0,5}マン|ultramarathon[\s\-]?man|ジーン.{0,5}ヒルセンボック', re.I),
     "Ultramarathon Man", "ultramarathon-man"),

    (re.compile(r'can[\s\']?t[\s\-]?hurt[\s\-]?me|キャント[\s\-]?ハート[\s\-]?ミー|デビッド.{0,5}ゴギンズ|goggins', re.I),
     "Can't Hurt Me", "cant-hurt-me"),

    (re.compile(r'finding[\s\-]?ultra|ファインディング[\s\-]?ウルトラ|リッチ.{0,5}ロール|rich[\s\-]?roll', re.I),
     "Finding Ultra", "finding-ultra"),

    # ── 日本語ランニング本 ──────────────────────────────────────────────
    (re.compile(r'マラソンは最初の一歩から|最初の一歩.{0,10}マラソン', re.I),
     "マラソンは最初の一歩から", "marathon-first-step"),

    (re.compile(r'42\.195[\s\-]?km.{0,5}の科学|マラソンの科学', re.I),
     "42.195kmの科学", "marathon-science"),

    (re.compile(r'ランニングする前に読む本|走る前に読む', re.I),
     "ランニングする前に読む本", "before-running"),

    (re.compile(r'サブ3への道|sub[\s\-]?3.{0,5}マラソン.{0,5}[本書]', re.I),
     "サブ3への道", "sub3-guide"),

    # ── 栄養・身体ケア ──────────────────────────────────────────────────
    (re.compile(r'ランナーのための栄養学|ランニング.{0,5}栄養.{0,5}[本書]', re.I),
     "ランナーのための栄養学", "runner-nutrition"),

    (re.compile(r'スポーツ栄養学.{0,5}[本書]|[本書].{0,5}スポーツ栄養', re.I),
     "スポーツ栄養学", "sports-nutrition"),
]


def extract_book_mentions(text: str) -> list[dict]:
    """
    テキストから書籍言及を抽出する。

    Returns:
        [{"product_id": str, "brand_key": "book", "brand_display": "書籍",
          "model_name": str, "raw_mention": str}, ...]
    """
    if not text:
        return []

    results = []
    seen: set[str] = set()

    sentences = re.split(r'[。\n！？!?\.\r]', text)
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue

        for pat, title, slug in _BOOK_PATTERNS:
            m = pat.search(sent)
            if not m:
                continue

            product_id = f"book/{slug}"
            if product_id in seen:
                continue
            seen.add(product_id)

            start = max(0, m.start() - 15)
            end   = min(len(sent), m.end() + 15)
            results.append({
                "product_id":    product_id,
                "brand_key":     "book",
                "brand_display": "書籍",
                "model_name":    title,
                "raw_mention":   sent[start:end].strip(),
            })

    return results
