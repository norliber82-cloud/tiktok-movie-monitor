"""Check what's actually in the Bitable videos table."""
import json
import requests
from . import bitable_client as bc
from . import config

url = (f"https://open.feishu.cn/open-apis/bitable/v1/apps/"
       f"{config.BITABLE_APP_TOKEN}/tables/{config.BITABLE_VIDEOS_TABLE}"
       f"/records?page_size=25")
r = requests.get(url, headers=bc._headers(), timeout=15).json()
items = r.get("data", {}).get("items", [])
total = r.get("data", {}).get("total", 0)
print(f"Total records in table: {total}")
print(f"Fetched: {len(items)}")
print()

# Check which records have Chinese fields vs English fields
cn_count = 0
en_count = 0
for rec in items:
    f = rec.get("fields", {})
    if "视频ID" in f or "作者" in f or "标题" in f:
        cn_count += 1
    elif "video_id" in f or "author" in f or "caption" in f:
        en_count += 1

print(f"Records with Chinese fields: {cn_count}")
print(f"Records with English fields: {en_count}")
print()

# Show last 3 records (most recent)
print("=== Last 3 records ===")
for rec in items[-3:]:
    f = rec.get("fields", {})
    print(f"\nrecord_id: {rec.get('record_id')}")
    for k, v in sorted(f.items()):
        val = str(v)[:100] if v else ""
        if val:
            print(f"  {k}: {val}")
