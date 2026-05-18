"""See what's actually in the creators table."""
import json
import requests
from . import bitable_client as bc
from . import config

API = "https://open.feishu.cn/open-apis"

url = (f"{API}/bitable/v1/apps/{config.BITABLE_APP_TOKEN}"
       f"/tables/{config.BITABLE_CREATORS_TABLE}/records?page_size=50")
r = requests.get(url, headers=bc._headers(), timeout=15).json()
print(f"code={r.get('code')} total={r.get('data',{}).get('total')}")
items = r.get("data", {}).get("items", [])
print(f"fetched: {len(items)}")
for i, rec in enumerate(items, 1):
    f = rec.get("fields", {})
    keys = sorted(f.keys())
    name = f.get("用户名") or f.get("author_unique") or "?"
    print(f"  {i:2d}. record={rec['record_id']}  user={name}  fields={keys[:5]}")
