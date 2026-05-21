"""Viral scan: pull recent videos from followed creators and flag 1M+ in 3d.

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
VIRAL_MIN_PLAYS = 1_000_000
VIRAL_WINDOW_DAYS = 3
VIDEOS_PER_CREATOR = 30


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
# TikTokApi: pull videos
# ============================================================

async def _pull_videos(usernames: list[str], ms_token: str,
                       count: int) -> dict[str, list[dict]]:
    from TikTokApi import TikTokApi

    results: dict[str, list[dict]] = {}
    async with TikTokApi() as api:
        await api.create_sessions(
            ms_tokens=[ms_token],
            num_sessions=1,
            sleep_after=3,
            headless=True,
            browser="webkit",
        )
        for u in usernames:
            try:
                user = api.user(username=u)
                vids = []
                async for v in user.videos(count=count):
                    vd = v.as_dict
                    a = vd.get("author", {}) or {}
                    s = vd.get("stats", {}) or {}
                    vid_obj = vd.get("video", {}) or {}
                    vid_id = str(vd.get("id", ""))
                    uniq = a.get("uniqueId") or u
                    vids.append({
                        "video_id":      vid_id,
                        "author_unique": uniq,
                        "caption":       vd.get("desc", "") or "",
                        "create_time":   int(vd.get("createTime", 0)),
                        "play_count":    int(s.get("playCount") or 0),
                        "like_count":    int(s.get("diggCount") or 0),
                        "comment_count": int(s.get("commentCount") or 0),
                        "share_count":   int(s.get("shareCount") or 0),
                        "duration":      int(vid_obj.get("duration", 0) or 0),
                        "video_url":     f"https://www.tiktok.com/@{uniq}/video/{vid_id}",
                        "cover_url":     vid_obj.get("cover", "") or "",
                    })
                results[u] = vids
                logger.info("  @%s: %d videos", u, len(vids))
            except Exception as exc:
                logger.warning("  @%s failed: %s", u, exc)
                results[u] = []
            await asyncio.sleep(2.0)
    return results


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

    ms_token = os.getenv("MS_TOKEN", "").strip()
    if not ms_token:
        logger.error("MS_TOKEN not set"); sys.exit(1)
    if not _b.is_configured():
        logger.error("Feishu not configured"); sys.exit(1)

    # 1. Read creators from Bitable
    usernames = _fetch_creator_usernames()
    logger.info("Loaded %d creators from following_creators table", len(usernames))
    if not usernames:
        logger.info("No creators to scan"); return

    # 2. Pull videos via TikTokApi
    all_videos = asyncio.run(_pull_videos(usernames, ms_token, VIDEOS_PER_CREATOR))

    # 3. Filter: 1M+ plays in last 3 days
    now = int(time.time())
    cutoff = now - VIRAL_WINDOW_DAYS * 86400
    viral = []
    for u, vids in all_videos.items():
        for v in vids:
            ct = int(v.get("create_time") or 0)
            plays = int(v.get("play_count") or 0)
            if ct >= cutoff and plays >= VIRAL_MIN_PLAYS:
                viral.append(v)

    logger.info("Found %d viral videos (>=%dM in %dd) across %d creators",
                len(viral), VIRAL_MIN_PLAYS // 1_000_000,
                VIRAL_WINDOW_DAYS, len(all_videos))

    # 4. Write to Bitable
    if viral:
        _write_viral(viral)
    else:
        logger.info("No viral hits this run")


if __name__ == "__main__":
    main()
