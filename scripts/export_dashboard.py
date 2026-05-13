"""Read both Bitable tables via tenant access token and dump two JSON files
into dashboard/ for the static site to consume."""

from __future__ import annotations

import json
import os
import pathlib
import time

import requests

API_BASE = "https://open.feishu.cn/open-apis"
OUT_DIR = pathlib.Path("dashboard")


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
    url = (f"{API_BASE}/bitable/v1/apps/{app_token}"
           f"/tables/{table_id}/records")
    headers = {"Authorization": f"Bearer {token}"}
    records = []
    page_token = None
    for _ in range(20):  # up to 20 pages * 500 = 10k
        params = {"page_size": 500}
        if page_token:
            params["page_token"] = page_token
        resp = requests.get(url, headers=headers, params=params, timeout=30).json()
        if resp.get("code") != 0:
            print(f"fetch failed: {resp}")
            break
        data = resp.get("data", {})
        for rec in data.get("items", []):
            records.append(rec.get("fields", {}))
        page_token = data.get("page_token")
        if not data.get("has_more"):
            break
    return records


def _clean(records: list[dict]) -> list[dict]:
    """Unpack Feishu's hyperlink/person-array wrappers into plain scalars."""
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

    videos_table = _env("BITABLE_VIDEOS_TABLE")
    creators_table = _env("BITABLE_CREATORS_TABLE")

    videos = _clean(fetch_all(videos_table, token)) if videos_table else []
    creators = _clean(fetch_all(creators_table, token)) if creators_table else []

    now = int(time.time() * 1000)
    (OUT_DIR / "videos.json").write_text(
        json.dumps({"generated_at": now, "items": videos}, ensure_ascii=False),
        encoding="utf-8")
    (OUT_DIR / "creators.json").write_text(
        json.dumps({"generated_at": now, "items": creators}, ensure_ascii=False),
        encoding="utf-8")
    print(f"Exported: {len(videos)} videos, {len(creators)} creators")


if __name__ == "__main__":
    main()
