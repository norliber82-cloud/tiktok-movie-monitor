"""Feishu Bitable writer.

Writes video hits and creator records into two Bitable data tables.
Completely optional — if the required env vars are missing, this module
becomes a no-op. The code auto-creates any missing columns on first use.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

import requests

from . import db

logger = logging.getLogger(__name__)

API_BASE = "https://open.feishu.cn/open-apis"


# ------------------------- env / config -------------------------

def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def is_configured() -> bool:
    return bool(
        _env("FEISHU_APP_ID")
        and _env("FEISHU_APP_SECRET")
        and _env("BITABLE_APP_TOKEN")
        and (_env("BITABLE_VIDEOS_TABLE") or _env("BITABLE_CREATORS_TABLE"))
    )


# ------------------------- tenant access token -------------------------

_token_cache = {"token": "", "exp": 0}


def _get_tenant_token() -> Optional[str]:
    now = int(time.time())
    if _token_cache["token"] and _token_cache["exp"] - now > 120:
        return _token_cache["token"]
    try:
        resp = requests.post(
            f"{API_BASE}/auth/v3/tenant_access_token/internal",
            json={"app_id": _env("FEISHU_APP_ID"),
                  "app_secret": _env("FEISHU_APP_SECRET")},
            timeout=10,
        )
        data = resp.json()
    except Exception as exc:
        logger.exception("Feishu auth failed: %s", exc)
        return None
    if data.get("code") != 0:
        logger.error("Feishu auth rejected: %s", data)
        return None
    _token_cache["token"] = data["tenant_access_token"]
    _token_cache["exp"] = now + int(data.get("expire", 7200))
    return _token_cache["token"]


def _headers() -> Optional[dict]:
    tok = _get_tenant_token()
    if not tok:
        return None
    return {"Authorization": f"Bearer {tok}",
            "Content-Type": "application/json; charset=utf-8"}


# ------------------------- schema definition -------------------------

# Feishu Bitable field types
#   1 = Text, 2 = Number, 3 = SingleSelect, 5 = DateTime, 11 = User (N/A),
#   15 = Link, 17 = Attachment, 1001 = CreatedTime
VIDEO_FIELDS = [
    ("视频ID",       1),
    ("平台",         3),
    ("等级",         3),
    ("可信度",       3),
    ("语言",         3),
    ("作者",         1),
    ("标题",         1),
    ("原片名",       1),
    ("播放量",       2),
    ("点赞数",       2),
    ("评论数",       2),
    ("分享数",       2),
    ("时长(秒)",     2),
    ("匹配标签",     1),
    ("标签",         1),
    ("发布时间",     5),
    ("入库时间",     5),
    ("视频链接",     15),
    ("视频URL",      1),
    ("封面链接",     15),
    ("封面URL",      1),
]

CREATOR_FIELDS = [
    ("用户名",       1),
    ("昵称",         1),
    ("语言",         3),
    ("粉丝数",       2),
    ("中位播放",     2),
    ("7日最高播放",  2),
    ("14日发帖数",   2),
    ("30日发帖数",   2),
    ("垂直度",       2),
    ("判定原因",     1),
    ("评估时间",     5),
    ("主页URL",      1),
    ("主页链接",     15),
]


def _get_field_map(table_id: str) -> dict[str, str]:
    """Returns {field_name: field_id}. Auto-creates missing fields."""
    headers = _headers()
    if not headers:
        return {}
    app_token = _env("BITABLE_APP_TOKEN")

    url = f"{API_BASE}/bitable/v1/apps/{app_token}/tables/{table_id}/fields"
    try:
        resp = requests.get(url, headers=headers, params={"page_size": 100}, timeout=10)
        data = resp.json()
    except Exception as exc:
        logger.exception("Fetch Bitable fields failed: %s", exc)
        return {}
    if data.get("code") != 0:
        logger.error("Fetch Bitable fields rejected: %s", data)
        return {}
    return {f["field_name"]: f["field_name"]
            for f in data.get("data", {}).get("items", [])}


def _ensure_fields(table_id: str, wanted: list[tuple[str, int]]) -> set[str]:
    """Create missing fields. Returns set of field names we want to write
    (i.e. the names from `wanted`), regardless of what else exists in the table."""
    headers = _headers()
    if not headers:
        return {name for name, _ in wanted}
    app_token = _env("BITABLE_APP_TOKEN")
    existing = set(_get_field_map(table_id).keys())

    for name, ftype in wanted:
        if name in existing:
            continue
        url = f"{API_BASE}/bitable/v1/apps/{app_token}/tables/{table_id}/fields"
        try:
            resp = requests.post(url, headers=headers,
                                 json={"field_name": name, "type": ftype},
                                 timeout=10)
            data = resp.json()
        except Exception as exc:
            logger.warning("Could not create field %s: %s", name, exc)
            continue
        if data.get("code") == 0:
            existing.add(name)
        else:
            logger.warning("Create field %s rejected: %s", name, data)

    # Always return the wanted field names so the payload filter works correctly
    return {name for name, _ in wanted}


# ------------------------- row conversion -------------------------

def _to_ms(ts: Optional[int]) -> Optional[int]:
    if not ts:
        return None
    return int(ts) * 1000


def _video_record(row) -> dict:
    return {
        "视频ID": str(row["video_id"]),
        "平台": (row["platform"] or "tiktok") if "platform" in row.keys() else "tiktok",
        "等级": row["tier"] or "",
        "可信度": row.get("confidence") or "",
        "语言": row["language"] or "",
        "作者": f"@{row['author_unique']}",
        "标题": (row["caption"] or "")[:2000],
        "原片名": row.get("source_title") or "",
        "播放量": row["play_count"] or 0,
        "点赞数": row["like_count"] or 0,
        "评论数": row["comment_count"] or 0,
        "分享数": row["share_count"] or 0,
        "时长(秒)": row["duration"] or 0,
        "匹配标签": row["matched_tag"] or "",
        "标签": row["hashtags"] or "",
        "发布时间": _to_ms(row["create_time"]),
        "入库时间": _to_ms(row["first_seen_at"]),
        "视频链接": {"link": row["video_url"], "text": "打开"},
        "视频URL": row["video_url"] or "",
        "封面链接": {"link": row["cover_url"], "text": "封面"} if row["cover_url"] else None,
        "封面URL": row["cover_url"] or "",
    }


def _creator_record(row) -> dict:
    profile_url = f"https://www.tiktok.com/@{row['author_unique']}"
    return {
        "用户名": row["author_unique"],
        "昵称": row["nickname"] or "",
        "语言": row["language"] or "",
        "粉丝数": row["follower_count"] or 0,
        "中位播放": row["median_plays"] or 0,
        "7日最高播放": row["max_plays_7d"] or 0,
        "14日发帖数": row["posts_14d"] or 0,
        "30日发帖数": row["posts_30d"] or 0,
        "垂直度": float(row["vertical_ratio"] or 0),
        "判定原因": row["reason"] or "",
        "评估时间": _to_ms(row["last_evaluated_at"]),
        "主页URL": profile_url,
        "主页链接": {"link": profile_url, "text": "主页"},
    }


# ------------------------- batch insert -------------------------

def _batch_create(table_id: str, records: list[dict], allowed_fields: set[str]) -> int:
    if not records:
        return 0
    headers = _headers()
    if not headers:
        return 0
    app_token = _env("BITABLE_APP_TOKEN")
    url = f"{API_BASE}/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_create"

    # Feishu limit: 500 records per batch
    created = 0
    for i in range(0, len(records), 500):
        chunk = records[i:i + 500]
        # prune None values and unknown fields
        payload = [{"fields": {k: v for k, v in r.items()
                               if v is not None and k in allowed_fields}}
                   for r in chunk]
        try:
            resp = requests.post(url, headers=headers,
                                 json={"records": payload}, timeout=20)
            data = resp.json()
        except Exception as exc:
            logger.exception("Bitable batch_create failed: %s", exc)
            continue
        if data.get("code") == 0:
            created += len(data.get("data", {}).get("records", []))
        else:
            logger.error("Bitable batch_create rejected: %s", data)
    return created


def sync_videos() -> int:
    if not is_configured():
        return 0
    table_id = _env("BITABLE_VIDEOS_TABLE")
    if not table_id:
        return 0

    rows = db.fetch_unsynced_videos()
    if not rows:
        return 0

    allowed = _ensure_fields(table_id, VIDEO_FIELDS)
    # Pre-check Bitable for IDs already present (defense against cache loss)
    existing_ids = _fetch_existing_field_values(table_id, "视频ID")
    new_rows = [r for r in rows if str(r["video_id"]) not in existing_ids]

    skipped = len(rows) - len(new_rows)
    if skipped:
        # Mark the skipped rows as synced so we don't re-check them next run
        db.mark_videos_synced([r["video_id"] for r in rows
                               if str(r["video_id"]) in existing_ids])
        logger.info("Bitable videos: skipped %d already-present", skipped)

    records = [_video_record(r) for r in new_rows]
    created = _batch_create(table_id, records, allowed)
    if created:
        db.mark_videos_synced([r["video_id"] for r in new_rows[:created]])
    logger.info("Bitable videos synced: %d / %d (skipped %d dup)",
                created, len(new_rows), skipped)
    return created


def sync_creators() -> int:
    if not is_configured():
        return 0
    table_id = _env("BITABLE_CREATORS_TABLE")
    if not table_id:
        return 0

    rows = db.fetch_unsynced_monitored_authors()
    if not rows:
        return 0

    allowed = _ensure_fields(table_id, CREATOR_FIELDS)
    existing_users = _fetch_existing_field_values(table_id, "用户名")
    new_rows = [r for r in rows if r["author_unique"] not in existing_users]

    skipped = len(rows) - len(new_rows)
    if skipped:
        db.mark_authors_synced([r["author_unique"] for r in rows
                                if r["author_unique"] in existing_users])
        logger.info("Bitable creators: skipped %d already-present", skipped)

    records = [_creator_record(r) for r in new_rows]
    created = _batch_create(table_id, records, allowed)
    if created:
        db.mark_authors_synced([r["author_unique"] for r in new_rows[:created]])
    logger.info("Bitable creators synced: %d / %d (skipped %d dup)",
                created, len(new_rows), skipped)
    return created


def _fetch_existing_field_values(table_id: str, field_name: str) -> set[str]:
    """Return the set of already-present values for a single field, used for
    pre-write dedupe. Cheap (just one paginated GET)."""
    headers = _headers()
    if not headers:
        return set()
    app_token = _env("BITABLE_APP_TOKEN")
    url = f"{API_BASE}/bitable/v1/apps/{app_token}/tables/{table_id}/records"
    out = set()
    page_token = None
    for _ in range(40):
        params = {"page_size": 500}
        if page_token:
            params["page_token"] = page_token
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=30).json()
        except Exception as exc:
            logger.warning("dedupe pre-fetch failed: %s", exc)
            break
        if resp.get("code") != 0:
            break
        d = resp.get("data", {})
        for rec in d.get("items", []):
            v = rec.get("fields", {}).get(field_name)
            if v:
                out.add(str(v))
        page_token = d.get("page_token")
        if not d.get("has_more"):
            break
    return out
