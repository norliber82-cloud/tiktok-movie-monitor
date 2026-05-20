"""Diagnose JP table permissions."""
import requests
from . import bitable_client as bc
from . import config

API = "https://open.feishu.cn/open-apis"

# Hardcoded JP table IDs
JP_VIDEOS = "tblGCE433yHlyi19"
JP_CREATORS = "tbl0rNNay2uZb3zv"

print("Checking app permissions on each table...\n")

for label, table_id in [("OLD videos", config.BITABLE_VIDEOS_TABLE),
                         ("OLD creators", config.BITABLE_CREATORS_TABLE),
                         ("NEW jp_videos", JP_VIDEOS),
                         ("NEW jp_creators", JP_CREATORS)]:
    url = f"{API}/bitable/v1/apps/{config.BITABLE_APP_TOKEN}/tables/{table_id}/fields"
    r = requests.get(url, headers=bc._headers(), params={"page_size": 5}, timeout=15).json()
    code = r.get("code")
    if code == 0:
        n = len(r.get("data", {}).get("items", []))
        print(f"  [OK]  {label:18s} {table_id}  fields={n}")
    else:
        print(f"  [FAIL] {label:18s} {table_id}  code={code} msg={r.get('msg')}")
