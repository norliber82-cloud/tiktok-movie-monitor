#!/usr/bin/env python3
"""Export all 4 Bitable tables into dashboard JSON files."""

from __future__ import annotations
import json, os, pathlib, time
import requests

API_BASE = "https://open.feishu.cn/open-apis"
OUT_DIR = pathlib.Path("dashboard")

TABLES = {
    "us_videos":   "tblrY6LqfrQsc1qv",
    "us_creators": "tbl7L9IRcsfPAk1k",
    "jp_videos":   "tblGCE433yHlyi19",
    "jp_creators": "tbl0rNNay2uZb3zv",
}

REGION_MAP = {"us": "en", "jp": "ja"}

# Field name mapping: 飞书中文 → dashboard JS expects
VIDEO_FIELD_MAP = {
    "视频URL": "video_url",
    "封面URL": "cover_url",
    "等级": "tier",
    "平台": "platform",
    "语言": "language",
    "作者": "author",
    "标题": "caption",
    "播放量": "play_count",
    "点赞数": "like_count",
    "评论数": "comment_count",
    "分享数": "share_count",
    "发布时间": "create_time",
    "时长(秒)": "duration",
    "标签": "tags",
    "匹配标签": "matched_tag",
    "原片名": "film_title",
    "可信度": "confidence",
    "视频ID": "video_id",
}

CREATOR_FIELD_MAP = {
    "主页URL": "profile_url",
    "作者": "author_unique",
    "用户名": "author_unique",
    "昵称": "nickname",
    "粉丝数": "followers",
    "中位播放": "median_plays",
    "7日最高播放": "max_plays_7d",
    "14日发帖数": "posts_14d",
    "30日发帖数": "posts_30d",
    "垂直度": "vertical_ratio",
    "评估时间": "evaluated_at",
    "总点赞": "total_likes",
    "视频数": "video_count",
    "评估": "eval_status",
    "来源": "source",
    "简介": "bio",
}


def _env(k: str) -> str:
    return os.getenv(k, "").strip()


def tenant_token() -> str:
    r = requests.post(
        f"{API_BASE}/auth/v3/tenant_access_token/internal",
        json={"app_id": _env("FEISHU_APP_ID"),
              "app_secret": _env("FEISHU_APP_SECRET")},
        timeout=10,
    ).json()
    if r.get("code") != 0:
        raise RuntimeError(f"auth failed: {r}")
    return r["tenant_access_token"]


def fetch_all(table_id: str, token: str) -> list[dict]:
    app_token = _env("BITABLE_APP_TOKEN")
    url = f"{API_BASE}/bitable/v1/apps/{app_token}/tables/{table_id}/records"
    headers = {"Authorization": f"Bearer {token}"}
    records = []
    page_token = None
    for _ in range(20):
        params = {"page_size": 500}
        if page_token:
            params["page_token"] = page_token
        resp = requests.get(url, headers=headers, params=params, timeout=30).json()
        if resp.get("code") != 0:
            print(f"  fetch failed: {resp.get('msg')}")
            break
        data = resp.get("data", {})
        for rec in data.get("items", []):
            fields = rec.get("fields", {})
            fields["_record_id"] = rec.get("record_id", "")
            records.append(fields)
        page_token = data.get("page_token")
        if not data.get("has_more"):
            break
    return records


def _clean(records: list[dict], is_creator: bool = False) -> list[dict]:
    field_map = CREATOR_FIELD_MAP if is_creator else VIDEO_FIELD_MAP
    out = []
    for rec in records:
        clean = {}
        for k, v in rec.items():
            # Unpack Feishu link/array wrappers
            if isinstance(v, dict) and "link" in v:
                v = v.get("link")
            elif isinstance(v, list) and v and isinstance(v[0], dict) and "text" in v[0]:
                v = "".join(x.get("text", "") for x in v)
            
            # Map to English field name
            new_key = field_map.get(k, k)
            clean[new_key] = v
        out.append(clean)
    return out


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    token = tenant_token()

    all_videos = []
    all_creators = []

    for key, table_id in TABLES.items():
        region, kind = key.split("_")
        is_creator = "creators" in kind
        print(f"Fetching {key} ({table_id})...")
        records = _clean(fetch_all(table_id, token), is_creator=is_creator)
        
        for r in records:
            r["_region"] = region.upper()
            if "language" not in r:
                r["language"] = REGION_MAP[region]
            # Ensure play_count and like_count are numbers
            for num_field in ["play_count", "like_count", "comment_count", "share_count",
                              "followers", "median_plays", "max_plays_7d", "posts_14d", "posts_30d"]:
                if num_field in r and r[num_field] is not None:
                    try:
                        r[num_field] = int(r[num_field])
                    except (ValueError, TypeError):
                        r[num_field] = 0
        
        if is_creator:
            all_creators.extend(records)
        else:
            all_videos.extend(records)

    now = int(time.time() * 1000)

    (OUT_DIR / "videos.json").write_text(
        json.dumps({"generated_at": now, "items": all_videos}, ensure_ascii=False),
        encoding="utf-8")
    (OUT_DIR / "creators.json").write_text(
        json.dumps({"generated_at": now, "items": all_creators}, ensure_ascii=False),
        encoding="utf-8")

    print(f"Done: {len(all_videos)} videos ({sum(1 for v in all_videos if v.get('_region')=='JP')} JP), "
          f"{len(all_creators)} creators ({sum(1 for c in all_creators if c.get('_region')=='JP')} JP)")


if __name__ == "__main__":
    main()
