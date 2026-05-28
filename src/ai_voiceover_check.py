"""AI voiceover-commentary verification using Gemini multimodal.

Reads videos from JP/US Bitable tables (filtered by 可信度=中/低), downloads
each video, asks Gemini to classify whether it's a voiceover-narrating-movie
video or something else (creator on-camera, meme, original short film, etc.).

Updates the Bitable record with:
  - 是否解说: 是 / 否 / 不确定
  - AI判断依据: short reason
  - AI识别片名: best-effort movie title from the visuals

Designed to run as its own GitHub Actions workflow (ai-verify.yml).

Cost (Gemini 2.5 Flash):
  - $0.30 per 1M input tokens (incl. video frames)
  - 60s video ≈ ~30K tokens ≈ $0.009/video
  - Daily 50 videos = $0.45/day = ~$13/month
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

import requests as _requests

from . import bitable as _b

logger = logging.getLogger(__name__)

API = "https://open.feishu.cn/open-apis"
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"

# Tables to verify
TABLES = [
    ("us_videos", os.getenv("BITABLE_VIDEOS_TABLE",     "tblrY6LqfrQsc1qv")),
    ("jp_videos", os.getenv("BITABLE_JP_VIDEOS_TABLE",  "tblGCE433yHlyi19")),
    ("liked",     "tblzY8kdXrffenE9"),
]

# How many videos to process per run (cap for cost control)
MAX_PER_RUN = 30
MAX_PER_TABLE = 15

# Only verify videos with confidence=中/低 (skip 高 — already trusted)
TARGET_CONFIDENCES = {"中", "低", ""}


# ============================================================
# Bitable: read videos needing AI verification
# ============================================================

def _str(v):
    if isinstance(v, list):
        return " ".join(t.get("text", "") for t in v if isinstance(t, dict))
    return str(v) if v else ""


def _list_unverified(table_id: str, limit: int) -> list[dict]:
    """Pull videos with empty 是否解说 column."""
    headers = _b._headers()
    if not headers:
        return []
    app_token = _b._env("BITABLE_APP_TOKEN")
    url = f"{API}/bitable/v1/apps/{app_token}/tables/{table_id}/records"
    out = []
    page_token = None
    for _ in range(40):
        params = {"page_size": 500}
        if page_token:
            params["page_token"] = page_token
        try:
            r = _requests.get(url, headers=headers, params=params, timeout=30).json()
        except Exception as exc:
            logger.warning("list failed: %s", exc)
            break
        if r.get("code") != 0:
            break
        d = r.get("data", {})
        for rec in d.get("items", []):
            f = rec.get("fields", {}) or {}
            video_url = _str(f.get("视频URL"))
            if not video_url or "/video/" not in video_url:
                continue
            already = _str(f.get("是否解说"))
            if already.strip():
                continue
            confidence = _str(f.get("可信度", ""))
            if confidence not in TARGET_CONFIDENCES:
                continue
            out.append({
                "record_id": rec["record_id"],
                "video_url": video_url,
                "caption": _str(f.get("标题", "")),
                "author":  _str(f.get("作者", "")),
            })
            if len(out) >= limit:
                break
        page_token = d.get("page_token")
        if not d.get("has_more") or len(out) >= limit:
            break
    return out


def _batch_update(table_id: str, updates: list[dict]) -> int:
    if not updates:
        return 0
    headers = _b._headers()
    app_token = _b._env("BITABLE_APP_TOKEN")
    url = f"{API}/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_update"
    written = 0
    for i in range(0, len(updates), 500):
        chunk = updates[i:i + 500]
        try:
            r = _requests.post(url, headers=headers,
                               json={"records": chunk}, timeout=30).json()
            if r.get("code") == 0:
                written += len(r.get("data", {}).get("records", []))
            else:
                logger.warning("batch_update rejected: %s", r)
        except Exception as exc:
            logger.warning("batch_update failed: %s", exc)
    return written


def _ensure_ai_columns(table_id: str) -> None:
    """Ensure the AI verification columns exist on this table."""
    _b._ensure_fields(table_id, [
        ("是否解说", 3),     # SingleSelect: 是/否/不确定
        ("AI判断依据", 1),    # Text
        ("AI识别片名", 1),    # Text
    ])


# ============================================================
# Video download (yt-dlp via subprocess)
# ============================================================

def _download_video(url: str, out_dir: Path) -> Optional[Path]:
    """Use yt-dlp to download a TikTok video."""
    import subprocess
    out_template = str(out_dir / "%(id)s.%(ext)s")
    try:
        result = subprocess.run(
            [
                "yt-dlp",
                "-f", "best[height<=720]/best",  # cap at 720p to save tokens
                "--max-filesize", "30M",
                "-q", "--no-warnings",
                "-o", out_template,
                "--no-playlist",
                url,
            ],
            capture_output=True, timeout=60, text=True,
        )
        if result.returncode != 0:
            logger.warning("yt-dlp failed: %s", result.stderr[:200])
            return None
    except subprocess.TimeoutExpired:
        logger.warning("yt-dlp timeout: %s", url)
        return None
    except FileNotFoundError:
        logger.error("yt-dlp not installed — `pip install yt-dlp`")
        return None

    # Find the downloaded file
    files = list(out_dir.glob("*.mp4")) + list(out_dir.glob("*.webm"))
    if not files:
        return None
    # Return the most recently modified
    return max(files, key=lambda p: p.stat().st_mtime)


# ============================================================
# Gemini multimodal API
# ============================================================

PROMPT = """你是一个 TikTok 视频分类助手。判断这个视频是否是"配音解说电影"类型。

定义：
- ✅ 配音解说：画面是电影/电视剧的剪辑片段，声音是旁白配音讲解剧情
- ❌ 真人出镜：博主自己在镜头前讲话、推荐、点评（即使讲的是电影也算"否"）
- ❌ 原创内容：博主自己拍的短片、迷因、舞台、综艺
- ❌ 切片/预告片：纯电影画面没有解说旁白，或只是 trailer
- ❌ 评论分享：列表型推荐，作者出镜介绍

请严格按 JSON 格式返回（不要 markdown，不要解释）：
{
  "is_voiceover_commentary": true/false,
  "confidence": 0.0-1.0,
  "reason": "20字以内中文判断依据",
  "detected_movie_title": "如果识别出电影名（中文+原名），否则空字符串"
}"""


def _call_gemini(video_path: Path, api_key: str,
                 caption: str = "") -> Optional[dict]:
    """Call Gemini Flash with the video file."""
    # Step 1: upload the file via Gemini Files API
    upload_url = (
        f"{GEMINI_API_BASE}/files"
        f"?key={api_key}"
    )
    metadata = {"file": {"display_name": video_path.name}}

    file_size = video_path.stat().st_size
    headers_init = {
        "X-Goog-Upload-Protocol": "resumable",
        "X-Goog-Upload-Command": "start",
        "X-Goog-Upload-Header-Content-Length": str(file_size),
        "X-Goog-Upload-Header-Content-Type": "video/mp4",
        "Content-Type": "application/json",
    }
    try:
        init_resp = _requests.post(upload_url, headers=headers_init,
                                   json=metadata, timeout=30)
        upload_url2 = init_resp.headers.get("X-Goog-Upload-Url")
        if not upload_url2:
            logger.warning("no upload URL: %s", init_resp.text[:200])
            return None

        # Step 2: upload the bytes
        with open(video_path, "rb") as f:
            data = f.read()
        upload_resp = _requests.post(
            upload_url2,
            headers={
                "X-Goog-Upload-Offset": "0",
                "X-Goog-Upload-Command": "upload, finalize",
            },
            data=data, timeout=120,
        )
        file_info = upload_resp.json().get("file", {})
        file_uri = file_info.get("uri")
        if not file_uri:
            logger.warning("no file URI: %s", upload_resp.text[:200])
            return None

        # Step 3: wait for the file to be processed
        for _ in range(20):
            time.sleep(3)
            check = _requests.get(
                f"{file_uri}?key={api_key}", timeout=10,
            ).json()
            state = check.get("state")
            if state == "ACTIVE":
                break
            if state == "FAILED":
                logger.warning("file upload failed: %s", check)
                return None

        # Step 4: call generateContent with the file + prompt
        gen_url = (
            f"{GEMINI_API_BASE}/models/gemini-2.0-flash:generateContent"
            f"?key={api_key}"
        )
        gen_body = {
            "contents": [{
                "parts": [
                    {"file_data": {
                        "mime_type": "video/mp4",
                        "file_uri": file_uri,
                    }},
                    {"text": PROMPT + "\n\nVideo caption: " + caption[:500]},
                ],
            }],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.1,
            },
        }
        resp = _requests.post(gen_url, json=gen_body, timeout=60).json()
        if "candidates" not in resp:
            logger.warning("gemini error: %s", resp)
            return None
        text = resp["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)
    except Exception as exc:
        logger.warning("gemini call failed: %s", exc)
        return None


# ============================================================
# Main
# ============================================================

def _setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%H:%M:%S",
    )


def main():
    _setup_logging()
    t0 = time.time()

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        logger.error("GEMINI_API_KEY not set"); sys.exit(1)
    if not _b.is_configured():
        logger.error("Feishu not configured"); sys.exit(1)

    # Make a tmp dir for video downloads
    tmp_dir = Path("/tmp/ai_videos") if Path("/tmp").exists() else Path.cwd() / "_ai_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    total_processed = 0
    total_classified = 0

    for label, table_id in TABLES:
        if not table_id or total_processed >= MAX_PER_RUN:
            continue
        budget = min(MAX_PER_TABLE, MAX_PER_RUN - total_processed)
        logger.info("=== AI verify %s (%s) — budget %d ===",
                    label, table_id, budget)

        _ensure_ai_columns(table_id)
        videos = _list_unverified(table_id, budget)
        logger.info("Found %d unverified videos", len(videos))
        if not videos:
            continue

        updates = []
        for i, v in enumerate(videos):
            logger.info("  [%d/%d] %s", i + 1, len(videos),
                        v["video_url"].rsplit("/", 1)[-1])

            # Download
            mp4 = _download_video(v["video_url"], tmp_dir)
            if not mp4:
                logger.warning("    skip: download failed")
                continue

            # Classify
            result = _call_gemini(mp4, api_key, caption=v["caption"])
            try:
                mp4.unlink()
            except Exception:
                pass

            if not result:
                continue

            is_vc = result.get("is_voiceover_commentary")
            verdict = "是" if is_vc is True else ("否" if is_vc is False else "不确定")
            reason = (result.get("reason") or "")[:200]
            title = (result.get("detected_movie_title") or "")[:200]

            update_fields = {
                "是否解说":   verdict,
                "AI判断依据": reason,
            }
            if title:
                update_fields["AI识别片名"] = title

            updates.append({
                "record_id": v["record_id"],
                "fields":    update_fields,
            })
            logger.info("    → %s | %s | title=%r",
                        verdict, reason[:50], title[:30])
            total_classified += 1
            time.sleep(2)  # be polite to Gemini

        if updates:
            written = _batch_update(table_id, updates)
            logger.info("Updated %d records in Bitable", written)

        total_processed += len(videos)

    elapsed = time.time() - t0
    logger.info("=== AI verify done: %d classified / %d processed in %.1f min ===",
                total_classified, total_processed, elapsed / 60)


if __name__ == "__main__":
    main()
