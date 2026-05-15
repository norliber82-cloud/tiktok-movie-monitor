"""Pull the most recent video URL from Bitable for the smoke test."""

import json
from . import bitable_client as bc

records = bc.list_videos()
records = [r for r in records if r.get("发布时间")]
records.sort(key=lambda r: r.get("发布时间", 0), reverse=True)
if not records:
    print("NO RECORDS")
else:
    latest = records[0]
    url = latest.get("视频链接")
    if isinstance(url, dict):
        url = url.get("link")
    print(url)
