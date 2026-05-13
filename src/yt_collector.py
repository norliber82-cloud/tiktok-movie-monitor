"""YouTube Shorts collector.

Uses yt-dlp's flat search extraction — no API key required, no auth.
Filters by duration (<=3 min), posting age, and movie-commentary keywords.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from yt_dlp import YoutubeDL

from . import db
from .classifier import classify_tier, detect_language, is_movie_commentary
from .config import (
    YT_MIN_TIER_VIEWS,
    YT_PER_QUERY_LIMIT,
    YT_SEARCH_QUERIES,
    YT_SHORTS_MAX_DURATION,
    WINDOW_DAYS,
)

logger = logging.getLogger(__name__)
WINDOW_SECONDS = WINDOW_DAYS * 24 * 3600


_YDL_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "extract_flat": False,      # we need view_count, duration, upload_date
    "ignoreerrors": True,
    "socket_timeout": 30,
    "noplaylist": True,
}


def _search_shorts(query: str, limit: int) -> list[dict]:
    """Search YouTube for Shorts. Uses the 'ytsearchdate<N>' pseudo-URL
    which returns the most recently uploaded matches."""
    url = f"ytsearchdate{limit}:{query} #shorts"
    opts = {**_YDL_OPTS, "playlistend": limit, "default_search": "ytsearch"}
    results = []
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info:
        return results
    for entry in (info.get("entries") or []):
        if entry:
            results.append(entry)
    return results


def _entry_to_row(entry: dict, query: str, now_ts: int) -> Optional[dict]:
    try:
        vid = entry.get("id") or ""
        if not vid:
            return None
        duration = int(entry.get("duration") or 0)
        if duration <= 0 or duration > YT_SHORTS_MAX_DURATION:
            return None

        # upload_date is 'YYYYMMDD' in yt-dlp output
        upload_date = entry.get("upload_date") or ""
        if len(upload_date) == 8:
            ts = int(time.mktime(time.strptime(upload_date, "%Y%m%d")))
        else:
            ts = int(entry.get("timestamp") or 0)
        if not ts:
            return None

        view_count = int(entry.get("view_count") or 0)
        tier = classify_tier(ts, view_count, now_ts)
        if tier is None or view_count < YT_MIN_TIER_VIEWS:
            return None

        caption = (entry.get("title") or "") + " \n " + (entry.get("description") or "")
        tags_raw = entry.get("tags") or []
        tags = [t.strip("# ") for t in tags_raw if isinstance(t, str)]
        lang = detect_language(entry.get("language", "") or "", caption, tags)

        if not is_movie_commentary(caption, tags):
            return None

        uploader = entry.get("uploader_id") or entry.get("channel_id") or ""
        nickname = entry.get("uploader") or entry.get("channel") or ""
        return {
            "video_id": f"yt:{vid}",
            "platform": "youtube",
            "author_id": entry.get("channel_id", "") or "",
            "author_unique": uploader,
            "caption": (entry.get("title") or "")[:500],
            "hashtags": ",".join(tags),
            "create_time": ts,
            "play_count": view_count,
            "like_count": int(entry.get("like_count") or 0),
            "comment_count": int(entry.get("comment_count") or 0),
            "share_count": 0,
            "duration": duration,
            "video_url": f"https://www.youtube.com/shorts/{vid}",
            "cover_url": entry.get("thumbnail", "") or "",
            "matched_tag": query,
            "language": lang,
            "tier": tier,
            "_nickname": nickname,
        }
    except (TypeError, ValueError) as exc:
        logger.warning("Could not parse YT entry: %s", exc)
        return None


def run_yt_collection() -> dict:
    """Run a single YouTube Shorts collection pass."""
    db.init_db()
    now_ts = int(time.time())
    hits = 0

    for q in YT_SEARCH_QUERIES:
        try:
            entries = _search_shorts(q, YT_PER_QUERY_LIMIT)
        except Exception as exc:
            logger.exception("YT search failed for %r: %s", q, exc)
            continue

        per_q_hits = 0
        for e in entries:
            row = _entry_to_row(e, q, now_ts)
            if not row:
                continue
            if now_ts - row["create_time"] > WINDOW_SECONDS:
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
            hits += 1
        logger.info("YT search %r: %d entries, %d tier-hits",
                    q, len(entries), per_q_hits)

    logger.info("YT collection total tier-hits: %d", hits)
    return {"yt_tier_hits": hits}
