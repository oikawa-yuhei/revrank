"""RUNNET ランナーの知恵袋スクレイパー。

新着投稿（質問＋回答）を取得し、商品言及を抽出する。
差分取得: 前回の最大 questionId 以降のみ処理する。
"""
import re
import time
import requests
from bs4 import BeautifulSoup

from community.extract import extract_mentions

BASE       = "https://runnet.jp"
LIST_URL   = BASE + "/community/chiebukuro/"
DETAIL_URL = BASE + "/community/chiebukuro/questionContentsAction.do"
INTERVAL   = 1.5   # リクエスト間隔 (秒)
HEADERS    = {"User-Agent": "Mozilla/5.0 (compatible; RunGearArchive/1.0)"}
SOURCE_KEY = "runnet_chie"


def _get(url, params=None):
    r = requests.get(url, params=params, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r


def fetch_new_posts(last_id: int = 0, max_pages: int = 10) -> list[dict]:
    """
    last_id より新しい投稿を取得する。

    Returns:
        [{"source_url": str, "question_id": int, "text": str}, ...]
    """
    posts = []

    for page in range(1, max_pages + 1):
        try:
            r = _get(LIST_URL, params={"page": page} if page > 1 else None)
        except requests.RequestException as e:
            print(f"  [WARN] 一覧取得失敗 page={page}: {e}")
            break

        soup = BeautifulSoup(r.text, "html.parser")
        ids_on_page = _parse_list_ids(soup)

        if not ids_on_page:
            break

        # last_id 以下のものが出たらここで止める
        new_ids = [i for i in ids_on_page if i > last_id]
        if not new_ids:
            break

        for qid in new_ids:
            time.sleep(INTERVAL)
            try:
                text = _fetch_detail(qid)
            except Exception as e:
                print(f"  [WARN] 詳細取得失敗 id={qid}: {e}")
                continue

            posts.append({
                "source_url":  f"{DETAIL_URL}?command=init&&questionId={qid}",
                "question_id": qid,
                "text":        text,
            })

        # ページ上の全 ID が new_ids だった場合のみ次ページへ
        if len(new_ids) < len(ids_on_page):
            break

        time.sleep(INTERVAL)

    return posts


def _parse_list_ids(soup: BeautifulSoup) -> list[int]:
    """一覧ページから questionId を抽出する。"""
    ids = []
    for a in soup.find_all("a", href=True):
        m = re.search(r"questionId=(\d+)", a["href"])
        if m:
            ids.append(int(m.group(1)))
    return sorted(set(ids), reverse=True)


def _fetch_detail(qid: int) -> str:
    """投稿詳細ページから質問＋回答テキストを結合して返す。"""
    r = _get(DETAIL_URL, params={"command": "init", "questionId": qid})
    soup = BeautifulSoup(r.text, "html.parser")

    texts = []
    # 質問本文と回答本文を含む可能性が高いセレクタ群
    for tag in soup.find_all(["p", "div"], class_=re.compile(r"(question|answer|content|body|text)", re.I)):
        t = tag.get_text(separator=" ", strip=True)
        if t:
            texts.append(t)

    # フォールバック: body 全文
    if not texts:
        body = soup.find("body")
        texts = [body.get_text(separator=" ", strip=True)] if body else []

    return "\n".join(texts)


def collect(last_id: int, max_pages: int | None = None) -> tuple[list[dict], int]:
    """
    新着投稿を収集し、言及リストと新しい max_id を返す。

    Returns:
        (mentions, new_max_id)
        mentions: [{"source": str, "source_url": str, "product_id": str,
                    "brand_key": str, "raw_mention": str}, ...]
    """
    posts = fetch_new_posts(last_id, max_pages=max_pages or 10)
    if not posts:
        return [], last_id

    new_max_id = max(p["question_id"] for p in posts)
    mentions = []

    for post in posts:
        for m in extract_mentions(post["text"]):
            mentions.append({
                "source":      SOURCE_KEY,
                "source_url":  post["source_url"],
                "product_id":  m["product_id"],
                "brand_key":   m["brand_key"],
                "model_name":  m["model_name"],
                "raw_mention": m["raw_mention"],
            })

    return mentions, new_max_id
