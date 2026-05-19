"""Probe Douyin discover page for usable structured data."""
import requests
import re
import json

ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

url = "https://www.douyin.com/discover"
r = requests.get(url, headers={"User-Agent": ua}, timeout=15)
print(f"status: {r.status_code}, length: {len(r.text)}")

# Look for the rehydrate JSON
patterns = [
    (r'<script id="RENDER_DATA"[^>]*>(.+?)</script>', 'RENDER_DATA'),
    (r'<script[^>]*id="ROUTER_DATA"[^>]*>(.+?)</script>', 'ROUTER_DATA'),
    (r'self\.__pace_f\.push\(\[\d+,(.+?)\]\)', '__pace_f'),
    (r'window\.__INITIAL_STATE__\s*=\s*({.+?})\s*;', 'INITIAL_STATE'),
]

for pat, name in patterns:
    matches = re.findall(pat, r.text, re.DOTALL)
    print(f"\n{name}: {len(matches)} matches")
    if matches:
        # Print first 200 chars of first match
        sample = matches[0][:300]
        print(f"  sample: {sample[:200]}")

# Look for aweme/video JSON occurrences
print(f"\naweme_list count: {r.text.count('aweme_list')}")
print(f"awemeList count: {r.text.count('awemeList')}")
print(f"play_count count: {r.text.count('play_count')}")
print(f"digg_count count: {r.text.count('digg_count')}")

# Try to find a structured JSON blob
import re
# Look for big JSON structures embedded
big_json_re = re.compile(r'\{"aweme_list":\[.+?\]\}', re.DOTALL)
m = big_json_re.search(r.text)
if m:
    print(f"\nFound aweme_list JSON, length={len(m.group(0))}")
    print(f"Preview: {m.group(0)[:500]}")
