"""楽天市場ジャンルID検索ツール。

キーワードを入力するとジャンルツリーを再帰的に探索して候補を表示する。
見つかったIDを ichiba/config.py の GENRES に設定すること。

使い方:
    python tools/find_genre.py パワーメーター
    python tools/find_genre.py ハイドレーション
    python tools/find_genre.py リカバリー
"""
import os
import sys
import time

import requests
from dotenv import load_dotenv

load_dotenv()

GENRE_URL = "https://openapi.rakuten.co.jp/ichiba/api/IchibaGenre/Search/20140222"
APP_ID    = os.environ.get("RAKUTEN_ICHIBA_APP_ID", "")

# ランニング・スポーツ関連の親ジャンルIDから探索する
ROOT_GENRE_IDS = [
    100371,   # スポーツ・アウトドア
]


def search_genre(genre_id, keyword, depth=0, visited=None):
    if visited is None:
        visited = set()
    if genre_id in visited or depth > 5:
        return
    visited.add(genre_id)

    try:
        r = requests.get(GENRE_URL, params={
            "applicationId": APP_ID,
            "format":        "json",
            "genreId":       genre_id,
        }, timeout=10)
        data = r.json()
    except Exception as e:
        print(f"  [ERR] genreId={genre_id}: {e}")
        return

    genre_info = data.get("current", {})
    current_name = genre_info.get("genreName", "")
    current_id   = genre_info.get("genreId", genre_id)

    if keyword in current_name:
        indent = "  " * depth
        print(f"{indent}[HIT] id={current_id}  {current_name}")

    for child in data.get("children", []):
        child_name = child.get("genreName", "")
        child_id   = child.get("genreId")
        if not child_id:
            continue

        if keyword in child_name:
            indent = "  " * (depth + 1)
            print(f"{indent}[HIT] id={child_id}  {child_name}")

        # 部分一致でなくても子を探索（ツリー全体をたどる）
        time.sleep(0.5)
        search_genre(child_id, keyword, depth + 1, visited)


def main():
    if not APP_ID:
        sys.exit("環境変数 RAKUTEN_ICHIBA_APP_ID が未設定です")

    keyword = " ".join(sys.argv[1:]).strip()
    if not keyword:
        sys.exit("使い方: python tools/find_genre.py <キーワード>")

    print(f"キーワード「{keyword}」でジャンルツリーを探索中...\n")
    for root_id in ROOT_GENRE_IDS:
        search_genre(root_id, keyword)

    print("\n完了。[HIT] の id を ichiba/config.py の GENRES に設定してください。")


if __name__ == "__main__":
    main()
