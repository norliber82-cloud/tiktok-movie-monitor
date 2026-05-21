"""Local incremental state for the account tracker.

Two state files per account live under ``D:\\搬运\\.account_state\\``:
  ``{label}_following.json``   — last snapshot of who this account follows
  ``{label}_liked_seen.json``  — set of video_ids we've already pulled

Both are simple JSON dumps so you can inspect or reset them by hand.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

STATE_DIR = Path(r"D:\搬运\.account_state")
STATE_DIR.mkdir(parents=True, exist_ok=True)


def _path(label: str, suffix: str) -> Path:
    return STATE_DIR / f"{label}_{suffix}.json"


# ============================================================
# Following snapshot (full list of who you follow)
# ============================================================

def load_following_snapshot(label: str) -> dict[str, dict]:
    """Returns {unique_id: user_dict} of last-known following list.
    Empty dict on first run."""
    p = _path(label, "following")
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Could not load %s: %s", p, exc)
        return {}


def save_following_snapshot(label: str, data: dict[str, dict]) -> None:
    p = _path(label, "following")
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def diff_following(old: dict[str, dict], new: dict[str, dict]) -> dict:
    """Returns:
        added:    [user_dict, ...]    new follows since last snapshot
        removed:  [user_dict, ...]    unfollowed since last snapshot
        kept:     [user_dict, ...]    unchanged (still following)
    """
    old_keys = set(old.keys())
    new_keys = set(new.keys())
    added_keys   = new_keys - old_keys
    removed_keys = old_keys - new_keys
    kept_keys    = new_keys & old_keys
    return {
        "added":   [new[k] for k in added_keys],
        "removed": [old[k] for k in removed_keys],
        "kept":    [new[k] for k in kept_keys],
    }


# ============================================================
# Liked-videos seen set (so we don't re-process the same video)
# ============================================================

def load_seen_likes(label: str) -> set[str]:
    p = _path(label, "liked_seen")
    if not p.exists():
        return set()
    try:
        return set(json.loads(p.read_text(encoding="utf-8")))
    except Exception:
        return set()


def save_seen_likes(label: str, seen: set[str]) -> None:
    p = _path(label, "liked_seen")
    # Cap at 5000 to keep file tiny
    capped = list(seen)[-5000:]
    p.write_text(json.dumps(capped, ensure_ascii=False), encoding="utf-8")
