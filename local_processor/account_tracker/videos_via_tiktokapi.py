"""Pull a user's recent posts via TikTokApi (uses MS_TOKEN to sign).

The cookie-based /api/post/item_list/ endpoint requires `_signature`
which we can't compute without running TikTok's JS. TikTokApi handles
that for us via Playwright, and it's already a project dependency.

This module exposes sync wrappers so the account_runner doesn't have
to be async.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Iterable

logger = logging.getLogger(__name__)


def _shape(vd: dict) -> dict:
    """Match the shape returned by tiktok_account.get_user_videos."""
    a = vd.get("author", {}) or {}
    s = vd.get("stats", {}) or {}
    v = vd.get("video", {}) or {}
    vid_id = str(vd.get("id", ""))
    uniq = a.get("uniqueId") or ""
    return {
        "video_id":      vid_id,
        "author_unique": uniq,
        "caption":       vd.get("desc", "") or "",
        "create_time":   int(vd.get("createTime", 0)),
        "play_count":    int(s.get("playCount") or 0),
        "like_count":    int(s.get("diggCount") or 0),
        "comment_count": int(s.get("commentCount") or 0),
        "share_count":   int(s.get("shareCount") or 0),
        "duration":      int(v.get("duration", 0) or 0),
        "video_url":     f"https://www.tiktok.com/@{uniq}/video/{vid_id}",
        "cover_url":     v.get("cover", "") or "",
    }


def _shape_following(user_data: dict) -> dict:
    """Shape a user dict from TikTokApi's user.info() into the same format
    as tiktok_account.get_following() returns."""
    u = user_data.get("user", {}) or user_data
    st = user_data.get("stats", {}) or {}
    return {
        "unique_id":      u.get("uniqueId") or "",
        "sec_uid":        u.get("secUid") or "",
        "user_id":        str(u.get("id") or ""),
        "nickname":       u.get("nickname") or "",
        "avatar_url":     u.get("avatarLarger") or u.get("avatarMedium") or "",
        "signature":      u.get("signature") or "",
        "follower_count": int(st.get("followerCount") or 0),
        "video_count":    int(st.get("videoCount") or 0),
    }


async def _fetch_one(api, username: str, count: int) -> list[dict]:
    out = []
    user = api.user(username=username)
    async for v in user.videos(count=count):
        try:
            out.append(_shape(v.as_dict))
        except Exception:
            continue
    return out


async def _fetch_many(usernames: Iterable[str], count: int,
                      ms_token: str) -> dict[str, list[dict]]:
    from TikTokApi import TikTokApi
    results: dict[str, list[dict]] = {}
    # Build proxy list for TikTokApi (Playwright ProxySettings format)
    # Note: if v2rayN TUN mode is active (global), Playwright will
    # automatically route through it without explicit proxy config.
    # Only set proxies if ALL_PROXY is explicitly configured AND
    # we're not already in TUN/global mode.
    proxies_list = None  # rely on system-level TUN/global proxy
    async with TikTokApi() as api:
        await api.create_sessions(
            ms_tokens=[ms_token],
            num_sessions=1,
            sleep_after=3,
            headless=False,
            browser="chromium",
            proxies=proxies_list,
        )
        for u in usernames:
            try:
                vids = await _fetch_one(api, u, count)
                results[u] = vids
                logger.info("  videos[@%s]: %d", u, len(vids))
            except Exception as exc:
                logger.warning("  videos[@%s] failed: %s", u, exc)
                results[u] = []
            # be polite
            await asyncio.sleep(2.0)
    return results


async def _fetch_following_via_api(username: str, ms_token: str,
                                   count: int = 500,
                                   cookie_path: str | None = None) -> list[dict]:
    """Pull a user's following list via Playwright browser context.

    TikTokApi 7.x doesn't expose a .following() method, so we drive
    Playwright directly: open the user's profile following tab, then
    intercept the /api/user/list/ XHR responses that fire when the
    browser scrolls.

    We inject the FULL cookie jar from the exported file so TikTok
    sees a fully-authenticated session (not just msToken).
    """
    import json as _json
    from playwright.async_api import async_playwright

    out: list[dict] = []
    seen_ids: set[str] = set()

    # Load full cookie jar if available
    browser_cookies = []
    if cookie_path:
        try:
            raw = _json.loads(open(cookie_path, encoding="utf-8").read())
            for c in raw:
                domain = c.get("domain", "")
                if "tiktok" not in domain:
                    continue
                bc = {
                    "name": c["name"],
                    "value": c["value"],
                    "domain": domain,
                    "path": c.get("path", "/"),
                }
                if c.get("expirationDate"):
                    bc["expires"] = int(c["expirationDate"])
                browser_cookies.append(bc)
        except Exception as exc:
            logger.warning("Could not load cookies from %s: %s", cookie_path, exc)

    async with async_playwright() as p:
        # Route through local SOCKS5 proxy to avoid IP-based blocks
        proxy_url = os.environ.get("ALL_PROXY", "socks5://127.0.0.1:10808")
        launch_opts = {"headless": False}
        if proxy_url:
            launch_opts["proxy"] = {"server": proxy_url}
        browser = await p.chromium.launch(**launch_opts)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        )
        # Inject full cookie jar
        if browser_cookies:
            await context.add_cookies(browser_cookies)
        else:
            # Fallback: just msToken
            await context.add_cookies([{
                "name": "msToken",
                "value": ms_token,
                "domain": ".tiktok.com",
                "path": "/",
            }])

        page = await context.new_page()

        # Capture XHR responses from the following-list endpoint
        async def _on_response(response):
            if "/api/user/list/" not in response.url:
                return
            try:
                data = await response.json()
                for entry in data.get("userList", []):
                    u = entry.get("user", {})
                    uid = u.get("uniqueId")
                    if not uid or uid in seen_ids:
                        continue
                    seen_ids.add(uid)
                    st = entry.get("stats", {}) or {}
                    out.append({
                        "unique_id":      uid,
                        "sec_uid":        u.get("secUid") or "",
                        "user_id":        str(u.get("id") or ""),
                        "nickname":       u.get("nickname") or "",
                        "avatar_url":     u.get("avatarLarger") or "",
                        "signature":      u.get("signature") or "",
                        "follower_count": int(st.get("followerCount") or 0),
                        "video_count":    int(st.get("videoCount") or 0),
                    })
            except Exception:
                pass

        page.on("response", _on_response)

        # Navigate to the user's following tab
        url = f"https://www.tiktok.com/@{username}/following"
        try:
            await page.goto(url, wait_until="networkidle", timeout=60000)
        except Exception:
            # Even if timeout fires, we may have captured some data
            pass

        # Scroll down to trigger more pages
        for _ in range(20):
            if len(out) >= count:
                break
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(2.0)

        await browser.close()

    logger.info("Playwright following(@%s): captured %d users", username, len(out))
    return out


def fetch_user_videos_batch(usernames: list[str], *, count: int = 30,
                            ms_token: str | None = None
                            ) -> dict[str, list[dict]]:
    """Synchronous wrapper. Returns {username: [video_dict, ...]}.

    Pass `ms_token` explicitly to use a region-specific token (so US runs
    use the US-cookie token and JP runs use the JP-cookie one).
    Falls back to env MS_TOKEN.
    """
    ms_token = ms_token or os.getenv("MS_TOKEN", "").strip()
    if not ms_token:
        raise RuntimeError(
            "MS_TOKEN not set in env — cannot pull user posts via TikTokApi")
    if not usernames:
        return {}
    logger.info("TikTokApi pulling videos for %d users (count=%d)…",
                len(usernames), count)
    return asyncio.run(_fetch_many(usernames, count, ms_token))


def fetch_following_list(username: str, *, ms_token: str | None = None,
                         count: int = 500,
                         cookie_path: str | None = None) -> list[dict]:
    """Synchronous wrapper to pull a user's following list via Playwright.
    Returns list of user dicts in the same shape as Account.get_following()."""
    ms_token = ms_token or os.getenv("MS_TOKEN", "").strip()
    if not ms_token:
        raise RuntimeError(
            "MS_TOKEN not set — cannot pull following via Playwright")
    logger.info("Playwright pulling following for @%s (count=%d)…",
                username, count)
    return asyncio.run(_fetch_following_via_api(username, ms_token, count,
                                               cookie_path=cookie_path))
