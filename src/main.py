"""Entrypoint: collect then notify."""

import asyncio
import logging
import os
import sys

from dotenv import load_dotenv

from .collector import run_collection
from .notifier import push_new_hits, push_summary


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
        hits = await run_collection()
    except Exception as exc:
        log.exception("Collection failed: %s", exc)
        # Still exit 0 so the workflow commits the DB and keeps running next time.
        return 0

    pushed = push_new_hits()
    push_summary(scan_hits=len(hits))
    log.info("Done. qualifying=%d pushed=%d", len(hits), pushed)
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
