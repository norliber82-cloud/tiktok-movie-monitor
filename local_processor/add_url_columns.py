"""Add plain-text URL columns ('视频URL' and '封面URL') and backfill from
existing 视频链接 / 封面链接 (which are link objects, not copyable text).
"""

import time
import requests

from . import bitable_client as bc
from . import config

API_BASE = "https://open.feishu.cn/open-apis"


def fetch_all(table_id):
    url = f"{API_BASE}/bitable/v1/apps/{config.BITABLE_APP_TOKEN}/tables/{table_id}/records"
    out = []
    page_token = None
    for _ in range(50):
        params = {"page_size": 500}
        if page_token:
            params["page_token"] = page_token
        r = requests.get(url, headers=bc._headers(), params=params, timeout=30).json()
        if r.get("code") != 0:
            print(f"fetch error: {r}")
            break
        d = r.get("data", {})
        out.extend(d.get("items", []))
        page_token = d.get("page_token")
        if not d.get("has_more"):
            break
    return out


def get_field_id(table_id, name):
    url = f"{API_BASE}/bitable/v1/apps/{config.BITABLE_APP_TOKEN}/tables/{table_id}/fields"
    r = requests.get(url, headers=bc._headers(),
                     params={"page_size": 100}, timeout=15).json()
    for f in r.get("data", {}).get("items", []):
        if f["field_name"] == name:
            return f["field_id"]
    return None


def main():
    table_id = config.BITABLE_VIDEOS_TABLE

    # 1. Ensure plain-text columns exist
    print("Step 1: ensuring '视频URL' and '封面URL' text columns exist...")
    bc.ensure_field(table_id, "视频URL", bc.FIELD_TYPE["text"])
    bc.ensure_field(table_id, "封面URL", bc.FIELD_TYPE["text"])

    # 2. Backfill from existing link fields
    print("\nStep 2: backfilling from 视频链接 / 封面链接...")
    records = fetch_all(table_id)
    print(f"  records: {len(records)}")

    updated = 0
    for rec in records:
        f = rec.get("fields", {})
        rid = rec["record_id"]
        update = {}

        link_obj = f.get("视频链接")
        if isinstance(link_obj, dict) and link_obj.get("link") and not f.get("视频URL"):
            update["视频URL"] = link_obj["link"]

        cover_obj = f.get("封面链接")
        if isinstance(cover_obj, dict) and cover_obj.get("link") and not f.get("封面URL"):
            update["封面URL"] = cover_obj["link"]

        if update:
            url2 = (f"{API_BASE}/bitable/v1/apps/{config.BITABLE_APP_TOKEN}"
                    f"/tables/{table_id}/records/{rid}")
            r = requests.put(url2, headers=bc._headers(),
                             json={"fields": update}, timeout=15).json()
            ok = r.get("code") == 0
            print(f"  [{'OK' if ok else 'FAIL'}] {rid}: {list(update.keys())}")
            updated += 1
            time.sleep(0.25)

    print(f"\nDone. Backfilled {updated} records.")


if __name__ == "__main__":
    main()
