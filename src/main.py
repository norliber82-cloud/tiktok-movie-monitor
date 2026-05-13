"""Entrypoint. Two modes:

  fast: only Phase A (primary hashtag scan) + notify + Bitable sync.
        Used by the 45-min cron. Runtime ≈ 6–8 min.

  deep: Phase B (discovery seed) + Phase C (creator eval).
        Used by a separate hourly cron. Runtime ≈ 10–13 min.
"""

import argparse
import asyncio
import logging
import sys

from dotenv import load_dotenv

from . import bitable
from .collector import run_collection
from .notifier import push_new_creators, push_new_hits
from .yt_collector import run_yt_collection


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
        stream=sys.stdout,
    )


async def _run(mode: str) -> int:
    load_dotenv()
    _setup_logging()
    log = logging.getLogger("main")
    log.info("Starting monitor in mode=%s", mode)

    try:
        summary = await run_collection(mode=mode)
    except Exception as exc:
        log.exception("Collection failed: %s", exc)
        summary = {}

    # YouTube Shorts runs synchronously (no playwright / no async needed).
    # Kept in both modes because yt-dlp is cheap: ~20s per run.
    try:
        yt_summary = run_yt_collection()
        summary = {**summary, **yt_summary}
    except Exception as exc:
        log.exception("YT collection failed: %s", exc)

    video_pushes = push_new_hits()
    creator_pushes = push_new_creators() if mode == "deep" else 0

    video_synced = bitable.sync_videos() if bitable.is_configured() else 0
    creator_synced = bitable.sync_creators() if bitable.is_configured() and mode == "deep" else 0

    log.info(
        "Done (mode=%s). collect=%s | webhook: videos=%d creators=%d | "
        "bitable: videos=%d creators=%d (configured=%s)",
        mode, summary, video_pushes, creator_pushes,
        video_synced, creator_synced, bitable.is_configured(),
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("fast", "deep"), default="fast")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_run(args.mode)))


if __name__ == "__main__":
    main()
