"""One-time table setup: create all Chinese fields, clean empty records.

Usage: python -m local_processor.setup_table
"""
import json
import requests

from . import bitable_client as bc
from . import config

VIDEOS_FIELDS = [
    ("视频ID",       1),  ("平台",       3),  ("等级",     3),
    ("语言",         3),  ("作者",       1),  ("标题",     1),
    ("播放量",       2),  ("点赞数",     2),  ("评论数",   2),
    ("分享数",       2),  ("时长(秒)",   2),  ("匹配标签", 1),
    ("标签",         1),  ("发布时间",   5),  ("入库时间", 5),
    ("视频链接",    15),  ("封面链接",  15),
    # Local processor adds:
    ("原片名",       1),  ("分析摘要",   1),
    ("开头钩子",     1),  ("爆款评分",   2),
]

CREATORS_FIELDS = [
    ("用户名",       1),  ("昵称",       1),  ("语言",       3),
    ("粉丝数",       2),  ("中位播放",   2),  ("7日最高播放", 2),
    ("14日发帖数",   2),  ("30日发帖数", 2),  ("垂直度",     2),
    ("判定原因",     1),  ("评估时间",   5),  ("主页链接",  15),
]

def ensure_table_fields(table_id: str, schema):
    print(f"\n=== Table {table_id} ===")
    existing = bc.list_field_names(table_id)
    print(f"existing fields: {sorted(existing)}")
    for name, ftype in schema:
        if name in existing:
            print(f"  [skip] {name}")
            continue
        ok = bc.ensure_field(table_id, name, ftype)
        print(f"  [add ] {name}  ->  {'OK' if ok else 'FAIL'}")


def list_empty_records(table_id: str) -> list[str]:
    url = (f"https://open.feishu.cn/open-apis/bitable/v1/apps/"
           f"{config.BITABLE_APP_TOKEN}/tables/{table_id}/records")
    empty = []
    page_token = None
    for _ in range(40):
        params = {"page_size": 500}
        if page_token: params["page_token"] = page_token
        r = requests.get(url, headers=bc._headers(), params=params, timeout=30).json()
        if r.get("code") != 0: break
        for rec in r["data"].get("items", []):
            if not rec.get("fields"):
                empty.append(rec["record_id"])
        page_token = r["data"].get("page_token")
        if not r["data"].get("has_more"): break
    return empty


def delete_records(table_id: str, ids: list[str]):
    if not ids:
        return
    url = (f"https://open.feishu.cn/open-apis/bitable/v1/apps/"
           f"{config.BITABLE_APP_TOKEN}/tables/{table_id}/records/batch_delete")
    # Max 500 per batch
    for i in range(0, len(ids), 500):
        chunk = ids[i:i+500]
        r = requests.post(url, headers=bc._headers(),
                          json={"records": chunk}, timeout=20).json()
        print(f"  deleted batch of {len(chunk)}: code={r.get('code')}")


def main():
    print("Step 1: ensuring Chinese fields exist")
    ensure_table_fields(config.BITABLE_VIDEOS_TABLE,   VIDEOS_FIELDS)
    ensure_table_fields(config.BITABLE_CREATORS_TABLE, CREATORS_FIELDS)

    print("\nStep 2: cleaning empty records")
    empty_videos = list_empty_records(config.BITABLE_VIDEOS_TABLE)
    print(f"  videos table empty records: {len(empty_videos)}")
    delete_records(config.BITABLE_VIDEOS_TABLE, empty_videos)

    empty_creators = list_empty_records(config.BITABLE_CREATORS_TABLE)
    print(f"  creators table empty records: {len(empty_creators)}")
    delete_records(config.BITABLE_CREATORS_TABLE, empty_creators)

    print("\nDone.")

if __name__ == "__main__":
    main()
