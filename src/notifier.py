"""Feishu (Lark) custom-bot notifier — tiered video alerts + creator alerts."""

import base64
import hashlib
import hmac
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

import requests

from . import db
from .classifier import tier_meta

logger = logging.getLogger(__name__)

_LANG_FLAG = {"en": "🇺🇸 EN", "ja": "🇯🇵 JA", "zh": "🇨🇳 ZH",
              "ko": "🇰🇷 KO", "es": "🇪🇸 ES", "pt": "🇵🇹 PT"}

_PLATFORM_BADGE = {
    "tiktok":  "▶️ TikTok",
    "youtube": "📺 YouTube Shorts",
}


def _feishu_sign(secret: str, ts: int) -> str:
    s = f"{ts}\n{secret}"
    digest = hmac.new(s.encode("utf-8"), b"", digestmod=hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


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
    ok = data.get("code", data.get("StatusCode", -1)) == 0
    if not ok:
        logger.error("Feishu rejected payload: %s", data)
    return ok


def _fmt_time(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


# ------------------------- video card -------------------------

def _build_video_card(row) -> dict:
    meta = tier_meta(row["tier"]) or {"label": row["tier"], "color": "blue"}
    cap = (row["caption"] or "").strip()
    if len(cap) > 200:
        cap = cap[:197] + "..."
    age_h = (int(time.time()) - int(row["create_time"])) / 3600.0
    lang_tag = _LANG_FLAG.get(row["language"] or "", row["language"] or "??")
    platform = (row["platform"] or "tiktok") if "platform" in row.keys() else "tiktok"
    plat_tag = _PLATFORM_BADGE.get(platform, platform)

    btn_text = "🎬 Open on YouTube" if platform == "youtube" else "🎬 Open on TikTok"

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
            "content": f"**⏱️ 时长 / 🗣️**\n{row['duration']}s · {lang_tag}"}},
        {"is_short": True, "text": {"tag": "lark_md",
            "content": f"**📅 发布**\n{_fmt_time(row['create_time'])}\n({age_h:.1f}h ago)"}},
    ]
    elements = [
        {"tag": "div", "text": {"tag": "lark_md",
            "content": f"**@{row['author_unique']}** · {plat_tag} · #{row['matched_tag']}"}},
        {"tag": "div", "text": {"tag": "lark_md",
            "content": cap or "_(no caption)_"}},
        {"tag": "div", "fields": fields},
    ]
    if row["hashtags"]:
        tags_line = " ".join(f"#{t}" for t in row["hashtags"].split(",") if t)
        elements.append({"tag": "div", "text": {"tag": "lark_md",
            "content": f"_{tags_line}_"}})
    elements.append({"tag": "action", "actions": [
        {"tag": "button",
         "text": {"tag": "plain_text", "content": btn_text},
         "url": row["video_url"], "type": "primary"}]})

    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {"template": meta["color"],
                       "title": {"tag": "plain_text", "content": meta["label"]}},
            "elements": elements,
        },
    }


# ------------------------- creator card -------------------------

def _build_creator_card(row) -> dict:
    lang_tag = _LANG_FLAG.get(row["language"] or "", row["language"] or "??")
    median_plays = row["median_plays"] or 0
    max_plays_7d = row["max_plays_7d"] or 0
    posts_14d    = row["posts_14d"] or 0
    posts_30d    = row["posts_30d"] or 0
    fields = [
        {"is_short": True, "text": {"tag": "lark_md",
            "content": f"**📊 中位播放**\n{median_plays:,}"}},
        {"is_short": True, "text": {"tag": "lark_md",
            "content": f"**🚀 7日最大**\n{max_plays_7d:,}"}},
        {"is_short": True, "text": {"tag": "lark_md",
            "content": f"**🗓️ 14d 发帖**\n{posts_14d}"}},
        {"is_short": True, "text": {"tag": "lark_md",
            "content": f"**🗓️ 30d 发帖**\n{posts_30d}"}},
        {"is_short": True, "text": {"tag": "lark_md",
            "content": f"**🎯 垂直度**\n{(row['vertical_ratio'] or 0) * 100:.0f}%"}},
        {"is_short": True, "text": {"tag": "lark_md",
            "content": f"**👥 粉丝 / 🗣️**\n{(row['follower_count'] or 0):,} · {lang_tag}"}},
    ]
    elements = [
        {"tag": "div", "text": {"tag": "lark_md",
            "content": f"**@{row['author_unique']}**" +
                       (f" ({row['nickname']})" if row['nickname'] else "")}},
        {"tag": "div", "fields": fields},
        {"tag": "action", "actions": [
            {"tag": "button",
             "text": {"tag": "plain_text", "content": "👤 Open profile"},
             "url": f"https://www.tiktok.com/@{row['author_unique']}",
             "type": "primary"}]},
    ]
    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {"template": "green",
                       "title": {"tag": "plain_text",
                                 "content": "🌱 New creator to monitor"}},
            "elements": elements,
        },
    }


# ------------------------- public API -------------------------

def push_new_hits() -> int:
    webhook = os.getenv("FEISHU_WEBHOOK", "").strip()
    if not webhook:
        logger.warning("FEISHU_WEBHOOK not set, skipping notifications")
        return 0
    secret = os.getenv("FEISHU_SECRET", "").strip() or None

    rows = db.fetch_unalerted_videos()
    if not rows:
        logger.info("No new qualifying videos to push")
        return 0

    pushed = []
    for row in rows:
        if _send(webhook, secret, _build_video_card(row)):
            pushed.append(row["video_id"])
            time.sleep(1.2)
    db.mark_videos_alerted(pushed)
    logger.info("Pushed %d / %d qualifying videos", len(pushed), len(rows))
    return len(pushed)


def push_new_creators() -> int:
    webhook = os.getenv("FEISHU_WEBHOOK", "").strip()
    if not webhook:
        return 0
    secret = os.getenv("FEISHU_SECRET", "").strip() or None

    rows = db.fetch_unalerted_monitored_authors()
    if not rows:
        return 0
    pushed = []
    for row in rows:
        if _send(webhook, secret, _build_creator_card(row)):
            pushed.append(row["author_unique"])
            time.sleep(1.2)
    db.mark_authors_alerted(pushed)
    logger.info("Pushed %d / %d creators", len(pushed), len(rows))
    return len(pushed)
