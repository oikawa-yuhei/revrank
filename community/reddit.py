"""Reddit スクレイパー。

ランニング関連サブレディットの新着投稿・コメントから商品言及を抽出する。
Reddit JSON API（認証不要・公開データ）を使用。

差分取得: last_timestamp (Unix 秒) 以降の投稿のみ処理する。
"""
import time
import requests

from community.extract import extract_mentions

SOURCE_KEY = "reddit"
BASE       = "https://oauth.reddit.com"
AUTH_URL   = "https://www.reddit.com/api/v1/access_token"
INTERVAL   = 2.0
USER_AGENT = "RunGearArchive/1.0 (running gear research; contact: archive42.run)"

SUBREDDITS = [
    "running",          # 総合ランニング (750K+)
    "AdvancedRunning",  # 上級者向け技術議論
    "Garmin",           # GPS ウォッチ専用
    "ultrarunning",     # ウルトラマラソン
    "trailrunning",     # トレイルラン
    "RunningShoeGeeks", # シューズ専門
]

_token_cache: dict = {}


def _get_token(client_id: str, client_secret: str) -> str:
    """Reddit OAuth2 アクセストークンを取得・キャッシュする。"""
    import time
    cached = _token_cache.get("token")
    expires = _token_cache.get("expires", 0)
    if cached and time.time() < expires - 60:
        return cached

    r = requests.post(
        AUTH_URL,
        auth=(client_id, client_secret),
        data={"grant_type": "client_credentials"},
        headers={"User-Agent": USER_AGENT},
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    _token_cache["token"]   = data["access_token"]
    _token_cache["expires"] = time.time() + data.get("expires_in", 3600)
    return _token_cache["token"]


def _get(url, params=None, token: str = ""):
    headers = {
        "User-Agent":    USER_AGENT,
        "Authorization": f"Bearer {token}",
    }
    r = requests.get(url, params=params, headers=headers, timeout=15)
    r.raise_for_status()
    return r


def _fetch_subreddit_new(subreddit: str, token: str,
                         after: str | None = None) -> dict:
    """新着投稿リストを JSON で取得する。"""
    params = {"limit": 100, "raw_json": 1}
    if after:
        params["after"] = after
    r = _get(f"{BASE}/r/{subreddit}/new", params=params, token=token)
    return r.json()


def _fetch_comments(subreddit: str, post_id: str, token: str) -> str:
    """投稿のコメント本文を結合して返す。"""
    try:
        r = _get(f"{BASE}/r/{subreddit}/comments/{post_id}",
                 params={"limit": 100, "depth": 3, "raw_json": 1},
                 token=token)
        data = r.json()
        texts = []
        # data[1] がコメントツリー
        if len(data) > 1:
            _collect_comment_bodies(data[1]["data"]["children"], texts, depth=0)
        return "\n".join(texts)
    except Exception:
        return ""


def _collect_comment_bodies(children: list, out: list, depth: int):
    if depth > 3:
        return
    for child in children:
        if child.get("kind") != "t1":
            continue
        d = child["data"]
        body = d.get("body", "")
        if body and body != "[deleted]" and body != "[removed]":
            out.append(body)
        replies = d.get("replies")
        if isinstance(replies, dict):
            _collect_comment_bodies(
                replies["data"]["children"], out, depth + 1
            )


def collect(last_timestamp: float, subreddits: list[str] = SUBREDDITS
            ) -> tuple[list[dict], float]:
    """
    新着投稿＋コメントから言及を収集する。

    環境変数 REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET が必要。

    Args:
        last_timestamp: Unix 秒。これより新しい投稿のみ処理する。

    Returns:
        (mentions, new_last_timestamp)
    """
    import os
    client_id     = os.environ.get("REDDIT_CLIENT_ID", "")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        print("  [SKIP] REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET が未設定")
        return [], last_timestamp

    try:
        token = _get_token(client_id, client_secret)
    except Exception as e:
        print(f"  [WARN] Reddit 認証失敗: {e}")
        return [], last_timestamp

    all_mentions: list[dict] = []
    processed_post_ids: set[str] = set()
    newest_ts = last_timestamp

    for subreddit in subreddits:
        print(f"  [reddit] r/{subreddit}")
        after = None

        for _page in range(5):   # 最大 5ページ (500件)
            try:
                data = _fetch_subreddit_new(subreddit, token, after=after)
            except requests.RequestException as e:
                print(f"    [WARN] {e}")
                break

            time.sleep(INTERVAL)

            posts = data.get("data", {}).get("children", [])
            if not posts:
                break

            stop_paging = False
            for post in posts:
                d  = post["data"]
                ts = d.get("created_utc", 0)
                pid = d.get("id", "")

                if ts <= last_timestamp:
                    stop_paging = True
                    break

                if pid in processed_post_ids:
                    continue
                processed_post_ids.add(pid)

                if ts > newest_ts:
                    newest_ts = ts

                post_url = f"{BASE}/r/{subreddit}/comments/{pid}/"

                # タイトル + 本文
                title    = d.get("title", "")
                selftext = d.get("selftext", "")
                post_text = f"{title}\n{selftext}"

                for m in extract_mentions(post_text):
                    all_mentions.append({
                        "source":      SOURCE_KEY,
                        "source_url":  post_url,
                        "product_id":  m["product_id"],
                        "brand_key":   m["brand_key"],
                        "model_name":  m["model_name"],
                        "raw_mention": m["raw_mention"],
                    })

                # コメントも取得（投稿数が多い場合は上位スレのみ）
                if d.get("num_comments", 0) > 0:
                    time.sleep(INTERVAL)
                    comment_text = _fetch_comments(subreddit, pid, token)
                    for m in extract_mentions(comment_text):
                        comment_url = post_url
                        all_mentions.append({
                            "source":      SOURCE_KEY,
                            "source_url":  comment_url,
                            "product_id":  m["product_id"],
                            "brand_key":   m["brand_key"],
                            "model_name":  m["model_name"],
                            "raw_mention": m["raw_mention"],
                        })

            after = data["data"].get("after")
            if stop_paging or not after:
                break

        time.sleep(INTERVAL)

    return all_mentions, newest_ts
