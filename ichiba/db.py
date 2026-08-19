import sqlite3
from contextlib import closing

from ichiba.config import DB_PATH


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(DB_PATH)) as conn:
        # ── 旧テーブル: build_site.py が参照するため維持 ──────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS item_rankings (
                fetched_date    TEXT    NOT NULL,
                genre_id        INTEGER NOT NULL,
                genre_key       TEXT    NOT NULL,
                rank            INTEGER NOT NULL,
                item_code       TEXT    NOT NULL,
                item_name       TEXT,
                item_price      INTEGER,
                item_url        TEXT,
                affiliate_url   TEXT,
                image_url       TEXT,
                shop_name       TEXT,
                shop_code       TEXT,
                review_count    INTEGER,
                review_average  REAL,
                point_rate      INTEGER,
                item_caption    TEXT,
                PRIMARY KEY (fetched_date, genre_id, rank)
            )
        """)

        # ── 正規化商品マスタ: Phase 3-1 (名寄せ) で product_id を割り当てる ────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS products (
                product_id    TEXT PRIMARY KEY,
                brand         TEXT,
                model_name    TEXT,
                genre_key     TEXT,
                created_at    TEXT DEFAULT (date('now'))
            )
        """)

        # ── 楽天出品エントリ: item_code (shopCode:itemId) 単位 ─────────────────
        # product_id は Phase 3-1 完了後に埋まる（それまで NULL）
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rakuten_items (
                item_code     TEXT PRIMARY KEY,
                product_id    TEXT,
                genre_key     TEXT,
                item_name     TEXT,
                item_url      TEXT,
                affiliate_url TEXT,
                image_url     TEXT,
                shop_code     TEXT,
                shop_name     TEXT,
                updated_at    TEXT,
                FOREIGN KEY (product_id) REFERENCES products(product_id)
            )
        """)

        # ── 日次スナップショット: 価格・口コミ・在庫の推移を蓄積 ──────────────
        # 旧スキーマ (item_name 等を持つ) から変わるため自動マイグレーション
        _migrate_daily_snapshot(conn)

        # ── コミュニティ言及: 各ソースから収集した商品言及を蓄積 ──────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mentions (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                collected_at TEXT    NOT NULL,
                source       TEXT    NOT NULL,
                source_url   TEXT,
                product_id   TEXT,
                brand_key    TEXT,
                model_name   TEXT,
                raw_mention  TEXT,
                UNIQUE (source, source_url, product_id)
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_mentions_product ON mentions (product_id, collected_at)"
        )

        conn.commit()


def _migrate_daily_snapshot(conn):
    """daily_snapshot の旧スキーマ（item_name 等を持つもの）を新スキーマに移行する。"""
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(daily_snapshot)")}
    if existing_cols and "item_name" in existing_cols:
        # 旧スキーマが存在する場合は削除（データ収集前のため安全）
        conn.execute("DROP TABLE daily_snapshot")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_snapshot (
            date          TEXT    NOT NULL,
            item_code     TEXT    NOT NULL,
            genre_key     TEXT    NOT NULL,
            price         INTEGER,
            review_count  INTEGER,
            avg_rating    REAL,
            in_stock      INTEGER DEFAULT 1,
            rank          INTEGER,
            point_rate    INTEGER,
            PRIMARY KEY (date, item_code)
        )
    """)


def save_ranking_items(fetched_date, genre_id, genre_key, items):
    """旧テーブル (item_rankings) に書き込む。build_site.py の参照先。"""
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.executemany("""
            INSERT OR REPLACE INTO item_rankings
            (fetched_date, genre_id, genre_key, rank,
             item_code, item_name, item_price,
             item_url, affiliate_url, image_url,
             shop_name, shop_code,
             review_count, review_average, point_rate, item_caption)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (fetched_date, genre_id, genre_key, item["rank"],
             item["item_code"], item["item_name"], item["item_price"],
             item["item_url"], item["affiliate_url"], item["image_url"],
             item["shop_name"], item["shop_code"],
             item["review_count"], item["review_average"], item["point_rate"],
             item.get("item_caption", ""))
            for item in items
        ])
        conn.commit()


def save_snapshot_items(date, genre_key, items):
    """rakuten_items と daily_snapshot に書き込む。時系列分析の基盤。"""
    with closing(sqlite3.connect(DB_PATH)) as conn:
        # 楽天出品マスタを upsert（商品名・URL・画像は最新で上書き）
        conn.executemany("""
            INSERT OR REPLACE INTO rakuten_items
            (item_code, genre_key, item_name, item_url, affiliate_url,
             image_url, shop_code, shop_name, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (item["item_code"], genre_key, item["item_name"],
             item["item_url"], item["affiliate_url"], item["image_url"],
             item["shop_code"], item["shop_name"], date)
            for item in items
        ])

        # 日次スナップショットを記録（変動指標のみ）
        conn.executemany("""
            INSERT OR REPLACE INTO daily_snapshot
            (date, item_code, genre_key, price, review_count, avg_rating,
             in_stock, rank, point_rate)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
        """, [
            (date, item["item_code"], genre_key, item["item_price"],
             item["review_count"], item["review_average"],
             item["rank"], item["point_rate"])
            for item in items
        ])
        conn.commit()
