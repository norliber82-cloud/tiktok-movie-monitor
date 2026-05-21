"""Bitable writer for the two new tables (liked_videos, following_creators).

Reuses the auth/Token helpers from src.bitable so we don't duplicate logic.
"""

from __future__ import annotations

import logging
import os
import time

import requests

from src import bitable as _b

logger = logging.getLogger(__name__)
API = "https://open.feishu.cn/open-apis"

# ============================================================
# Config (table IDs hard-coded for the two new tables)
# ============================================================

LIKED_VIDEOS_TABLE       = "tblzY8kdXrffenE9"
FOLLOWING_CREATORS_TABLE = "tblRc6b9FrxMu4Gv"


# ============================================================
# Field schema for the new tables
# ============================================================

LIKED_VIDEO_FIELDS = [
    ("视频ID",       1),
    ("来源账号",     3),   # us / jp
    ("作者",         1),
    ("作者昵称",     1),
    ("标题",         1),
    ("播放量",       2),
    ("点赞数",       2),
    ("评论数",       2),
    ("分享数",       2),
    ("时长(秒)",     2),
    ("发布时间",     5),
    ("收录时间",     5),
    ("视频URL",      1),
    ("视频按钮",    15),
    ("封面URL",      1),
]

CREATOR_FIELDS = [
    ("用户名",       1),
    ("昵称",         1),
    ("来源",         3),    # following_us / following_jp / liked_us / liked_jp / recurse
    ("粉丝数",       2),
    ("关注数",       2),
    ("视频数",       2),
    ("总点赞",       2),
    ("简介",         1),
    ("头像",         1),
    ("主页URL",      1),
    ("主页按钮",    15),
    ("发现时间",     5),
    ("最近爆款",     1),
]


# ============================================================
# Helpers
# ============================================================

def _to_ms(ts) -> int | None:
    if not ts: return None
    try:    return int(ts) * 1000
    except: return None


def _exists_check(table_id: str, field: str) -> set[str]:
    """Return the set of values currently in `field` on this table.
    Used to dedupe before insert."""
    return _b._fetch_existing_field_values(table_id, field)


def _ensure(table_id: str, schema):
    return _b._ensure_fields(table_id, schema)


def _batch_create(table_id: str, records: list[dict], allowed: set[str]) -> int:
    if not records:
        return 0
    return _b._batch_create(table_id, records, allowed)


# ============================================================
# Public writers
# ============================================================

def write_liked_videos(rows: list[dict], source_account: str) -> int:
    """rows: list of dicts from Account.get_liked_videos().
    source_account: 'us' or 'jp'."""
    if not rows:
        return 0

    allowed  = _ensure(LIKED_VIDEOS_TABLE, LIKED_VIDEO_FIELDS)
    existing = _exists_check(LIKED_VIDEOS_TABLE, "视频ID")
    new_rows = [r for r in rows if str(r["video_id"]) not in existing]
    skipped  = len(rows) - len(new_rows)

    now_ms = int(time.time() * 1000)
    records = []
    for r in new_rows:
        records.append({
            "视频ID":     str(r["video_id"]),
            "来源账号":   source_account,
            "作者":       f"@{r.get('author_unique', '')}",
            "作者昵称":   r.get("nickname") or "",
            "标题":       (r.get("caption") or "")[:2000],
            "播放量":     r.get("play_count") or 0,
            "点赞数":     r.get("like_count") or 0,
            "评论数":     r.get("comment_count") or 0,
            "分享数":     r.get("share_count") or 0,
            "时长(秒)":   r.get("duration") or 0,
            "发布时间":   _to_ms(r.get("create_time")),
            "收录时间":   now_ms,
            "视频URL":    r.get("video_url") or "",
            "视频按钮":   {"link": r.get("video_url"), "text": "打开"} if r.get("video_url") else None,
            "封面URL":    r.get("cover_url") or "",
        })

    created = _batch_create(LIKED_VIDEOS_TABLE, records, allowed)
    logger.info("liked_videos: %d new, %d skipped (dup), %d written",
                len(new_rows), skipped, created)
    return created


def write_viral_videos_to_main(rows: list[dict], region: str) -> int:
    """For req #3: a video found on a followed creator's profile that
    hit 1M+ plays in 3d. Writes into the main BITABLE_VIDEOS_TABLE so
    it shows up alongside the hashtag-monitor hits.

    region: 'US' / 'JP'
    """
    if not rows:
        return 0
    table_id = os.getenv("BITABLE_VIDEOS_TABLE", "").strip()
    if not table_id:
        logger.warning("BITABLE_VIDEOS_TABLE not set — skipping viral write")
        return 0

    allowed = _b._ensure_fields(table_id, _b.VIDEO_FIELDS)
    existing = _b._fetch_existing_field_values(table_id, "视频ID")
    new_rows = [r for r in rows if str(r["video_id"]) not in existing]
    skipped = len(rows) - len(new_rows)

    now_ms = int(time.time() * 1000)
    records = []
    for r in new_rows:
        u = r.get("author_unique") or ""
        records.append({
            "视频ID":     str(r["video_id"]),
            "平台":       "tiktok",
            "等级":       "RED",
            "可信度":     "高",
            "语言":       "en" if region == "US" else "ja",
            "作者":       f"@{u}",
            "标题":       (r.get("caption") or "")[:2000],
            "播放量":     r.get("play_count") or 0,
            "点赞数":     r.get("like_count") or 0,
            "评论数":     r.get("comment_count") or 0,
            "分享数":     r.get("share_count") or 0,
            "时长(秒)":   r.get("duration") or 0,
            "匹配标签":   f"following_{region.lower()}",
            "标签":       "",
            "发布时间":   _to_ms(r.get("create_time")),
            "入库时间":   now_ms,
            "视频链接":   {"link": r.get("video_url"), "text": "打开"} if r.get("video_url") else None,
            "视频URL":    r.get("video_url") or "",
            "封面链接":   {"link": r.get("cover_url"), "text": "封面"} if r.get("cover_url") else None,
            "封面URL":    r.get("cover_url") or "",
        })

    created = _b._batch_create(table_id, records, allowed)
    logger.info("viral_videos[%s] -> main table: %d new, %d dup-skip, %d written",
                region, len(new_rows), skipped, created)
    return created


def write_creators(rows: list[dict], source_label: str) -> int:
    """rows: list of dicts (must include unique_id, nickname, follower_count, etc.)
    source_label: 'following_us' / 'following_jp' / 'liked_us' / 'liked_jp' / 'recurse_us' / 'recurse_jp'."""
    if not rows:
        return 0

    allowed  = _ensure(FOLLOWING_CREATORS_TABLE, CREATOR_FIELDS)
    existing = _exists_check(FOLLOWING_CREATORS_TABLE, "用户名")
    new_rows = [r for r in rows if r.get("unique_id") and r["unique_id"] not in existing]
    skipped  = len(rows) - len(new_rows)

    now_ms = int(time.time() * 1000)
    records = []
    for r in new_rows:
        u = r["unique_id"]
        profile = f"https://www.tiktok.com/@{u}"
        records.append({
            "用户名":     u,
            "昵称":       r.get("nickname") or "",
            "来源":       source_label,
            "粉丝数":     r.get("follower_count") or 0,
            "关注数":     r.get("following_count") or 0,
            "视频数":     r.get("video_count") or 0,
            "总点赞":     r.get("heart_count") or 0,
            "简介":       (r.get("signature") or "")[:500],
            "头像":       r.get("avatar_url") or "",
            "主页URL":    profile,
            "主页按钮":   {"link": profile, "text": "主页"},
            "发现时间":   now_ms,
        })

    created = _batch_create(FOLLOWING_CREATORS_TABLE, records, allowed)
    logger.info("creators: %d new, %d skipped (dup), %d written",
                len(new_rows), skipped, created)
    return created
