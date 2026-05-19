"""Inspect Bitable for duplicate records by 视频ID."""
from collections import Counter, defaultdict
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

# Videos table
records = fetch_all(config.BITABLE_VIDEOS_TABLE)
print(f"\n=== VIDEOS TABLE ({len(records)} records) ===\n")

video_id_count = Counter()
record_id_by_vid = defaultdict(list)
for rec in records:
    f = rec.get("fields", {})
    vid = f.get("视频ID")
    if vid:
        video_id_count[vid] += 1
        record_id_by_vid[vid].append(rec["record_id"])

dups = {k: v for k, v in video_id_count.items() if v > 1}
print(f"Unique 视频ID: {len(video_id_count)}")
print(f"Duplicates: {len(dups)} 视频ID appear more than once")
print()

if dups:
    print("Top 10 duplicates:")
    for vid, cnt in sorted(dups.items(), key=lambda x: -x[1])[:10]:
        print(f"  {vid}  → {cnt} copies, record_ids: {record_id_by_vid[vid]}")

# How many empty records?
empty_count = sum(1 for r in records if not r.get("fields"))
print(f"\nEmpty records (no fields at all): {empty_count}")

# Records missing 视频ID?
no_vid_count = sum(1 for r in records if r.get("fields") and not r["fields"].get("视频ID"))
print(f"Records with fields but no 视频ID: {no_vid_count}")

# Check creators
print()
print(f"\n=== CREATORS TABLE ===\n")
creators = fetch_all(config.BITABLE_CREATORS_TABLE)
print(f"Total: {len(creators)}")
user_count = Counter()
for rec in creators:
    u = rec.get("fields", {}).get("用户名")
    if u: user_count[u] += 1
cdups = {k: v for k, v in user_count.items() if v > 1}
print(f"Unique 用户名: {len(user_count)}")
print(f"Duplicates: {len(cdups)}")
if cdups:
    print("Top 10 duplicates:")
    for u, cnt in sorted(cdups.items(), key=lambda x: -x[1])[:10]:
        print(f"  @{u}  → {cnt} copies")
