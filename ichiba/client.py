import time

import requests

from ichiba.config import MAX_RETRIES, PAGE_SIZE, PAGES_PER_GENRE, RANKING_URL, REQUEST_INTERVAL, RETRY_BACKOFF


class IchibaApiError(RuntimeError):
    pass


def _request(url, params, origin):
    headers = {"Origin": origin, "Referer": origin + "/"}
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=15)
            data = r.json()
        except (requests.exceptions.RequestException, ValueError) as e:
            last_error = e
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF)
            continue
        if "errors" in data:
            raise IchibaApiError(f"APIエラー: {data['errors']}")
        return data
    raise IchibaApiError(f"通信エラー({MAX_RETRIES}回リトライ失敗): {last_error}")


def _normalize(raw_item):
    # レスポンスは {"Item": {...}} または直接 {...} の可能性があるため両対応
    item = raw_item.get("Item", raw_item)
    images = item.get("smallImageUrls") or []
    image_url = images[0].get("imageUrl", "") if images else ""
    return {
        "rank":           item.get("rank"),
        "item_code":      item.get("itemCode", ""),
        "item_name":      item.get("itemName", ""),
        "item_caption":   item.get("itemCaption", ""),
        "item_price":     item.get("itemPrice"),
        "item_url":       item.get("itemUrl", ""),
        "affiliate_url":  item.get("affiliateUrl", ""),
        "image_url":      image_url,
        "shop_name":      item.get("shopName", ""),
        "shop_code":      item.get("shopCode", ""),
        "review_count":   item.get("reviewCount"),
        "review_average": item.get("reviewAverage"),
        "point_rate":     item.get("pointRate"),
    }


def fetch_ranking(app_id, access_key, origin, genre_id,
                  affiliate_id=None,
                  pages=PAGES_PER_GENRE, hits=PAGE_SIZE):
    """指定ジャンルの上位ランキングをまとめて取得し、正規化済みのリストを返す。"""
    items = []
    for page in range(1, pages + 1):
        if page > 1:
            time.sleep(REQUEST_INTERVAL)
        params = {
            "applicationId": app_id,
            "accessKey":     access_key,
            "format":        "json",
            "genreId":       genre_id,
            "page":          page,
            "hits":          hits,
        }
        if affiliate_id:
            params["affiliateId"] = affiliate_id
        data = _request(RANKING_URL, params, origin)
        for raw in data.get("Items", []):
            items.append(_normalize(raw))
    return items
