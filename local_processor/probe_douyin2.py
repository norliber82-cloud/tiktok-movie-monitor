"""Decode and inspect Douyin's RENDER_DATA blob."""
import requests
import re
import json
import urllib.parse

ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

url = "https://www.douyin.com/discover"
r = requests.get(url, headers={"User-Agent": ua}, timeout=15)

m = re.search(r'<script id="RENDER_DATA"[^>]*>(.+?)</script>', r.text, re.DOTALL)
raw = m.group(1)
decoded = urllib.parse.unquote(raw)
print(f"Decoded length: {len(decoded)}")

try:
    data = json.loads(decoded)
    print(f"Top-level keys: {list(data.keys())}")
    print()

    def walk(obj, path="", depth=0):
        if depth > 4:
            return
        if isinstance(obj, dict):
            for k, v in obj.items():
                kpath = f"{path}.{k}" if path else k
                if k in ("video_list", "aweme_list", "list", "items", "videos", "data"):
                    if isinstance(v, list) and v:
                        print(f"  {kpath}: list of {len(v)}, sample keys: {list(v[0].keys())[:10] if isinstance(v[0], dict) else 'non-dict'}")
                walk(v, kpath, depth + 1)
        elif isinstance(obj, list) and obj:
            walk(obj[0], f"{path}[0]", depth + 1)

    walk(data)

    # Save the parsed data for inspection
    with open("D:\\搬运\\_douyin_render.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("\nSaved to D:\\搬运\\_douyin_render.json")
except Exception as e:
    print(f"JSON parse error: {e}")
    print(f"First 500 chars: {decoded[:500]}")
