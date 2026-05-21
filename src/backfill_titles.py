"""Backfill `原片名` for videos already in Feishu Bitable.

Reads all records from the videos tables (US + JP + liked_videos),
filters to those with empty `原片名`, fetches comments via TikTokApi,
extracts the title, and updates the record.

Usage (via GitHub Actions or one-off):
    python -m src.backfill_titles
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time

from dotenv import load_dotenv

load_dotenv()

import requests as _requests

from . import bitable as _b
from .comments import extract_title_from_comments, fetch_comments_for_video

logger = logging.getLogger(__name__)

API = "https://open.feishu.cn/open-apis"

# Tables to backfill — each has both 视频ID and 原片名 columns
TABLES = [
    ("videos_us",    os.getenv("BITABLE_VIDEOS_TABLE", "tblrY6LqfrQsc1qv")),
    ("videos_jp",    os.getenv("BITABLE_JP_VIDEOS_TABLE", "tblGCE433yHlyi19")),
    ("liked_videos", "tblzY8kdXrffenE9"),
]

# Cap per run so we don't blow up the cost
MAX_PER_RUN = 100
MAX_PER_TABLE = 50


def _setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%H:%M:%S",
    )


def _list_records_needing_backfill(table_id: str, limit: int = 50
                                   ) -> list[dict]:
    """Pull records where 原片名 is empty and 视频ID is set."""
    headers = _b._headers()
    if not headers:
        return []
    app_token = _b._env("BITABLE_APP_TOKEN")
    url = f"{API}/bitable/v1/apps/{app_token}/tables/{table_id}/records"
    out = []
    page_token = None
    for _ in range(40):
        params = {"page_size": 500}
        if page_token:
            params["page_token"] = page_token
        try:
            r = _requests.get(url, headers=headers, params=params, timeout=30).json()
        except Exception as exc:
            logger.warning("list rejected: %s", exc); break
        if r.get("code") != 0:
            logger.warning("list rejected: %s", r); break
        d = r.get("data", {})
        for rec in d.get("items", []):
            f = rec.get("fields", {}) or {}
            video_id = f.get("视频ID")
            if not video_id:
                continue
            if isinstance(video_id, list):
                video_id = video_id[0].get("text") if video_id else None
            video_id = str(video_id) if video_id else ""
            if not video_id:
                continue
            # Skip if 原片名 is already filled
            existing_title = f.get("原片名")
            if existing_title and str(existing_title).strip():
                continue
            # Get author for is_author check
            author = f.get("作者") or ""
            if isinstance(author, str):
                author = author.lstrip("@")
            out.append({
                "record_id": rec["record_id"],
                "video_id":  video_id,
                "author":    author,
            })
            if len(out) >= limit:
                break
        page_token = d.get("page_token")
        if not d.get("has_more") or len(out) >= limit:
            break
    return out


def _batch_update(table_id: str, updates: list[dict]) -> int:
    if not updates:
        return 0
    headers = _b._headers()
    app_token = _b._env("BITABLE_APP_TOKEN")
    url = f"{API}/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_update"
    written = 0
    for i in range(0, len(updates), 500):
        chunk = updates[i:i + 500]
        try:
            r = _requests.post(url, headers=headers,
                               json={"records": chunk}, timeout=30).json()
            if r.get("code") == 0:
                written += len(r.get("data", {}).get("records", []))
            else:
                logger.warning("batch_update rejected: %s", r)
        except Exception as exc:
            logger.warning("batch_update failed: %s", exc)
    return written


async def _extract_titles_batch(records: list[dict],
                                ms_token: str) -> list[dict]:
    """For each record, fetch comments and extract title.
    Returns list of {record_id, fields: {原片名: title}} for non-empty titles."""
    from TikTokApi import TikTokApi

    updates = []
    async with TikTokApi() as api:
        await api.create_sessions(
            ms_tokens=[ms_token],
            num_sessions=2,
            sleep_after=3,
            headless=True,
            browser="webkit",
            enable_session_recovery=True,
        )
        for i, rec in enumerate(records):
            try:
                comments = await fetch_comments_for_video(
                    api, rec["video_id"], count=20,
                    author_unique=rec.get("author", ""),
                )
                title = extract_title_from_comments(
                    comments, author_unique=rec.get("author", ""))
                if title:
                    updates.append({
                        "record_id": rec["record_id"],
                        "fields": {"原片名": title},
                    })
                    logger.info("  [%d/%d] %s → %s",
                                i + 1, len(records), rec["video_id"], title)
                else:
                    logger.debug("  [%d/%d] %s: no title found",
                                 i + 1, len(records), rec["video_id"])
            except Exception as exc:
                logger.debug("  [%d/%d] %s failed: %s",
                             i + 1, len(records), rec["video_id"], str(exc)[:80])
            await asyncio.sleep(1.0)
    return updates


def main():
    _setup_logging()
    t0 = time.time()

    ms_token = os.getenv("MS_TOKEN", "").strip()
    if not ms_token:
        logger.error("MS_TOKEN not set"); sys.exit(1)
    if not _b.is_configured():
        logger.error("Feishu not configured"); sys.exit(1)

    total_processed = 0
    total_filled = 0

    for label, table_id in TABLES:
        if not table_id:
            continue
        if total_processed >= MAX_PER_RUN:
            logger.info("Reached MAX_PER_RUN (%d), stopping", MAX_PER_RUN)
            break

        budget = min(MAX_PER_TABLE, MAX_PER_RUN - total_processed)
        logger.info("=== Backfill %s (%s) — budget %d ===",
                    label, table_id, budget)

        records = _list_records_needing_backfill(table_id, limit=budget)
        logger.info("Found %d records needing backfill", len(records))
        if not records:
            continue

        updates = asyncio.run(_extract_titles_batch(records, ms_token))
        logger.info("Extracted %d titles from %d videos",
                    len(updates), len(records))

        if updates:
            written = _batch_update(table_id, updates)
            logger.info("Updated %d records in Bitable", written)
            total_filled += written

        total_processed += len(records)

    elapsed = time.time() - t0
    logger.info("=== Backfill done: %d filled / %d processed in %.1f min ===",
                total_filled, total_processed, elapsed / 60)


if __name__ == "__main__":
    main()
