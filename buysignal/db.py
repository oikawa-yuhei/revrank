"""BuySignal用テーブルを既存DBに追加する。"""
import sqlite3
from contextlib import closing

from ichiba.config import DB_PATH


def init_buysignal_db():
    with closing(sqlite3.connect(DB_PATH)) as conn:
        # 日次バズ集計ログ
        conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_buzz_logs (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id      TEXT    NOT NULL,
                date            TEXT    NOT NULL,
                mention_count   INTEGER NOT NULL DEFAULT 0,
                weighted_score  REAL    NOT NULL DEFAULT 0.0,
                z_score         REAL,
                is_spike        INTEGER DEFAULT 0,
                UNIQUE (product_id, date)
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_buzz_product_date "
            "ON daily_buzz_logs (product_id, date)"
        )

        # 価格ログ（スパイク発生時 + 固定上位商品のみ記録）
        conn.execute("""
            CREATE TABLE IF NOT EXISTS price_logs (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id    TEXT    NOT NULL,
                fetched_at    TEXT    NOT NULL,
                platform      TEXT    NOT NULL,
                price         INTEGER,
                affiliate_url TEXT,
                item_name     TEXT,
                item_code     TEXT
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_price_product "
            "ON price_logs (product_id, fetched_at)"
        )
        conn.commit()
