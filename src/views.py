"""One-shot script to create Bitable views on the `videos` data table.

Run with:  python -m src.views

Views created (grid type, all sorted by create_time desc):
  - All · by time
  - 🇺🇸 English
  - 🇯🇵 Japanese
  - ▶️ TikTok
  - 📺 YouTube Shorts
  - 🔥 RED (1M+)
  - 🟧 ORANGE (500K+)
  - 🟡 YELLOW (200K+)
  - Last 24h
"""

from __future__ import annotations

import logging
import os
import sys
import time

import requests

from .bitable import _get_tenant_token, API_BASE, _env, is_configured

logger = logging.getLogger(__name__)

# (view_name, filter_spec, sort_spec)
# filter_spec uses Bitable open-api v1 filter grammar.
VIEWS = [
    ("All · by time",
     None,
     [{"field_name": "create_time", "desc": True}]),
    ("🇺🇸 English",
     [("language", "is", "en")],
     [{"field_name": "create_time", "desc": True}]),
    ("🇯🇵 Japanese",
     [("language", "is", "ja")],
     [{"field_name": "create_time", "desc": True}]),
    ("▶️ TikTok",
     [("platform", "is", "tiktok")],
     [{"field_name": "create_time", "desc": True}]),
    ("📺 YouTube Shorts",
     [("platform", "is", "youtube")],
     [{"field_name": "create_time", "desc": True}]),
    ("🔥 RED (1M+)",
     [("tier", "is", "RED")],
     [{"field_name": "play_count", "desc": True}]),
    ("🟧 ORANGE (500K+)",
     [("tier", "is", "ORANGE")],
     [{"field_name": "play_count", "desc": True}]),
    ("🟡 YELLOW (200K+)",
     [("tier", "is", "YELLOW")],
     [{"field_name": "play_count", "desc": True}]),
]


def _headers():
    tok = _get_tenant_token()
    if not tok:
        return None
    return {"Authorization": f"Bearer {tok}",
            "Content-Type": "application/json; charset=utf-8"}


def _get_fields(table_id: str) -> dict:
    headers = _headers()
    if not headers:
        return {}
    app_token = _env("BITABLE_APP_TOKEN")
    url = f"{API_BASE}/bitable/v1/apps/{app_token}/tables/{table_id}/fields"
    resp = requests.get(url, headers=headers, params={"page_size": 100}, timeout=10).json()
    if resp.get("code") != 0:
        logger.error("fields fetch failed: %s", resp)
        return {}
    return {f["field_name"]: f for f in resp.get("data", {}).get("items", [])}


def _list_views(table_id: str) -> dict:
    headers = _headers()
    app_token = _env("BITABLE_APP_TOKEN")
    url = f"{API_BASE}/bitable/v1/apps/{app_token}/tables/{table_id}/views"
    resp = requests.get(url, headers=headers, params={"page_size": 100}, timeout=10).json()
    return {v["view_name"]: v
            for v in resp.get("data", {}).get("items", [])}


def _create_view(table_id: str, name: str) -> str | None:
    headers = _headers()
    app_token = _env("BITABLE_APP_TOKEN")
    url = f"{API_BASE}/bitable/v1/apps/{app_token}/tables/{table_id}/views"
    resp = requests.post(url, headers=headers,
                         json={"view_name": name, "view_type": "grid"},
                         timeout=10).json()
    if resp.get("code") != 0:
        logger.error("create view %s failed: %s", name, resp)
        return None
    return resp["data"]["view"]["view_id"]


def _patch_view(table_id: str, view_id: str,
                filter_spec, sort_spec) -> bool:
    headers = _headers()
    app_token = _env("BITABLE_APP_TOKEN")
    url = (f"{API_BASE}/bitable/v1/apps/{app_token}"
           f"/tables/{table_id}/views/{view_id}")

    property_payload = {}
    if filter_spec:
        property_payload["filter_info"] = {
            "conjunction": "and",
            "conditions": [
                {"field_name": f, "operator": op, "value": [v]}
                for (f, op, v) in filter_spec
            ],
        }
    if sort_spec:
        property_payload["sort_info"] = {"sort_conditions": sort_spec}

    if not property_payload:
        return True

    resp = requests.patch(url, headers=headers,
                          json={"property": property_payload},
                          timeout=10).json()
    if resp.get("code") != 0:
        logger.error("patch view %s failed: %s", view_id, resp)
        return False
    return True


def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s | %(message)s")
    if not is_configured():
        print("Bitable env vars missing. Set FEISHU_APP_ID / FEISHU_APP_SECRET / "
              "BITABLE_APP_TOKEN / BITABLE_VIDEOS_TABLE", file=sys.stderr)
        sys.exit(1)

    table_id = _env("BITABLE_VIDEOS_TABLE")
    if not table_id:
        print("BITABLE_VIDEOS_TABLE missing", file=sys.stderr)
        sys.exit(1)

    fields = _get_fields(table_id)
    if not fields:
        print("Could not list fields — check that the self-built app has "
              "edit access on the Base.", file=sys.stderr)
        sys.exit(1)

    existing = _list_views(table_id)
    print(f"Existing views: {list(existing.keys())}")

    for name, flt, srt in VIEWS:
        # Skip if the filter references a field the table doesn't have yet.
        missing = [f for (f, _, _) in (flt or []) if f not in fields]
        if missing:
            print(f"⏭  Skipping {name!r} (missing fields: {missing}). "
                  "Run the monitor once to auto-create them first.")
            continue

        if name in existing:
            view_id = existing[name]["view_id"]
            action = "updated"
        else:
            view_id = _create_view(table_id, name)
            if not view_id:
                continue
            action = "created"
            time.sleep(0.5)

        if _patch_view(table_id, view_id, flt, srt):
            print(f"✓ {action}: {name}")
        else:
            print(f"✗ {action} ({name}) — patch failed")


if __name__ == "__main__":
    main()
