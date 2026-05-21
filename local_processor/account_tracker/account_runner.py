"""Main runner for the account-level tracker.

Wires together cookie-authenticated TikTok endpoints, local snapshot
state, and Feishu Bitable writers for the four jobs:

  1. Liked videos       — pulled from the logged-in account's like list
  2. Following diff     — new/removed follows since last snapshot
  3. Following's videos — flag any 1M+ plays in last 3 days (req #3)
  4. Recursive discovery — followed creators' following lists, looking
                           for 1-5万 fans + 7-day-active (req #4)

Run modes:
  python -m local_processor.account_tracker.account_runner            # both regions
  python -m local_processor.account_tracker.account_runner --only us
  python -m local_processor.account_tracker.account_runner --dry-run  # no writes

Designed to run on the local machine (NOT GitHub Actions): the cookies
have an IP fingerprint and CI runners would trip risk control.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

# allow `python local_processor/account_tracker/account_runner.py` too
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from local_processor.account_tracker import (
    bitable_io,
    filters,
    state_store,
)
from local_processor.account_tracker.tiktok_account import Account
from local_processor.account_tracker.videos_via_tiktokapi import (
    fetch_user_videos_batch,
    fetch_following_list,
)


# ============================================================
# Config
# ============================================================

COOKIES = {
    "us": r"D:\搬运\.cookies\us.json",
    "jp": r"D:\搬运\.cookies\jp.json",
}

# Caps to keep the runner bounded.
LIKED_PAGES_PER_ACCOUNT     = 8       # ~30/page → 240 most-recent likes
LIKED_MAX_AGE_DAYS         = 7       # stop pulling once we hit likes older than this
FOLLOWING_PAGES_PER_ACCOUNT = 30      # 30/page → up to 900
USER_VIDEOS_PAGES           = 2       # 35/page → most-recent ~70 videos
RECURSE_FOLLOWING_PAGES     = 6       # how deep into each peer's following list
RECURSE_BUDGET_PER_ACCOUNT  = 30      # max peers we recurse into per region
PROFILE_FETCH_BUDGET        = 120     # max user-detail HTTP calls per run

VIRAL_MIN_PLAYS = 1_000_000
VIRAL_WINDOW_D  = 3
TARGET_FOLLOWERS_MIN = 10_000
TARGET_FOLLOWERS_MAX = 50_000
RECENT_POST_DAYS     = 7

logger = logging.getLogger(__name__)


# ============================================================
# Per-region pipeline
# ============================================================

class RegionRunner:
    def __init__(self, label: str, *, dry_run: bool = False):
        self.label = label
        self.dry_run = dry_run
        cookie_path = COOKIES[label]
        if not Path(cookie_path).exists():
            raise FileNotFoundError(f"Cookie file missing: {cookie_path}")
        logger.info("[%s] loading cookies from %s", label, cookie_path)
        self.account = Account(label, cookie_path)
        logger.info("[%s] %s", label, self.account)
        self.profile_calls = 0
        # Prefer per-region MS_TOKEN, fall back to MS_TOKEN, then to the
        # token embedded in the cookie file itself (always present).
        self.ms_token = (
            os.getenv(f"MS_TOKEN_{label.upper()}", "").strip()
            or os.getenv("MS_TOKEN", "").strip()
            or self.account.cookies.get("msToken", "")
        )
        if self.ms_token:
            logger.info("[%s] msToken loaded (len=%d)", label, len(self.ms_token))
        else:
            logger.warning("[%s] no msToken available — viral/recurse will fail",
                           label)
        # Counters for the final summary
        self.stats = {
            "new_follows": 0,
            "removed_follows": 0,
            "new_liked_videos": 0,
            "viral_videos": 0,
            "recurse_creators": 0,
            "errors": [],
        }

    # ----- helpers -----

    def _maybe_fetch_profile(self, unique_id: str) -> Optional[dict]:
        """Honors the per-run profile budget."""
        if self.profile_calls >= PROFILE_FETCH_BUDGET:
            return None
        self.profile_calls += 1
        try:
            return self.account.get_user_detail(unique_id)
        except Exception as exc:
            self.stats["errors"].append(f"user_detail @{unique_id}: {exc}")
            return None

    def _write_creators(self, creators: list[dict], source: str) -> int:
        if not creators:
            return 0
        if self.dry_run:
            logger.info("[dry-run][%s] would write %d creators (source=%s)",
                        self.label, len(creators), source)
            return len(creators)
        return bitable_io.write_creators(creators, source)

    # ----- jobs -----

    def job_following_diff(self) -> list[dict]:
        """Pull current following list, diff against snapshot, write new ones.
        Falls back to TikTokApi (Playwright) if the cookie API is rate-limited."""
        logger.info("[%s] job_following_diff: pulling following list…", self.label)
        try:
            current = self.account.get_following(
                self.account.sec_uid, max_pages=FOLLOWING_PAGES_PER_ACCOUNT,
            )
        except Exception as exc:
            self.stats["errors"].append(f"get_following: {exc}")
            logger.exception("[%s] get_following failed", self.label)
            current = []

        # Fallback: if cookie API returned 0 (rate-limited), use TikTokApi
        if not current and self.ms_token:
            logger.info("[%s] cookie API returned 0 — falling back to TikTokApi",
                        self.label)
            try:
                current = fetch_following_list(
                    self.account.unique_id,
                    ms_token=self.ms_token,
                    count=500,
                    cookie_path=COOKIES[self.label],
                )
            except Exception as exc:
                self.stats["errors"].append(f"TikTokApi following fallback: {exc}")
                logger.exception("[%s] TikTokApi following fallback failed",
                                 self.label)
                current = []

        logger.info("[%s] current following count: %d", self.label, len(current))

        old_snap = state_store.load_following_snapshot(self.label)
        new_snap = {u["unique_id"]: u for u in current if u.get("unique_id")}

        diff = state_store.diff_following(old_snap, new_snap)
        added   = diff["added"]
        removed = diff["removed"]
        kept    = diff["kept"]

        self.stats["new_follows"]     = len(added)
        self.stats["removed_follows"] = len(removed)

        logger.info("[%s] following diff: +%d / -%d / =%d",
                    self.label, len(added), len(removed), len(kept))

        # Enrich newly-added with full profile (fans, video count) before write
        enriched_added = []
        for u in added:
            uniq = u.get("unique_id")
            if not uniq:
                continue
            detail = self._maybe_fetch_profile(uniq)
            if detail:
                u.update(detail)
            enriched_added.append(u)

        self._write_creators(enriched_added, f"following_{self.label}")

        # Persist the new snapshot regardless of write outcome
        if not self.dry_run:
            state_store.save_following_snapshot(self.label, new_snap)

        # Return the union (added + kept) for downstream jobs
        return list(new_snap.values())

    def job_liked_videos(self):
        """Pull recent likes; for any new ones, write the video + the author."""
        logger.info("[%s] job_liked_videos: pulling liked feed…", self.label)
        try:
            liked = self.account.get_liked_videos(
                self.account.sec_uid, max_pages=LIKED_PAGES_PER_ACCOUNT,
            )
        except Exception as exc:
            self.stats["errors"].append(f"get_liked_videos: {exc}")
            logger.exception("[%s] get_liked_videos failed", self.label)
            return

        logger.info("[%s] pulled %d liked videos", self.label, len(liked))
        if not liked:
            return

        # Filter: only keep likes from the last LIKED_MAX_AGE_DAYS days
        now = int(time.time())
        cutoff = now - LIKED_MAX_AGE_DAYS * 86400
        recent_liked = [v for v in liked
                        if int(v.get("create_time") or 0) >= cutoff]
        logger.info("[%s] %d liked within %d days (dropped %d older)",
                    self.label, len(recent_liked), LIKED_MAX_AGE_DAYS,
                    len(liked) - len(recent_liked))

        seen = state_store.load_seen_likes(self.label)
        new_videos = [v for v in recent_liked
                      if v.get("video_id") and v["video_id"] not in seen]
        logger.info("[%s] new liked since last run: %d", self.label, len(new_videos))

        # Write videos first; only mark them as seen if the write actually
        # succeeded (otherwise a Feishu outage would silently drop data).
        write_ok = False
        if not self.dry_run:
            written = bitable_io.write_liked_videos(new_videos, source_account=self.label)
            # Treat a write that touched any record (or had nothing to do) as success.
            write_ok = (written == len(new_videos)) or not new_videos
        else:
            logger.info("[dry-run][%s] would write %d liked videos",
                        self.label, len(new_videos))

        self.stats["new_liked_videos"] = len(new_videos)

        # Pull author profile for each new video's author and write to creators
        unique_authors = {v["author_unique"] for v in new_videos
                          if v.get("author_unique")}
        author_creators = []
        for uniq in unique_authors:
            detail = self._maybe_fetch_profile(uniq)
            if detail:
                author_creators.append(detail)
        self._write_creators(author_creators, f"liked_{self.label}")

        # Persist seen set only when the videos write actually succeeded.
        if not self.dry_run and write_ok and new_videos:
            new_ids = {v["video_id"] for v in new_videos}
            state_store.save_seen_likes(self.label, seen | new_ids)
        elif not self.dry_run and not write_ok:
            logger.warning("[%s] liked write failed — not persisting seen state",
                           self.label)

    def job_following_viral(self, following: list[dict]):
        """For each followed user, pull their recent videos and flag the ones
        that are >= 1M plays in the last 3 days (req #3)."""
        usernames = [u["unique_id"] for u in following if u.get("unique_id")]
        if not usernames:
            return
        logger.info("[%s] job_following_viral: scanning %d creators…",
                    self.label, len(usernames))

        try:
            batch = fetch_user_videos_batch(usernames, count=30,
                                            ms_token=self.ms_token)
        except Exception as exc:
            self.stats["errors"].append(f"viral fetch_batch: {exc}")
            logger.exception("[%s] fetch_user_videos_batch failed", self.label)
            return

        viral_rows = []
        for uniq, vids in batch.items():
            for v in vids:
                if filters.is_recent_viral(v,
                                           min_plays=VIRAL_MIN_PLAYS,
                                           window_days=VIRAL_WINDOW_D):
                    viral_rows.append(v)

        logger.info("[%s] found %d viral videos (>=%dM in %dd)",
                    self.label,
                    len(viral_rows),
                    VIRAL_MIN_PLAYS // 1_000_000,
                    VIRAL_WINDOW_D)

        if not viral_rows:
            return

        if self.dry_run:
            for v in viral_rows[:5]:
                logger.info("  [dry-run] viral: @%s plays=%s",
                            v.get("author_unique"), v.get("play_count"))
            return

        bitable_io.write_viral_videos_to_main(viral_rows, region=self.label.upper())
        self.stats["viral_videos"] = len(viral_rows)

    def job_recursive_discover(self, following: list[dict]):
        """For each peer in `following`, fetch *their* following list and
        keep creators with 1-5万 fans + posted in last 7 days (req #4)."""
        peers = [u for u in following if u.get("sec_uid")]
        peers = peers[:RECURSE_BUDGET_PER_ACCOUNT]
        logger.info("[%s] job_recursive_discover: recursing into %d peers…",
                    self.label, len(peers))

        # Collect candidates first (de-dupe by unique_id)
        candidates: dict[str, dict] = {}
        for peer in peers:
            try:
                peer_following = self.account.get_following(
                    peer["sec_uid"], max_pages=RECURSE_FOLLOWING_PAGES,
                )
            except Exception as exc:
                self.stats["errors"].append(
                    f"recurse @{peer.get('unique_id')}: {exc}")
                continue
            for c in peer_following:
                uid = c.get("unique_id")
                if not uid or uid in candidates:
                    continue
                # First-pass filter: rough follower band (data from list API).
                # The list API gives follower_count too — keep only those
                # already in the band before spending a profile call.
                f = int(c.get("follower_count") or 0)
                if not (TARGET_FOLLOWERS_MIN <= f <= TARGET_FOLLOWERS_MAX):
                    continue
                candidates[uid] = c

        logger.info("[%s] %d size-band candidates from peers",
                    self.label, len(candidates))

        if not candidates:
            return

        # Second pass: enrich each via profile scrape (powered by cookie HTML)
        enriched = []
        for uid, c in candidates.items():
            detail = self._maybe_fetch_profile(uid)
            if not detail:
                continue
            if not filters.is_target_size(detail,
                                          TARGET_FOLLOWERS_MIN,
                                          TARGET_FOLLOWERS_MAX):
                continue
            enriched.append(detail)

        if not enriched:
            logger.info("[%s] recursive: nothing left after profile re-check",
                        self.label)
            return

        # Third pass: 7-day cadence check via TikTokApi batch (single Playwright session)
        try:
            video_batch = fetch_user_videos_batch(
                [d["unique_id"] for d in enriched],
                count=10,
                ms_token=self.ms_token,
            )
        except Exception as exc:
            self.stats["errors"].append(f"recurse fetch_batch: {exc}")
            logger.exception("[%s] cadence batch fetch failed", self.label)
            return

        kept = []
        for d in enriched:
            vids = video_batch.get(d["unique_id"], [])
            latest_ts = max((int(v.get("create_time") or 0) for v in vids),
                            default=0)
            if not filters.has_recent_post(latest_ts, days=RECENT_POST_DAYS):
                continue
            d["最近爆款"] = ""  # placeholder column
            kept.append(d)

        logger.info("[%s] recursive: kept %d creators after cadence filter",
                    self.label, len(kept))

        self.stats["recurse_creators"] = len(kept)
        self._write_creators(kept, f"recurse_{self.label}")

    # ----- orchestration -----

    def run(self):
        t0 = time.time()
        logger.info("=" * 60)
        logger.info("Starting region runner: %s (dry_run=%s)",
                    self.label, self.dry_run)
        logger.info("=" * 60)

        # Job 1: liked videos (independent of following snapshot)
        self.job_liked_videos()

        # Job 2: following diff — also returns full current following list
        following = self.job_following_diff()

        # Job 3: scan each followed creator's recent videos for viral hits
        if following:
            self.job_following_viral(following)

        # Job 4: recurse one level into peers' following to find 1-5w fans
        if following:
            self.job_recursive_discover(following)

        elapsed = time.time() - t0
        logger.info("[%s] region run finished in %.1fs", self.label, elapsed)
        logger.info("[%s] stats: %s", self.label, self.stats)


# ============================================================
# Entrypoint
# ============================================================

def _setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def main():
    load_dotenv()
    _setup_logging()

    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=["us", "jp"],
                        help="Run only one region")
    parser.add_argument("--dry-run", action="store_true",
                        help="Skip all Bitable writes, just log")
    parser.add_argument("--skip-recurse", action="store_true",
                        help="Skip the heavy recursive discovery job")
    args = parser.parse_args()

    targets = [args.only] if args.only else ["us", "jp"]

    overall = {}
    for label in targets:
        try:
            runner = RegionRunner(label, dry_run=args.dry_run)
            if args.skip_recurse:
                # Patch the method to a no-op
                runner.job_recursive_discover = lambda *a, **kw: None  # type: ignore
            runner.run()
            overall[label] = runner.stats
        except Exception as exc:
            logger.exception("Runner for %s blew up", label)
            overall[label] = {"fatal": str(exc)}

    print("\n=== FINAL SUMMARY ===")
    for label, stats in overall.items():
        print(f"  [{label}] {stats}")


if __name__ == "__main__":
    main()
