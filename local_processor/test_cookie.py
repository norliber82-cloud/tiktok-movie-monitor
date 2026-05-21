"""Test if the cookie files can authenticate against TikTok's account API."""

import json
import sys
import requests


def cookies_to_dict(cookie_json_path):
    with open(cookie_json_path, "r", encoding="utf-8") as f:
        items = json.load(f)
    return {c["name"]: c["value"] for c in items}


def test_account(label, cookie_path):
    print(f"\n=== {label} ({cookie_path}) ===")
    try:
        cookies = cookies_to_dict(cookie_path)
    except Exception as exc:
        print(f"  load fail: {exc}")
        return

    print(f"  cookies loaded: {len(cookies)} keys")

    # Sanity check: check the auth-critical cookies are present
    needed = ["sessionid", "sid_tt", "uid_tt", "tt_csrf_token", "msToken"]
    missing = [k for k in needed if k not in cookies]
    if missing:
        print(f"  MISSING cookies: {missing}")
        return
    print(f"  all 5 critical cookies present")

    # Try the simplest authenticated endpoint: /passport/account/info
    # This works when cookies are valid and tells us the logged-in user.
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/131.0 Safari/537.36",
        "Referer": "https://www.tiktok.com/",
        "Accept": "application/json",
    }

    # Endpoint: webapp.user-detail HTML scrape — same approach as followers.py.
    # When logged in, the user's secUid lives in __DEFAULT_SCOPE__.app.userInfo.
    # We hit our own profile by /@self redirect doesn't work, so we try
    # /following list which only logged-in users can access.
    import re
    headers["Accept"] = "text/html,application/xhtml+xml"
    url = "https://www.tiktok.com/foryou"
    try:
        r = requests.get(url, headers=headers, cookies=cookies,
                         timeout=15, allow_redirects=True)
        print(f"  HTTP {r.status_code}, len={len(r.text)}")
        # Look for "isLogin" or "userInfo" in rehydrate data
        m = re.search(r'"uniqueId":"([^"]+)","secUid":"([^"]+)"',
                      r.text[:500000])
        if m:
            print(f"  detected unique_id from rehydrate: @{m.group(1)}")
        # Also check for "Sign up" text that indicates logged-out state
        if 'data-e2e="login-button"' in r.text or '/login' in r.url:
            print(f"  WARN: page redirected to login, cookies may be invalid")
        else:
            print(f"  page accessible (cookies seem valid)")
    except Exception as exc:
        print(f"  request failed: {exc}")


if __name__ == "__main__":
    test_account("US", r"D:\搬运\.cookies\us.json")
    test_account("JP/EU", r"D:\搬运\.cookies\jp.json")
