"""Confidence scoring for scanned videos.

Assigns a trust level based on whether the video's author is in the
user's whitelist (following/liked creators from the account tracker).

Levels:
  高 — author is in the whitelist (following or liked)
  中 — author not in whitelist, but title matches strict commentary keywords
  低 — only matched via hashtag, no other signal

The whitelist is loaded from the Feishu Bitable `following_creators` table
at startup and cached for the duration of the run.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import requests

logger = logging.getLogger(__name__)

API = "https://open.feishu.cn/open-apis"
FOLLOWING_CREATORS_TABLE = "tblRc6b9FrxMu4Gv"

# Strict keywords that indicate genuine movie commentary (not clips/edits)
_STRICT_KEYWORDS = [
    # English
    "ending explained", "movie recap", "film breakdown",
    "scene breakdown", "hidden detail", "movie analysis",
    "film analysis", "movie commentary", "plot explained",
    "film theory", "movie explained", "why this movie",
    "what nobody noticed", "director's trick",
    # Japanese
    "映画紹介", "映画考察", "映画解説", "ネタバレ",
    # Chinese
    "电影解说", "影视解说", "剧情解说",
]

_whitelist_cache: Optional[set[str]] = None


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def _get_tenant_token() -> Optional[str]:
    """Minimal auth — reuses src.bitable's token if available."""
    try:
        from . import bitable as _b
        return _b._get_tenant_token()
    except Exception:
        return None


def load_whitelist() -> set[str]:
    """Load the set of trusted usernames from the following_creators table.
    Cached after first call within a process."""
    global _whitelist_cache
    if _whitelist_cache is not None:
        return _whitelist_cache

    _whitelist_cache = set()
    token = _get_tenant_token()
    if not token:
        logger.warning("confidence: no Feishu token — whitelist empty")
        return _whitelist_cache

    app_token = _env("BITABLE_APP_TOKEN")
    if not app_token:
        return _whitelist_cache

    headers = {"Authorization": f"Bearer {token}",
               "Content-Type": "application/json; charset=utf-8"}
    url = f"{API}/bitable/v1/apps/{app_token}/tables/{FOLLOWING_CREATORS_TABLE}/records"
    page_token = None
    for _ in range(40):
        params = {"page_size": 500}
        if page_token:
            params["page_token"] = page_token
        try:
            r = requests.get(url, headers=headers, params=params, timeout=30).json()
        except Exception:
            break
        if r.get("code") != 0:
            break
        d = r.get("data", {})
        for rec in d.get("items", []):
            f = rec.get("fields", {}) or {}
            u = f.get("用户名")
            if u and isinstance(u, str):
                _whitelist_cache.add(u.strip().lower())
        page_token = d.get("page_token")
        if not d.get("has_more"):
            break

    logger.info("confidence: loaded %d trusted creators", len(_whitelist_cache))
    return _whitelist_cache


def score(author_unique: str, caption: str) -> str:
    """Return '高', '中', or '低'."""
    whitelist = load_whitelist()

    # High: author in whitelist
    if (author_unique or "").strip().lower() in whitelist:
        return "高"

    # Medium: strict keyword match in caption
    cap_lower = f" {(caption or '').lower()} "
    if any(kw in cap_lower for kw in _STRICT_KEYWORDS):
        return "中"

    # Low: everything else
    return "低"
