"""YouTube Shorts collector using YouTube Data API v3.

Uses the search.list endpoint (free, 10k quota/day) to find recent Shorts
matching movie-commentary queries, then filters by tier/age/keywords.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

import requests

from . import db
from .classifier import classify_tier, detect_language, is_movie_commentary
from .config import (
    ALLOWED_LANGUAGES,
    TIERS,
    WINDOW_DAYS,
    YT_MIN_TIER_VIEWS,
    YT_PER_QUERY_LIMIT,
    YT_SEARCH_QUERIES,
    YT_SHORTS_MAX_DURATION,
)

logger = logging.getLogger(__name__)
WINDOW_SECONDS = WINDOW_DAYS * 24 * 3600
API_BASE = "https://www.googleapis.com/youtube/v3"


def _api_key() -> str:
    return os.getenv("YOUTUBE_API_KEY", "").strip()


def _iso_to_ts(iso: str) -> int:
    """Parse ISO 8601 datetime string to unix timestamp."""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return int(dt.timestamp())
    except (ValueError, TypeError):
        return 0


def _duration_to_seconds(dur: str) -> int:
    """Parse ISO 8601 duration like PT1M30S to seconds."""
    import re
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", dur or "")
    if not m:
        return 0
    h, mi, s = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + s


def _search_videos(query: str, limit: int, published_after: str) -> list[str]:
    """Search for video IDs matching query, published after given ISO date."""
    key = _api_key()
    if not key:
        return []

    ids = []
    page_token = None
    remaining = limit

    while remaining > 0:
        params = {
            "part": "id",
            "q": query,
            "type": "video",
            "videoDuration": "short",  # <=4 min
            "order": "date",
            "publishedAfter": published_after,
            "maxResults": min(remaining, 50),
            "key": key,
        }
        if page_token:
            params["pageToken"] = page_token

        try:
            resp = requests.get(f"{API_BASE}/search", params=params, timeout=15)
            data = resp.json()
        except Exception as exc:
            logger.warning("YT search API error for %r: %s", query, exc)
            break

        if "error" in data:
            logger.error("YT API error: %s", data["error"].get("message", data["error"]))
            break

        for item in data.get("items", []):
            vid_id = item.get("id", {}).get("videoId")
            if vid_id:
                ids.append(vid_id)

        page_token = data.get("nextPageToken")
        remaining -= 50
        if not page_token:
            break

    return ids


def _get_video_details(video_ids: list[str]) -> list[dict]:
    """Batch-fetch video details (stats, duration, snippet)."""
    key = _api_key()
    if not key or not video_ids:
        return []

    results = []
    # API allows max 50 IDs per call
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i:i + 50]
        params = {
            "part": "snippet,statistics,contentDetails",
            "id": ",".join(chunk),
            "key": key,
        }
        try:
            resp = requests.get(f"{API_BASE}/videos", params=params, timeout=15)
            data = resp.json()
        except Exception as exc:
            logger.warning("YT videos API error: %s", exc)
            continue

        if "error" in data:
            logger.error("YT API error: %s", data["error"].get("message", data["error"]))
            continue

        for item in data.get("items", []):
            results.append(item)

    return results


def _item_to_row(item: dict, query: str, now_ts: int) -> Optional[dict]:
    """Convert a YouTube API video item to our DB row format."""
    try:
        vid_id = item["id"]
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})
        content = item.get("contentDetails", {})

        duration = _duration_to_seconds(content.get("duration", ""))
        if duration <= 0 or duration > YT_SHORTS_MAX_DURATION:
            return None

        create_time = _iso_to_ts(snippet.get("publishedAt", ""))
        if not create_time or now_ts - create_time > WINDOW_SECONDS:
            return None

        view_count = int(stats.get("viewCount", 0) or 0)
        tier = classify_tier(create_time, view_count, now_ts)
        if tier is None or view_count < YT_MIN_TIER_VIEWS:
            return None

        title = snippet.get("title", "") or ""
        description = (snippet.get("description", "") or "")[:500]
        caption = f"{title}\n{description}"
        tags = snippet.get("tags") or []
        lang = detect_language(
            snippet.get("defaultAudioLanguage", "") or snippet.get("defaultLanguage", "") or "",
            caption, tags,
        )

        if not is_movie_commentary(caption, tags):
            return None

        # Language filter
        if lang not in ALLOWED_LANGUAGES:
            return None

        channel_id = snippet.get("channelId", "")
        channel_title = snippet.get("channelTitle", "")

        return {
            "video_id": f"yt:{vid_id}",
            "platform": "youtube",
            "author_id": channel_id,
            "author_unique": channel_id,
            "caption": title,
            "hashtags": ",".join(tags[:20]),
            "create_time": create_time,
            "play_count": view_count,
            "like_count": int(stats.get("likeCount", 0) or 0),
            "comment_count": int(stats.get("commentCount", 0) or 0),
            "share_count": 0,
            "duration": duration,
            "video_url": f"https://www.youtube.com/shorts/{vid_id}",
            "cover_url": (snippet.get("thumbnails") or {}).get("high", {}).get("url", ""),
            "matched_tag": query,
            "language": lang,
            "tier": tier,
            "_nickname": channel_title,
        }
    except (TypeError, ValueError, KeyError) as exc:
        logger.warning("Could not parse YT item: %s", exc)
        return None


def run_yt_collection() -> dict:
    """Run a single YouTube Shorts collection pass."""
    key = _api_key()
    if not key:
        logger.info("YOUTUBE_API_KEY not set, skipping YouTube collection")
        return {"yt_tier_hits": 0}

    db.init_db()
    now_ts = int(time.time())
    published_after = (
        datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    total_hits = 0

    for query in YT_SEARCH_QUERIES:
        video_ids = _search_videos(query, YT_PER_QUERY_LIMIT, published_after)
        if not video_ids:
            logger.info("YT search %r: 0 results", query)
            continue

        details = _get_video_details(video_ids)
        per_q_hits = 0
        for item in details:
            row = _item_to_row(item, query, now_ts)
            if not row:
                continue
            nickname = row.pop("_nickname", None)
            db.upsert_video(row)
            if row["author_unique"]:
                db.touch_author_candidate(
                    author_unique=row["author_unique"],
                    author_id=row["author_id"],
                    nickname=nickname,
                    language=row["language"],
                )
            per_q_hits += 1
            total_hits += 1

        logger.info("YT search %r: %d IDs → %d details → %d tier-hits",
                    query, len(video_ids), len(details), per_q_hits)

    logger.info("YT collection total tier-hits: %d", total_hits)
    return {"yt_tier_hits": total_hits}
