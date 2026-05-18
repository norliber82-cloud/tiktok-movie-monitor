"""Backfill follower_count for every MONITORED creator in Bitable.

Uses direct HTTP scraping of the TikTok user page (not the unofficial API)
since this script runs from your desktop where TikTok isn't blocking us.
"""

import json
import logging
import random
import re
import sys
import time

import requests

from . import bitable_client as bc
from . import config

API = "https://open.feishu.cn/open-apis"

UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0",
]

REHYDRATE_RE = re.compile(
    r'__UNIVERSAL_DATA_FOR_REHYDRATION__[^>]*>([^<]+)<', re.DOTALL
)


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s | %(message)s",
        stream=sys.stdout,
    )


def fetch_tiktok_user_stats(username: str) -> dict | None:
    """Returns {'follower_count', 'following', 'heart_count', 'video_count', 'nickname'}
    or None on failure."""
    url = f"https://www.tiktok.com/@{username.lstrip('@')}"
    headers = {
        "User-Agent": random.choice(UA_POOL),
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
    }
    try:
        r = requests.get(url, headers=headers, timeout=20)
    except Exception as exc:
        logging.warning("network fail @%s: %s", username, exc)
        return None
    if r.status_code != 200:
        logging.warning("HTTP %s for @%s", r.status_code, username)
        return None
    m = REHYDRATE_RE.search(r.text)
    if not m:
        logging.warning("no rehydrate blob for @%s", username)
        return None
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    user_detail = (data.get("__DEFAULT_SCOPE__", {})
                       .get("webapp.user-detail", {}))
    user = user_detail.get("userInfo", {}).get("user", {})
    stats = user_detail.get("userInfo", {}).get("stats", {})
    if not stats:
        return None
    return {
        "follower_count": int(stats.get("followerCount") or 0),
        "following":      int(stats.get("followingCount") or 0),
        "heart_count":    int(stats.get("heartCount") or 0),
        "video_count":    int(stats.get("videoCount") or 0),
        "nickname":       user.get("nickname") or "",
        "secUid":         user.get("secUid") or "",
    }


def fetch_creators_records():
    """All records from the creators table."""
    url = (f"{API}/bitable/v1/apps/{config.BITABLE_APP_TOKEN}"
           f"/tables/{config.BITABLE_CREATORS_TABLE}/records")
    out = []
    page_token = None
    for _ in range(40):
        params = {"page_size": 500}
        if page_token:
            params["page_token"] = page_token
        r = requests.get(url, headers=bc._headers(), params=params, timeout=30).json()
        if r.get("code") != 0:
            break
        d = r.get("data", {})
        out.extend(d.get("items", []))
        page_token = d.get("page_token")
        if not d.get("has_more"):
            break
    return out


def update_record(record_id: str, fields: dict) -> bool:
    url = (f"{API}/bitable/v1/apps/{config.BITABLE_APP_TOKEN}"
           f"/tables/{config.BITABLE_CREATORS_TABLE}/records/{record_id}")
    r = requests.put(url, headers=bc._headers(),
                     json={"fields": fields}, timeout=15).json()
    if r.get("code") != 0:
        logging.warning("update_record failed: %s", r)
        return False
    return True


def main(force: bool = False):
    """Backfill follower_count for creators with missing/zero values.
    Set force=True to refresh ALL creators."""
    setup_logging()
    log = logging.getLogger("backfill_followers")

    records = fetch_creators_records()
    log.info("Total creators in Bitable: %d", len(records))

    targets = []
    for rec in records:
        f = rec.get("fields", {})
        username = f.get("用户名")
        followers = f.get("粉丝数")
        if not username:
            continue
        # Treat None, 0, "" all as "missing"
        is_missing = followers in (None, 0, "", "0") or not followers
        if force or is_missing:
            targets.append((rec["record_id"], username))

    log.info("Need backfill: %d", len(targets))

    ok, fail = 0, 0
    for i, (rid, username) in enumerate(targets, 1):
        stats = fetch_tiktok_user_stats(username)
        if not stats:
            log.warning("[%d/%d] FAIL @%s", i, len(targets), username)
            fail += 1
            continue

        update = {"粉丝数": stats["follower_count"]}
        if stats["nickname"]:
            update["昵称"] = stats["nickname"]

        if update_record(rid, update):
            log.info("[%d/%d] OK @%s — %s followers, %s videos",
                     i, len(targets), username,
                     f"{stats['follower_count']:,}",
                     stats["video_count"])
            ok += 1
        else:
            fail += 1

        # Polite spacing — TikTok's HTML endpoint isn't rate-limited but be nice
        time.sleep(random.uniform(1.5, 3.0))

    log.info("Done. ok=%d fail=%d", ok, fail)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--force", action="store_true",
                   help="Refresh follower_count for ALL creators (not just empty ones)")
    args = p.parse_args()
    main(force=args.force)
