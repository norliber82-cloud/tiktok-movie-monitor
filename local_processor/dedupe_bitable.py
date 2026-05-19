"""Dedupe Bitable records.

For videos: keep one record per 视频ID (the earliest record_id), delete the rest.
For creators: same logic, keep one per 用户名.
Also removes records with no fields at all (empty stubs).
"""

import time
from collections import defaultdict
import requests
from . import bitable_client as bc
from . import config

API = "https://open.feishu.cn/open-apis"


def fetch_all(table_id):
    url = f"{API}/bitable/v1/apps/{config.BITABLE_APP_TOKEN}/tables/{table_id}/records"
    out = []
    page_token = None
    for _ in range(50):
        params = {"page_size": 500}
        if page_token: params["page_token"] = page_token
        r = requests.get(url, headers=bc._headers(), params=params, timeout=30).json()
        if r.get("code") != 0: break
        d = r.get("data", {})
        out.extend(d.get("items", []))
        page_token = d.get("page_token")
        if not d.get("has_more"): break
    return out


def batch_delete(table_id, ids):
    if not ids: return 0
    url = (f"{API}/bitable/v1/apps/{config.BITABLE_APP_TOKEN}"
           f"/tables/{table_id}/records/batch_delete")
    deleted = 0
    for i in range(0, len(ids), 500):
        chunk = ids[i:i+500]
        r = requests.post(url, headers=bc._headers(),
                          json={"records": chunk}, timeout=20).json()
        if r.get("code") == 0:
            deleted += len(chunk)
        else:
            print(f"  delete batch failed: {r}")
        time.sleep(0.3)
    return deleted


def dedupe_videos():
    print("\n=== Dedupe VIDEOS ===")
    records = fetch_all(config.BITABLE_VIDEOS_TABLE)
    print(f"Fetched: {len(records)}")

    # Group by 视频ID
    by_vid = defaultdict(list)
    empty_ids = []
    for rec in records:
        f = rec.get("fields", {})
        if not f:
            empty_ids.append(rec["record_id"])
            continue
        vid = f.get("视频ID")
        if not vid:
            empty_ids.append(rec["record_id"])
            continue
        by_vid[vid].append(rec["record_id"])

    # For each vid, keep the first record_id, delete the rest
    to_delete = list(empty_ids)
    for vid, rids in by_vid.items():
        if len(rids) > 1:
            # keep rids[0], delete rids[1:]
            to_delete.extend(rids[1:])

    print(f"  Empty records to remove: {len(empty_ids)}")
    print(f"  Duplicate records to remove: {len(to_delete) - len(empty_ids)}")
    print(f"  Total to delete: {len(to_delete)}")

    deleted = batch_delete(config.BITABLE_VIDEOS_TABLE, to_delete)
    print(f"  Deleted: {deleted}")
    print(f"  Remaining: {len(records) - deleted}")


def dedupe_creators():
    print("\n=== Dedupe CREATORS ===")
    records = fetch_all(config.BITABLE_CREATORS_TABLE)
    print(f"Fetched: {len(records)}")

    by_user = defaultdict(list)
    empty_ids = []
    for rec in records:
        f = rec.get("fields", {})
        if not f:
            empty_ids.append(rec["record_id"])
            continue
        u = f.get("用户名")
        if not u:
            empty_ids.append(rec["record_id"])
            continue
        by_user[u].append(rec["record_id"])

    to_delete = list(empty_ids)
    for u, rids in by_user.items():
        if len(rids) > 1:
            to_delete.extend(rids[1:])

    print(f"  Empty records to remove: {len(empty_ids)}")
    print(f"  Duplicate records to remove: {len(to_delete) - len(empty_ids)}")
    deleted = batch_delete(config.BITABLE_CREATORS_TABLE, to_delete)
    print(f"  Deleted: {deleted}")
    print(f"  Remaining: {len(records) - deleted}")


if __name__ == "__main__":
    dedupe_videos()
    dedupe_creators()
    print("\nDone.")
