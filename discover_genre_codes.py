"""楽天市場 IchibaGenre Search API でジャンルIDを探索するヘルパー。

使い方:
    python discover_genre_codes.py                    # ルート直下の全ジャンルを表示
    python discover_genre_codes.py 551177             # ジャンルID 551177 の子階層を表示
    python discover_genre_codes.py --search ランニング  # 名前でキーワード検索
    python discover_genre_codes.py --search ゴルフ --depth 2

.env に以下が必要:
    RAKUTEN_ICHIBA_APP_ID
    RAKUTEN_ICHIBA_ACCESS_KEY
    RAKUTEN_ORIGIN
"""
import argparse
import os
import sys
import time

import requests
from dotenv import load_dotenv

GENRE_SEARCH_URL = "https://openapi.rakuten.co.jp/ichibagt/api/IchibaGenre/Search/20260701"
REQUEST_INTERVAL = 1.2


def fetch_genre(app_id: str, access_key: str, origin: str, genre_id: int) -> dict:
    params = {"applicationId": app_id, "accessKey": access_key,
              "genreId": genre_id, "format": "json"}
    headers = {"Origin": origin, "Referer": origin + "/"}
    r = requests.get(GENRE_SEARCH_URL, params=params, headers=headers, timeout=10)
    data = r.json()
    if "errors" in data or r.status_code != 200:
        raise RuntimeError(f"APIエラー {r.status_code}: {data}")
    return data


def _name(node: dict) -> str:
    return node.get("nameJa") or node.get("genreName", "?")


def print_tree(app_id, access_key, origin, genre_id, depth, max_depth):
    data = fetch_genre(app_id, access_key, origin, genre_id)
    current  = data.get("genre", {})
    children = data.get("children", [])
    indent   = "  " * depth
    gid      = current.get("genreId", genre_id)

    if depth > 0:
        print(f"{indent}[{gid}] {_name(current)}")

    if depth < max_depth:
        for child in children:
            cid = child.get("genreId")
            if not cid:
                continue
            time.sleep(REQUEST_INTERVAL)
            print_tree(app_id, access_key, origin, cid, depth + 1, max_depth)


def search_keyword(app_id, access_key, origin, keyword, genre_id, depth, max_depth):
    try:
        data = fetch_genre(app_id, access_key, origin, genre_id)
    except RuntimeError:
        return
    current  = data.get("genre", {})
    children = data.get("children", [])
    gid      = current.get("genreId", genre_id)
    indent   = "  " * depth

    if keyword in _name(current) and depth > 0:
        print(f"{indent}[{gid}] {_name(current)}")

    if depth < max_depth:
        for child in children:
            child_id   = child.get("genreId")
            child_name = _name(child)
            if keyword in child_name:
                print(f"{'  ' * (depth + 1)}[{child_id}] {child_name}")
            if child_id:
                time.sleep(REQUEST_INTERVAL)
                search_keyword(app_id, access_key, origin, keyword, child_id,
                               depth + 1, max_depth)


def main():
    parser = argparse.ArgumentParser(description="楽天市場ジャンルIDを探索する")
    parser.add_argument("genre_id", nargs="?", type=int, default=0,
                        help="表示するジャンルID（省略時はルート）")
    parser.add_argument("--search", metavar="KEYWORD",
                        help="ジャンル名でキーワード検索")
    parser.add_argument("--depth", type=int, default=2,
                        help="探索する階層の深さ（デフォルト2）")
    args = parser.parse_args()

    load_dotenv()
    app_id     = os.environ.get("RAKUTEN_ICHIBA_APP_ID")
    access_key = os.environ.get("RAKUTEN_ICHIBA_ACCESS_KEY")
    origin     = os.environ.get("RAKUTEN_ORIGIN")
    if not app_id or not access_key or not origin:
        sys.exit("環境変数 RAKUTEN_ICHIBA_APP_ID / RAKUTEN_ICHIBA_ACCESS_KEY / RAKUTEN_ORIGIN が未設定です。")

    if args.search:
        print(f"'{args.search}' を含むジャンルを探索中（depth={args.depth}）...")
        search_keyword(app_id, access_key, origin, args.search,
                       args.genre_id, 0, args.depth)
    else:
        print(f"ジャンルID {args.genre_id} の子階層（depth={args.depth}）:")
        print_tree(app_id, access_key, origin, args.genre_id, 0, args.depth)


if __name__ == "__main__":
    main()
