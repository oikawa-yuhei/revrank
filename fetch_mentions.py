"""コミュニティ言及収集バッチ (日次差分)。

RUNNET 知恵袋・note.com の新着コンテンツを取得し、
商品言及を mentions テーブルに蓄積する。

使い方:
    python fetch_mentions.py              # 全ソース・差分のみ
    python fetch_mentions.py --dry-run    # 確認のみ（DB書き込みなし）
    python fetch_mentions.py --source runnet  # ソース指定
"""
import argparse
import json
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from ichiba.config import DB_PATH
from ichiba.db import init_db

STATE_FILE = Path(__file__).parent / "data" / "community_state.json"

DEFAULT_STATE = {
    "runnet_chie":  {"last_id": 0},
    "note_hashtag": {"last_fetched": "2020-01-01T00:00:00+09:00"},
    "reddit":       {"last_timestamp": 0.0},
    "chiebukuro":   {"seen_ids": {}},
    "fivech":       {"threads": {}},
}


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return DEFAULT_STATE.copy()


def save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def save_mentions(mentions: list[dict], collected_at: str):
    """mentions テーブルに書き込む。UNIQUE 制約でダブりは自動スキップ。"""
    with closing(sqlite3.connect(DB_PATH)) as conn:
        inserted = 0
        for m in mentions:
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO mentions
                    (collected_at, source, source_url, product_id,
                     brand_key, model_name, raw_mention)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    collected_at,
                    m["source"], m.get("source_url"), m.get("product_id"),
                    m.get("brand_key"), m.get("model_name"), m.get("raw_mention"),
                ))
                inserted += conn.execute("SELECT changes()").fetchone()[0]
            except Exception as e:
                print(f"  [WARN] DB書き込み失敗: {e}")
        conn.commit()
    return inserted


def run_runnet(state: dict, dry_run: bool, max_pages: int | None = None) -> int:
    from community.runnet import collect
    last_id = state.get("runnet_chie", {}).get("last_id", 0)
    print(f"\n[RUNNET 知恵袋] last_id={last_id}")

    mentions, new_max_id = collect(last_id, max_pages=max_pages)
    print(f"  新着投稿から {len(mentions)} 件の言及を取得")

    for m in mentions[:5]:
        print(f"  {m['product_id']:<35}  {m['raw_mention'][:40]}")
    if len(mentions) > 5:
        print(f"  ... 他 {len(mentions)-5} 件")

    if not dry_run and mentions:
        inserted = save_mentions(mentions, date.today().isoformat())
        print(f"  DB挿入: {inserted} 件")

    if not dry_run:
        state["runnet_chie"]["last_id"] = new_max_id

    return len(mentions)


def run_note(state: dict, dry_run: bool) -> int:
    from community.note_scraper import collect
    last_fetched = state.get("note_hashtag", {}).get("last_fetched", "2020-01-01T00:00:00+09:00")
    print(f"\n[note.com] last_fetched={last_fetched}")

    mentions, new_last_fetched = collect(last_fetched)
    print(f"  新着記事から {len(mentions)} 件の言及を取得")

    for m in mentions[:5]:
        print(f"  {m['product_id']:<35}  {m['raw_mention'][:40]}")
    if len(mentions) > 5:
        print(f"  ... 他 {len(mentions)-5} 件")

    if not dry_run and mentions:
        inserted = save_mentions(mentions, date.today().isoformat())
        print(f"  DB挿入: {inserted} 件")

    if not dry_run:
        state["note_hashtag"]["last_fetched"] = new_last_fetched

    return len(mentions)


def run_reddit(state: dict, dry_run: bool) -> int:
    from community.reddit import collect
    last_ts = state.get("reddit", {}).get("last_timestamp", 0.0)
    print(f"\n[Reddit] last_timestamp={last_ts}")

    mentions, new_ts = collect(last_ts)
    print(f"  新着投稿から {len(mentions)} 件の言及を取得")

    for m in mentions[:5]:
        print(f"  {m['product_id']:<35}  {m['raw_mention'][:40]}")
    if len(mentions) > 5:
        print(f"  ... 他 {len(mentions)-5} 件")

    if not dry_run and mentions:
        inserted = save_mentions(mentions, date.today().isoformat())
        print(f"  DB挿入: {inserted} 件")

    if not dry_run:
        state.setdefault("reddit", {})["last_timestamp"] = new_ts

    return len(mentions)


def run_chiebukuro(state: dict, dry_run: bool) -> int:
    from community.chiebukuro import collect
    seen_ids = state.get("chiebukuro", {}).get("seen_ids", {})
    print(f"\n[Yahoo!知恵袋] 既知QA数={sum(len(v) for v in seen_ids.values())}")

    mentions, new_seen = collect(seen_ids)
    print(f"  新着 Q&A から {len(mentions)} 件の言及を取得")

    for m in mentions[:5]:
        print(f"  {m['product_id']:<35}  {m['raw_mention'][:40]}")
    if len(mentions) > 5:
        print(f"  ... 他 {len(mentions)-5} 件")

    if not dry_run and mentions:
        inserted = save_mentions(mentions, date.today().isoformat())
        print(f"  DB挿入: {inserted} 件")

    if not dry_run:
        state.setdefault("chiebukuro", {})["seen_ids"] = new_seen

    return len(mentions)


def run_fivech(state: dict, dry_run: bool) -> int:
    from community.fivech import collect
    thread_state = state.get("fivech", {}).get("threads", {})
    print(f"\n[5ch] 既知スレ数={len(thread_state)}")

    mentions, new_thread_state = collect(thread_state)
    print(f"  新着レスから {len(mentions)} 件の言及を取得")

    for m in mentions[:5]:
        print(f"  {m['product_id']:<35}  {m['raw_mention'][:40]}")
    if len(mentions) > 5:
        print(f"  ... 他 {len(mentions)-5} 件")

    if not dry_run and mentions:
        inserted = save_mentions(mentions, date.today().isoformat())
        print(f"  DB挿入: {inserted} 件")

    if not dry_run:
        state.setdefault("fivech", {})["threads"] = new_thread_state

    return len(mentions)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",   action="store_true")
    parser.add_argument("--source",    choices=["runnet", "note", "reddit", "chiebukuro", "fivech"], default=None)
    parser.add_argument("--max-pages", type=int, default=None,
                        help="取得する最大ページ数 (テスト用。省略時はデフォルト)")
    args = parser.parse_args()

    init_db()
    state = load_state()
    today = date.today().isoformat()
    total = 0

    sources = [args.source] if args.source else ["runnet", "note", "reddit", "chiebukuro", "fivech"]

    if "runnet" in sources:
        total += run_runnet(state, args.dry_run, args.max_pages)

    if "note" in sources:
        total += run_note(state, args.dry_run)

    if "reddit" in sources:
        total += run_reddit(state, args.dry_run)

    if "chiebukuro" in sources:
        total += run_chiebukuro(state, args.dry_run)

    if "fivech" in sources:
        total += run_fivech(state, args.dry_run)

    if not args.dry_run:
        save_state(state)

    print(f"\n完了: {today}  合計 {total} 件の言及を収集")

    # 言及数サマリーを表示
    if not args.dry_run:
        _print_summary()


def _print_summary():
    with closing(sqlite3.connect(DB_PATH)) as conn:
        rows = conn.execute("""
            SELECT product_id, brand_key, model_name,
                   COUNT(*) as total,
                   SUM(CASE WHEN collected_at >= date('now', '-7 days')  THEN 1 ELSE 0 END) as w7,
                   SUM(CASE WHEN collected_at >= date('now', '-30 days') THEN 1 ELSE 0 END) as d30
            FROM mentions
            WHERE product_id IS NOT NULL
            GROUP BY product_id
            ORDER BY total DESC
            LIMIT 20
        """).fetchall()

    if not rows:
        return

    print("\n■ 言及数ランキング (上位20件)")
    print(f"  {'product_id':<38}  {'7日':>4}  {'30日':>5}  {'累計':>5}")
    print(f"  {'-'*38}  {'----':>4}  {'-----':>5}  {'-----':>5}")
    for pid, brand, model, total, w7, d30 in rows:
        print(f"  {pid:<38}  {w7:>4}  {d30:>5}  {total:>5}")


if __name__ == "__main__":
    main()
