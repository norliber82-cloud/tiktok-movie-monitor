"""Backfill follower_count for creators whose 粉丝数 is missing/0 in Bitable.

Runs from inside the GitHub Actions workflow. Uses direct HTTP scraping of
the TikTok user-page HTML (not the unofficial API), which is much more
robust on cloud runners than TikTok-Api's playwright-based calls.
"""

from __future__ import annotations

import json
import logging
import os
import random
import re
import time

import requests

logger = logging.getLogger(__name__)

API = "https://open.feishu.cn/open-apis"

UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0",
]

REHYDRATE_RE = re.compile(
    r'__UNIVERSAL_DATA_FOR_REHYDRATION__[^>]*>([^<]+)<', re.DOTALL
)

# How many creators to process per workflow run (cap to keep run-time short)
MAX_PER_RUN = 25
# Polite spacing between TikTok HTTP requests
SLEEP_MIN = 1.2
SLEEP_MAX = 2.5


def _env(k: str) -> str:
    return os.getenv(k, "").strip()


def is_configured() -> bool:
    return bool(_env("FEISHU_APP_ID") and _env("FEISHU_APP_SECRET")
                and _env("BITABLE_APP_TOKEN") and _env("BITABLE_CREATORS_TABLE"))


# ============================================================
# Feishu auth + Bitable helpers (mirror src/bitable.py)
# ============================================================

_token_cache = {"token": "", "exp": 0}


def _tenant_token() -> str | None:
    now = int(time.time())
    if _token_cache["token"] and _token_cache["exp"] - now > 120:
        return _token_cache["token"]
    try:
        r = requests.post(
            f"{API}/auth/v3/tenant_access_token/internal",
            json={"app_id": _env("FEISHU_APP_ID"),
                  "app_secret": _env("FEISHU_APP_SECRET")},
            timeout=10,
        ).json()
    except Exception as exc:
        logger.warning("Feishu auth failed: %s", exc)
        return None
    if r.get("code") != 0:
        logger.warning("Feishu auth rejected: %s", r)
        return None
    _token_cache["token"] = r["tenant_access_token"]
    _token_cache["exp"] = now + int(r.get("expire", 7200))
    return _token_cache["token"]


def _headers() -> dict | None:
    tok = _tenant_token()
    if not tok:
        return None
    return {"Authorization": f"Bearer {tok}",
            "Content-Type": "application/json; charset=utf-8"}


def _fetch_creators_needing_backfill(limit: int) -> list[tuple[str, str]]:
    """Return [(record_id, username), ...] of creators where 粉丝数 is empty/0."""
    table_id = _env("BITABLE_CREATORS_TABLE")
    headers = _headers()
    if not headers:
        return []
    url = (f"{API}/bitable/v1/apps/{_env('BITABLE_APP_TOKEN')}"
           f"/tables/{table_id}/records")
    targets = []
    page_token = None
    for _ in range(40):
        params = {"page_size": 500}
        if page_token:
            params["page_token"] = page_token
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=30).json()
        except Exception as exc:
            logger.warning("Bitable list creators failed: %s", exc)
            break
        if resp.get("code") != 0:
            logger.warning("Bitable list creators rejected: %s", resp)
            break
        d = resp.get("data", {})
        for rec in d.get("items", []):
            f = rec.get("fields", {})
            username = f.get("用户名")
            followers = f.get("粉丝数")
            avatar = f.get("头像")
            if not username:
                continue
            # Need backfill if follower_count is empty OR avatar is empty
            needs_followers = not followers or followers in (0, "0", "")
            needs_avatar = not avatar
            if needs_followers or needs_avatar:
                targets.append((rec["record_id"], username))
                if len(targets) >= limit:
                    return targets
        page_token = d.get("page_token")
        if not d.get("has_more"):
            break
    return targets


def _update_creator(record_id: str, fields: dict) -> bool:
    headers = _headers()
    if not headers:
        return False
    url = (f"{API}/bitable/v1/apps/{_env('BITABLE_APP_TOKEN')}"
           f"/tables/{_env('BITABLE_CREATORS_TABLE')}/records/{record_id}")
    try:
        r = requests.put(url, headers=headers,
                         json={"fields": fields}, timeout=15).json()
    except Exception as exc:
        logger.warning("update_record exception: %s", exc)
        return False
    return r.get("code") == 0


def _ensure_field(name: str, ftype: int) -> None:
    """Create a field on the creators table if it doesn't exist yet."""
    headers = _headers()
    if not headers:
        return
    table_id = _env("BITABLE_CREATORS_TABLE")
    url = f"{API}/bitable/v1/apps/{_env('BITABLE_APP_TOKEN')}/tables/{table_id}/fields"
    # Check existing
    try:
        r = requests.get(url, headers=headers, params={"page_size": 100}, timeout=15).json()
        existing = {f["field_name"] for f in r.get("data", {}).get("items", [])}
    except Exception:
        return
    if name in existing:
        return
    try:
        requests.post(url, headers=headers,
                      json={"field_name": name, "type": ftype}, timeout=15)
    except Exception:
        pass


# ============================================================
# TikTok scraping
# ============================================================

def _fetch_user_stats(username: str) -> dict | None:
    """Pull stats off the public TikTok user-page HTML."""
    url = f"https://www.tiktok.com/@{username.lstrip('@')}"
    headers = {
        "User-Agent": random.choice(UA_POOL),
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
    }
    try:
        r = requests.get(url, headers=headers, timeout=20)
    except Exception as exc:
        logger.warning("TikTok HTTP fail @%s: %s", username, exc)
        return None
    if r.status_code != 200:
        logger.warning("TikTok HTTP %s @%s", r.status_code, username)
        return None
    m = REHYDRATE_RE.search(r.text)
    if not m:
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
        "video_count":    int(stats.get("videoCount") or 0),
        "nickname":       user.get("nickname") or "",
        "avatar_url":     user.get("avatarLarger") or user.get("avatarMedium") or "",
    }


# ============================================================
# Public entry
# ============================================================

def backfill_followers() -> int:
    """Top-up missing follower_count for up to MAX_PER_RUN creators per call.
    Safe to call every workflow run — only touches records with empty 粉丝数."""
    if not is_configured():
        logger.info("Bitable not configured — skipping follower backfill")
        return 0

    # Ensure the 头像 field exists (type=1 = text)
    _ensure_field("头像", 1)

    targets = _fetch_creators_needing_backfill(MAX_PER_RUN)
    if not targets:
        logger.info("No creators need follower backfill")
        return 0
    logger.info("Backfilling follower_count for %d creators", len(targets))

    ok = 0
    for i, (rid, username) in enumerate(targets, 1):
        stats = _fetch_user_stats(username)
        if not stats:
            logger.warning("[%d/%d] FAIL @%s", i, len(targets), username)
            time.sleep(random.uniform(SLEEP_MIN, SLEEP_MAX))
            continue
        update = {"粉丝数": stats["follower_count"]}
        if stats["nickname"]:
            update["昵称"] = stats["nickname"]
        if stats.get("avatar_url"):
            update["头像"] = stats["avatar_url"]
        if _update_creator(rid, update):
            logger.info("[%d/%d] OK @%s — %s followers",
                        i, len(targets), username,
                        f"{stats['follower_count']:,}")
            ok += 1
        time.sleep(random.uniform(SLEEP_MIN, SLEEP_MAX))

    logger.info("Follower backfill done: %d/%d", ok, len(targets))
    return ok
