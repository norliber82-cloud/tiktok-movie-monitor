"""Print current field order of both tables."""
import requests
from . import bitable_client as bc
from . import config

API = "https://open.feishu.cn/open-apis"

def show(table_id, label):
    url = f"{API}/bitable/v1/apps/{config.BITABLE_APP_TOKEN}/tables/{table_id}/fields"
    r = requests.get(url, headers=bc._headers(), params={"page_size": 100}, timeout=15).json()
    print(f"\n=== {label} ({table_id}) ===")
    for i, f in enumerate(r.get("data",{}).get("items",[]), 1):
        print(f"  {i:2d}. {f['field_name']:20s}  type={f.get('type')}  id={f['field_id']}")

show(config.BITABLE_VIDEOS_TABLE,   "videos")
show(config.BITABLE_CREATORS_TABLE, "creators")
