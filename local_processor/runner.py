"""End-to-end local processor.

For each newly added Bitable video record (within the last N hours):
  1. Download watermark-free source MP4 to D:\搬运\01原素材带字幕\YYYY-MM-DD\
  2. Transcribe with faster-whisper
  3. Send to Gemini for structured analysis
  4. Save .json (analysis), .txt (transcript+title)
  5. Append to global index CSV
  6. Write 原片名 + 分析摘要 back to Bitable
"""

import csv
import json
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import bitable_client as bc
from . import config
from .analyzer import analyze_video
from .downloader import download, safe_filename
from .transcriber import transcribe

logger = logging.getLogger(__name__)

INDEX_HEADERS = [
    "处理时间", "发布日期", "等级", "平台", "语言", "作者", "原片名",
    "标题", "播放量", "视频URL", "本地路径",
]


def setup_logging():
    config.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
        handlers=[
            logging.FileHandler(config.LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def load_state() -> dict:
    if config.STATE_FILE.exists():
        try:
            return json.loads(config.STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"processed_ids": [], "last_run_ms": 0}


def save_state(state: dict) -> None:
    config.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def date_folder(create_time_ms: int) -> Path:
    if not create_time_ms:
        d = datetime.now()
    else:
        d = datetime.fromtimestamp(create_time_ms / 1000)
    folder = config.DOWNLOAD_ROOT / d.strftime("%Y-%m-%d")
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def append_index(row: dict) -> None:
    config.INDEX_DIR.mkdir(parents=True, exist_ok=True)
    fp = config.INDEX_DIR / "索引.csv"
    write_header = not fp.exists()
    with fp.open("a", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=INDEX_HEADERS)
        if write_header:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in INDEX_HEADERS})


def write_doc(folder: Path, basename: str, transcript: dict, analysis: dict,
              record: dict) -> None:
    """Write a human-readable .txt with caption + transcript + key analysis."""
    fp = folder / f"{basename}.txt"
    lines = [
        "=" * 60,
        f"作者: {record.get('作者', '')}",
        f"标题: {record.get('标题', '')}",
        f"等级: {record.get('等级', '')}    平台: {record.get('平台', '')}    语言: {record.get('语言', '')}",
        f"播放量: {record.get('播放量', '')}    点赞: {record.get('点赞数', '')}    评论: {record.get('评论数', '')}",
        f"发布: {record.get('发布时间', '')}    时长: {record.get('时长(秒)', '')}秒",
        f"视频URL: {record.get('视频链接', '')}",
        "=" * 60,
        "",
        f"【原片名】 {analysis.get('original_movie_title', '未识别')}",
        f"【一句话摘要】 {analysis.get('summary_one_sentence', '')}",
        "",
        "─" * 60,
        "【完整文案】",
        "─" * 60,
        transcript.get("text", "(转录失败)"),
        "",
        "─" * 60,
        "【分段文案】",
        "─" * 60,
    ]
    for seg in transcript.get("segments", []):
        lines.append(f"[{seg['start']:>6.1f}s - {seg['end']:>6.1f}s] {seg['text']}")
    lines.extend([
        "",
        "─" * 60,
        "【AI 结构与爆款分析】",
        "─" * 60,
        json.dumps(analysis, ensure_ascii=False, indent=2),
    ])
    fp.write_text("\n".join(lines), encoding="utf-8")


def write_back_to_bitable(record: dict, analysis: dict) -> None:
    """Add 原片名 + 分析摘要 + 钩子 columns to the videos table."""
    table = config.BITABLE_VIDEOS_TABLE
    bc.ensure_field(table, "原片名",     bc.FIELD_TYPE["text"])
    bc.ensure_field(table, "分析摘要",   bc.FIELD_TYPE["text"])
    bc.ensure_field(table, "开头钩子",   bc.FIELD_TYPE["text"])
    bc.ensure_field(table, "爆款评分",   bc.FIELD_TYPE["number"])

    structure = analysis.get("structure", {}) or {}
    viral = analysis.get("viral_factors", {}) or {}

    fields = {
        "原片名":     str(analysis.get("original_movie_title") or ""),
        "分析摘要":   str(analysis.get("summary_one_sentence") or ""),
        "开头钩子":   str(structure.get("hook_seconds_0_3") or ""),
        "爆款评分":   int(viral.get("score_0_100") or 0),
    }
    rec_id = record.get("_record_id")
    if rec_id:
        bc.update_record(table, rec_id, fields)


def hours_ago_ms(hours: int) -> int:
    return int((datetime.now(timezone.utc)
                - timedelta(hours=hours)).timestamp() * 1000)


def main(lookback_hours: int = 26):
    """Process every Bitable record posted within the last `lookback_hours`."""
    setup_logging()
    state = load_state()
    processed_ids = set(state.get("processed_ids", []))

    since_ms = hours_ago_ms(lookback_hours)
    logger.info("Fetching Bitable records posted since %s",
                datetime.fromtimestamp(since_ms / 1000))

    all_records = bc.list_videos(filter_since_ms=since_ms)
    new_records = [r for r in all_records
                   if str(r.get("视频ID", "")) not in processed_ids]
    logger.info("Total in window: %d, new to process: %d",
                len(all_records), len(new_records))
    new_records = new_records[:config.MAX_VIDEOS_PER_RUN]    successes, failures = 0, 0
    for i, rec in enumerate(new_records, 1):
        vid_id   = str(rec.get("视频ID", "")).strip()
        url      = rec.get("视频链接") or rec.get("video_url") or ""
        if isinstance(url, dict):
            url = url.get("link", "")
        author   = (rec.get("作者") or "").lstrip("@")
        tier     = rec.get("等级") or "?"
        ct_ms    = rec.get("发布时间") or rec.get("create_time") or 0
        if isinstance(ct_ms, str):
            try: ct_ms = int(ct_ms)
            except ValueError: ct_ms = 0

        if not vid_id or not url:
            logger.warning("[%d/%d] skip: no id/url", i, len(new_records))
            continue

        out_dir = date_folder(ct_ms)
        # Make filename: TIER_author_videoid (no fancy chars)
        cleaned_id = safe_filename(vid_id.replace("yt:", "yt_"), 30)
        basename = f"{tier}_{safe_filename(author, 20)}_{cleaned_id}"

        logger.info("[%d/%d] %s — downloading...", i, len(new_records), basename)
        video_path = download(url, out_dir, basename)
        if not video_path or not video_path.exists():
            logger.warning("download failed: %s", url)
            failures += 1
            continue

        size_mb = video_path.stat().st_size / 1024 / 1024
        logger.info("downloaded %s (%.1f MB)", video_path.name, size_mb)

        # Step 2: Whisper
        try:
            tx = transcribe(video_path)
            logger.info("transcribed: %s, %.1fs, %d chars",
                        tx["language"], tx["duration"], len(tx["text"]))
        except Exception as exc:
            logger.exception("transcribe failed: %s", exc)
            tx = {"language": "?", "duration": 0, "text": "", "segments": []}

        # Skip very long files (probably mistagged)
        if tx.get("duration", 0) > config.SKIP_LONGER_THAN_SECONDS:
            logger.info("skip analysis: too long (%.0fs)", tx["duration"])
            continue

        # Step 3: Gemini
        try:
            analysis = analyze_video(video_path, transcript=tx.get("text"))
            logger.info("gemini analyzed: title=%s, score=%s",
                        analysis.get("original_movie_title"),
                        (analysis.get("viral_factors") or {}).get("score_0_100"))
        except Exception as exc:
            logger.exception("gemini analyze failed: %s", exc)
            analysis = {"error": str(exc)}

        # Step 4: persist
        (out_dir / f"{basename}.json").write_text(
            json.dumps({
                "record": {k: v for k, v in rec.items() if k != "_record_id"},
                "transcript": tx,
                "analysis": analysis,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        write_doc(out_dir, basename, tx, analysis, rec)

        # Step 5: index
        append_index({
            "处理时间":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "发布日期":   out_dir.name,
            "等级":       tier,
            "平台":       rec.get("平台", ""),
            "语言":       rec.get("语言", ""),
            "作者":       rec.get("作者", ""),
            "原片名":     analysis.get("original_movie_title") or "",
            "标题":       (rec.get("标题") or "")[:200],
            "播放量":     rec.get("播放量", ""),
            "视频URL":    url,
            "本地路径":   str(video_path),
        })

        # Step 6: write back
        try:
            write_back_to_bitable(rec, analysis)
        except Exception as exc:
            logger.warning("bitable write-back failed: %s", exc)

        processed_ids.add(vid_id)
        successes += 1

        # Save state after every video — survives crashes
        state["processed_ids"] = sorted(processed_ids)[-5000:]
        state["last_run_ms"] = int(time.time() * 1000)
        save_state(state)

    logger.info("DONE — successes=%d failures=%d", successes, failures)

    # ---- Step 7: backfill follower_count for any creator without one ----
    try:
        from .backfill_followers import main as bf_main
        logger.info("Running follower backfill...")
        bf_main(force=False)
    except Exception as exc:
        logger.exception("Follower backfill failed: %s", exc)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--hours", type=int, default=26,
                   help="Look-back window in hours (default 26)")
    args = p.parse_args()
    main(lookback_hours=args.hours)
