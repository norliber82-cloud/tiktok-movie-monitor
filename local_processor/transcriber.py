"""Transcribe video audio with faster-whisper (GPU-accelerated)."""

import logging
from functools import lru_cache
from pathlib import Path

from faster_whisper import WhisperModel

from . import config

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_model() -> WhisperModel:
    logger.info("Loading Whisper model %s on %s (%s)...",
                config.WHISPER_MODEL, config.WHISPER_DEVICE,
                config.WHISPER_COMPUTE_TYPE)
    return WhisperModel(
        config.WHISPER_MODEL,
        device=config.WHISPER_DEVICE,
        compute_type=config.WHISPER_COMPUTE_TYPE,
    )


def transcribe(video_path: Path) -> dict:
    """Returns {'language': 'en', 'duration': 60.5, 'text': '...', 'segments': [...]}.

    Returns an empty-text result if the video has no usable audio stream
    (corrupted file, video-only, etc.) instead of crashing."""
    model = get_model()
    try:
        segments_iter, info = model.transcribe(
            str(video_path),
            beam_size=5,
            vad_filter=True,
            language=config.TRANSCRIBE_LANGUAGE,
        )
        segments = []
        full_text = []
        for seg in segments_iter:
            segments.append({
                "start": round(seg.start, 2),
                "end": round(seg.end, 2),
                "text": seg.text.strip(),
            })
            full_text.append(seg.text.strip())
        return {
            "language": info.language,
            "language_probability": round(info.language_probability, 3),
            "duration": round(info.duration, 2),
            "text": " ".join(full_text),
            "segments": segments,
        }
    except Exception as exc:
        logger.warning("Whisper transcribe failed for %s: %s", video_path, exc)
        return {
            "language": "?",
            "language_probability": 0.0,
            "duration": 0.0,
            "text": "",
            "segments": [],
            "error": str(exc),
        }
