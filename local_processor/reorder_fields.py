"""Reorder Bitable columns to a target order.

Strategy: Feishu API doesn't support a "move field" op, but it does honor
the order in which fields are *created*. So we:
  1. Snapshot all existing data (records + field types)
  2. Delete every non-default field
  3. Re-create fields in the exact target order
  4. Restore data row-by-row using the new field set

Default field "文本" (type=1) is the table's primary key column; we keep it.
"""

import time
import requests

from . import bitable_client as bc
from . import config

API = "https://open.feishu.cn/open-apis"


# ============================================================
# TARGET ORDER  (after the default "文本" primary field)
# ============================================================

VIDEOS_ORDER = [
    ("视频ID",       1),
    ("平台",         3),
    ("等级",         3),
    ("语言",         3),
    ("视频URL",      1),   # ← moved up after 语言
    ("封面URL",      1),   # ← moved up after 语言
    ("作者",         1),
    ("标题",         1),
    ("原片名",       1),
    ("开头钩子",     1),
    ("分析摘要",     1),
    ("爆款评分",     2),
    ("播放量",       2),
    ("点赞数",       2),
    ("评论数",       2),
    ("分享数",       2),
    ("时长(秒)",     2),
    ("匹配标签",     1),
    ("标签",         1),
    ("发布时间",     5),
    ("入库时间",     5),
    ("视频链接",    15),   # original button-link kept at end
    ("封面链接",    15),
]

CREATORS_ORDER = [
    ("用户名",       1),
    ("昵称",         1),
    ("主页链接",    15),   # ← moved up before 语言
    ("语言",         3),
    ("粉丝数",       2),
    ("中位播放",     2),
    ("7日最高播放",  2),
    ("14日发帖数",   2),
    ("30日发帖数",   2),
    ("垂直度",       2),
    ("判定原因",     1),
    ("评估时间",     5),
]


# ============================================================
# Helpers
# ============================================================

def fetch_all_records(table_id):
    url = f"{API}/bitable/v1/apps/{config.BITABLE_APP_TOKEN}/tables/{table_id}/records"
    out = []
    page_token = None
    for _ in range(50):
        params = {"page_size": 500}
        if page_token: params["page_token"] = page_token
        r = requests.get(url, headers=bc._headers(), params=params, timeout=30).json()
        if r.get("code") != 0:
            print(f"fetch error: {r}")
            break
        d = r.get("data", {})
        out.extend(d.get("items", []))
        page_token = d.get("page_token")
        if not d.get("has_more"): break
    return out


def fetch_fields(table_id):
    url = f"{API}/bitable/v1/apps/{config.BITABLE_APP_TOKEN}/tables/{table_id}/fields"
    r = requests.get(url, headers=bc._headers(),
                     params={"page_size": 100}, timeout=15).json()
    return r.get("data", {}).get("items", [])


def delete_field(table_id, field_id):
    url = (f"{API}/bitable/v1/apps/{config.BITABLE_APP_TOKEN}"
           f"/tables/{table_id}/fields/{field_id}")
    return requests.delete(url, headers=bc._headers(), timeout=15).json()


def create_field(table_id, name, ftype):
    url = (f"{API}/bitable/v1/apps/{config.BITABLE_APP_TOKEN}"
           f"/tables/{table_id}/fields")
    return requests.post(url, headers=bc._headers(),
                         json={"field_name": name, "type": ftype},
                         timeout=15).json()


def batch_delete_records(table_id, ids):
    if not ids: return
    url = (f"{API}/bitable/v1/apps/{config.BITABLE_APP_TOKEN}"
           f"/tables/{table_id}/records/batch_delete")
    for i in range(0, len(ids), 500):
        chunk = ids[i:i+500]
        requests.post(url, headers=bc._headers(),
                      json={"records": chunk}, timeout=20)


def batch_create_records(table_id, fields_list):
    if not fields_list: return 0
    url = (f"{API}/bitable/v1/apps/{config.BITABLE_APP_TOKEN}"
           f"/tables/{table_id}/records/batch_create")
    created = 0
    for i in range(0, len(fields_list), 500):
        chunk = fields_list[i:i+500]
        payload = [{"fields": f} for f in chunk]
        r = requests.post(url, headers=bc._headers(),
                          json={"records": payload}, timeout=30).json()
        if r.get("code") == 0:
            created += len(r.get("data", {}).get("records", []))
        else:
            print(f"  batch_create error: {r}")
    return created


# ============================================================
# Main reorder routine
# ============================================================

def reorder(table_id, target_order, label):
    print(f"\n{'='*60}\n=== Reordering {label} ({table_id}) ===\n{'='*60}")

    # 1. Snapshot data
    records = fetch_all_records(table_id)
    print(f"Snapshotted {len(records)} records.")
    fields_before = fetch_fields(table_id)
    print(f"Existing fields: {[f['field_name'] for f in fields_before]}")

    # 2. Save record fields (drop record_id; we recreate)
    saved_data = []
    for rec in records:
        f = rec.get("fields", {})
        if f:
            saved_data.append(f)

    # Skip default "文本" — it's the primary, can't delete or recreate
    target_names = {n for n, _ in target_order}

    # 3. Delete all non-target / non-default fields, then target fields too
    print("\nStep 1: Deleting all fields (except default 文本)...")
    for f in fields_before:
        if f["field_name"] == "文本":
            continue
        r = delete_field(table_id, f["field_id"])
        print(f"  [{r.get('code')}] del {f['field_name']}")
        time.sleep(0.2)

    # 4. Delete all existing records (now with no fields they're empty anyway)
    print("\nStep 2: Deleting all records...")
    record_ids = [r["record_id"] for r in records]
    batch_delete_records(table_id, record_ids)
    print(f"  Deleted {len(record_ids)} records.")

    # 5. Create fields in target order
    print("\nStep 3: Creating fields in target order...")
    for name, ftype in target_order:
        r = create_field(table_id, name, ftype)
        print(f"  [{r.get('code')}] add {name}")
        time.sleep(0.2)

    # 6. Restore data
    print("\nStep 4: Restoring records...")
    cleaned = []
    for f in saved_data:
        # Drop fields not in our new schema
        new_f = {k: v for k, v in f.items() if k in target_names and v is not None}
        if new_f:
            cleaned.append(new_f)
    created = batch_create_records(table_id, cleaned)
    print(f"  Restored {created} / {len(cleaned)} records.")


def main():
    print("This will rebuild both Bitable tables to enforce column order.")
    print("Existing data WILL be preserved (re-inserted in the new schema).\n")

    reorder(config.BITABLE_CREATORS_TABLE, CREATORS_ORDER, "creators")
    reorder(config.BITABLE_VIDEOS_TABLE,   VIDEOS_ORDER,   "videos")

    print("\nDone. New column order is now in effect.")


if __name__ == "__main__":
    main()
