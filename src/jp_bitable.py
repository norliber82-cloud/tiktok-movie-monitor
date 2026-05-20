"""Bitable writer for the JP monitor.

Same logic as src.bitable but targeting BITABLE_JP_VIDEOS_TABLE /
BITABLE_JP_CREATORS_TABLE instead of the global tables.
"""

import os

from . import bitable as _b


def is_configured() -> bool:
    return bool(_b._env("FEISHU_APP_ID") and _b._env("FEISHU_APP_SECRET")
                and _b._env("BITABLE_APP_TOKEN")
                and (_b._env("BITABLE_JP_VIDEOS_TABLE")
                     or _b._env("BITABLE_JP_CREATORS_TABLE")))


def sync_videos() -> int:
    if not is_configured():
        return 0
    table_id = _b._env("BITABLE_JP_VIDEOS_TABLE")
    if not table_id:
        return 0

    rows = _b.db.fetch_unsynced_videos()
    if not rows:
        return 0

    allowed = _b._ensure_fields(table_id, _b.VIDEO_FIELDS)
    existing = _b._fetch_existing_field_values(table_id, "视频ID")
    new_rows = [r for r in rows if str(r["video_id"]) not in existing]

    skipped = len(rows) - len(new_rows)
    if skipped:
        _b.db.mark_videos_synced([r["video_id"] for r in rows
                                  if str(r["video_id"]) in existing])

    records = [_b._video_record(r) for r in new_rows]
    created = _b._batch_create(table_id, records, allowed)
    if created:
        _b.db.mark_videos_synced([r["video_id"] for r in new_rows[:created]])
    _b.logger.info("JP Bitable videos: %d synced, %d skipped (dup)",
                   created, skipped)
    return created


def sync_creators() -> int:
    if not is_configured():
        return 0
    table_id = _b._env("BITABLE_JP_CREATORS_TABLE")
    if not table_id:
        return 0

    rows = _b.db.fetch_unsynced_monitored_authors()
    if not rows:
        return 0

    allowed = _b._ensure_fields(table_id, _b.CREATOR_FIELDS)
    existing = _b._fetch_existing_field_values(table_id, "用户名")
    new_rows = [r for r in rows if r["author_unique"] not in existing]

    skipped = len(rows) - len(new_rows)
    if skipped:
        _b.db.mark_authors_synced([r["author_unique"] for r in rows
                                   if r["author_unique"] in existing])

    records = [_b._creator_record(r) for r in new_rows]
    created = _b._batch_create(table_id, records, allowed)
    if created:
        _b.db.mark_authors_synced([r["author_unique"] for r in new_rows[:created]])
    _b.logger.info("JP Bitable creators: %d synced, %d skipped (dup)",
                   created, skipped)
    return created
