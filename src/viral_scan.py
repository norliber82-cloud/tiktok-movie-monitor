"""Viral scan: pull recent videos from followed creators and flag 1M+ in 3d.

Also pulls the user's public liked videos via TikTokApi (Playwright).

Designed to run on GitHub Actions (clean IP, no cookie needed).
Reads the creator list from the Feishu Bitable `following_creators` table,
then uses TikTokApi (Playwright) to pull each creator's recent videos.
Any video with >= 1M plays posted in the last 3 days gets written to the
main videos table as a RED-tier hit.

Usage:
    python -m src.viral_scan
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

import requests as _requests

from . import bitable as _b

logger = logging.getLogger(__name__)

API = "https://open.feishu.cn/open-apis"

# ============================================================
# Config
# ============================================================

FOLLOWING_CREATORS_TABLE = "tblRc6b9FrxMu4Gv"
LIKED_VIDEOS_TABLE      = "tblzY8kdXrffenE9"
VIRAL_MIN_PLAYS = 1_000_000
VIRAL_WINDOW_DAYS = 3
VIDEOS_PER_CREATOR = 30

# Accounts whose public liked-videos we pull
LIKED_ACCOUNTS = [
    "powerfuljourney",   # US
    "kariasxshf9",       # JP
]
LIKED_MAX_AGE_DAYS = 7

# TikTokApi session config — tuned for reliability
NUM_SESSIONS = 3
SLEEP_AFTER_SESSION = 5
PER_USER_TIMEOUT = 15  # seconds max per user before giving up


# ============================================================
# Feishu: read creator usernames from the table
# ============================================================

def _fetch_creator_usernames() -> list[str]:
    """Pull all usernames from the following_creators table."""
    headers = _b._headers()
    if not headers:
        logger.error("Feishu auth failed — cannot read creators")
        return []
    app_token = _b._env("BITABLE_APP_TOKEN")
    url = f"{API}/bitable/v1/apps/{app_token}/tables/{FOLLOWING_CREATORS_TABLE}/records"
    usernames = []
    page_token = None
    for _ in range(40):
        params = {"page_size": 500}
        if page_token:
            params["page_token"] = page_token
        try:
            r = _requests.get(url, headers=headers, params=params, timeout=30).json()
        except Exception as exc:
            logger.warning("Fetch creators failed: %s", exc)
            break
        if r.get("code") != 0:
            logger.error("Fetch creators rejected: %s", r)
            break
        d = r.get("data", {})
        for rec in d.get("items", []):
            f = rec.get("fields", {}) or {}
            u = f.get("用户名")
            if u and isinstance(u, str) and u.strip():
                usernames.append(u.strip().lstrip("@"))
        page_token = d.get("page_token")
        if not d.get("has_more"):
            break
    return usernames


# ============================================================
# Video shape helper
# ============================================================

def _shape_video(vd: dict, fallback_author: str = "") -> Optional[dict]:
    """Parse a TikTokApi video dict into our standard shape."""
    try:
        a = vd.get("author", {}) or {}
        s = vd.get("stats", {}) or {}
        vid_obj = vd.get("video", {}) or {}
        vid_id = str(vd.get("id", ""))
        if not vid_id:
            return None
        uniq = a.get("uniqueId") or fallback_author
        return {
            "video_id":      vid_id,
            "author_unique": uniq,
            "nickname":      a.get("nickname") or "",
            "caption":       vd.get("desc", "") or "",
            "create_time":   int(vd.get("createTime", 0)),
            "play_count":    int(s.get("playCount") or 0),
            "like_count":    int(s.get("diggCount") or 0),
            "comment_count": int(s.get("commentCount") or 0),
            "share_count":   int(s.get("shareCount") or 0),
            "duration":      int(vid_obj.get("duration", 0) or 0),
            "video_url":     f"https://www.tiktok.com/@{uniq}/video/{vid_id}",
            "cover_url":     vid_obj.get("cover", "") or "",
        }
    except Exception:
        return None


# ============================================================
# TikTokApi: unified session for all pulls
# ============================================================

async def _run_all(usernames: list[str], liked_accounts: list[str],
                   ms_token: str, videos_per_creator: int
                   ) -> tuple[dict[str, list[dict]], dict[str, list[dict]]]:
    """Single Playwright session that does both:
    1. Pull videos for each creator in `usernames`
    2. Pull liked videos for each account in `liked_accounts`

    Returns (creator_videos, liked_videos) dicts.
    """
    from TikTokApi import TikTokApi

    creator_results: dict[str, list[dict]] = {}
    liked_results: dict[str, list[dict]] = {}

    success_count = 0
    fail_count = 0

    async with TikTokApi() as api:
        await api.create_sessions(
            ms_tokens=[ms_token],
            num_sessions=NUM_SESSIONS,
            sleep_after=SLEEP_AFTER_SESSION,
            headless=True,
            browser="webkit",
            enable_session_recovery=True,
            allow_partial_sessions=True,
            min_sessions=1,
        )

        # --- Part 1: Creator videos ---
        logger.info("--- Pulling videos for %d creators ---", len(usernames))
        for i, u in enumerate(usernames):
            try:
                user = api.user(username=u)
                vids = []
                async for v in user.videos(count=videos_per_creator):
                    shaped = _shape_video(v.as_dict, fallback_author=u)
                    if shaped:
                        vids.append(shaped)
                creator_results[u] = vids
                success_count += 1
                if vids:
                    logger.info("  [%d/%d] @%s: %d videos",
                                i + 1, len(usernames), u, len(vids))
            except Exception as exc:
                fail_count += 1
                # Only log first few failures to avoid spam
                if fail_count <= 5:
                    logger.warning("  [%d/%d] @%s failed: %s",
                                   i + 1, len(usernames), u,
                                   str(exc)[:100])
                elif fail_count == 6:
                    logger.warning("  ... suppressing further failure logs")
                creator_results[u] = []
            await asyncio.sleep(1.5)

        logger.info("Creator videos: %d success, %d failed out of %d",
                    success_count, fail_count, len(usernames))

        # --- Part 2: Liked videos ---
        logger.info("--- Pulling liked videos for %d accounts ---",
                    len(liked_accounts))
        for username in liked_accounts:
            try:
                user = api.user(username=username)
                vids = []
                async for v in user.liked(count=200):
                    shaped = _shape_video(v.as_dict)
                    if shaped:
                        vids.append(shaped)
                liked_results[username] = vids
                logger.info("  @%s liked: %d videos", username, len(vids))
            except Exception as exc:
                logger.warning("  @%s liked failed: %s", username, str(exc)[:100])
                liked_results[username] = []
            await asyncio.sleep(2.0)

    return creator_results, liked_results


# ============================================================
# Filter + write
# ============================================================

def _to_ms(ts) -> Optional[int]:
    if not ts:
        return None
    return int(ts) * 1000


def _write_viral(viral_rows: list[dict]) -> int:
    """Write viral hits to the main videos table."""
    if not viral_rows:
        return 0
    table_id = _b._env("BITABLE_VIDEOS_TABLE")
    if not table_id:
        logger.warning("BITABLE_VIDEOS_TABLE not set")
        return 0

    allowed = _b._ensure_fields(table_id, _b.VIDEO_FIELDS)
    existing = _b._fetch_existing_field_values(table_id, "视频ID")
    new_rows = [r for r in viral_rows if str(r["video_id"]) not in existing]
    skipped = len(viral_rows) - len(new_rows)

    now_ms = int(time.time() * 1000)
    records = []
    for r in new_rows:
        u = r.get("author_unique") or ""
        records.append({
            "视频ID":     str(r["video_id"]),
            "平台":       "tiktok",
            "等级":       "RED",
            "可信度":     "高",
            "语言":       "",
            "作者":       f"@{u}",
            "标题":       (r.get("caption") or "")[:2000],
            "播放量":     r.get("play_count") or 0,
            "点赞数":     r.get("like_count") or 0,
            "评论数":     r.get("comment_count") or 0,
            "分享数":     r.get("share_count") or 0,
            "时长(秒)":   r.get("duration") or 0,
            "匹配标签":   "following_viral",
            "标签":       "",
            "发布时间":   _to_ms(r.get("create_time")),
            "入库时间":   now_ms,
            "视频链接":   {"link": r.get("video_url"), "text": "打开"} if r.get("video_url") else None,
            "视频URL":    r.get("video_url") or "",
            "封面链接":   {"link": r.get("cover_url"), "text": "封面"} if r.get("cover_url") else None,
            "封面URL":    r.get("cover_url") or "",
        })

    created = _b._batch_create(table_id, records, allowed)
    logger.info("viral_scan: %d found, %d new, %d dup-skip, %d written",
                len(viral_rows), len(new_rows), skipped, created)
    return created


def _write_liked(liked_vids: list[dict], region: str) -> int:
    """Write liked videos to the liked_videos table."""
    if not liked_vids:
        return 0
    from local_processor.account_tracker import bitable_io
    written = bitable_io.write_liked_videos(liked_vids, source_account=region)
    # Also write minimal creator records
    unique_authors = {v["author_unique"] for v in liked_vids
                      if v.get("author_unique")}
    if unique_authors:
        minimal = [{"unique_id": u, "nickname": "", "follower_count": 0}
                   for u in unique_authors]
        bitable_io.write_creators(minimal, f"liked_{region}")
    return written


# ============================================================
# Main
# ============================================================

def _setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def main():
    _setup_logging()
    t0 = time.time()

    ms_token = os.getenv("MS_TOKEN", "").strip()
    if not ms_token:
        logger.error("MS_TOKEN not set"); sys.exit(1)
    if not _b.is_configured():
        logger.error("Feishu not configured"); sys.exit(1)

    # 1. Read creators from Bitable
    usernames = _fetch_creator_usernames()
    logger.info("Loaded %d creators from following_creators table", len(usernames))

    # 2. Run everything in one Playwright session
    creator_videos, liked_videos = asyncio.run(
        _run_all(usernames, LIKED_ACCOUNTS, ms_token, VIDEOS_PER_CREATOR)
    )

    # 3. Filter creator videos: 1M+ plays in last 3 days
    now = int(time.time())
    cutoff = now - VIRAL_WINDOW_DAYS * 86400
    viral = []
    total_vids_pulled = 0
    for u, vids in creator_videos.items():
        total_vids_pulled += len(vids)
        for v in vids:
            ct = int(v.get("create_time") or 0)
            plays = int(v.get("play_count") or 0)
            if ct >= cutoff and plays >= VIRAL_MIN_PLAYS:
                viral.append(v)

    logger.info("Scanned %d total videos across %d creators",
                total_vids_pulled, len(creator_videos))
    logger.info("Found %d viral videos (>=%dM in %dd)",
                len(viral), VIRAL_MIN_PLAYS // 1_000_000, VIRAL_WINDOW_DAYS)

    # 4. Write viral hits
    if viral:
        _write_viral(viral)
    else:
        logger.info("No viral hits this run")

    # 5. Process liked videos
    liked_cutoff = now - LIKED_MAX_AGE_DAYS * 86400
    for username, vids in liked_videos.items():
        region = "us" if username == "powerfuljourney" else "jp"
        recent = [v for v in vids if int(v.get("create_time") or 0) >= liked_cutoff]
        logger.info("Liked @%s: %d total, %d within %d days",
                    username, len(vids), len(recent), LIKED_MAX_AGE_DAYS)
        if recent:
            written = _write_liked(recent, region)
            logger.info("  @%s: %d written", username, written)

    elapsed = time.time() - t0
    logger.info("=== viral_scan finished in %.1f minutes ===", elapsed / 60)


if __name__ == "__main__":
    main()
