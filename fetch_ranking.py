"""楽天市場ランキングアーカイブ: 日次収集バッチ。

対象ジャンルごとに上位90件(3ページ×30件)のランキングを取得し SQLite に保存する。
毎日1回、同じ時刻に実行する想定 (Windows タスクスケジューラ推奨):

    python fetch_ranking.py
    python fetch_ranking.py --genres golf running
    python fetch_ranking.py --date 2026-08-13   # 過去日付で再取得
"""
import argparse
import os
import sys
import time
from datetime import date

from dotenv import load_dotenv

from ichiba.client import IchibaApiError, fetch_ranking
from ichiba.config import GENRES, REQUEST_INTERVAL
from ichiba.db import init_db, save_ranking_items


def main():
    parser = argparse.ArgumentParser(description="楽天市場ランキングを取得しDBに保存する")
    parser.add_argument("--genres", nargs="*", default=None,
                        help="取得対象ジャンルキー (省略時は全ジャンル)")
    parser.add_argument("--date", default=None,
                        help="取得日付 YYYY-MM-DD (省略時は今日)")
    args = parser.parse_args()

    load_dotenv()
    app_id     = os.environ.get("RAKUTEN_ICHIBA_APP_ID")
    access_key = os.environ.get("RAKUTEN_ICHIBA_ACCESS_KEY")
    origin     = os.environ.get("RAKUTEN_ORIGIN")
    if not app_id or not access_key or not origin:
        sys.exit("環境変数 RAKUTEN_ICHIBA_APP_ID / RAKUTEN_ICHIBA_ACCESS_KEY / RAKUTEN_ORIGIN が未設定です。")

    fetched_date = args.date or date.today().isoformat()
    target_keys  = args.genres or list(GENRES.keys())

    unknown = [k for k in target_keys if k not in GENRES]
    if unknown:
        sys.exit(f"不明なジャンルキー: {unknown}  有効なキー: {list(GENRES.keys())}")

    init_db()

    total_ok = total_ng = 0

    for i, key in enumerate(target_keys):
        genre = GENRES[key]
        if i > 0:
            time.sleep(REQUEST_INTERVAL)

        try:
            items = fetch_ranking(app_id, access_key, origin, genre["id"])
            save_ranking_items(fetched_date, genre["id"], key, items)
            print(f"[OK] {key} ({genre['label']}) {len(items)}件")
            total_ok += 1
        except IchibaApiError as e:
            print(f"[NG] {key} ({genre['label']}): {e}", file=sys.stderr)
            total_ng += 1

    print(f"\n完了: {fetched_date}  成功={total_ok} 失敗={total_ng} / {len(target_keys)}ジャンル")


if __name__ == "__main__":
    main()
