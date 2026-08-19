"""Yahoo!知恵袋 スクレイパー。

ランニング関連キーワードで検索し、Q&A から商品言及を抽出する。
差分取得: 検索キーワードごとに最後に見た question_id を記録する。
"""
import re
import time
import requests
from bs4 import BeautifulSoup

from community.extract import extract_mentions

SOURCE_KEY  = "chiebukuro"
DETAIL_BASE = "https://detail.chiebukuro.yahoo.co.jp"
YAHOO_SEARCH = "https://search.yahoo.co.jp/search"
INTERVAL    = 2.0
HEADERS     = {"User-Agent": "Mozilla/5.0 (compatible; RunGearArchive/1.0)"}

SEARCH_QUERIES = [
    "ランニングシューズ おすすめ",
    "カーボンシューズ おすすめ",
    "厚底シューズ おすすめ",
    "マラソン シューズ",
    "ガーミン ランニングウォッチ",
    "GPSウォッチ おすすめ",
    "ランニング 本 おすすめ",
    "トレイルラン シューズ",
]


def _get(url, params=None):
    r = requests.get(url, params=params, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r


def _search_ids(query: str, pages: int = 3) -> list[str]:
    """Yahoo 検索経由で chiebukuro の question_id リストを返す。"""
    ids = []
    site_query = f"{query} site:detail.chiebukuro.yahoo.co.jp"
    for page in range(1, pages + 1):
        params = {"p": site_query, "b": (page - 1) * 10 + 1}
        try:
            r = _get(YAHOO_SEARCH, params=params)
        except requests.RequestException:
            break
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            m = re.search(r"/qa/question_detail/(q\d+)", href)
            if m:
                ids.append(m.group(1))
        time.sleep(INTERVAL)
    return list(dict.fromkeys(ids))


def _fetch_qa_text(qid: str) -> str:
    """質問 + 回答の本文テキストを返す。"""
    url = f"{DETAIL_BASE}/qa/question_detail/{qid}"
    try:
        r = _get(url)
    except requests.RequestException:
        return ""
    soup = BeautifulSoup(r.text, "html.parser")

    texts = []
    # 質問本文
    for tag in soup.find_all(class_=re.compile(r"question|QuestionDetailQuestion", re.I)):
        t = tag.get_text(separator=" ", strip=True)
        if t:
            texts.append(t)
    # ベストアンサー・回答
    for tag in soup.find_all(class_=re.compile(r"answer|Answer|bestanswer|BestAnswer", re.I)):
        t = tag.get_text(separator=" ", strip=True)
        if t:
            texts.append(t)

    # フォールバック
    if not texts:
        main = soup.find("main") or soup.find("body")
        if main:
            texts = [main.get_text(separator=" ", strip=True)]

    return "\n".join(texts)


def collect(seen_ids: dict, queries: list[str] = SEARCH_QUERIES
            ) -> tuple[list[dict], dict]:
    """
    新着 Q&A から言及を収集する。

    Args:
        seen_ids: {query: {qid, ...}} — 処理済み question_id のセット

    Returns:
        (mentions, new_seen_ids)
    """
    all_mentions: list[dict] = []
    new_seen = {q: set(v) for q, v in seen_ids.items()}

    for query in queries:
        print(f"  [知恵袋] {query}")
        known = new_seen.get(query, set())
        ids = _search_ids(query)

        new_ids = [i for i in ids if i not in known]
        if not new_ids:
            continue

        for qid in new_ids:
            time.sleep(INTERVAL)
            text = _fetch_qa_text(qid)
            qa_url = f"{DETAIL_BASE}/qa/question_detail/{qid}"

            for m in extract_mentions(text):
                all_mentions.append({
                    "source":      SOURCE_KEY,
                    "source_url":  qa_url,
                    "product_id":  m["product_id"],
                    "brand_key":   m["brand_key"],
                    "model_name":  m["model_name"],
                    "raw_mention": m["raw_mention"],
                })

            known.add(qid)

        new_seen[query] = known

    # セットは JSON 非対応なのでリストに変換
    return all_mentions, {q: list(v) for q, v in new_seen.items()}
