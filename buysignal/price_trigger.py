"""スパイク発生商品の楽天最安値を取得し price_logs に保存する。

トリガー型: スパイクした商品 + 固定上位N商品 のみ API を呼び出す。
商品数に依存しない O(spike + top_n) のAPI呼び出し。
"""
import os
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timezone

import requests

from ichiba.config import DB_PATH
from buysignal.config import FIXED_PRICE_CHECK_TOP_N

RAKUTEN_ITEM_SEARCH = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701"
INTERVAL = 1.5


def _product_id_to_keyword(product_id: str) -> str:
    """product_id スラッグを楽天検索キーワードに変換する。

    asics/gel-kayano-31   → 'ASICS gel kayano 31'
    on_running/cloudmonster → 'On Running cloudmonster'
    garmin/forerunner-570  → 'Garmin forerunner 570'
    """
    parts = product_id.split("/", 1)
    brand = parts[0].replace("_", " ").title()
    model = parts[1].replace("-", " ") if len(parts) > 1 else ""
    return f"{brand} {model}".strip()


def _search_rakuten(keyword: str, app_id: str, access_key: str,
                    origin: str, affiliate_id: str = "") -> dict | None:
    """楽天 IchibaItem/Search で最安値アイテムを1件返す。

    2026年2月のAPI移行によりaccessKey + Origin/Refererヘッダが必須。
    (ichiba/client.py の fetch_ranking と同じ認証方式)
    """
    params: dict = {
        "applicationId": app_id,
        "accessKey":     access_key,
        "keyword":       keyword,
        "sort":          "+itemPrice",
        "hits":          3,
        "format":        "json",
    }
    if affiliate_id:
        params["affiliateId"] = affiliate_id
    headers = {"Origin": origin, "Referer": origin + "/"}
    try:
        r = requests.get(RAKUTEN_ITEM_SEARCH, params=params,
                         headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"    [WARN] 楽天API失敗 ({keyword}): {e}")
        return None

    items = data.get("Items", [])
    if not items:
        return None
    item = items[0].get("Item", items[0])
    return {
        "price":         item.get("itemPrice"),
        "item_name":     item.get("itemName", ""),
        "item_code":     item.get("itemCode", ""),
        "affiliate_url": item.get("affiliateUrl", "") or item.get("itemUrl", ""),
    }


def run(target_date: str | None = None) -> int:
    """スパイク商品 + 固定上位商品の楽天価格を取得し price_logs に保存する。"""
    from buysignal.buzz_score import get_spiked_products, get_top_products

    app_id       = os.environ.get("RAKUTEN_ICHIBA_APP_ID", "")
    access_key   = os.environ.get("RAKUTEN_ICHIBA_ACCESS_KEY", "")
    origin       = os.environ.get("RAKUTEN_ORIGIN", "")
    affiliate_id = os.environ.get("RAKUTEN_AFFILIATE_ID", "")
    if not app_id or not access_key or not origin:
        print("  [SKIP] RAKUTEN_ICHIBA_APP_ID / RAKUTEN_ICHIBA_ACCESS_KEY / RAKUTEN_ORIGIN が未設定")
        return 0

    spiked = get_spiked_products(target_date)
    top    = get_top_products(FIXED_PRICE_CHECK_TOP_N)
    targets = list(dict.fromkeys(spiked + top))

    print(f"  価格取得対象: スパイク {len(spiked)} 件 + 固定上位 {len(top)} 件"
          f" (重複除去後 {len(targets)} 件)")

    fetched_at = datetime.now(tz=timezone.utc).isoformat()
    saved = 0

    with closing(sqlite3.connect(DB_PATH)) as conn:
        for product_id in targets:
            keyword = _product_id_to_keyword(product_id)
            result = _search_rakuten(keyword, app_id, access_key, origin, affiliate_id)
            if result:
                conn.execute("""
                    INSERT INTO price_logs
                    (product_id, fetched_at, platform, price,
                     affiliate_url, item_name, item_code)
                    VALUES (?, ?, 'rakuten', ?, ?, ?, ?)
                """, (product_id, fetched_at,
                      result["price"], result["affiliate_url"],
                      result["item_name"], result["item_code"]))
                price_str = f"{result['price']:,}円" if result["price"] else "N/A"
                print(f"    {product_id:<38}  {price_str}")
                saved += 1
                conn.commit()  # 1件ごとにコミット。途中で落ちてもここまでの分は残る
            time.sleep(INTERVAL)

    print(f"  price_trigger: {saved}/{len(targets)} 件を記録")
    return saved
