"""Entry point for the Japan-only TikTok monitor.

Runs in its own GitHub Actions workflow with its own MS_TOKEN_JP secret
and its own Bitable tables (BITABLE_JP_VIDEOS_TABLE / BITABLE_JP_CREATORS_TABLE).
"""

import argparse
import asyncio
import logging
import os
import sys
import time
from typing import Optional

from dotenv import load_dotenv
from TikTokApi import TikTokApi

from . import db, jp_config
from .classifier import classify_tier as base_classify_tier, detect_language, evaluate_creator, is_movie_commentary
from .config import (
    BROWSER, HEADLESS, SESSION_SLEEP_AFTER,
)
from .followers import backfill_followers as backfill_followers_global

logger = logging.getLogger(__name__)
# JP uses a wider posting-age window than US so that 7-day RED tier
# (newly relaxed) actually qualifies. Computed from JP_TIERS' max age.
WINDOW_SECONDS = max(t[4] for t in jp_config.JP_TIERS) * 3600


# ============================================================
# JP-specific tier classifier (overrides the global TIERS)
# ============================================================

def jp_classify_tier(create_time: int, play_count: int, now_ts: int) -> Optional[str]:
    """Use JP_TIERS (lower thresholds) instead of the global TIERS."""
    age_h = (now_ts - create_time) / 3600.0
    for code, _, _, min_views, max_age_h, _ in jp_config.JP_TIERS:
        if play_count >= min_views and age_h <= max_age_h:
            return code
    return None


def jp_tier_meta(code: str) -> dict:
    for c, label, color, min_views, max_age_h, rank in jp_config.JP_TIERS:
        if c == code:
            return {"code": c, "label": label, "color": color,
                    "min_views": min_views, "max_age_h": max_age_h, "rank": rank}
    return {}


# ============================================================
# Helpers (mirror collector.py but JP-specific)
# ============================================================

def _extract_hashtags(text_extra: list) -> list[str]:
    return [t.get("hashtagName") for t in (text_extra or []) if t.get("hashtagName")]


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
        tier = jp_classify_tier(create_time, play, now_ts)
        lang = detect_language(vid.get("textLanguage", ""), caption, tags)

        return {
            "video_id": str(vid["id"]),
            "platform": "tiktok",
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


async def _scan_hashtag(api, tag: str, limit: int, is_discovery: bool,
                       now_ts: int) -> tuple[int, int, int]:
    """Scan one hashtag for JP content. Same shape as the global collector,
    but uses JP_TIERS + JP_ALLOWED_LANGUAGES + JP duration limits."""
    total = tier_hits = seeds = 0
    try:
        async for video in api.hashtag(name=tag).videos(count=limit):
            total += 1
            vid_dict = video.as_dict
            parsed = _to_video_row(vid_dict, matched_tag=tag, now_ts=now_ts)
            if not parsed:
                continue

            is_mc = is_movie_commentary(parsed["caption"], parsed["tag_list"])

            if parsed["author_unique"] and is_mc:
                db.touch_author_candidate(
                    author_unique=parsed["author_unique"],
                    author_id=parsed["author_id"],
                    nickname=parsed.get("nickname"),
                    language=parsed["language"],
                )
                seeds += 1

            posting_age_ok = (parsed["create_time"] != 0 and
                              now_ts - parsed["create_time"] <= WINDOW_SECONDS)

            if is_mc and posting_age_ok:
                # JP-only language filter
                if parsed["language"] not in jp_config.JP_ALLOWED_LANGUAGES:
                    continue

                dur = parsed.get("duration") or 0
                if dur < jp_config.JP_MIN_DURATION_SECONDS or dur > jp_config.JP_MAX_DURATION_SECONDS:
                    continue

                row = {k: v for k, v in parsed.items()
                       if k not in ("tag_list", "nickname")}
                if is_discovery:
                    row["tier"] = None
                    db.upsert_video(row)
                else:
                    db.upsert_video(row)
                    if row["tier"] is not None:
                        tier_hits += 1
                        if parsed["author_unique"]:
                            db.promote_viral_author(
                                author_unique=parsed["author_unique"],
                                author_id=parsed["author_id"],
                                nickname=parsed.get("nickname"),
                                language=parsed["language"],
                                play_count=parsed["play_count"],
                                create_time=parsed["create_time"],
                            )
    except Exception as exc:
        logger.exception("Error scanning #%s: %s", tag, exc)
    else:
        logger.info("JP #%s: %d items, %d tier-hits, %d seeds (%s)",
                    tag, total, tier_hits, seeds,
                    "discovery" if is_discovery else "primary")
    return total, tier_hits, seeds


def _evaluate_creator_from_db(author_unique: str, now_ts: int) -> Optional[dict]:
    rows = db.fetch_author_videos(author_unique)
    if not rows:
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
    info = db.get_author_info(author_unique)
    verdict["author_unique"] = author_unique
    verdict["nickname"] = info.get("nickname") if info else None
    verdict["follower_count"] = info.get("follower_count") if info else None
    verdict["language"] = info.get("language") if info else None
    return verdict


# ============================================================
# Main collection
# ============================================================

async def run_jp_collection() -> dict:
    """Run the JP scan pass. Uses MS_TOKEN_JP."""
    ms_token = os.getenv("MS_TOKEN_JP", "").strip()
    if not ms_token:
        raise RuntimeError("MS_TOKEN_JP is required")

    db.init_db()
    now_ts = int(time.time())
    tier_total = seed_total = eval_accept = eval_reject = 0

    async with TikTokApi() as api:
        await api.create_sessions(
            ms_tokens=[ms_token],
            num_sessions=1,
            sleep_after=SESSION_SLEEP_AFTER,
            headless=HEADLESS,
            browser=BROWSER,
        )

        # Phase A: primary JP hashtags
        logger.info("Phase A: %d JP primary hashtags", len(jp_config.JP_HASHTAGS))
        for tag in jp_config.JP_HASHTAGS:
            _, hits, seeds = await _scan_hashtag(
                api, tag, jp_config.JP_PER_TAG_LIMIT,
                is_discovery=False, now_ts=now_ts,
            )
            tier_total += hits
            seed_total += seeds
            await asyncio.sleep(jp_config.JP_SLEEP_BETWEEN_TAGS)

        # Phase B: discovery
        logger.info("Phase B: %d JP discovery hashtags", len(jp_config.JP_DISCOVERY_HASHTAGS))
        for tag in jp_config.JP_DISCOVERY_HASHTAGS:
            _, _, seeds = await _scan_hashtag(
                api, tag, jp_config.JP_PER_DISCOVERY_TAG_LIMIT,
                is_discovery=True, now_ts=now_ts,
            )
            seed_total += seeds
            await asyncio.sleep(jp_config.JP_SLEEP_BETWEEN_TAGS)

    # Phase C: creator evaluation (local DB)
    candidates = db.fetch_authors_to_evaluate(
        limit=jp_config.JP_CREATORS_EVAL_BUDGET,
        reject_reeval_seconds=14 * 86400,
        monitored_refresh_seconds=3 * 86400,
    )
    logger.info("Phase C: evaluating %d creators (JP)", len(candidates))
    for cand in candidates:
        verdict = _evaluate_creator_from_db(cand["author_unique"], now_ts=now_ts)
        if verdict is None:
            continue
        # Override eval thresholds for JP
        # If reason mentions median_out_of_range and the median is in JP range, flip to MONITORED
        median = verdict.get("median_plays") or 0
        reasons = (verdict.get("reason") or "").split(";")
        if (jp_config.JP_CREATOR_MEDIAN_MIN <= median <= jp_config.JP_CREATOR_MEDIAN_MAX
                and verdict.get("status") == "REJECTED"):
            # Re-judge using JP thresholds
            jp_reasons = [r for r in reasons
                          if not r.startswith("median_out_of_range")
                             and not r.startswith("no_viral")]
            max_7d = verdict.get("max_plays_7d") or 0
            if max_7d < jp_config.JP_CREATOR_VIRAL_MIN and max_7d < median * jp_config.JP_CREATOR_VIRAL_MULTIPLIER:
                jp_reasons.append(f"jp_no_viral(max={max_7d})")
            verdict["status"] = "MONITORED" if not jp_reasons else "REJECTED"
            verdict["reason"] = ";".join(jp_reasons) if jp_reasons else "jp_ok"

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
            logger.info("MONITORED: @%s median=%s viral7d=%s",
                        verdict["author_unique"],
                        verdict.get("median_plays"),
                        verdict.get("max_plays_7d"))
        else:
            eval_reject += 1

    summary = {
        "tier_hits": tier_total, "author_seeds": seed_total,
        "creators_accepted": eval_accept, "creators_rejected": eval_reject,
    }
    logger.info("JP collection summary: %s", summary)
    return summary


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
        stream=sys.stdout,
    )


async def _run() -> int:
    load_dotenv()
    _setup_logging()
    log = logging.getLogger("jp_main")
    log.info("Starting JP monitor")

    try:
        summary = await run_jp_collection()
    except Exception as exc:
        log.exception("JP collection failed: %s", exc)
        summary = {}

    # Push + Bitable sync use the JP tables
    from . import jp_bitable
    from .notifier import push_new_hits, push_new_creators

    # Patch Bitable env vars to point to JP tables for this process
    if os.getenv("BITABLE_JP_VIDEOS_TABLE"):
        os.environ["BITABLE_VIDEOS_TABLE"] = os.environ["BITABLE_JP_VIDEOS_TABLE"]
    if os.getenv("BITABLE_JP_CREATORS_TABLE"):
        os.environ["BITABLE_CREATORS_TABLE"] = os.environ["BITABLE_JP_CREATORS_TABLE"]

    video_pushes = push_new_hits()
    creator_pushes = push_new_creators()

    video_synced = jp_bitable.sync_videos()
    creator_synced = jp_bitable.sync_creators()

    try:
        followers_filled = backfill_followers_global()
    except Exception as exc:
        log.exception("Follower backfill failed: %s", exc)
        followers_filled = 0

    log.info("JP done. collect=%s | webhook: videos=%d creators=%d | "
             "bitable: videos=%d creators=%d | followers=%d",
             summary, video_pushes, creator_pushes,
             video_synced, creator_synced, followers_filled)
    return 0


def main():
    raise SystemExit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
