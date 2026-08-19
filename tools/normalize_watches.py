"""GPSウォッチ 名寄せランナー (Phase 3-1)。

item_rankings の running_watch データを読み込み:
  1. 商品名を正規化して product_id を割り当て
  2. products テーブルに登録
  3. rakuten_items テーブルを upsert して product_id を紐付け

使い方:
    python tools/normalize_watches.py --dry-run   # 確認のみ（DB 書き込みなし）
    python tools/normalize_watches.py              # 実行
"""
import argparse
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ichiba.config import DB_PATH
from ichiba.normalize import normalize

GENRE_KEY = 'running_watch'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='DB 書き込みをスキップ')
    args = parser.parse_args()

    with closing(sqlite3.connect(DB_PATH)) as conn:
        rows = conn.execute("""
            SELECT DISTINCT ir.item_code, ir.item_name,
                   ir.item_url, ir.affiliate_url, ir.image_url,
                   ir.shop_code, ir.shop_name
            FROM item_rankings ir
            WHERE ir.genre_key = ?
        """, (GENRE_KEY,)).fetchall()

    if not rows:
        print("データなし。fetch_ranking.py を先に実行してください。")
        return

    print(f"対象: {len(rows)} 出品 (genre_key={GENRE_KEY})")

    # 名寄せ処理
    matched: dict[str, dict] = {}   # product_id -> {meta, items}
    unmatched_model: list[tuple] = []  # ブランドは分かったがモデル未抽出
    unmatched_brand: list[tuple] = []  # ブランドも不明

    for item_code, item_name, item_url, affiliate_url, image_url, shop_code, shop_name in rows:
        product_id, brand_key, brand_display, model_name = normalize(item_name, GENRE_KEY)

        item = {
            'item_code':     item_code,
            'item_name':     item_name,
            'item_url':      item_url,
            'affiliate_url': affiliate_url,
            'image_url':     image_url,
            'shop_code':     shop_code,
            'shop_name':     shop_name,
        }

        if product_id:
            if product_id not in matched:
                matched[product_id] = {
                    'brand_key':     brand_key,
                    'brand_display': brand_display,
                    'model_name':    model_name,
                    'items':         [],
                }
            matched[product_id]['items'].append(item)
        elif brand_key:
            unmatched_model.append((item_code, item_name, brand_key))
        else:
            unmatched_brand.append((item_code, item_name))

    # ── レポート ──────────────────────────────────────────────────────────
    total_listings = sum(len(v['items']) for v in matched.values())
    coverage = total_listings / len(rows) * 100 if rows else 0

    print(f"\n■ 名寄せ結果")
    print(f"  正規化済み商品: {len(matched)} 種")
    print(f"  紐付き出品数:   {total_listings} / {len(rows)} ({coverage:.0f}%)")
    print(f"  モデル未抽出:   {len(unmatched_model)} 件（ブランドは判明）")
    print(f"  ブランド不明:   {len(unmatched_brand)} 件")

    # ブランドごとに整理して表示
    from collections import defaultdict
    by_brand: dict[str, list] = defaultdict(list)
    for pid, info in sorted(matched.items()):
        by_brand[info['brand_display']].append((pid, info))

    print()
    for brand, products in sorted(by_brand.items()):
        print(f"  [{brand}]")
        for pid, info in sorted(products):
            shops = ', '.join({i['shop_name'][:12] for i in info['items'][:3]})
            print(f"    {pid:<40}  {len(info['items'])} 出品  ({shops})")

    if unmatched_model:
        print(f"\n■ モデル未抽出（先頭15件）— ルール追加を検討")
        for item_code, item_name, brand_key in unmatched_model[:15]:
            print(f"  [{brand_key}]  {item_name[:70]}")

    if unmatched_brand:
        print(f"\n■ ブランド不明（先頭10件）— ブランド辞書への追加を検討")
        for item_code, item_name in unmatched_brand[:10]:
            print(f"  {item_name[:70]}")

    if args.dry_run:
        print("\n--dry-run: DB 書き込みをスキップ")
        return

    # ── DB 書き込み ───────────────────────────────────────────────────────
    with closing(sqlite3.connect(DB_PATH)) as conn:
        inserted_products  = 0
        upserted_items     = 0

        for product_id, info in matched.items():
            result = conn.execute("""
                INSERT OR IGNORE INTO products
                (product_id, brand, model_name, genre_key)
                VALUES (?, ?, ?, ?)
            """, (product_id, info['brand_display'], info['model_name'], GENRE_KEY))
            inserted_products += result.rowcount

            for item in info['items']:
                conn.execute("""
                    INSERT OR REPLACE INTO rakuten_items
                    (item_code, product_id, genre_key,
                     item_name, item_url, affiliate_url, image_url,
                     shop_code, shop_name, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, date('now'))
                """, (
                    item['item_code'], product_id, GENRE_KEY,
                    item['item_name'], item['item_url'], item['affiliate_url'],
                    item['image_url'], item['shop_code'], item['shop_name'],
                ))
                upserted_items += 1

        conn.commit()

    print(f"\n✓ products: {inserted_products} 件新規登録")
    print(f"✓ rakuten_items: {upserted_items} 件 upsert")
    print(f"\n次のステップ:")
    print(f"  - モデル未抽出の {len(unmatched_model)} 件は ichiba/normalize.py のルールを追記")
    print(f"  - 十分な数が揃ったら Phase 3-2（商品選定・ブランドホワイトリスト）へ")


if __name__ == '__main__':
    main()
