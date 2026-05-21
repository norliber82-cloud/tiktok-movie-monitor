"""One-time backfill: fill the new 主页URL column on creator tables.

Targets the three creator tables we maintain:
  1. BITABLE_CREATORS_TABLE       (main, US)
  2. BITABLE_JP_CREATORS_TABLE    (JP)
  3. tblRc6b9FrxMu4Gv             (account_tracker / following_creators)

For every record where 用户名 is set but 主页URL is empty, we write
``https://www.tiktok.com/@{用户名}`` and (where applicable) populate the
button-style 主页链接 too.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

import requests

from src import bitable as _b


API = "https://open.feishu.cn/open-apis"
ACCOUNT_TRACKER_TABLE = "tblRc6b9FrxMu4Gv"


def _list_records(table_id: str) -> list[dict]:
    """Pull every record from a table (paginated)."""
    headers = _b._headers()
    if not headers:
        raise RuntimeError("No Feishu auth — check FEISHU_APP_ID / SECRET in .env")
    app_token = _b._env("BITABLE_APP_TOKEN")
    url = f"{API}/bitable/v1/apps/{app_token}/tables/{table_id}/records"
    out = []
    page_token = None
    for _ in range(80):
        params = {"page_size": 500}
        if page_token:
            params["page_token"] = page_token
        r = requests.get(url, headers=headers, params=params, timeout=30).json()
        if r.get("code") != 0:
            print(f"  ! list rejected: {r}")
            break
        d = r.get("data", {})
        out.extend(d.get("items", []))
        page_token = d.get("page_token")
        if not d.get("has_more"):
            break
    return out


def _batch_update(table_id: str, updates: list[dict]) -> int:
    """`updates` = [{record_id, fields}, ...]. Returns count of updated."""
    if not updates:
        return 0
    headers = _b._headers()
    app_token = _b._env("BITABLE_APP_TOKEN")
    url = f"{API}/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_update"
    updated = 0
    for i in range(0, len(updates), 500):
        chunk = updates[i:i + 500]
        r = requests.post(
            url, headers=headers, json={"records": chunk}, timeout=30,
        ).json()
        if r.get("code") == 0:
            updated += len(r.get("data", {}).get("records", []))
        else:
            print(f"  ! batch_update rejected: {r}")
    return updated


def _build_update(rec: dict, *, want_button: bool) -> dict | None:
    fields = rec.get("fields", {}) or {}
    username = fields.get("用户名")
    if not username:
        return None
    if isinstance(username, list):  # link/lookup field shape
        username = username[0].get("text") if username else None
    if not username:
        return None
    username = str(username).lstrip("@")
    profile = f"https://www.tiktok.com/@{username}"

    needs = {}
    if not fields.get("主页URL"):
        needs["主页URL"] = profile
    # Where a button column already exists, only fill it when empty
    if want_button and not fields.get("主页链接"):
        needs["主页链接"] = {"link": profile, "text": "主页"}

    if not needs:
        return None
    return {"record_id": rec["record_id"], "fields": needs}


def backfill_table(table_id: str, label: str, *, want_button: bool = True):
    print(f"\n=== {label} ({table_id}) ===")
    records = _list_records(table_id)
    print(f"  total records: {len(records)}")

    # Auto-create the column if it doesn't exist yet
    _b._ensure_fields(table_id, [("主页URL", 1)])

    updates = []
    for rec in records:
        u = _build_update(rec, want_button=want_button)
        if u:
            updates.append(u)
    print(f"  records needing backfill: {len(updates)}")

    n = _batch_update(table_id, updates)
    print(f"  records updated: {n}")


def main():
    if not _b.is_configured():
        print("Feishu not configured — check .env"); sys.exit(1)

    main_us = os.getenv("BITABLE_CREATORS_TABLE", "").strip()
    main_jp = os.getenv("BITABLE_JP_CREATORS_TABLE", "").strip()

    if main_us:
        backfill_table(main_us, "US main creators")
    else:
        print("BITABLE_CREATORS_TABLE not set — skipping US main")

    if main_jp:
        backfill_table(main_jp, "JP main creators")
    else:
        print("BITABLE_JP_CREATORS_TABLE not set — skipping JP main")

    # account_tracker table already has both columns under different names
    # (主页URL + 主页按钮); same backfill works.
    backfill_table(ACCOUNT_TRACKER_TABLE,
                   "account_tracker following_creators",
                   want_button=False)  # uses 主页按钮, not 主页链接


if __name__ == "__main__":
    main()
