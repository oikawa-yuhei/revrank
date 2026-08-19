"""5ch スクレイパー。

ランニング・マラソン板の新着レスから商品言及を抽出する。
差分取得: スレッドごとに既読レス数を記録し、新着分のみ処理する。

対象板:
  - マラソン・駅伝板 https://mao.5ch.net/marathon/
"""
import re
import time
import requests
from bs4 import BeautifulSoup

from community.extract import extract_mentions

SOURCE_KEY = "fivech"
INTERVAL   = 2.0
HEADERS    = {"User-Agent": "Mozilla/5.0 (compatible; RunGearArchive/1.0)"}

BOARDS = [
    ("sports", "athletics"),  # 陸上競技板（ランニング・マラソン含む）
]

# ギア関連スレッドを優先的に検出するキーワード
GEAR_THREAD_KEYWORDS = re.compile(
    r'シューズ|靴|ウォッチ|時計|ガーミン|polar|coros|suunto|garmin'
    r'|nike|asics|hoka|adidas|アシックス|ナイキ|ホカ'
    r'|ランニング用品|ギア|装備|コンプレッション|タイツ'
    r'|ウェア|ザック|ベスト|ポール|サングラス'
    r'|サプリ|補給|ジェル|Born to Run|ダニエルズ|マフェトン',
    re.IGNORECASE,
)


def _get(url):
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r


def _fetch_thread_list(server: str, board: str) -> list[dict]:
    """板のスレッド一覧を取得する。[(thread_id, title, post_count), ...]"""
    url = f"https://{server}.5ch.net/{board}/"
    try:
        r = _get(url)
    except requests.RequestException as e:
        print(f"  [WARN] スレ一覧取得失敗 {url}: {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    threads = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        m = re.search(r"/test/read\.cgi/\w+/(\d+)/?", href)
        if not m:
            continue
        thread_id = int(m.group(1))
        title = a.get_text(strip=True)
        # スレタイ右隣の "(N)" からレス数を抽出
        count_m = re.search(r'\((\d+)\)', a.find_next_sibling(string=True) or "")
        post_count = int(count_m.group(1)) if count_m else 0
        threads.append({
            "thread_id":  thread_id,
            "title":      title,
            "post_count": post_count,
        })

    return threads


def _fetch_thread_posts(server: str, board: str, thread_id: int,
                        from_post: int = 1) -> list[str]:
    """スレッドの指定レス番以降の本文を取得する。"""
    url = (f"https://{server}.5ch.net/test/read.cgi/{board}/{thread_id}/"
           f"{from_post}-")
    try:
        r = _get(url)
    except requests.RequestException as e:
        print(f"    [WARN] スレ取得失敗 {thread_id}: {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    texts = []

    # 5ch の投稿本文は <div class="post"> > <div class="message"> 構造
    for post_div in soup.find_all("div", class_="post"):
        msg = post_div.find("div", class_="message")
        if msg:
            texts.append(msg.get_text(separator=" ", strip=True))

    # フォールバック: <dd> タグ (旧形式)
    if not texts:
        for dd in soup.find_all("dd"):
            t = dd.get_text(separator=" ", strip=True)
            if t:
                texts.append(t)

    return texts


def collect(thread_state: dict, boards: list[tuple] = BOARDS
            ) -> tuple[list[dict], dict]:
    """
    新着レスから言及を収集する。

    Args:
        thread_state: {thread_id_str: last_post_count} の辞書

    Returns:
        (mentions, new_thread_state)
    """
    all_mentions: list[dict] = []
    new_state = dict(thread_state)

    for server, board in boards:
        print(f"  [5ch] {server}.5ch.net/{board}/")
        threads = _fetch_thread_list(server, board)
        time.sleep(INTERVAL)

        for t in threads:
            tid   = t["thread_id"]
            title = t["title"]
            total = t["post_count"]
            tid_s = str(tid)

            known = thread_state.get(tid_s, 0)

            # ギア関連スレ or 既知スレ（過去に言及があったもの）の新着のみ
            is_gear = GEAR_THREAD_KEYWORDS.search(title)
            has_new = total > known

            if not (is_gear or (known > 0 and has_new)):
                continue
            if not has_new:
                continue

            from_post = max(1, known + 1)
            print(f"    {title[:40]}  ({known}→{total})")

            time.sleep(INTERVAL)
            posts = _fetch_thread_posts(server, board, tid, from_post)

            thread_url = f"https://{server}.5ch.net/test/read.cgi/{board}/{tid}/"

            for post_text in posts:
                for m in extract_mentions(post_text):
                    all_mentions.append({
                        "source":      SOURCE_KEY,
                        "source_url":  thread_url,
                        "product_id":  m["product_id"],
                        "brand_key":   m["brand_key"],
                        "model_name":  m["model_name"],
                        "raw_mention": m["raw_mention"],
                    })

            new_state[tid_s] = total

    return all_mentions, new_state
