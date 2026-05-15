"""Clean up English columns from creators table."""
import requests
import time
from . import bitable_client as bc
from . import config

API_BASE = "https://open.feishu.cn/open-apis"
table_id = config.BITABLE_CREATORS_TABLE

# Get fields
url = f"{API_BASE}/bitable/v1/apps/{config.BITABLE_APP_TOKEN}/tables/{table_id}/fields"
r = requests.get(url, headers=bc._headers(), params={"page_size": 100}, timeout=15).json()
fields = {f["field_name"]: f["field_id"] for f in r.get("data", {}).get("items", [])}
print("Current fields:", list(fields.keys()))

# English fields to delete
en_fields = [
    "author_unique", "nickname", "language", "follower_count",
    "median_plays", "max_plays_7d", "posts_14d", "posts_30d",
    "vertical_ratio", "reason", "evaluated_at", "profile_url",
]

for name in en_fields:
    if name in fields:
        url2 = (f"{API_BASE}/bitable/v1/apps/{config.BITABLE_APP_TOKEN}"
                f"/tables/{table_id}/fields/{fields[name]}")
        r2 = requests.delete(url2, headers=bc._headers(), timeout=15).json()
        code = r2.get("code")
        print(f"  delete {name}: code={code}")
        time.sleep(0.3)

print("Done")
