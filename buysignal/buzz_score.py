"""日次バズスコア集計 & Zスコアスパイク検出。

aggregate_daily : mentions テーブルから当日言及を集計 → daily_buzz_logs
compute_z_scores: 過去N日の移動平均・標準偏差 → zスコア・is_spike を更新
get_spiked_products: 本日スパイクした product_id リスト
get_top_products   : 累計言及数上位N商品（固定価格チェック対象）
"""
import math
import sqlite3
from contextlib import closing
from datetime import date, timedelta

from ichiba.config import DB_PATH
from buysignal.config import MEDIA_WEIGHTS, SPIKE_WINDOW_DAYS, SPIKE_Z_THRESHOLD


def aggregate_daily(target_date: str | None = None) -> int:
    """mentionsテーブルの当日データを媒体重み付きで集計しdaily_buzz_logsに保存する。"""
    target = target_date or date.today().isoformat()
    with closing(sqlite3.connect(DB_PATH)) as conn:
        rows = conn.execute("""
            SELECT product_id, source, COUNT(*) as cnt
            FROM mentions
            WHERE collected_at = ?
              AND product_id IS NOT NULL
            GROUP BY product_id, source
        """, (target,)).fetchall()

        by_product: dict[str, tuple[int, float]] = {}
        for product_id, source, cnt in rows:
            w = MEDIA_WEIGHTS.get(source, 1.0)
            prev_count, prev_wscore = by_product.get(product_id, (0, 0.0))
            by_product[product_id] = (prev_count + cnt, prev_wscore + cnt * w)

        for product_id, (count, wscore) in by_product.items():
            # mentionsテーブルから毎回「当日の全件」を集計し直すため、UPSERTは
            # 加算ではなく置き換え。同日に2回実行しても二重加算されない。
            conn.execute("""
                INSERT INTO daily_buzz_logs (product_id, date, mention_count, weighted_score)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (product_id, date) DO UPDATE SET
                    mention_count  = excluded.mention_count,
                    weighted_score = excluded.weighted_score
            """, (product_id, target, count, round(wscore, 3)))

        conn.commit()

    n = len(by_product)
    print(f"  aggregate_daily({target}): {n} 商品を集計")
    return n


def compute_z_scores(target_date: str | None = None) -> list[tuple[str, float | None, bool]]:
    """過去WINDOW_DAYS日の移動平均・標準偏差からzスコアを算出しis_spikeを更新する。"""
    target = target_date or date.today().isoformat()
    window_start = (
        date.fromisoformat(target) - timedelta(days=SPIKE_WINDOW_DAYS)
    ).isoformat()

    with closing(sqlite3.connect(DB_PATH)) as conn:
        today_rows = conn.execute("""
            SELECT product_id, weighted_score
            FROM daily_buzz_logs
            WHERE date = ?
        """, (target,)).fetchall()

        results: list[tuple[str, float | None, bool]] = []
        for product_id, today_score in today_rows:
            hist = conn.execute("""
                SELECT weighted_score
                FROM daily_buzz_logs
                WHERE product_id = ?
                  AND date >= ?
                  AND date <  ?
                ORDER BY date
            """, (product_id, window_start, target)).fetchall()

            scores = [r[0] for r in hist]
            z: float | None
            if len(scores) < 3:
                z, is_spike = None, False
            else:
                mu = sum(scores) / len(scores)
                sigma = math.sqrt(sum((s - mu) ** 2 for s in scores) / len(scores))
                if sigma < 0.01:
                    z, is_spike = 0.0, False
                else:
                    z = (today_score - mu) / sigma
                    is_spike = z >= SPIKE_Z_THRESHOLD

            conn.execute("""
                UPDATE daily_buzz_logs
                SET z_score  = ?,
                    is_spike = ?
                WHERE product_id = ? AND date = ?
            """, (round(z, 3) if z is not None else None,
                  1 if is_spike else 0,
                  product_id, target))
            results.append((product_id, z, is_spike))

        conn.commit()

    spikes = [r for r in results if r[2]]
    print(f"  compute_z_scores({target}): "
          f"{len(results)} 商品評価, スパイク {len(spikes)} 件")
    if spikes:
        for pid, z, _ in sorted(spikes, key=lambda x: x[1] or 0, reverse=True):
            print(f"    ★ {pid}  z={z:.2f}")
    return results


def get_spiked_products(target_date: str | None = None) -> list[str]:
    target = target_date or date.today().isoformat()
    with closing(sqlite3.connect(DB_PATH)) as conn:
        rows = conn.execute("""
            SELECT product_id FROM daily_buzz_logs
            WHERE date = ? AND is_spike = 1
            ORDER BY z_score DESC
        """, (target,)).fetchall()
    return [r[0] for r in rows]


def get_top_products(n: int) -> list[str]:
    """累計言及数上位N商品（固定価格チェック対象）を返す。"""
    with closing(sqlite3.connect(DB_PATH)) as conn:
        rows = conn.execute("""
            SELECT product_id, SUM(mention_count) as total
            FROM daily_buzz_logs
            WHERE product_id IS NOT NULL
            GROUP BY product_id
            ORDER BY total DESC
            LIMIT ?
        """, (n,)).fetchall()
    return [r[0] for r in rows]
