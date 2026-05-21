"""Backfill `原片名` for videos already in Feishu Bitable.

Uses Apify's clockworks/tiktok-comments-scraper for reliable comment
extraction (TikTokApi gets bot-blocked on GitHub Actions).

Reads all records from the videos tables (US + JP + liked_videos),
filters to those with empty `原片名`, fetches comments via Apify in batch,
extracts the title, and updates the record.

Usage:
    python -m src.backfill_titles
"""

from __future__ import annotations

import logging
import os
import sys
import time
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

import requests as _requests

from . import bitable as _b
from .comments import extract_titles_via_apify

logger = logging.getLogger(__name__)

API = "https://open.feishu.cn/open-apis"

# Tables to backfill — each has both 视频ID and 原片名 columns
TABLES = [
    ("videos_us",    os.getenv("BITABLE_VIDEOS_TABLE", "tblrY6LqfrQsc1qv")),
    ("videos_jp",    os.getenv("BITABLE_JP_VIDEOS_TABLE", "tblGCE433yHlyi19")),
    ("liked_videos", "tblzY8kdXrffenE9"),
]

# Cap per run: 100 videos * 10 comments = 1000 comments ≈ $1 of Apify credit
MAX_PER_RUN = 100
APIFY_BATCH_SIZE = 25  # videos per Apify call (single sync request)
COMMENTS_PER_VIDEO = 10


def _setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%H:%M:%S",
    )


def _list_records_needing_backfill(table_id: str, limit: int = 50
                                   ) -> list[dict]:
    """Pull records where 原片名 is empty and 视频URL is set."""
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
            video_url = f.get("视频URL")
            if isinstance(video_url, list):
                video_url = video_url[0].get("text") if video_url else None
            video_url = (video_url or "").strip()
            if not video_url or "/video/" not in video_url:
                continue
            existing_title = f.get("原片名")
            if existing_title and str(existing_title).strip():
                continue
            author = f.get("作者") or ""
            if isinstance(author, str):
                author = author.lstrip("@")
            out.append({
                "record_id": rec["record_id"],
                "video_url": video_url,
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


def backfill_table(table_id: str, label: str, budget: int) -> int:
    """Returns number of records actually backfilled."""
    logger.info("=== Backfill %s (%s) — budget %d ===", label, table_id, budget)

    records = _list_records_needing_backfill(table_id, limit=budget)
    logger.info("Found %d records needing backfill", len(records))
    if not records:
        return 0

    # Process in Apify batches
    all_updates = []
    for i in range(0, len(records), APIFY_BATCH_SIZE):
        chunk = records[i:i + APIFY_BATCH_SIZE]
        pairs = [(r["video_url"], r.get("author", "")) for r in chunk]
        logger.info("  Apify batch %d/%d (%d videos)…",
                    i // APIFY_BATCH_SIZE + 1,
                    (len(records) + APIFY_BATCH_SIZE - 1) // APIFY_BATCH_SIZE,
                    len(chunk))
        titles = extract_titles_via_apify(pairs,
                                          comments_per_post=COMMENTS_PER_VIDEO)

        for r in chunk:
            t = titles.get(r["video_url"])
            if t:
                all_updates.append({
                    "record_id": r["record_id"],
                    "fields": {"原片名": t},
                })
                logger.info("    ✓ %s → %s", r["video_url"][-25:], t)

        # Be polite between Apify calls
        if i + APIFY_BATCH_SIZE < len(records):
            time.sleep(2)

    logger.info("Extracted %d titles from %d videos",
                len(all_updates), len(records))

    if all_updates:
        written = _batch_update(table_id, all_updates)
        logger.info("Updated %d records in Bitable", written)
        return written
    return 0


def main():
    _setup_logging()
    t0 = time.time()

    if not os.getenv("APIFY_API_TOKEN", "").strip():
        logger.error("APIFY_API_TOKEN not set"); sys.exit(1)
    if not _b.is_configured():
        logger.error("Feishu not configured"); sys.exit(1)

    total_filled = 0
    remaining = MAX_PER_RUN

    for label, table_id in TABLES:
        if not table_id:
            continue
        if remaining <= 0:
            logger.info("Reached MAX_PER_RUN, stopping")
            break

        budget = min(remaining, 50)  # max 50 per table per run
        filled = backfill_table(table_id, label, budget)
        total_filled += filled
        remaining -= budget  # consume budget regardless of fills

    elapsed = time.time() - t0
    logger.info("=== Backfill done: %d filled in %.1f min ===",
                total_filled, elapsed / 60)


if __name__ == "__main__":
    main()
