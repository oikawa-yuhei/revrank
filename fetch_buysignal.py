"""BuySignal 日次バッチ。

1. RSSフィード収集 (はてなブックマーク / YouTube / カスタム)
2. mentions → daily_buzz_logs 集計 (媒体重み付き)
3. Zスコア計算・スパイク判定
4. スパイク商品 + 固定上位商品の楽天価格取得 → price_logs

使い方:
    python fetch_buysignal.py               # 通常実行
    python fetch_buysignal.py --dry-run     # DB書き込みなし（確認用）
    python fetch_buysignal.py --skip-rss    # RSS収集をスキップ（集計・価格のみ）
    python fetch_buysignal.py --skip-price  # 価格取得をスキップ
    python fetch_buysignal.py --date 2026-08-16  # 過去日付で集計のみ再実行
"""
import argparse
import json
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
from ichiba.config import DB_PATH
from ichiba.db import init_db
from buysignal.db import init_buysignal_db
from buysignal.config import (
    FIXED_PRICE_CHECK_TOP_N,
    HATENA_QUERIES, HATENA_RSS_TEMPLATE,
    YOUTUBE_CHANNELS, YOUTUBE_RSS_TEMPLATE,
    CUSTOM_RSS_FEEDS,
)

STATE_FILE = Path(__file__).parent / "data" / "buysignal_state.json"
DEFAULT_STATE: dict = {
    "rss_blog":    {"last_fetched": "2020-01-01T00:00:00+00:00"},
    "rss_youtube": {"last_fetched": "2020-01-01T00:00:00+00:00"},
}


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return DEFAULT_STATE.copy()


def save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _save_mentions(mentions: list[dict], collected_at: str) -> int:
    inserted = 0
    with closing(sqlite3.connect(DB_PATH)) as conn:
        for m in mentions:
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO mentions
                    (collected_at, source, source_url, product_id,
                     brand_key, model_name, raw_mention)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (collected_at,
                      m["source"], m.get("source_url"), m.get("product_id"),
                      m.get("brand_key"), m.get("model_name"), m.get("raw_mention")))
                inserted += conn.execute("SELECT changes()").fetchone()[0]
            except Exception as e:
                print(f"  [WARN] DB書き込み失敗: {e}")
        conn.commit()
    return inserted


def run_rss(state: dict, dry_run: bool, today: str) -> int:
    from buysignal.rss_collector import collect_hatena, collect_youtube, collect_custom
    total = 0

    # はてなブックマーク検索RSS
    last_blog = state.get("rss_blog", {}).get("last_fetched", "2020-01-01T00:00:00+00:00")
    print(f"\n[RSS/はてなブックマーク] last_fetched={last_blog}")
    mentions, new_last = collect_hatena(last_blog, HATENA_QUERIES, HATENA_RSS_TEMPLATE)
    print(f"  {len(mentions)} 件の言及を取得")
    if not dry_run:
        ins = _save_mentions(mentions, today)
        print(f"  DB挿入: {ins} 件")
        state.setdefault("rss_blog", {})["last_fetched"] = new_last
    total += len(mentions)

    # YouTube チャンネルRSS
    if YOUTUBE_CHANNELS:
        last_yt = state.get("rss_youtube", {}).get("last_fetched", "2020-01-01T00:00:00+00:00")
        print(f"\n[RSS/YouTube] last_fetched={last_yt}")
        mentions, new_last = collect_youtube(last_yt, YOUTUBE_CHANNELS, YOUTUBE_RSS_TEMPLATE)
        print(f"  {len(mentions)} 件の言及を取得")
        if not dry_run:
            ins = _save_mentions(mentions, today)
            print(f"  DB挿入: {ins} 件")
            state.setdefault("rss_youtube", {})["last_fetched"] = new_last
        total += len(mentions)
    else:
        print("\n[RSS/YouTube] チャンネル未設定 → buysignal/config.py の YOUTUBE_CHANNELS に追加")

    # カスタムRSSフィード
    if CUSTOM_RSS_FEEDS:
        last_custom = state.get("rss_blog", {}).get("last_fetched", "2020-01-01T00:00:00+00:00")
        mentions, _ = collect_custom(last_custom, CUSTOM_RSS_FEEDS)
        if not dry_run and mentions:
            ins = _save_mentions(mentions, today)
            print(f"  [カスタムRSS] DB挿入: {ins} 件")
        total += len(mentions)

    return total


def run_buzz_score(dry_run: bool, target_date: str) -> None:
    from buysignal.buzz_score import aggregate_daily, compute_z_scores
    print(f"\n[BuzzScore] {target_date}")
    aggregate_daily(target_date)
    if not dry_run:
        compute_z_scores(target_date)
    else:
        print("  [dry-run] Zスコア計算をスキップ")


def run_price_trigger(dry_run: bool, target_date: str) -> None:
    from buysignal.buzz_score import get_spiked_products, get_top_products
    from buysignal.price_trigger import run as price_run
    print(f"\n[PriceTrigger]")
    if dry_run:
        spiked = get_spiked_products(target_date)
        top = get_top_products(FIXED_PRICE_CHECK_TOP_N)
        print(f"  [dry-run] スパイク商品: {spiked}")
        print(f"  [dry-run] 固定チェック上位: {top[:5]}")
    else:
        price_run(target_date)


def _print_summary(target_date: str):
    with closing(sqlite3.connect(DB_PATH)) as conn:
        rows = conn.execute("""
            SELECT b.product_id,
                   b.mention_count,
                   b.weighted_score,
                   b.z_score,
                   b.is_spike,
                   p.price
            FROM daily_buzz_logs b
            LEFT JOIN (
                SELECT product_id, MIN(price) as price
                FROM price_logs
                WHERE date(fetched_at) = ?
                GROUP BY product_id
            ) p ON b.product_id = p.product_id
            WHERE b.date = ?
            ORDER BY b.weighted_score DESC
            LIMIT 30
        """, (target_date, target_date)).fetchall()

    if not rows:
        print("  (本日のデータなし)")
        return

    print(f"\n■ BuySignal 日次サマリー ({target_date})")
    print(f"  {'product_id':<38}  {'件':>4}  {'wt':>5}  {'z':>5}  spike  {'最安値':>8}")
    print(f"  {'-'*38}  {'----':>4}  {'-----':>5}  {'-----':>5}  -----  {'--------':>8}")
    for pid, cnt, wscore, z, spike, price in rows:
        spike_mark = "  ★  " if spike else "     "
        z_str = f"{z:+.2f}" if z is not None else " N/A "
        price_str = f"{price:,}円" if price else "    -   "
        print(f"  {pid:<38}  {cnt:>4}  {wscore:>5.1f}  {z_str:>5}  {spike_mark}  {price_str:>8}")


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="BuySignal 日次バッチ")
    parser.add_argument("--dry-run",    action="store_true", help="DB書き込みなし")
    parser.add_argument("--skip-rss",   action="store_true", help="RSSフィード収集をスキップ")
    parser.add_argument("--skip-price", action="store_true", help="価格取得をスキップ")
    parser.add_argument("--date", default=None, metavar="YYYY-MM-DD",
                        help="集計対象日 (省略時は今日)")
    args = parser.parse_args()

    init_db()
    init_buysignal_db()
    state = load_state()
    today = args.date or date.today().isoformat()

    total_mentions = 0
    if not args.skip_rss:
        total_mentions = run_rss(state, args.dry_run, today)

    run_buzz_score(args.dry_run, today)

    if not args.skip_price:
        run_price_trigger(args.dry_run, today)

    if not args.dry_run:
        save_state(state)

    _print_summary(today)
    print(f"\n完了: {today}  RSS新規言及 {total_mentions} 件")


if __name__ == "__main__":
    main()
