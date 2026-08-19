"""商品名寄せエンジン (Phase 3-1)。

item_name からブランド＋型番を抽出し、正規化商品ID (product_id) を生成する。
ジャンルごとにブランド・モデルルールを登録する設計。

product_id 形式: "{brand_key}/{model_slug}"
  例: "garmin/forerunner-955", "polar/vantage-v3"
"""
import re


# ── ノイズ除去 ─────────────────────────────────────────────────────────────
# マーケティング文言・カテゴリ語・括弧内の補足情報を削除する
_NOISE = re.compile(
    r'【[^】]*】'          # 【送料無料】【正規品】等
    r'|〔[^〕]*〕'
    r'|\[[^\]]*\]'         # [Slate] 等の色指定
    r'|（[^）]*）'         # 全角括弧
    r'|\([^)]*\)'          # 半角括弧（型番末尾・説明）
    r'|送料無料'
    r'|正規[輸入]*品?'
    r'|国内正規'
    r'|日本語[表示対応]*'
    r'|保証[付き]*'
    r'|新品'
    r'|特価'
    r'|最安値'
    r'|ポイント\d+倍?'
    r'|楽天[ランキング]*'
    r'|ランニングウォッチ'  # ジャンル語はモデル抽出の妨げになる
    r'|GPS[ウォッチ時計]*'
    r'|スポーツウォッチ'
    r'|アウトドアウォッチ'
    r'|スマートウォッチ',
    re.IGNORECASE,
)


def _clean(name: str) -> str:
    s = _NOISE.sub(' ', name)
    return re.sub(r'\s+', ' ', s).strip()


def _slug(s: str) -> str:
    """表示名をDBキー・URLパスに使えるスラグに変換する。"""
    s = s.lower().strip()
    s = re.sub(r'[\s/\-_]+', '-', s)
    s = re.sub(r'[^a-z0-9\-]', '', s)
    return s.strip('-')


# ── ブランド検出 ──────────────────────────────────────────────────────────
# (brand_key, display_name, 検出パターンのリスト)
_BRAND_DEFS = [
    # ── GPS ウォッチ ──────────────────────────────────────────────────────
    ('garmin',      'Garmin',      [r'ガーミン',        r'\bgarmin\b']),
    ('polar',       'Polar',       [r'ポラール?',        r'\bpolar\b']),
    ('suunto',      'Suunto',      [r'スント',           r'\bsuunto\b']),
    ('coros',       'Coros',       [r'コロス',           r'\bcoros\b']),
    ('apple',       'Apple',       [r'アップル',         r'\bapple\b']),
    ('wahoo',       'Wahoo',       [r'ワフー',           r'\bwahoo\b']),
    ('amazfit',     'Amazfit',     [r'アマズフィット',   r'\bamazfit\b']),
    ('epson',       'Epson',       [r'エプソン',         r'\bepson\b']),

    # ── ランニングシューズ ────────────────────────────────────────────────
    ('nike',        'Nike',        [r'ナイキ',           r'\bnike\b']),
    ('asics',       'ASICS',       [r'アシックス',       r'\basics\b']),
    ('adidas',      'Adidas',      [r'アディダス',       r'\badidas\b']),
    ('new_balance', 'New Balance', [r'ニューバランス',   r'\bnew[\s\-]?balance\b']),
    ('hoka',        'Hoka',        [r'ホカ(?:オネオネ)?', r'\bhoka\b']),
    ('on_running',  'On',          [r'オン(?:ランニング)?クラウド', r'クラウドモンスター', r'クラウドブーム',
                                    r'\bon\s+running\b', r'\bcloudboom\b', r'\bcloudmonster\b', r'\bcloudsurfer\b']),
    ('brooks',      'Brooks',      [r'ブルックス',       r'\bbrooks\b']),
    ('saucony',     'Saucony',     [r'サッカニー',       r'\bsaucony\b']),
    ('mizuno',      'Mizuno',      [r'ミズノ',           r'\bmizuno\b']),
    ('puma',        'Puma',        [r'プーマ',           r'\bpuma\b']),
    ('salomon',     'Salomon',     [r'サロモン',         r'\bsalomon\b']),
    ('altra',       'Altra',       [r'アルトラ',         r'\baltra\b']),
]
_BRAND_RE = [
    (key, display, re.compile('|'.join(pats), re.IGNORECASE))
    for key, display, pats in _BRAND_DEFS
]


def _detect_brand(name: str):
    """(brand_key, display_name) を返す。未検出なら (None, None)。"""
    for key, display, pat in _BRAND_RE:
        if pat.search(name):
            return key, display
    return None, None


# ── モデル抽出ルール ──────────────────────────────────────────────────────
# brand_key -> [(パターン, 型番生成関数(match) -> str)]
# 上から順にマッチを試み、最初にヒットしたものを採用する。
_MODEL_RULES: dict[str, list[tuple[re.Pattern, object]]] = {

    'garmin': [
        # Forerunner 165 / 255 / 265 / 955 / 965 / … (3桁モデル番号)
        (re.compile(r'forerunner[\s\-]?(\d{3})(s|m)?(?:[\s\-](?:solar|music|sapphire))*', re.I),
         lambda m: f"Forerunner {m.group(1)}{(m.group(2) or '').upper()}"),

        # Fenix 7X Pro / 7S Pro / 8 Pro 等 (Pro あり — lookahead で先に試みる)
        (re.compile(r'fen[iî]x[\s\-]?(\d+)(s|x)?(?=.*?\bpro\b)', re.I),
         lambda m: f"Fenix {m.group(1)}{(m.group(2) or '').upper()} Pro"),
        # Fenix 7 / 7S / 7X / 8 / … (Pro なし)
        (re.compile(r'fen[iî]x[\s\-]?(\d+)(s|x)?', re.I),
         lambda m: f"Fenix {m.group(1)}{(m.group(2) or '').upper()}"),
        # フェニックス (カナ表記のみの場合)
        (re.compile(r'フェニックス[\s\-]?(\d+)(s|x)?', re.I),
         lambda m: f"Fenix {m.group(1)}{(m.group(2) or '').upper()}"),

        # Epix Gen 2 / Epix Pro
        (re.compile(r'epix(?:[\s\-]?(gen[\s\-]?(\d+)|pro))?', re.I),
         lambda m: (
             f"Epix Gen {m.group(2)}" if (m.group(1) and 'gen' in m.group(1).lower())
             else ('Epix Pro' if (m.group(1) and 'pro' in m.group(1).lower())
             else 'Epix')
         )),

        # Instinct 2 / 2S / 3 / …
        (re.compile(r'instinct[\s\-]?(\d+)?(s|solar)?', re.I),
         lambda m: f"Instinct {m.group(1) or '2'}{(m.group(2) or '').upper()}"),

        # Vivoactive 4 / 5
        (re.compile(r'vi?voactive[\s\-]?(\d+)', re.I),
         lambda m: f"Vivoactive {m.group(1)}"),

        # Venu 3 / 3S
        (re.compile(r'venu[\s\-]?(\d+)?(s)?', re.I),
         lambda m: f"Venu {m.group(1) or '3'}{(m.group(2) or '').upper()}"),

        # Lily 2
        (re.compile(r'\blily[\s\-]?(\d+)?', re.I),
         lambda m: f"Lily {m.group(1) or '2'}"),
    ],

    'polar': [
        # Vantage V / V2 / V3 / M / M2
        (re.compile(r'vantage[\s\-]?(v|m)[\s\-]?(\d+)?', re.I),
         lambda m: f"Vantage {m.group(1).upper()}{m.group(2) or '3'}"),

        # Grit X / X2 / X2 Pro
        (re.compile(r'grit[\s\-]?x[\s\-]?(\d+)?(?:[\s\-]?(pro))?', re.I),
         lambda m: f"Grit X{m.group(1) or '2'}{' Pro' if m.group(2) else ''}"),

        # Pacer / Pacer Pro
        (re.compile(r'pacer(?:[\s\-]?(pro))?', re.I),
         lambda m: f"Pacer{' Pro' if m.group(1) else ''}"),

        # Ignite 3
        (re.compile(r'ignite[\s\-]?(\d+)', re.I),
         lambda m: f"Ignite {m.group(1)}"),
    ],

    'suunto': [
        # 固有名詞モデルを先に試みる（数字パターンより前に置く）
        # Vertical / Vertical Titanium
        (re.compile(r'vertical(?:[\s\-]?(titanium|steel))?', re.I),
         lambda m: f"Vertical{' ' + m.group(1).title() if m.group(1) else ''}"),

        # Race / Race Pro / Race S
        (re.compile(r'\brace(?:[\s\-]?(pro|s))?', re.I),
         lambda m: f"Race{' ' + m.group(1).title() if m.group(1) else ''}"),

        # Wing
        (re.compile(r'\bwing\b', re.I),
         lambda m: "Wing"),

        # Run / Run S
        (re.compile(r'\brun(?:[\s\-]?(s|pro))?\b', re.I),
         lambda m: f"Run{' ' + m.group(1).title() if m.group(1) else ''}"),

        # Suunto 9 Peak / 9 Peak Pro
        # 型番コード(SS050922000等)を避けるため "Suunto" を必須にし 1-2桁に限定する
        (re.compile(r'suunto[\s\-]?(\d{1,2})[\s\-]?(peak)?(?:[\s\-]?(pro))?', re.I),
         lambda m: (
             f"{m.group(1)}"
             + (' Peak' if m.group(2) else '')
             + (' Pro' if m.group(3) else '')
         )),
    ],

    'coros': [
        # APEX 2 / APEX 2 Pro
        (re.compile(r'apex[\s\-]?(\d+)?(?:[\s\-]?(pro))?', re.I),
         lambda m: f"Apex {m.group(1) or '2'}{' Pro' if m.group(2) else ''}"),

        # PACE 3
        (re.compile(r'pace[\s\-]?(\d+)', re.I),
         lambda m: f"Pace {m.group(1)}"),

        # VERTIX 2 / 2S
        (re.compile(r'vertix[\s\-]?(\d+)?(s)?', re.I),
         lambda m: f"Vertix {m.group(1) or '2'}{(m.group(2) or '').upper()}"),
    ],

    'apple': [
        # Apple Watch Ultra / Ultra 2
        (re.compile(r'watch[\s\-]?ultra[\s\-]?(\d+)?', re.I),
         lambda m: f"Watch Ultra {m.group(1) or '2'}"),

        # Apple Watch Series 9 / 10
        (re.compile(r'watch[\s\-]?series[\s\-]?(\d+)', re.I),
         lambda m: f"Watch Series {m.group(1)}"),

        # Apple Watch SE / SE 2
        (re.compile(r'watch[\s\-]?se[\s\-]?(\d+)?', re.I),
         lambda m: f"Watch SE{' ' + m.group(1) if m.group(1) else ''}"),
    ],

    'wahoo': [
        (re.compile(r'\brival\b', re.I),
         lambda m: "Rival"),
    ],

    'amazfit': [
        # Cheetah Pro / Cheetah Round
        (re.compile(r'cheetah(?:[\s\-]?(pro|round))?', re.I),
         lambda m: f"Cheetah{' ' + m.group(1).title() if m.group(1) else ''}"),
        # Balance / Balance 3 / Balance 2
        (re.compile(r'balance[\s\-]?(\d+)?', re.I),
         lambda m: f"Balance {m.group(1) or '3'}"),
        # GTR 4 / GTS 4
        (re.compile(r'g[tr]s?[\s\-]?(\d+)(?:[\s\-]?(mini|pro))?', re.I),
         lambda m: f"GT{m.group(0)[1].upper()} {m.group(1)}{' ' + m.group(2).title() if m.group(2) else ''}"),
        # T-Rex Ultra / Ultra 2
        (re.compile(r't[\-\s]?rex(?:[\s\-]?(ultra|pro))?(?:[\s\-]?(\d+))?', re.I),
         lambda m: f"T-Rex{' ' + m.group(1).title() if m.group(1) else ''}{' ' + m.group(2) if m.group(2) else ''}"),
    ],

    'epson': [
        (re.compile(r'sf[\s\-]?(\d+)(b)?', re.I),
         lambda m: f"SF-{m.group(1)}{(m.group(2) or '').upper()}"),
    ],

    # ── ランニングシューズ ────────────────────────────────────────────────
    'nike': [
        # カーボン系
        (re.compile(r'vapor[\s\-]?fly[\s\-]?(?:next[\s\-]?%[\s\-]?)?(\d+)?', re.I),
         lambda m: f"Vaporfly {m.group(1) or '4'}"),
        (re.compile(r'alpha[\s\-]?fly[\s\-]?(\d+)?', re.I),
         lambda m: f"Alphafly {m.group(1) or '3'}"),
        (re.compile(r'zoom[\s\-]?fly[\s\-]?(\d+)?', re.I),
         lambda m: f"Zoom Fly {m.group(1) or '6'}"),
        # 練習系
        (re.compile(r'pegasus[\s\-]?(\d+)|ペガサス[\s\-]?(\d+)', re.I),
         lambda m: f"Pegasus {m.group(1) or m.group(2)}"),
        (re.compile(r'vomero[\s\-]?(plus|\d+)?|ボメロ[\s\-]?(プラス|\d+)?', re.I),
         lambda m: (
             f"Vomero {m.group(1)}" if (m.group(1) and m.group(1).isdigit())
             else ("Vomero Plus" if (m.group(1) and 'plus' in m.group(1).lower()) or m.group(2) == 'プラス'
             else (f"Vomero {m.group(2)}" if m.group(2) and m.group(2).isdigit()
             else "Vomero Plus"))
         )),
        (re.compile(r'invincible[\s\-]?(\d+)?|インビンシブル', re.I),
         lambda m: f"Invincible {m.group(1) or '4'}"),
        (re.compile(r'react[\s\-]?infinity[\s\-]?run[\s\-]?(\d+)?', re.I),
         lambda m: f"React Infinity Run {m.group(1) or '4'}"),
    ],

    'asics': [
        # カーボン系
        (re.compile(r'magic[\s\-]?speed[\s\-]?(\d+)?|マジックスピード[\s\-]?(\d+)?', re.I),
         lambda m: f"Magic Speed {m.group(1) or m.group(2) or '5'}"),
        (re.compile(r'meta[\s\-]?speed[\s\-]?(sky|edge)(?:[\s\-]?(paris|\d+))?|メタスピード[\s\-]?(スカイ|エッジ)', re.I),
         lambda m: f"Metaspeed {(m.group(1) or '').title() or 'Sky'}"),
        (re.compile(r'super[\s\-]?blast[\s\-]?(\d+)?|スーパーブラスト', re.I),
         lambda m: f"Superblast {m.group(1) or '2'}"),
        # テンポ系
        (re.compile(r'evo[\s\-]?ride[\s\-]?(?:speed[\s\-]?)?(\d+)?|エボライドスピード', re.I),
         lambda m: f"Evoride Speed {m.group(1) or '2'}"),
        # 練習系
        (re.compile(r'nova[\s\-]?blast[\s\-]?(\d+)?|ノバブラスト[\s\-]?(\d+)?', re.I),
         lambda m: f"Nova Blast {m.group(1) or m.group(2) or '5'}"),
        (re.compile(r'gel[\s\-]?nimbus[\s\-]?(\d+)?|ゲルニンバス[\s\-]?(\d+)?', re.I),
         lambda m: f"Gel-Nimbus {m.group(1) or m.group(2) or '26'}"),
        (re.compile(r'gel[\s\-]?kayano[\s\-]?(\d+)?|ゲルカヤノ[\s\-]?(\d+)?|カヤノ[\s\-]?(\d+)', re.I),
         lambda m: f"Gel-Kayano {m.group(1) or m.group(2) or m.group(3) or '31'}"),
        (re.compile(r'gel[\s\-]?cumulus[\s\-]?(\d+)?|ゲルキュムラス', re.I),
         lambda m: f"Gel-Cumulus {m.group(1) or '26'}"),
        (re.compile(r'gel[\s\-]?rocket[\s\-]?(\d+)?', re.I),
         lambda m: f"Gel-Rocket {m.group(1) or '11'}"),
    ],

    'adidas': [
        (re.compile(r'adizero[\s\-]?adios[\s\-]?pro[\s\-]?(\d+)?', re.I),
         lambda m: f"Adizero Adios Pro {m.group(1) or '3'}"),
        (re.compile(r'adizero[\s\-]?boston[\s\-]?(\d+)?', re.I),
         lambda m: f"Adizero Boston {m.group(1) or '12'}"),
        (re.compile(r'adizero[\s\-]?sl[\s\-]?(\d+)?', re.I),
         lambda m: f"Adizero SL {m.group(1) or '2'}"),
        (re.compile(r'supernova[\s\-]?(rise|stride)?[\s\-]?(\d+)?', re.I),
         lambda m: f"Supernova{' ' + m.group(1).title() if m.group(1) else ''} {m.group(2) or ''}".strip()),
        (re.compile(r'ultra[\s\-]?boost[\s\-]?(\d+)?', re.I),
         lambda m: f"Ultraboost {m.group(1) or '24'}"),
    ],

    'new_balance': [
        (re.compile(r'fuel[\s\-]?cell[\s\-]?super[\s\-]?comp(?:[\s\-]?trainer)?[\s\-]?v?(\d+)?', re.I),
         lambda m: f"FuelCell SuperComp Trainer v{m.group(1) or '3'}"),
        (re.compile(r'fuel[\s\-]?cell[\s\-]?rebel[\s\-]?v?(\d+)?', re.I),
         lambda m: f"FuelCell Rebel v{m.group(1) or '4'}"),
        (re.compile(r'fuel[\s\-]?cell[\s\-]?propel[\s\-]?v?(\d+)?', re.I),
         lambda m: f"FuelCell Propel v{m.group(1) or '4'}"),
        (re.compile(r'fresh[\s\-]?foam[\s\-]?x?[\s\-]?(\d{3,4})', re.I),
         lambda m: f"Fresh Foam X {m.group(1)}"),
        (re.compile(r'\b(1080|880|860|840)\b', re.I),
         lambda m: f"Fresh Foam X {m.group(1)}"),
    ],

    'hoka': [
        (re.compile(r'rocket[\s\-]?x[\s\-]?(\d+)?|ロケット[\s\-]?x[\s\-]?(\d+)?', re.I),
         lambda m: f"Rocket X {m.group(1) or m.group(2) or '3'}"),
        (re.compile(r'mach[\s\-]?(\d+)|マッハ[\s\-]?(\d+)', re.I),
         lambda m: f"Mach {m.group(1) or m.group(2) or '6'}"),
        (re.compile(r'rincon[\s\-]?(\d+)|リンコン[\s\-]?(\d+)', re.I),
         lambda m: f"Rincon {m.group(1) or m.group(2)}"),
        (re.compile(r'clifton[\s\-]?(\d+)|クリフトン[\s\-]?(\d+)', re.I),
         lambda m: f"Clifton {m.group(1) or m.group(2)}"),
        (re.compile(r'bondi[\s\-]?(\d+)|ボンダイ[\s\-]?(\d+)', re.I),
         lambda m: f"Bondi {m.group(1) or m.group(2)}"),
        (re.compile(r'speed[\s\-]?goat[\s\-]?(\d+)|スピードゴート[\s\-]?(\d+)', re.I),
         lambda m: f"Speedgoat {m.group(1) or m.group(2)}"),
        (re.compile(r'torrent[\s\-]?(\d+)', re.I),
         lambda m: f"Torrent {m.group(1)}"),
        (re.compile(r'carbon[\s\-]?x[\s\-]?(\d+)?', re.I),
         lambda m: f"Carbon X {m.group(1) or '3'}"),
    ],

    'on_running': [
        (re.compile(r'cloud[\s\-]?boom[\s\-]?echo[\s\-]?(\d+)?|クラウドブーム[\s\-]?エコー[\s\-]?(\d+)?', re.I),
         lambda m: f"Cloudboom Echo {m.group(1) or m.group(2) or '3'}"),
        (re.compile(r'cloud[\s\-]?monster(?:[\s\-]?hyper)?|クラウドモンスター(?:[\s\-]?ハイパー)?', re.I),
         lambda m: "Cloudmonster Hyper" if ('hyper' in m.group(0).lower() or 'ハイパー' in m.group(0)) else "Cloudmonster"),
        (re.compile(r'cloud[\s\-]?surfer[\s\-]?(\d+)?|クラウドサーファー[\s\-]?(\d+)?', re.I),
         lambda m: f"Cloudsurfer {m.group(1) or m.group(2) or ''}".strip()),
        (re.compile(r'cloud[\s\-]?5|クラウド[\s\-]?5', re.I),
         lambda m: "Cloud 5"),
        (re.compile(r'cloud[\s\-]?swift[\s\-]?(\d+)?|クラウドスウィフト[\s\-]?(\d+)?', re.I),
         lambda m: f"Cloudswift {m.group(1) or m.group(2) or '3'}"),
    ],

    'mizuno': [
        (re.compile(r'wave[\s\-]?rebel(?:ion)?[\s\-]?pro[\s\-]?(\d+)?', re.I),
         lambda m: f"Wave Rebellion Pro {m.group(1) or '2'}"),
        (re.compile(r'wave[\s\-]?shadow[\s\-]?(\d+)', re.I),
         lambda m: f"Wave Shadow {m.group(1)}"),
        (re.compile(r'wave[\s\-]?rider[\s\-]?(\d+)', re.I),
         lambda m: f"Wave Rider {m.group(1)}"),
        (re.compile(r'wave[\s\-]?inspire[\s\-]?(\d+)', re.I),
         lambda m: f"Wave Inspire {m.group(1)}"),
        (re.compile(r'wave[\s\-]?sky[\s\-]?(\d+)', re.I),
         lambda m: f"Wave Sky {m.group(1)}"),
        (re.compile(r'neo[\s\-]?vista[\s\-]?(\d+)?', re.I),
         lambda m: f"Neo Vista {m.group(1) or ''}".strip()),
    ],

    'brooks': [
        (re.compile(r'hyperion[\s\-]?max[\s\-]?(\d+)?', re.I),
         lambda m: f"Hyperion Max {m.group(1) or '2'}"),
        (re.compile(r'ghost[\s\-]?(\d+)', re.I),
         lambda m: f"Ghost {m.group(1)}"),
        (re.compile(r'adrenaline[\s\-]?gts[\s\-]?(\d+)', re.I),
         lambda m: f"Adrenaline GTS {m.group(1)}"),
        (re.compile(r'glycerin[\s\-]?(\d+)', re.I),
         lambda m: f"Glycerin {m.group(1)}"),
    ],

    'saucony': [
        (re.compile(r'endorphin[\s\-]?pro[\s\-]?(\d+)?', re.I),
         lambda m: f"Endorphin Pro {m.group(1) or '4'}"),
        (re.compile(r'endorphin[\s\-]?speed[\s\-]?(\d+)?', re.I),
         lambda m: f"Endorphin Speed {m.group(1) or '4'}"),
        (re.compile(r'kinvara[\s\-]?(\d+)', re.I),
         lambda m: f"Kinvara {m.group(1)}"),
        (re.compile(r'ride[\s\-]?(\d+)', re.I),
         lambda m: f"Ride {m.group(1)}"),
        (re.compile(r'triumph[\s\-]?(\d+)', re.I),
         lambda m: f"Triumph {m.group(1)}"),
    ],

    'puma': [
        (re.compile(r'deviate[\s\-]?nitro[\s\-]?elite[\s\-]?(\d+)?', re.I),
         lambda m: f"Deviate Nitro Elite {m.group(1) or '3'}"),
        (re.compile(r'velocity[\s\-]?nitro[\s\-]?(\d+)?', re.I),
         lambda m: f"Velocity Nitro {m.group(1) or '3'}"),
        (re.compile(r'magnify[\s\-]?nitro[\s\-]?(\d+)?', re.I),
         lambda m: f"Magnify Nitro {m.group(1) or '2'}"),
        (re.compile(r'fast[\s\-]?r[\s\-]?nitro[\s\-]?elite[\s\-]?(\d+)?', re.I),
         lambda m: f"Fast-R Nitro Elite {m.group(1) or '2'}"),
    ],

    'salomon': [
        (re.compile(r's[\s\-]?lab[\s\-]?(sense|ultra|speed)?[\s\-]?(\d+)?', re.I),
         lambda m: f"S/Lab {(m.group(1) or '').title()} {m.group(2) or ''}".strip()),
        (re.compile(r'speed[\s\-]?cross[\s\-]?(\d+)', re.I),
         lambda m: f"Speedcross {m.group(1)}"),
        (re.compile(r'ultra[\s\-]?glide[\s\-]?(\d+)?', re.I),
         lambda m: f"Ultra Glide {m.group(1) or '3'}"),
        (re.compile(r'pulsar[\s\-]?trail[\s\-]?(\d+)?', re.I),
         lambda m: f"Pulsar Trail {m.group(1) or '3'}"),
    ],

    'altra': [
        (re.compile(r'vanish[\s\-]?carbon[\s\-]?(\d+)?', re.I),
         lambda m: f"Vanish Carbon {m.group(1) or '2'}"),
        (re.compile(r'escalante[\s\-]?racer[\s\-]?(\d+)?', re.I),
         lambda m: f"Escalante Racer {m.group(1) or '25'}"),
        (re.compile(r'torin[\s\-]?(\d+)', re.I),
         lambda m: f"Torin {m.group(1)}"),
        (re.compile(r'lone[\s\-]?peak[\s\-]?(\d+)', re.I),
         lambda m: f"Lone Peak {m.group(1)}"),
    ],
}


def normalize(item_name: str, genre_key: str = 'running_watch'):
    """
    item_name を正規化し結果を返す。

    Returns:
        (product_id, brand_key, brand_display, model_name)
        マッチしない場合は (None, None, None, None)
    """
    clean = _clean(item_name)

    # ブランドはノイズ除去前の原文でも試みる（括弧内英語が唯一の手がかりの場合）
    brand_key, brand_display = _detect_brand(clean)
    if brand_key is None:
        brand_key, brand_display = _detect_brand(item_name)
    if brand_key is None:
        return None, None, None, None

    rules = _MODEL_RULES.get(brand_key, [])
    for pat, name_fn in rules:
        m = pat.search(clean)
        if m:
            try:
                model_name = name_fn(m)
            except Exception:
                continue
            product_id = f"{brand_key}/{_slug(model_name)}"
            return product_id, brand_key, brand_display, model_name

    # ブランドは分かったがモデルが抽出できなかった場合は brand_key のみ返す
    return None, brand_key, brand_display, None
