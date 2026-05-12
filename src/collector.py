"""Hashtag collector using the unofficial TikTok-Api wrapper."""

import asyncio
import logging
import os
import time
from typing import Optional

from TikTokApi import TikTokApi

from . import db
from .classifier import is_movie_commentary
from .config import (
    BROWSER,
    HASHTAGS,
    HEADLESS,
    MIN_VIEWS,
    PER_TAG_LIMIT,
    SESSION_SLEEP_AFTER,
    SLEEP_BETWEEN_TAGS,
    WINDOW_DAYS,
)

logger = logging.getLogger(__name__)

WINDOW_SECONDS = WINDOW_DAYS * 24 * 3600


def _extract_hashtags(text_extra: list) -> list[str]:
    tags = []
    for item in text_extra or []:
        name = item.get("hashtagName")
        if name:
            tags.append(name)
    return tags


def _to_row(vid: dict, matched_tag: str) -> Optional[dict]:
    try:
        stats = vid.get("stats") or vid.get("statsV2") or {}
        play = int(stats.get("playCount") or stats.get("playcount") or 0)
        author = vid.get("author") or {}
        tags = _extract_hashtags(vid.get("textExtra") or [])
        return {
            "video_id": str(vid["id"]),
            "author_id": str(author.get("id", "")),
            "author_unique": author.get("uniqueId", ""),
            "caption": vid.get("desc", "") or "",
            "hashtags": ",".join(tags),
            "create_time": int(vid.get("createTime", 0)),
            "play_count": play,
            "like_count": int(stats.get("diggCount", 0) or 0),
            "comment_count": int(stats.get("commentCount", 0) or 0),
            "share_count": int(stats.get("shareCount", 0) or 0),
            "duration": int((vid.get("video") or {}).get("duration", 0) or 0),
            "video_url": f"https://www.tiktok.com/@{author.get('uniqueId','')}/video/{vid['id']}",
            "cover_url": (vid.get("video") or {}).get("cover", ""),
            "matched_tag": matched_tag,
        }, tags
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning("Failed to parse video record: %s", exc)
        return None


async def _scan_hashtag(api: TikTokApi, tag: str) -> list[dict]:
    hits = []
    now = int(time.time())
    count = 0
    try:
        async for video in api.hashtag(name=tag).videos(count=PER_TAG_LIMIT):
            count += 1
            vid_dict = video.as_dict
            parsed = _to_row(vid_dict, matched_tag=tag)
            if not parsed:
                continue
            row, tags = parsed

            # Filter 1: posted within window
            if row["create_time"] == 0 or now - row["create_time"] > WINDOW_SECONDS:
                continue

            # Filter 2: plays threshold
            if row["play_count"] < MIN_VIEWS:
                continue

            # Filter 3: movie commentary classification
            if not is_movie_commentary(row["caption"], tags):
                continue

            hits.append(row)
    except Exception as exc:
        logger.exception("Error scanning hashtag %s after %d items: %s", tag, count, exc)
    else:
        logger.info("Hashtag #%s scanned: %d items, %d qualified", tag, count, len(hits))
    return hits


async def run_collection() -> list[dict]:
    ms_token = os.getenv("MS_TOKEN", "").strip()
    if not ms_token:
        raise RuntimeError("MS_TOKEN is required")

    db.init_db()
    all_hits: list[dict] = []

    async with TikTokApi() as api:
        await api.create_sessions(
            ms_tokens=[ms_token],
            num_sessions=1,
            sleep_after=SESSION_SLEEP_AFTER,
            headless=HEADLESS,
            browser=BROWSER,
        )

        for tag in HASHTAGS:
            hits = await _scan_hashtag(api, tag)
            for row in hits:
                db.upsert_video(row)
            all_hits.extend(hits)
            await asyncio.sleep(SLEEP_BETWEEN_TAGS)

    logger.info("Collection finished: %d qualifying videos this run", len(all_hits))
    return all_hits
