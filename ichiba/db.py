import sqlite3
from contextlib import closing

from ichiba.config import DB_PATH


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(DB_PATH)) as conn:
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
        conn.commit()


def save_ranking_items(fetched_date, genre_id, genre_key, items):
    """items: fetch_ranking() が返す正規化済みリストをまとめて保存する。"""
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
