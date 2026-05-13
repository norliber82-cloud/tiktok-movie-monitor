"""TikTok scraping: video hits, creator discovery, and creator evaluation."""

import asyncio
import logging
import os
import time
from typing import Optional

from TikTokApi import TikTokApi

from . import db
from .classifier import (
    classify_tier,
    detect_language,
    evaluate_creator,
    is_movie_commentary,
)
from .config import (
    BROWSER,
    CREATORS_EVAL_BUDGET_PER_RUN,
    CREATOR_MONITORED_REFRESH_DAYS,
    CREATOR_REJECT_REEVAL_DAYS,
    CREATOR_SAMPLE_SIZE,
    DISCOVERY_HASHTAGS,
    HASHTAGS,
    HEADLESS,
    PER_DISCOVERY_TAG_LIMIT,
    PER_TAG_LIMIT,
    SESSION_SLEEP_AFTER,
    SLEEP_BETWEEN_CREATORS,
    SLEEP_BETWEEN_TAGS,
    WINDOW_DAYS,
)

logger = logging.getLogger(__name__)

WINDOW_SECONDS = WINDOW_DAYS * 24 * 3600


# ------------------------- helpers -------------------------

def _extract_hashtags(text_extra: list) -> list[str]:
    tags = []
    for item in text_extra or []:
        name = item.get("hashtagName")
        if name:
            tags.append(name)
    return tags


def _get_stats(vid: dict) -> dict:
    return vid.get("stats") or vid.get("statsV2") or {}


def _to_video_row(vid: dict, matched_tag: str, now_ts: int) -> Optional[dict]:
    try:
        stats = _get_stats(vid)
        play = int(stats.get("playCount") or stats.get("playcount") or 0)
        author = vid.get("author") or {}
        tags = _extract_hashtags(vid.get("textExtra") or [])
        caption = vid.get("desc", "") or ""
        create_time = int(vid.get("createTime", 0))
        tier = classify_tier(create_time, play, now_ts)
        lang = detect_language(vid.get("textLanguage", ""), caption, tags)

        return {
            "video_id": str(vid["id"]),
            "author_id": str(author.get("id", "")),
            "author_unique": author.get("uniqueId", ""),
            "nickname": author.get("nickname", ""),
            "caption": caption,
            "hashtags": ",".join(tags),
            "tag_list": tags,
            "create_time": create_time,
            "play_count": play,
            "like_count": int(stats.get("diggCount", 0) or 0),
            "comment_count": int(stats.get("commentCount", 0) or 0),
            "share_count": int(stats.get("shareCount", 0) or 0),
            "duration": int((vid.get("video") or {}).get("duration", 0) or 0),
            "video_url": f"https://www.tiktok.com/@{author.get('uniqueId','')}/video/{vid['id']}",
            "cover_url": (vid.get("video") or {}).get("cover", ""),
            "matched_tag": matched_tag,
            "language": lang,
            "tier": tier,
        }
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning("Failed to parse video record: %s", exc)
        return None


async def _scan_hashtag(api: TikTokApi, tag: str, limit: int,
                        is_discovery: bool, now_ts: int) -> tuple[int, int, int]:
    """Scan a single hashtag. Returns (total_items, tier_hits, author_seeds)."""
    total, tier_hits, seeds = 0, 0, 0
    try:
        async for video in api.hashtag(name=tag).videos(count=limit):
            total += 1
            vid_dict = video.as_dict
            parsed = _to_video_row(vid_dict, matched_tag=tag, now_ts=now_ts)
            if not parsed:
                continue

            if parsed["author_unique"]:
                # Seed author queue regardless of tier / movie-match.
                # The author evaluator will filter these later.
                if is_movie_commentary(parsed["caption"], parsed["tag_list"]):
                    db.touch_author_candidate(
                        author_unique=parsed["author_unique"],
                        author_id=parsed["author_id"],
                        nickname=parsed.get("nickname"),
                        language=parsed["language"],
                    )
                    seeds += 1

            # Discovery pass only seeds authors; does not send alerts.
            if is_discovery:
                continue

            # Posting age outside of the outer window → skip
            if parsed["create_time"] == 0 or now_ts - parsed["create_time"] > WINDOW_SECONDS:
                continue

            if parsed["tier"] is None:
                continue

            if not is_movie_commentary(parsed["caption"], parsed["tag_list"]):
                continue

            # pop helper keys before persisting
            parsed.pop("tag_list", None)
            parsed.pop("nickname", None)
            db.upsert_video(parsed)
            tier_hits += 1
    except Exception as exc:
        logger.exception("Error scanning hashtag #%s after %d items: %s", tag, total, exc)
    else:
        logger.info(
            "Hashtag #%s scanned: %d items, %d tier-hits, %d author-seeds "
            "(mode=%s)",
            tag, total, tier_hits, seeds,
            "discovery" if is_discovery else "primary",
        )
    return total, tier_hits, seeds


async def _evaluate_creator(api: TikTokApi, author_unique: str,
                            now_ts: int) -> Optional[dict]:
    sample = []
    follower_count = 0
    nickname = None
    language_hint = None
    try:
        user = api.user(username=author_unique)
        try:
            user_info = await user.info()
            info_user = (user_info or {}).get("userInfo", {}).get("user", {})
            stats = (user_info or {}).get("userInfo", {}).get("stats", {})
            follower_count = int(stats.get("followerCount") or 0)
            nickname = info_user.get("nickname")
            language_hint = info_user.get("language") or None
        except Exception:
            pass

        async for v in user.videos(count=CREATOR_SAMPLE_SIZE):
            vd = v.as_dict
            stats = _get_stats(vd)
            tags = _extract_hashtags(vd.get("textExtra") or [])
            sample.append({
                "play_count": int(stats.get("playCount") or 0),
                "create_time": int(vd.get("createTime", 0)),
                "caption": vd.get("desc", "") or "",
                "hashtags": tags,
            })
    except Exception as exc:
        logger.warning("Failed to evaluate @%s: %s", author_unique, exc)
        return None

    verdict = evaluate_creator(sample, now_ts=now_ts)
    verdict["author_unique"] = author_unique
    verdict["nickname"] = nickname
    verdict["follower_count"] = follower_count
    verdict["language"] = language_hint
    return verdict


def _evaluate_creator_from_db(author_unique: str, now_ts: int) -> Optional[dict]:
    """Evaluate a creator using videos we've already collected in our DB.
    No API calls needed — pure SQLite aggregation."""
    rows = db.fetch_author_videos(author_unique)
    if len(rows) < 3:
        # Not enough data yet; skip (don't reject — we'll try again later
        # when we've accumulated more of their videos).
        return None

    sample = []
    for r in rows:
        sample.append({
            "play_count": r["play_count"] or 0,
            "create_time": r["create_time"] or 0,
            "caption": r["caption"] or "",
            "hashtags": (r["hashtags"] or "").split(","),
        })

    verdict = evaluate_creator(sample, now_ts=now_ts)
    # Pull nickname/language from the authors table (already stored from seeds)
    author_info = db.get_author_info(author_unique)
    verdict["author_unique"] = author_unique
    verdict["nickname"] = author_info.get("nickname") if author_info else None
    verdict["follower_count"] = author_info.get("follower_count") if author_info else None
    verdict["language"] = author_info.get("language") if author_info else None
    return verdict


# ------------------------- main entry -------------------------

async def run_collection(mode: str = "fast") -> dict:
    """Run one collection pass.

    mode='fast' : only primary hashtag scan (videos + cheap author seeds).
    mode='deep' : discovery hashtag expansion + creator evaluation.
    Returns a summary dict.
    """
    ms_token = os.getenv("MS_TOKEN", "").strip()
    if not ms_token:
        raise RuntimeError("MS_TOKEN is required")

    db.init_db()
    now_ts = int(time.time())
    tier_total = 0
    seed_total = 0
    eval_accept = 0
    eval_reject = 0

    async with TikTokApi() as api:
        await api.create_sessions(
            ms_tokens=[ms_token],
            num_sessions=1,
            sleep_after=SESSION_SLEEP_AFTER,
            headless=HEADLESS,
            browser=BROWSER,
        )

        # -------- A. Primary hashtag scan (video alerts + author seeds) --------
        logger.info("Phase A: primary hashtag scan (%d tags)", len(HASHTAGS))
        for tag in HASHTAGS:
            _, t_hits, seeds = await _scan_hashtag(
                api, tag, PER_TAG_LIMIT, is_discovery=False, now_ts=now_ts,
            )
            tier_total += t_hits
            seed_total += seeds
            await asyncio.sleep(SLEEP_BETWEEN_TAGS)

        if mode == "fast":
            # Fast mode stops here — notify + bitable happen in main.py.
            summary = {"mode": mode, "tier_hits": tier_total,
                       "author_seeds": seed_total,
                       "creators_accepted": 0, "creators_rejected": 0}
            logger.info("Collection summary: %s", summary)
            return summary

        # -------- B. Discovery hashtag scan (author seeds only) --------
        logger.info("Phase B: discovery hashtag scan (%d tags)", len(DISCOVERY_HASHTAGS))
        for tag in DISCOVERY_HASHTAGS:
            _, _, seeds = await _scan_hashtag(
                api, tag, PER_DISCOVERY_TAG_LIMIT, is_discovery=True, now_ts=now_ts,
            )
            seed_total += seeds
            await asyncio.sleep(SLEEP_BETWEEN_TAGS)

        # -------- C. Creator evaluation (from local DB, no API calls) --------
        reject_secs = CREATOR_REJECT_REEVAL_DAYS * 86400
        monitored_secs = CREATOR_MONITORED_REFRESH_DAYS * 86400
        candidates = db.fetch_authors_to_evaluate(
            limit=CREATORS_EVAL_BUDGET_PER_RUN,
            reject_reeval_seconds=reject_secs,
            monitored_refresh_seconds=monitored_secs,
        )
        logger.info("Phase C: evaluating %d creator candidates (from local DB)", len(candidates))
        for cand in candidates:
            verdict = _evaluate_creator_from_db(cand["author_unique"], now_ts=now_ts)
            if verdict is None:
                continue
            db.update_author_profile({
                "author_unique": verdict["author_unique"],
                "nickname": verdict.get("nickname"),
                "follower_count": verdict.get("follower_count"),
                "median_plays": verdict.get("median_plays"),
                "max_plays_7d": verdict.get("max_plays_7d"),
                "posts_14d": verdict.get("posts_14d"),
                "posts_30d": verdict.get("posts_30d"),
                "vertical_ratio": verdict.get("vertical_ratio"),
                "language": verdict.get("language"),
                "status": verdict["status"],
                "reason": verdict["reason"],
            })
            if verdict["status"] == "MONITORED":
                eval_accept += 1
                logger.info("MONITORED: @%s median=%s viral7d=%s posts14d=%s vert=%s",
                            verdict["author_unique"], verdict["median_plays"],
                            verdict["max_plays_7d"], verdict["posts_14d"],
                            verdict["vertical_ratio"])
            else:
                eval_reject += 1

    summary = {
        "mode": mode,
        "tier_hits": tier_total,
        "author_seeds": seed_total,
        "creators_accepted": eval_accept,
        "creators_rejected": eval_reject,
    }
    logger.info("Collection summary: %s", summary)
    return summary
