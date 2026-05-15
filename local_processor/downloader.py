"""Download watermark-free source videos via yt-dlp."""

import logging
import re
from pathlib import Path

import yt_dlp

from . import config

logger = logging.getLogger(__name__)

_BAD_FS_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_filename(s: str, max_len: int = 60) -> str:
    s = _BAD_FS_CHARS.sub("_", s).strip(". _")
    return s[:max_len] if s else "untitled"


def download(video_url: str, out_dir: Path, basename: str) -> Path | None:
    """Download a TikTok or YouTube video to out_dir/basename.mp4."""
    out_dir.mkdir(parents=True, exist_ok=True)
    out_template = str(out_dir / f"{basename}.%(ext)s")

    is_tiktok = "tiktok.com" in video_url

    ydl_opts = {
        "outtmpl": out_template,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": config.DOWNLOAD_TIMEOUT_SEC,
        # Best mp4-compatible quality, watermark-free for TikTok
        "format": "bv*+ba/b" if not is_tiktok else "best",
        "merge_output_format": "mp4",
        # Friendly UA to avoid 403s
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/131.0 Safari/537.36",
        },
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
    except Exception as exc:
        logger.warning("download failed for %s: %s", video_url, exc)
        return None

    final_path = Path(ydl.prepare_filename(info)).with_suffix(".mp4")
    if final_path.exists():
        return final_path
    # Fallback: any file matching basename in out_dir
    for p in out_dir.glob(f"{basename}.*"):
        if p.is_file():
            return p
    return None
