"""TikTok account-level operations using exported browser cookies.

Loads a cookie JSON (exported from Cookie-Editor extension), discovers
the logged-in user, then calls TikTok's internal web APIs that require
authentication: liked videos list, following list, user-detail, etc.

All endpoints used here are the same ones tiktok.com itself calls when
you browse the site — we just feed it our cookies so it returns data
for the logged-in user.
"""

from __future__ import annotations

import json
import logging
import os
import re
import random
import time
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

REHYDRATE_RE = re.compile(
    r'__UNIVERSAL_DATA_FOR_REHYDRATION__[^>]*>([^<]+)</script', re.DOTALL,
)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


# ============================================================
# Cookie loader
# ============================================================

def load_cookies(json_path: str) -> dict[str, str]:
    """Load Cookie-Editor JSON export and return a dict suitable for
    requests.cookies."""
    p = Path(json_path)
    items = json.loads(p.read_text(encoding="utf-8"))
    out = {}
    for c in items:
        # Take only TikTok-relevant cookies
        domain = c.get("domain", "")
        if "tiktok.com" not in domain:
            continue
        out[c["name"]] = c["value"]
    if not out:
        raise RuntimeError(f"No tiktok.com cookies found in {json_path}")
    return out


# ============================================================
# HTTP helpers with SSL retry
# ============================================================

def _sleep_jitter(base: float = 1.0, jitter: float = 0.6):
    time.sleep(base + random.random() * jitter)


# Proxy config: v2rayN local SOCKS5 proxy for bypassing IP rate-limits.
# Set to None to disable. The runner auto-detects from env ALL_PROXY too.
PROXY_URL = os.environ.get("ALL_PROXY", "socks5h://127.0.0.1:10808")
_PROXIES = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None


def _get(url: str, *, cookies: dict, params: dict | None = None,
         referer: str = "https://www.tiktok.com/",
         max_retries: int = 4, timeout: int = 20) -> requests.Response:
    headers = {
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": referer,
    }
    last_exc = None
    for attempt in range(max_retries):
        try:
            return requests.get(url, headers=headers, cookies=cookies,
                                params=params, proxies=_PROXIES, timeout=timeout)
        except (requests.exceptions.SSLError,
                requests.exceptions.ConnectionError) as exc:
            last_exc = exc
            logger.debug("retry %d/%d after %s",
                         attempt + 1, max_retries, type(exc).__name__)
            _sleep_jitter(1.5 + attempt, 0.8)
    raise last_exc  # type: ignore


# ============================================================
# Account discovery
# ============================================================

class Account:
    """Represents a logged-in TikTok account."""

    def __init__(self, label: str, cookie_path: str):
        self.label = label
        self.cookie_path = cookie_path
        self.cookies = load_cookies(cookie_path)
        self.unique_id: Optional[str] = None
        self.sec_uid: Optional[str] = None
        self.user_id: Optional[str] = None
        self.nickname: Optional[str] = None
        self._discover_self()

    def _discover_self(self):
        """Hit /foryou and parse the rehydrate JSON to find self."""
        r = _get("https://www.tiktok.com/foryou", cookies=self.cookies)
        m = REHYDRATE_RE.search(r.text)
        if not m:
            raise RuntimeError(f"[{self.label}] no rehydrate blob — cookies dead?")
        data = json.loads(m.group(1))
        scope = data.get("__DEFAULT_SCOPE__", {})

        # First try: webapp.app-context.user (newer rehydrate shape)
        user = scope.get("webapp.app-context", {}).get("user", {}) or {}
        if user.get("uniqueId"):
            self.unique_id = user.get("uniqueId")
            self.sec_uid = user.get("secUid")
            self.user_id = user.get("uid")
            self.nickname = user.get("nickname") or self.unique_id
            return

        # Fallback: scan all sub-scopes for a userInfo block
        for v in scope.values():
            if isinstance(v, dict) and "userInfo" in v:
                ui = v.get("userInfo", {}).get("user", {}) or {}
                if ui.get("uniqueId"):
                    self.unique_id = ui.get("uniqueId")
                    self.sec_uid = ui.get("secUid")
                    self.user_id = ui.get("id")
                    self.nickname = ui.get("nickname") or ui.get("uniqueId")
                    return

        raise RuntimeError(f"[{self.label}] could not determine logged-in user")

    def __repr__(self):
        return f"<Account {self.label}: @{self.unique_id} ({self.nickname})>"

    # ------------------------------------------------------------------
    # Endpoints
    # ------------------------------------------------------------------

    def get_user_detail(self, unique_id: str) -> Optional[dict]:
        """Pull a user's public profile via HTML scrape (anonymous works too,
        but we use cookies to stay consistent and avoid bot blocks)."""
        url = f"https://www.tiktok.com/@{unique_id.lstrip('@')}"
        try:
            r = _get(url, cookies=self.cookies, referer="https://www.tiktok.com/")
        except Exception as exc:
            logger.warning("get_user_detail @%s failed: %s", unique_id, exc)
            return None
        if r.status_code != 200:
            return None
        m = REHYDRATE_RE.search(r.text)
        if not m:
            return None
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            return None
        detail = data.get("__DEFAULT_SCOPE__", {}).get("webapp.user-detail", {})
        ui = detail.get("userInfo", {}).get("user", {}) or {}
        st = detail.get("userInfo", {}).get("stats", {}) or {}
        if not ui.get("uniqueId"):
            return None
        return {
            "unique_id":      ui.get("uniqueId"),
            "sec_uid":        ui.get("secUid"),
            "user_id":        ui.get("id"),
            "nickname":       ui.get("nickname") or ui.get("uniqueId"),
            "avatar_url":     ui.get("avatarLarger") or ui.get("avatarMedium") or "",
            "signature":      ui.get("signature", ""),
            "language":       ui.get("language", ""),
            "follower_count": int(st.get("followerCount") or 0),
            "following_count":int(st.get("followingCount") or 0),
            "video_count":    int(st.get("videoCount") or 0),
            "heart_count":    int(st.get("heartCount") or 0),
        }

    # ----- following list -----

    def get_following(self, sec_uid: str, max_pages: int = 20) -> list[dict]:
        """List who a given user follows. Requires cookies (logged-in only).

        Notes:
        - The endpoint distinguishes followers vs following via the `scene`
          parameter. scene=21 == FOLLOWING, scene=67 == FOLLOWERS.
        - Pagination cursor is returned in `minCursor` (not `maxCursor`).
          We pass it back as the next `minCursor`.
        - We also dedupe by uniqueId and stop when a page yields nothing
          new, since the API will keep returning hasMore=true forever
          even when it's already at the end.
        """
        url = "https://www.tiktok.com/api/user/list/"
        out = []
        seen_ids: set[str] = set()
        min_cursor = "0"
        last_cursor = None
        for page in range(max_pages):
            params = {
                "WebIdLastTime": "0",
                "aid": "1988",
                "app_language": "en",
                "app_name": "tiktok_web",
                "browser_language": "en-US",
                "browser_name": "Mozilla",
                "browser_online": "true",
                "browser_platform": "Win32",
                "browser_version": "5.0",
                "channel": "tiktok_web",
                "cookie_enabled": "true",
                "count": "30",
                "device_id": "0",
                "device_platform": "web_pc",
                "focus_state": "true",
                "from_page": "user",
                "history_len": "1",
                "is_fullscreen": "false",
                "is_page_visible": "true",
                "language": "en",
                "minCursor": min_cursor,
                "maxCursor": "0",
                "os": "windows",
                "priority_region": "",
                "referer": "",
                "region": "US",
                "screen_height": "1080",
                "screen_width": "1920",
                "scene": "21",
                "secUid": sec_uid,
                "tz_name": "America/Los_Angeles",
                "user_is_login": "true",
                "webcast_language": "en",
            }
            try:
                r = _get(url, cookies=self.cookies, params=params,
                         referer=f"https://www.tiktok.com/@x")
            except Exception as exc:
                logger.warning("following list req failed: %s", exc)
                break
            if r.status_code != 200:
                break
            if not r.text or not r.text.strip():
                logger.warning("[follow-list] empty body — looks like a soft rate-limit; backing off")
                break
            try:
                data = r.json()
            except Exception:
                break

            users = data.get("userList", [])
            if not users:
                break

            page_added = 0
            for entry in users:
                u = entry.get("user", {})
                uid = u.get("uniqueId")
                if not uid or uid in seen_ids:
                    continue
                seen_ids.add(uid)
                page_added += 1
                st = entry.get("stats", {}) or {}
                out.append({
                    "unique_id": uid,
                    "sec_uid":   u.get("secUid"),
                    "user_id":   u.get("id"),
                    "nickname":  u.get("nickname"),
                    "avatar_url":u.get("avatarLarger") or u.get("avatarMedium") or "",
                    "signature": u.get("signature", ""),
                    "follower_count": int(st.get("followerCount") or 0),
                    "video_count":    int(st.get("videoCount") or 0),
                })

            # Stop if hasMore is false, the cursor didn't change, or we got
            # nothing new this page (TikTok bug where it repeats the last set).
            new_cursor = str(data.get("minCursor", "0"))
            if not data.get("hasMore"):
                break
            if page_added == 0:
                logger.debug("following pagination: page %d had no new IDs, stopping", page)
                break
            if new_cursor == last_cursor:
                logger.debug("following pagination: cursor stuck at %s, stopping", new_cursor)
                break
            last_cursor = min_cursor
            min_cursor = new_cursor
            _sleep_jitter(1.5, 1.0)

        return out

    # ----- liked videos (your own) -----

    def get_liked_videos(self, sec_uid: Optional[str] = None,
                         max_pages: int = 10) -> list[dict]:
        """List liked videos. Only works for the logged-in user's own
        likes if they're public. We pass our own sec_uid by default."""
        sec_uid = sec_uid or self.sec_uid
        url = "https://www.tiktok.com/api/favorite/item_list/"
        out = []
        seen_vids: set[str] = set()
        cursor = "0"
        last_cursor = None
        for page in range(max_pages):
            params = {
                "aid": "1988",
                "app_language": "en",
                "app_name": "tiktok_web",
                "browser_language": "en-US",
                "browser_name": "Mozilla",
                "browser_online": "true",
                "browser_platform": "Win32",
                "browser_version": "5.0",
                "channel": "tiktok_web",
                "cookie_enabled": "true",
                "count": "30",
                "coverFormat": "2",
                "cursor": cursor,
                "device_id": "0",
                "device_platform": "web_pc",
                "focus_state": "true",
                "from_page": "user",
                "history_len": "1",
                "is_fullscreen": "false",
                "is_page_visible": "true",
                "language": "en",
                "os": "windows",
                "priority_region": "",
                "referer": "",
                "region": "US",
                "screen_height": "1080",
                "screen_width": "1920",
                "secUid": sec_uid,
                "tz_name": "America/Los_Angeles",
                "user_is_login": "true",
                "webcast_language": "en",
            }
            try:
                r = _get(url, cookies=self.cookies, params=params)
            except Exception as exc:
                logger.warning("liked list req failed: %s", exc)
                break
            if r.status_code != 200:
                break
            try:
                data = r.json()
            except Exception:
                break

            page_added = 0
            for vid in data.get("itemList", []):
                vid_id = str(vid.get("id", ""))
                if not vid_id or vid_id in seen_vids:
                    continue
                seen_vids.add(vid_id)
                page_added += 1
                a = vid.get("author", {})
                s = vid.get("stats", {}) or {}
                v = vid.get("video", {}) or {}
                out.append({
                    "video_id":      vid_id,
                    "author_unique": a.get("uniqueId"),
                    "author_id":     str(a.get("id", "")),
                    "nickname":      a.get("nickname"),
                    "caption":       vid.get("desc", "") or "",
                    "create_time":   int(vid.get("createTime", 0)),
                    "play_count":    int(s.get("playCount") or 0),
                    "like_count":    int(s.get("diggCount") or 0),
                    "comment_count": int(s.get("commentCount") or 0),
                    "share_count":   int(s.get("shareCount") or 0),
                    "duration":      int(v.get("duration", 0) or 0),
                    "video_url":     f"https://www.tiktok.com/@{a.get('uniqueId','')}/video/{vid.get('id')}",
                    "cover_url":     v.get("cover", ""),
                })

            new_cursor = str(data.get("cursor", "0"))
            if not data.get("hasMore"):
                break
            if page_added == 0 or new_cursor == last_cursor:
                break
            last_cursor = cursor
            cursor = new_cursor
            _sleep_jitter(1.5, 1.0)

        return out

    # ----- user's posted videos -----

    def get_user_videos(self, sec_uid: str, max_pages: int = 5) -> list[dict]:
        """List a user's posted videos."""
        url = "https://www.tiktok.com/api/post/item_list/"
        out = []
        seen_vids: set[str] = set()
        cursor = "0"
        last_cursor = None
        for page in range(max_pages):
            params = {
                "aid": "1988",
                "app_language": "en",
                "app_name": "tiktok_web",
                "channel": "tiktok_web",
                "count": "35",
                "cookie_enabled": "true",
                "coverFormat": "2",
                "cursor": cursor,
                "device_id": "0",
                "device_platform": "web_pc",
                "from_page": "user",
                "history_len": "1",
                "is_fullscreen": "false",
                "is_page_visible": "true",
                "language": "en",
                "os": "windows",
                "priority_region": "",
                "referer": "",
                "region": "US",
                "screen_height": "1080",
                "screen_width": "1920",
                "secUid": sec_uid,
                "tz_name": "America/Los_Angeles",
                "user_is_login": "true",
                "webcast_language": "en",
            }
            try:
                r = _get(url, cookies=self.cookies, params=params)
            except Exception as exc:
                logger.warning("user videos req failed: %s", exc)
                break
            if r.status_code != 200:
                break
            try:
                data = r.json()
            except Exception:
                break
            page_added = 0
            for vid in data.get("itemList", []):
                vid_id = str(vid.get("id", ""))
                if not vid_id or vid_id in seen_vids:
                    continue
                seen_vids.add(vid_id)
                page_added += 1
                a = vid.get("author", {})
                s = vid.get("stats", {}) or {}
                v = vid.get("video", {}) or {}
                out.append({
                    "video_id":      vid_id,
                    "author_unique": a.get("uniqueId"),
                    "caption":       vid.get("desc", "") or "",
                    "create_time":   int(vid.get("createTime", 0)),
                    "play_count":    int(s.get("playCount") or 0),
                    "like_count":    int(s.get("diggCount") or 0),
                    "comment_count": int(s.get("commentCount") or 0),
                    "share_count":   int(s.get("shareCount") or 0),
                    "duration":      int(v.get("duration", 0) or 0),
                    "video_url":     f"https://www.tiktok.com/@{a.get('uniqueId','')}/video/{vid.get('id')}",
                    "cover_url":     v.get("cover", ""),
                })

            new_cursor = str(data.get("cursor", "0"))
            if not data.get("hasMore"):
                break
            if page_added == 0 or new_cursor == last_cursor:
                break
            last_cursor = cursor
            cursor = new_cursor
            _sleep_jitter(1.5, 1.0)

        return out
