"""Entrypoint: collect → notify → sync Bitable."""

import asyncio
import logging
import sys

from dotenv import load_dotenv

from . import bitable
from .collector import run_collection
from .notifier import push_new_creators, push_new_hits


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
        stream=sys.stdout,
    )


async def _run() -> int:
    load_dotenv()
    _setup_logging()
    log = logging.getLogger("main")

    try:
        summary = await run_collection()
    except Exception as exc:
        log.exception("Collection failed: %s", exc)
        summary = {"tier_hits": 0, "author_seeds": 0,
                   "creators_accepted": 0, "creators_rejected": 0}

    video_pushes = push_new_hits()
    creator_pushes = push_new_creators()

    video_synced = bitable.sync_videos() if bitable.is_configured() else 0
    creator_synced = bitable.sync_creators() if bitable.is_configured() else 0

    log.info(
        "Done. collect=%s | webhook: videos=%d creators=%d | "
        "bitable: videos=%d creators=%d (configured=%s)",
        summary, video_pushes, creator_pushes,
        video_synced, creator_synced, bitable.is_configured(),
    )
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
