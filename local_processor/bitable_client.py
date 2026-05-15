"""Lightweight Feishu Bitable client for local-side reads/writes."""

import logging
import time
from typing import Optional

import requests

from . import config

logger = logging.getLogger(__name__)
API_BASE = "https://open.feishu.cn/open-apis"

_token_cache = {"token": "", "exp": 0}


def _tenant_token() -> str:
    now = int(time.time())
    if _token_cache["token"] and _token_cache["exp"] - now > 120:
        return _token_cache["token"]
    r = requests.post(
        f"{API_BASE}/auth/v3/tenant_access_token/internal",
        json={"app_id": config.FEISHU_APP_ID,
              "app_secret": config.FEISHU_APP_SECRET},
        timeout=15,
    ).json()
    if r.get("code") != 0:
        raise RuntimeError(f"feishu auth failed: {r}")
    _token_cache["token"] = r["tenant_access_token"]
    _token_cache["exp"] = now + int(r.get("expire", 7200))
    return _token_cache["token"]


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_tenant_token()}",
        "Content-Type": "application/json; charset=utf-8",
    }


def list_videos(filter_since_ms: Optional[int] = None) -> list[dict]:
    """Fetch all video records, optionally filtered to those created after a timestamp.

    Returns records with both Chinese and English field names normalized into
    Chinese keys (so downstream code only needs to handle Chinese)."""
    url = (f"{API_BASE}/bitable/v1/apps/{config.BITABLE_APP_TOKEN}"
           f"/tables/{config.BITABLE_VIDEOS_TABLE}/records")
    records = []
    page_token = None
    for _ in range(40):  # cap pagination
        params = {"page_size": 500}
        if page_token:
            params["page_token"] = page_token
        resp = requests.get(url, headers=_headers(), params=params, timeout=30).json()
        if resp.get("code") != 0:
            logger.warning("Bitable list failed: %s", resp)
            break
        data = resp.get("data", {})
        for rec in data.get("items", []):
            fields = _normalize_fields(rec.get("fields", {}))
            fields["_record_id"] = rec.get("record_id")
            records.append(fields)
        page_token = data.get("page_token")
        if not data.get("has_more"):
            break

    if filter_since_ms is not None:
        records = [r for r in records
                   if (_to_int(r.get("发布时间")) or 0) >= filter_since_ms]
    return records


# Map old English field names → new Chinese ones, so the rest of the
# pipeline can rely on a single naming convention.
_EN_TO_ZH = {
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


def _normalize_fields(fields: dict) -> dict:
    out = {}
    for k, v in fields.items():
        out[_EN_TO_ZH.get(k, k)] = v
    return out


def _to_int(v) -> int:
    if v is None: return 0
    if isinstance(v, (int, float)): return int(v)
    try: return int(v)
    except (TypeError, ValueError): return 0


def list_field_names(table_id: str) -> set[str]:
    url = f"{API_BASE}/bitable/v1/apps/{config.BITABLE_APP_TOKEN}/tables/{table_id}/fields"
    resp = requests.get(url, headers=_headers(),
                        params={"page_size": 100}, timeout=15).json()
    if resp.get("code") != 0:
        return set()
    return {f["field_name"] for f in resp.get("data", {}).get("items", [])}


def ensure_field(table_id: str, name: str, ftype: int = 1) -> bool:
    existing = list_field_names(table_id)
    if name in existing:
        return True
    url = f"{API_BASE}/bitable/v1/apps/{config.BITABLE_APP_TOKEN}/tables/{table_id}/fields"
    resp = requests.post(url, headers=_headers(),
                         json={"field_name": name, "type": ftype},
                         timeout=15).json()
    return resp.get("code") == 0


def update_record(table_id: str, record_id: str, fields: dict) -> bool:
    url = (f"{API_BASE}/bitable/v1/apps/{config.BITABLE_APP_TOKEN}"
           f"/tables/{table_id}/records/{record_id}")
    resp = requests.put(url, headers=_headers(),
                        json={"fields": fields}, timeout=15).json()
    if resp.get("code") != 0:
        logger.warning("update_record failed: %s", resp)
        return False
    return True


# Field type ids (Feishu Bitable):
#   1 = Text, 2 = Number, 3 = SingleSelect, 5 = DateTime, 15 = Link
FIELD_TYPE = {"text": 1, "number": 2, "select": 3, "datetime": 5, "link": 15}
