"""Spike test: can we reach a logged-in-only TikTok endpoint with the cookie?

We try multiple known endpoints. Anything that returns real JSON data with
authenticated content (not "login required") proves the cookies work.
"""

import json
import re
import sys
import urllib.parse

import requests


def cookies_to_dict(path):
    with open(path, encoding="utf-8") as f:
        return {c["name"]: c["value"] for c in json.load(f)}


def headers_for_tiktok(referer="https://www.tiktok.com/"):
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/131.0.0.0 Safari/537.36",
        "Referer": referer,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
    }


def find_self_secuid(cookies):
    """Hit /foryou and parse out our own secUid from rehydrate data.
    With the secUid we can call user-detail / user-following / etc."""
    r = requests.get(
        "https://www.tiktok.com/foryou",
        headers=headers_for_tiktok(),
        cookies=cookies,
        timeout=15,
    )
    # Find the user object in the rehydrate JSON
    m = re.search(
        r'__UNIVERSAL_DATA_FOR_REHYDRATION__[^>]*>([^<]+)</script',
        r.text,
    )
    if not m:
        return None, None, None
    try:
        data = json.loads(m.group(1))
    except Exception:
        return None, None, None
    scope = data.get("__DEFAULT_SCOPE__", {})
    user = scope.get("webapp.app-context", {}).get("user", {}) or {}
    if not user.get("uniqueId"):
        # Try another path
        for v in scope.values():
            if isinstance(v, dict) and "userInfo" in v:
                ui = v.get("userInfo", {}).get("user", {})
                if ui.get("uniqueId"):
                    return ui.get("uniqueId"), ui.get("secUid"), ui.get("nickname")
    return user.get("uniqueId"), user.get("secUid"), user.get("nickname")


def try_user_detail(cookies, sec_uid, unique_id):
    """Read your own profile via user-detail HTML scrape (no signing needed)."""
    url = f"https://www.tiktok.com/@{unique_id}"
    r = requests.get(url, headers=headers_for_tiktok(), cookies=cookies, timeout=15)
    m = re.search(
        r'__UNIVERSAL_DATA_FOR_REHYDRATION__[^>]*>([^<]+)</script',
        r.text,
    )
    if not m:
        return None
    data = json.loads(m.group(1))
    detail = (data.get("__DEFAULT_SCOPE__", {})
                  .get("webapp.user-detail", {}))
    user = detail.get("userInfo", {}).get("user", {})
    stats = detail.get("userInfo", {}).get("stats", {})
    return {
        "unique_id":      user.get("uniqueId"),
        "nickname":       user.get("nickname"),
        "follower":       stats.get("followerCount"),
        "following":      stats.get("followingCount"),
        "video":          stats.get("videoCount"),
    }


def try_following_list(cookies, sec_uid):
    """The /api/user/follow/list endpoint — requires logged-in cookies."""
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
        "minCursor": "0",
        "maxCursor": "0",
        "os": "windows",
        "priority_region": "",
        "referer": "",
        "region": "US",
        "screen_height": "1080",
        "screen_width": "1920",
        "scene": "67",
        "secUid": sec_uid,
        "tz_name": "America/Los_Angeles",
        "user_is_login": "true",
        "webcast_language": "en",
    }
    url = "https://www.tiktok.com/api/user/list/"
    h = headers_for_tiktok(referer=f"https://www.tiktok.com/@something")
    r = requests.get(url, headers=h, cookies=cookies, params=params, timeout=15)
    return r.status_code, r.text[:500]


def test_account(label, path):
    print(f"\n{'='*60}\n=== {label}: {path}\n{'='*60}")
    cookies = cookies_to_dict(path)
    print(f"  cookies: {len(cookies)} keys")

    # Step 1: discover self
    unique_id, sec_uid, nickname = find_self_secuid(cookies)
    if not unique_id:
        print("  [FAIL] Could not detect logged-in user from rehydrate data")
        # Fallback: dump login state from foryou
        return
    print(f"  [OK]   logged in as @{unique_id} ({nickname}) sec_uid={sec_uid[:30]}...")

    # Step 2: own profile stats
    detail = try_user_detail(cookies, sec_uid, unique_id)
    if detail:
        print(f"  [OK]   own profile: {detail['follower']} followers, "
              f"{detail['following']} following, {detail['video']} videos")

    # Step 3: try the list API (the litmus test for cookies-can-do-account-actions)
    code, body = try_following_list(cookies, sec_uid)
    print(f"  [tested user/list/] HTTP {code}")
    if "userList" in body or '"user"' in body[:300]:
        print("  [OK]   following list endpoint returned data")
    elif "login" in body.lower():
        print("  [FAIL] endpoint says login required")
    else:
        print(f"         body[:200]: {body[:200]}")


if __name__ == "__main__":
    test_account("US",    r"D:\搬运\.cookies\us.json")
    test_account("JP/EU", r"D:\搬运\.cookies\jp.json")
