"""Tiny pure-data filters for the account tracker pipeline.

Keeping these out of `tiktok_account.py` so they're easy to unit-test
and tweak without touching the HTTP layer.
"""

from __future__ import annotations

import time

# ----------------------------------------------------------------------
# Video-level filters
# ----------------------------------------------------------------------

def is_recent_viral(video: dict, *,
                    min_plays: int = 1_000_000,
                    window_days: int = 3,
                    now: int | None = None) -> bool:
    """A video is 'recent viral' iff plays >= min_plays AND it was
    posted in the last `window_days` days."""
    now = now or int(time.time())
    create_time = int(video.get("create_time") or 0)
    if not create_time:
        return False
    age = now - create_time
    if age < 0 or age > window_days * 86400:
        return False
    if int(video.get("play_count") or 0) < min_plays:
        return False
    return True


# ----------------------------------------------------------------------
# Creator-level filters
# ----------------------------------------------------------------------

def is_target_size(creator: dict,
                   min_followers: int = 10_000,
                   max_followers: int = 50_000) -> bool:
    """1-5 万粉档位."""
    f = int(creator.get("follower_count") or 0)
    return min_followers <= f <= max_followers


def has_recent_post(latest_video_create_time: int | None,
                    *, days: int = 7,
                    now: int | None = None) -> bool:
    """Stable cadence check: latest post within `days` days."""
    now = now or int(time.time())
    if not latest_video_create_time:
        return False
    return (now - int(latest_video_create_time)) <= days * 86400
