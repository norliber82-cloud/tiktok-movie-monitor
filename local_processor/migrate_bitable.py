"""One-time migration: copy English-field records into Chinese fields,
then delete the old English columns.

Usage: python -m local_processor.migrate_bitable
"""

import json
import time
import requests
from . import bitable_client as bc
from . import config

API_BASE = "https://open.feishu.cn/open-apis"

# English → Chinese field mapping
EN_TO_ZH = {
    "video_id":      "视频ID",
    "platform":      "平台",
    "tier":          "等级",
    "language":      "语言",
    "author":        "作者",
    "caption":       "标题",
    "play_count":    "播放量",
    "like_count":    "点赞数",
    "comment_count": "评论数",
    "share_count":   "分享数",
    "duration":      "时长(秒)",
    "matched_tag":   "匹配标签",
    "hashtags":      "标签",
    "create_time":   "发布时间",
    "first_seen_at": "入库时间",
    "video_url":     "视频链接",
    "cover_url":     "封面链接",
}

# Fields that are numbers (need int conversion)
NUMBER_FIELDS = {"播放量", "点赞数", "评论数", "分享数", "时长(秒)", "发布时间", "入库时间"}


def fetch_all_records(table_id):
    url = f"{API_BASE}/bitable/v1/apps/{config.BITABLE_APP_TOKEN}/tables/{table_id}/records"
    records = []
    page_token = None
    for _ in range(50):
        params = {"page_size": 500}
        if page_token:
            params["page_token"] = page_token
        r = requests.get(url, headers=bc._headers(), params=params, timeout=30).json()
        if r.get("code") != 0:
            print(f"ERROR fetching: {r}")
            break
        data = r.get("data", {})
        records.extend(data.get("items", []))
        page_token = data.get("page_token")
        if not data.get("has_more"):
            break
    return records


def update_record(table_id, record_id, fields):
    url = (f"{API_BASE}/bitable/v1/apps/{config.BITABLE_APP_TOKEN}"
           f"/tables/{table_id}/records/{record_id}")
    r = requests.put(url, headers=bc._headers(),
                     json={"fields": fields}, timeout=15).json()
    return r.get("code") == 0


def delete_field(table_id, field_id):
    url = (f"{API_BASE}/bitable/v1/apps/{config.BITABLE_APP_TOKEN}"
           f"/tables/{table_id}/fields/{field_id}")
    r = requests.delete(url, headers=bc._headers(), timeout=15).json()
    return r.get("code") == 0


def get_fields_with_ids(table_id):
    url = f"{API_BASE}/bitable/v1/apps/{config.BITABLE_APP_TOKEN}/tables/{table_id}/fields"
    r = requests.get(url, headers=bc._headers(),
                     params={"page_size": 100}, timeout=15).json()
    if r.get("code") != 0:
        return {}
    return {f["field_name"]: f["field_id"] for f in r.get("data", {}).get("items", [])}


def convert_value(zh_key, value):
    """Convert English-field value to the format expected by Chinese field."""
    if value is None:
        return None
    # Number fields: ensure int
    if zh_key in NUMBER_FIELDS:
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                try:
                    return int(float(value))
                except ValueError:
                    return None
        return int(value) if value else None
    # Link fields
    if zh_key in ("视频链接", "封面链接"):
        if isinstance(value, dict):
            return value  # already correct format
        if isinstance(value, str) and value.startswith("http"):
            return {"link": value, "text": "打开" if zh_key == "视频链接" else "封面"}
        return None
    # Text/select: just pass through
    return value


def main():
    table_id = config.BITABLE_VIDEOS_TABLE
    print("Step 1: Fetching all records...")
    records = fetch_all_records(table_id)
    print(f"  Total records: {len(records)}")

    # Identify records that have English fields but missing Chinese fields
    migrated = 0
    for rec in records:
        fields = rec.get("fields", {})
        record_id = rec.get("record_id")

        # Check if this record has English fields
        has_english = any(k in fields for k in EN_TO_ZH.keys())
        # Check if Chinese fields are already populated
        has_chinese = any(k in fields for k in EN_TO_ZH.values() if fields.get(k))

        if has_english and not has_chinese:
            # Build Chinese field update
            update = {}
            for en_key, zh_key in EN_TO_ZH.items():
                val = fields.get(en_key)
                if val is not None:
                    converted = convert_value(zh_key, val)
                    if converted is not None:
                        update[zh_key] = converted

            if update:
                ok = update_record(table_id, record_id, update)
                status = "OK" if ok else "FAIL"
                print(f"  [{status}] {record_id}: migrated {len(update)} fields")
                migrated += 1
                time.sleep(0.3)  # rate limit

    print(f"\nStep 2: Migrated {migrated} records from English to Chinese fields.")

    # Step 3: Delete English columns
    print("\nStep 3: Deleting old English columns...")
    field_map = get_fields_with_ids(table_id)
    deleted = 0
    # Also delete the default "文本" field that Feishu auto-creates
    en_fields_to_delete = list(EN_TO_ZH.keys()) + ["文本"]
    for en_name in en_fields_to_delete:
        if en_name in field_map:
            ok = delete_field(table_id, field_map[en_name])
            status = "OK" if ok else "FAIL"
            print(f"  [{status}] deleted column: {en_name}")
            deleted += 1
            time.sleep(0.3)
        else:
            print(f"  [skip] {en_name} not found")

    print(f"\n  Deleted {deleted} English columns.")

    # Step 4: Delete duplicate/empty records (records with no data at all)
    print("\nStep 4: Cleaning empty records...")
    records_after = fetch_all_records(table_id)
    empty_ids = []
    for rec in records_after:
        fields = rec.get("fields", {})
        # If after migration the record still has no meaningful data
        if not any(v for v in fields.values() if v):
            empty_ids.append(rec["record_id"])

    if empty_ids:
        url = (f"{API_BASE}/bitable/v1/apps/{config.BITABLE_APP_TOKEN}"
               f"/tables/{table_id}/records/batch_delete")
        for i in range(0, len(empty_ids), 500):
            chunk = empty_ids[i:i+500]
            r = requests.post(url, headers=bc._headers(),
                              json={"records": chunk}, timeout=20).json()
            print(f"  Deleted {len(chunk)} empty records: code={r.get('code')}")
    else:
        print("  No empty records found.")

    print("\nDone! Your table should now have only Chinese columns with all data merged.")


if __name__ == "__main__":
    main()
