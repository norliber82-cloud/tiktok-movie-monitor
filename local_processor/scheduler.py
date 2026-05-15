"""Lightweight always-on scheduler.

Started on Windows login. Behavior:
  - On startup: if today's 2 AM run was missed (PC was off then),
    immediately catch up.
  - Then loop forever, sleeping until next 02:00 to fire the daily run.

Survives reboots: writes a stamp file each time it runs successfully.
"""

import logging
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from . import config

STAMP_FILE = Path(r"D:\搬运\_last_run.stamp")
RUN_HOUR   = 2  # 02:00

logger = logging.getLogger(__name__)


def setup_logging():
    config.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
        handlers=[
            logging.FileHandler(config.LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def last_run_date() -> datetime.date | None:
    if STAMP_FILE.exists():
        try:
            return datetime.fromisoformat(
                STAMP_FILE.read_text(encoding="utf-8").strip()
            ).date()
        except Exception:
            return None
    return None


def stamp_now():
    STAMP_FILE.parent.mkdir(parents=True, exist_ok=True)
    STAMP_FILE.write_text(datetime.now().isoformat(), encoding="utf-8")


def run_processor():
    """Subprocess the runner so a crash here doesn't kill the scheduler."""
    py = sys.executable
    logger.info("Launching runner subprocess...")
    try:
        result = subprocess.run(
            [py, "-m", "local_processor.runner", "--hours", "26"],
            cwd=Path(__file__).resolve().parent.parent,
            timeout=4 * 3600,
        )
        logger.info("runner exited with code %s", result.returncode)
    except Exception as exc:
        logger.exception("runner subprocess failed: %s", exc)
    finally:
        stamp_now()


def next_run_at(now: datetime) -> datetime:
    today_run = now.replace(hour=RUN_HOUR, minute=0, second=0, microsecond=0)
    if now < today_run:
        return today_run
    return today_run + timedelta(days=1)


def main():
    setup_logging()
    logger.info("Scheduler started. Next-run-hour=%d. Stamp file=%s",
                RUN_HOUR, STAMP_FILE)

    # ---- Catch-up on startup ----
    today = datetime.now().date()
    last  = last_run_date()
    today_2am = datetime.now().replace(hour=RUN_HOUR, minute=0,
                                       second=0, microsecond=0)
    if datetime.now() >= today_2am and last != today:
        logger.info("Catch-up: missed today's 02:00 run (last=%s). Running now.",
                    last)
        run_processor()
    else:
        logger.info("No catch-up needed (last_run=%s, today=%s)", last, today)

    # ---- Main loop ----
    while True:
        now = datetime.now()
        target = next_run_at(now)
        sleep_sec = (target - now).total_seconds()
        logger.info("Sleeping until %s (~%.1f h)", target,
                    sleep_sec / 3600)
        # Sleep in chunks so we wake up promptly after suspend/resume cycles
        while sleep_sec > 0:
            chunk = min(sleep_sec, 300)
            time.sleep(chunk)
            sleep_sec = (target - datetime.now()).total_seconds()
        logger.info("Waking up to run scheduled processor at %s",
                    datetime.now())
        run_processor()


if __name__ == "__main__":
    main()
