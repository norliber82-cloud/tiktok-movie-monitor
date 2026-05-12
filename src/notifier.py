"""Feishu (Lark) custom-bot notifier."""

import base64
import hashlib
import hmac
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

import requests

from . import db

logger = logging.getLogger(__name__)


def _feishu_sign(secret: str, timestamp: int) -> str:
    """Compute the HMAC-SHA256 signature required by Feishu when
    'signature verification' is enabled on the custom bot."""
    string_to_sign = f"{timestamp}\n{secret}"
    digest = hmac.new(
        string_to_sign.encode("utf-8"),
        b"",
        digestmod=hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def _format_time(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _build_card(row) -> dict:
    """Build an interactive Feishu card for a single qualifying video."""
    caption = (row["caption"] or "").strip()
    if len(caption) > 200:
        caption = caption[:197] + "..."

    age_hours = (int(time.time()) - int(row["create_time"])) / 3600

    fields = [
        {"is_short": True, "text": {"tag": "lark_md",
            "content": f"**👀 播放**\n{row['play_count']:,}"}},
        {"is_short": True, "text": {"tag": "lark_md",
            "content": f"**❤️ 点赞**\n{row['like_count']:,}"}},
        {"is_short": True, "text": {"tag": "lark_md",
            "content": f"**💬 评论**\n{row['comment_count']:,}"}},
        {"is_short": True, "text": {"tag": "lark_md",
            "content": f"**🔁 分享**\n{row['share_count']:,}"}},
        {"is_short": True, "text": {"tag": "lark_md",
            "content": f"**⏱️ 时长**\n{row['duration']}s"}},
        {"is_short": True, "text": {"tag": "lark_md",
            "content": f"**📅 发布**\n{_format_time(row['create_time'])}\n({age_hours:.1f}h ago)"}},
    ]

    elements = [
        {"tag": "div", "text": {"tag": "lark_md",
            "content": f"**@{row['author_unique']}** · #{row['matched_tag']}"}},
        {"tag": "div", "text": {"tag": "lark_md",
            "content": caption or "_(no caption)_"}},
        {"tag": "div", "fields": fields},
    ]
    if row["hashtags"]:
        tags_line = " ".join(f"#{t}" for t in row["hashtags"].split(",") if t)
        elements.append({"tag": "div", "text": {"tag": "lark_md",
            "content": f"_{tags_line}_"}})
    elements.append({"tag": "action", "actions": [
        {"tag": "button",
         "text": {"tag": "plain_text", "content": "🎬 Open on TikTok"},
         "url": row["video_url"],
         "type": "primary"}]})

    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "red",
                "title": {"tag": "plain_text",
                          "content": f"🔥 1M+ in {max(1, int(age_hours/24))}d"},
            },
            "elements": elements,
        },
    }


def _send(webhook: str, secret: Optional[str], payload: dict) -> bool:
    if secret:
        ts = int(time.time())
        payload = {**payload, "timestamp": str(ts), "sign": _feishu_sign(secret, ts)}

    try:
        resp = requests.post(webhook, json=payload, timeout=10)
        data = resp.json()
    except Exception as exc:
        logger.exception("Feishu POST failed: %s", exc)
        return False

    # Feishu returns {"code":0,"msg":"ok"} on success, or {"StatusCode":0,...} on legacy.
    ok = data.get("code", data.get("StatusCode", -1)) == 0
    if not ok:
        logger.error("Feishu rejected payload: %s", data)
    return ok


def push_new_hits() -> int:
    webhook = os.getenv("FEISHU_WEBHOOK", "").strip()
    if not webhook:
        logger.warning("FEISHU_WEBHOOK not set, skipping notifications")
        return 0
    secret = os.getenv("FEISHU_SECRET", "").strip() or None

    rows = db.fetch_unalerted(min_views=1_000_000)
    if not rows:
        logger.info("No new qualifying videos to push")
        return 0

    pushed = []
    for row in rows:
        card = _build_card(row)
        if _send(webhook, secret, card):
            pushed.append(row["video_id"])
            # polite spacing to avoid Feishu rate limits (100 msgs/min per bot)
            time.sleep(1.2)
        else:
            logger.warning("Skip marking %s as alerted (send failed)", row["video_id"])

    db.mark_alerted(pushed, tier=1_000_000)
    logger.info("Pushed %d / %d qualifying videos", len(pushed), len(rows))
    return len(pushed)


def push_summary(scan_hits: int) -> None:
    """Send a small summary ping each run so you know the cron is alive."""
    webhook = os.getenv("FEISHU_WEBHOOK", "").strip()
    if not webhook:
        return
    secret = os.getenv("FEISHU_SECRET", "").strip() or None
    stats = db.recent_stats()
    payload = {
        "msg_type": "text",
        "content": {
            "text": (
                f"[TikTok Movie Monitor] run ok\n"
                f"this run qualifying: {scan_hits}\n"
                f"total stored: {stats['total']} | alerted: {stats['alerted']}\n"
                f"ts: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
            )
        },
    }
    # Only send the heartbeat if SEND_HEARTBEAT is truthy
    if os.getenv("SEND_HEARTBEAT", "").lower() in ("1", "true", "yes"):
        _send(webhook, secret, payload)
