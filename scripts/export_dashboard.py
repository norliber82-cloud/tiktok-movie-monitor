#!/usr/bin/env python3
"""Export all 4 Bitable tables into dashboard JSON files."""

from __future__ import annotations
import json, os, pathlib, time
import requests

API_BASE = "https://open.feishu.cn/open-apis"
OUT_DIR = pathlib.Path("dashboard")

# Table IDs (hardcoded for reliability — same as monitoring workflow)
TABLES = {
    "us_videos":   "tblrY6LqfrQsc1qv",
    "us_creators": "tbl7L9IRcsfPAk1k",
    "jp_videos":   "tblGCE433yHlyi19",
    "jp_creators": "tbl0rNNay2uZb3zv",
}

REGION_MAP = {"us": "en", "jp": "ja"}


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
            records.append(rec.get("fields", {}))
        page_token = data.get("page_token")
        if not data.get("has_more"):
            break
    return records


def _clean(records: list[dict]) -> list[dict]:
    out = []
    for rec in records:
        clean = {}
        for k, v in rec.items():
            if isinstance(v, dict) and "link" in v:
                clean[k] = v.get("link")
            elif isinstance(v, list) and v and isinstance(v[0], dict) and "text" in v[0]:
                clean[k] = "".join(x.get("text", "") for x in v)
            else:
                clean[k] = v
        out.append(clean)
    return out


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    token = tenant_token()

    all_videos = []
    all_creators = []

    for key, table_id in TABLES.items():
        region, kind = key.split("_")
        print(f"Fetching {key} ({table_id})...")
        records = _clean(fetch_all(table_id, token))
        
        # Tag every record with its region
        for r in records:
            r["_region"] = region.upper()
            if "语言" not in r:
                r["语言"] = REGION_MAP[region]
        
        if "videos" in kind:
            all_videos.extend(records)
        else:
            all_creators.extend(records)

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
