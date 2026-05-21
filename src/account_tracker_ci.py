"""Account tracker adapted for GitHub Actions (CI).

Runs the following + liked jobs without TikTokApi (no Playwright needed).
Uses cookie-based API calls only. Skips the viral scan and recursive
discovery (those are handled by viral-scan.yml separately).

Environment variables:
  ACCOUNT_COOKIES_US  — path to us.json cookie file
  ACCOUNT_COOKIES_JP  — path to jp.json cookie file
  ACCOUNT_STATE_DIR   — directory for state files (default: .account_state)
  ALL_PROXY           — set to "" to disable proxy on CI
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Patch state_store to use CI-friendly path
STATE_DIR = Path(os.environ.get("ACCOUNT_STATE_DIR", ".account_state"))
STATE_DIR.mkdir(parents=True, exist_ok=True)

# Monkey-patch the state_store module before importing account_tracker
import local_processor.account_tracker.state_store as _ss
_ss.STATE_DIR = STATE_DIR

from local_processor.account_tracker.tiktok_account import Account
from local_processor.account_tracker import state_store, bitable_io

logger = logging.getLogger(__name__)

LIKED_MAX_AGE_DAYS = 7


def _setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def run_region(label: str, cookie_path: str):
    """Run following-diff + liked-videos for one region."""
    if not Path(cookie_path).exists():
        logger.warning("[%s] cookie file not found: %s — skipping", label, cookie_path)
        return

    logger.info("[%s] loading cookies from %s", label, cookie_path)
    try:
        account = Account(label, cookie_path)
    except Exception as exc:
        logger.error("[%s] cookie auth failed: %s", label, exc)
        return
    logger.info("[%s] %s", label, account)

    # --- Job 1: Liked videos ---
    logger.info("[%s] pulling liked videos…", label)
    try:
        liked = account.get_liked_videos(account.sec_uid, max_pages=8)
    except Exception as exc:
        logger.warning("[%s] get_liked_videos failed: %s", label, exc)
        liked = []

    if liked:
        now = int(time.time())
        cutoff = now - LIKED_MAX_AGE_DAYS * 86400
        recent = [v for v in liked if int(v.get("create_time") or 0) >= cutoff]
        logger.info("[%s] %d liked total, %d within %d days",
                    label, len(liked), len(recent), LIKED_MAX_AGE_DAYS)

        seen = state_store.load_seen_likes(label)
        new_videos = [v for v in recent if v.get("video_id") and v["video_id"] not in seen]
        logger.info("[%s] %d new liked videos", label, len(new_videos))

        if new_videos:
            written = bitable_io.write_liked_videos(new_videos, source_account=label)
            if written:
                state_store.save_seen_likes(label, seen | {v["video_id"] for v in new_videos})

            # Write authors
            unique_authors = {v["author_unique"] for v in new_videos if v.get("author_unique")}
            author_details = []
            for uniq in list(unique_authors)[:50]:
                d = account.get_user_detail(uniq)
                if d:
                    author_details.append(d)
            if author_details:
                bitable_io.write_creators(author_details, f"liked_{label}")
    else:
        logger.info("[%s] liked videos returned 0 (private or empty)", label)

    # --- Job 2: Following diff ---
    logger.info("[%s] pulling following list…", label)
    try:
        current = account.get_following(account.sec_uid, max_pages=30)
    except Exception as exc:
        logger.warning("[%s] get_following failed: %s", label, exc)
        current = []

    if current:
        logger.info("[%s] following count: %d", label, len(current))
        old_snap = state_store.load_following_snapshot(label)
        new_snap = {u["unique_id"]: u for u in current if u.get("unique_id")}
        diff = state_store.diff_following(old_snap, new_snap)
        added = diff["added"]
        logger.info("[%s] following diff: +%d / -%d / =%d",
                    label, len(added), len(diff["removed"]), len(diff["kept"]))

        if added:
            # Enrich new follows with profile data
            enriched = []
            for u in added[:50]:
                d = account.get_user_detail(u.get("unique_id", ""))
                if d:
                    enriched.append(d)
                else:
                    enriched.append(u)
            bitable_io.write_creators(enriched, f"following_{label}")

        state_store.save_following_snapshot(label, new_snap)
    else:
        logger.info("[%s] following list returned 0 (rate-limited)", label)


def main():
    _setup_logging()

    us_path = os.environ.get("ACCOUNT_COOKIES_US", ".cookies/us.json")
    jp_path = os.environ.get("ACCOUNT_COOKIES_JP", ".cookies/jp.json")

    run_region("us", us_path)
    run_region("jp", jp_path)

    logger.info("=== Account tracker CI finished ===")


if __name__ == "__main__":
    main()
