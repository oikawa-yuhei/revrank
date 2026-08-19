"""note.com ハッシュタグスクレイパー。

指定したハッシュタグの新着記事を取得し、商品言及を抽出する。
差分取得: 前回の取得日時以降に公開された記事のみ処理する。

対象ハッシュタグ (ichiba/config.py の NOTE_HASHTAGS で管理):
  ランニングシューズ, ガーミン, GPSウォッチ, カーボンシューズ, etc.
"""
import re
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from community.extract import extract_mentions

BASE     = "https://note.com"
INTERVAL = 2.0
HEADERS  = {"User-Agent": "Mozilla/5.0 (compatible; RunGearArchive/1.0)"}
SOURCE_KEY = "note_hashtag"

# 取得するハッシュタグ (ランニングギアに関連するもの)
HASHTAGS = [
    # ── ギア ─────────────────────────────────────────────────
    "ランニングシューズ",
    "カーボンシューズ",
    "厚底シューズ",
    "ガーミン",
    "GPSウォッチ",
    "ランニングウォッチ",
    "ランニングギア",
    "トレイルラン",
    "マラソン",
    # ── 書籍 ─────────────────────────────────────────────────
    "ランニング本",
    "読書記録",      # #読書記録 は大量にある（スポーツ本も混在）
    "ランナーおすすめ",
]


def _get(url):
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r


def _parse_article_links(soup: BeautifulSoup) -> list[str]:
    """ハッシュタグ一覧から記事URLを抽出する。"""
    urls = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        # 絶対URL: https://note.com/username/n/xxx
        if re.match(r"^https://note\.com/[^/]+/n/[a-z0-9]+$", href):
            urls.append(href)
        # 相対URL: /username/n/xxx (フォールバック)
        elif re.match(r"^/[^/]+/n/[a-z0-9]+$", href):
            urls.append(BASE + href)
    return list(dict.fromkeys(urls))   # 重複除去・順序保持


def _parse_pub_date(soup: BeautifulSoup) -> datetime | None:
    """記事の公開日時を取得する。"""
    # <time datetime="2026-08-13T10:00:00+09:00"> 等
    tag = soup.find("time", datetime=True)
    if tag:
        try:
            return datetime.fromisoformat(tag["datetime"])
        except ValueError:
            pass
    return None


def _fetch_article_text(url: str) -> tuple[str, datetime | None]:
    """記事本文と公開日時を返す。"""
    try:
        r = _get(url)
    except requests.RequestException:
        return "", None

    soup = BeautifulSoup(r.text, "html.parser")
    pub_date = _parse_pub_date(soup)

    # 本文テキストを抽出 (noteの本文は class="note-common-styles__textnote-body" 等)
    body = (
        soup.find("div", class_=re.compile(r"note-body|textnote|article", re.I))
        or soup.find("article")
        or soup.find("main")
    )
    text = body.get_text(separator="\n", strip=True) if body else ""
    return text, pub_date


def collect(last_fetched: str, hashtags: list[str] = HASHTAGS) -> tuple[list[dict], str]:
    """
    新着記事を収集し、言及リストと新しい last_fetched 日時を返す。

    Args:
        last_fetched: ISO 8601 形式の最終取得日時 ("2026-08-01T00:00:00+09:00")

    Returns:
        (mentions, new_last_fetched)
    """
    try:
        cutoff = datetime.fromisoformat(last_fetched)
    except ValueError:
        cutoff = datetime(2020, 1, 1, tzinfo=timezone.utc)

    all_mentions: list[dict] = []
    processed_urls: set[str] = set()
    newest_dt = cutoff

    for hashtag in hashtags:
        tag_url = f"{BASE}/hashtag/{hashtag}"
        print(f"  [note] #{hashtag}")

        try:
            r = _get(tag_url)
        except requests.RequestException as e:
            print(f"    [WARN] {e}")
            continue

        soup = BeautifulSoup(r.text, "html.parser")
        article_urls = _parse_article_links(soup)

        for url in article_urls:
            if url in processed_urls:
                continue
            processed_urls.add(url)

            time.sleep(INTERVAL)
            text, pub_date = _fetch_article_text(url)

            # note.com は新着順なので cutoff より古い記事が出たらそれ以降はスキップ
            if pub_date and pub_date <= cutoff:
                break

            if pub_date and pub_date > newest_dt:
                newest_dt = pub_date

            for m in extract_mentions(text):
                all_mentions.append({
                    "source":      SOURCE_KEY,
                    "source_url":  url,
                    "product_id":  m["product_id"],
                    "brand_key":   m["brand_key"],
                    "model_name":  m["model_name"],
                    "raw_mention": m["raw_mention"],
                })

        time.sleep(INTERVAL)

    new_last_fetched = newest_dt.isoformat() if newest_dt != cutoff else last_fetched
    return all_mentions, new_last_fetched
