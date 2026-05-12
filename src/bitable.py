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
    ("video_id",       1),
    ("tier",           3),
    ("language",       3),
    ("author",         1),
    ("caption",        1),
    ("play_count",     2),
    ("like_count",     2),
    ("comment_count",  2),
    ("share_count",    2),
    ("duration",       2),
    ("matched_tag",    1),
    ("hashtags",       1),
    ("create_time",    5),
    ("first_seen_at",  5),
    ("video_url",      15),
    ("cover_url",      15),
]

CREATOR_FIELDS = [
    ("author_unique",   1),
    ("nickname",        1),
    ("language",        3),
    ("follower_count",  2),
    ("median_plays",    2),
    ("max_plays_7d",    2),
    ("posts_14d",       2),
    ("posts_30d",       2),
    ("vertical_ratio",  2),
    ("reason",          1),
    ("evaluated_at",    5),
    ("profile_url",     15),
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
    """Create missing fields. Returns set of available field names."""
    headers = _headers()
    if not headers:
        return set()
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
    return existing


# ------------------------- row conversion -------------------------

def _to_ms(ts: Optional[int]) -> Optional[int]:
    if not ts:
        return None
    return int(ts) * 1000


def _video_record(row) -> dict:
    return {
        "video_id": str(row["video_id"]),
        "tier": row["tier"] or "",
        "language": row["language"] or "",
        "author": f"@{row['author_unique']}",
        "caption": (row["caption"] or "")[:2000],
        "play_count": row["play_count"] or 0,
        "like_count": row["like_count"] or 0,
        "comment_count": row["comment_count"] or 0,
        "share_count": row["share_count"] or 0,
        "duration": row["duration"] or 0,
        "matched_tag": row["matched_tag"] or "",
        "hashtags": row["hashtags"] or "",
        "create_time": _to_ms(row["create_time"]),
        "first_seen_at": _to_ms(row["first_seen_at"]),
        "video_url": {"link": row["video_url"], "text": "Open"},
        "cover_url": {"link": row["cover_url"], "text": "Cover"} if row["cover_url"] else None,
    }


def _creator_record(row) -> dict:
    return {
        "author_unique": row["author_unique"],
        "nickname": row["nickname"] or "",
        "language": row["language"] or "",
        "follower_count": row["follower_count"] or 0,
        "median_plays": row["median_plays"] or 0,
        "max_plays_7d": row["max_plays_7d"] or 0,
        "posts_14d": row["posts_14d"] or 0,
        "posts_30d": row["posts_30d"] or 0,
        "vertical_ratio": float(row["vertical_ratio"] or 0),
        "reason": row["reason"] or "",
        "evaluated_at": _to_ms(row["last_evaluated_at"]),
        "profile_url": {"link": f"https://www.tiktok.com/@{row['author_unique']}",
                        "text": "Profile"},
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
    records = [_video_record(r) for r in rows]
    created = _batch_create(table_id, records, allowed)
    if created:
        db.mark_videos_synced([r["video_id"] for r in rows[:created]])
    logger.info("Bitable videos synced: %d / %d", created, len(rows))
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
    records = [_creator_record(r) for r in rows]
    created = _batch_create(table_id, records, allowed)
    if created:
        db.mark_authors_synced([r["author_unique"] for r in rows[:created]])
    logger.info("Bitable creators synced: %d / %d", created, len(rows))
    return created
