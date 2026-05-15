"""Smoke test: download + transcribe + analyze ONE specific video URL."""

import json
import logging
import sys
from pathlib import Path

from . import config
from .analyzer import analyze_video
from .downloader import download, safe_filename
from .transcriber import transcribe


def main(url: str):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
        stream=sys.stdout,
    )
    log = logging.getLogger("test")

    out_dir = config.DOWNLOAD_ROOT / "_smoke_test"
    out_dir.mkdir(parents=True, exist_ok=True)
    basename = "smoke_" + safe_filename(url.split("/")[-1].split("?")[0], 20)

    log.info("[1/3] Downloading %s", url)
    video_path = download(url, out_dir, basename)
    if not video_path or not video_path.exists():
        log.error("Download failed!")
        sys.exit(1)
    log.info("OK file: %s (%.1f MB)", video_path,
             video_path.stat().st_size / 1024 / 1024)

    log.info("[2/3] Transcribing with Whisper (large-v3 on GPU)...")
    tx = transcribe(video_path)
    log.info("Transcribed: %s, %.1fs", tx["language"], tx["duration"])
    log.info("Text (first 200 chars): %s", tx["text"][:200])

    log.info("[3/3] Sending to Gemini for analysis...")
    analysis = analyze_video(video_path, transcript=tx.get("text"))
    log.info("Analysis result:")
    print(json.dumps(analysis, ensure_ascii=False, indent=2))

    # Save outputs
    (out_dir / f"{basename}.json").write_text(
        json.dumps({"transcript": tx, "analysis": analysis},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info("Saved to %s.json", out_dir / basename)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m local_processor.test_one <video_url>")
        sys.exit(2)
    main(sys.argv[1])
