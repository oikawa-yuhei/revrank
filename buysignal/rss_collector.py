"""ブログ / YouTube RSSフィード収集モジュール。

はてなブックマーク検索RSS・YouTubeチャンネルRSS・独自RSSフィードから
新着テキストを取得し、商品言及を抽出する。
"""
import calendar
import time
import urllib.parse
from datetime import datetime, timezone

import feedparser

from community.extract import extract_mentions

INTERVAL = 1.5
SOURCE_BLOG    = "rss_blog"
SOURCE_YOUTUBE = "rss_youtube"


def _parse_entry_date(entry) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            return datetime.fromtimestamp(calendar.timegm(t), tz=timezone.utc)
    return None


def _entry_to_mentions(entry, source_key: str) -> list[dict]:
    content_val = ""
    if hasattr(entry, "content") and entry.content:
        content_val = entry.content[0].get("value", "")
    text = " ".join(filter(None, [
        getattr(entry, "title",   ""),
        getattr(entry, "summary", ""),
        content_val,
    ]))
    url = getattr(entry, "link", "") or ""
    return [
        {
            "source":      source_key,
            "source_url":  url,
            "product_id":  m["product_id"],
            "brand_key":   m["brand_key"],
            "model_name":  m["model_name"],
            "raw_mention": m["raw_mention"],
        }
        for m in extract_mentions(text)
    ]


def collect_hatena(
    last_fetched: str,
    queries: list[str],
    template: str,
) -> tuple[list[dict], str]:
    """はてなブックマーク検索RSSから新着ブックマーク記事の言及を収集する。"""
    try:
        cutoff = datetime.fromisoformat(last_fetched)
    except ValueError:
        cutoff = datetime(2020, 1, 1, tzinfo=timezone.utc)

    all_mentions: list[dict] = []
    seen_urls: set[str] = set()
    newest_dt = cutoff

    for query in queries:
        url = template.format(query=urllib.parse.quote(query))
        print(f"  [RSS/はてな] {query}")
        try:
            feed = feedparser.parse(url)
        except Exception as e:
            print(f"    [WARN] {e}")
            time.sleep(INTERVAL)
            continue

        for entry in feed.entries:
            pub  = _parse_entry_date(entry)
            link = getattr(entry, "link", "")
            if not link or link in seen_urls:
                continue
            if pub and pub <= cutoff:
                continue
            seen_urls.add(link)
            if pub and pub > newest_dt:
                newest_dt = pub
            all_mentions.extend(_entry_to_mentions(entry, SOURCE_BLOG))

        time.sleep(INTERVAL)

    new_last = newest_dt.isoformat() if newest_dt != cutoff else last_fetched
    return all_mentions, new_last


def collect_youtube(
    last_fetched: str,
    channels: dict[str, str],
    template: str,
) -> tuple[list[dict], str]:
    """YouTubeチャンネルRSSから新着動画のタイトル・説明文を収集する。"""
    if not channels:
        return [], last_fetched

    try:
        cutoff = datetime.fromisoformat(last_fetched)
    except ValueError:
        cutoff = datetime(2020, 1, 1, tzinfo=timezone.utc)

    all_mentions: list[dict] = []
    newest_dt = cutoff

    for name, channel_id in channels.items():
        url = template.format(channel_id=channel_id)
        print(f"  [RSS/YouTube] {name}")
        try:
            feed = feedparser.parse(url)
        except Exception as e:
            print(f"    [WARN] {e}")
            time.sleep(INTERVAL)
            continue

        for entry in feed.entries:
            pub = _parse_entry_date(entry)
            if pub and pub <= cutoff:
                continue
            if pub and pub > newest_dt:
                newest_dt = pub
            all_mentions.extend(_entry_to_mentions(entry, SOURCE_YOUTUBE))

        time.sleep(INTERVAL)

    new_last = newest_dt.isoformat() if newest_dt != cutoff else last_fetched
    return all_mentions, new_last


def collect_custom(
    last_fetched: str,
    feeds: list[str],
) -> tuple[list[dict], str]:
    """任意のRSSフィードから新着記事の言及を収集する。"""
    if not feeds:
        return [], last_fetched

    try:
        cutoff = datetime.fromisoformat(last_fetched)
    except ValueError:
        cutoff = datetime(2020, 1, 1, tzinfo=timezone.utc)

    all_mentions: list[dict] = []
    newest_dt = cutoff

    for feed_url in feeds:
        print(f"  [RSS/custom] {feed_url}")
        try:
            feed = feedparser.parse(feed_url)
        except Exception as e:
            print(f"    [WARN] {e}")
            time.sleep(INTERVAL)
            continue

        for entry in feed.entries:
            pub = _parse_entry_date(entry)
            if pub and pub <= cutoff:
                continue
            if pub and pub > newest_dt:
                newest_dt = pub
            all_mentions.extend(_entry_to_mentions(entry, SOURCE_BLOG))

        time.sleep(INTERVAL)

    new_last = newest_dt.isoformat() if newest_dt != cutoff else last_fetched
    return all_mentions, new_last
