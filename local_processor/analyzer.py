"""Use Gemini 2.5 Flash to analyze the video (multimodal: file upload).

Returns structured analysis: hook, structure, viral factors, original movie title.
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional

from google import genai
from google.genai import types

from . import config

logger = logging.getLogger(__name__)

_client: Optional[genai.Client] = None


def get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client


PROMPT = """You are an expert short-video content analyst specializing in movie-commentary content (#filmtok / #映画解説).

Analyze the attached video and respond with **ONLY** a JSON object in this exact schema:

{
  "original_movie_title": "the actual movie/show this commentary is about (in original language + English where helpful, e.g. '让子弹飞 / Let the Bullets Fly'). null if you cannot identify it.",
  "year": 2010,
  "language": "en | ja | zh | ko | other",
  "duration_estimate_seconds": 60,
  "structure": {
    "hook_seconds_0_3": "exact opening line (the first 3-second hook)",
    "hook_type": "question | shock | claim | promise | scenario | second_person | other",
    "main_beats": [
      {"t": "0:03", "what": "what happens at this beat"},
      {"t": "0:15", "what": "..."}
    ],
    "ending_cta": "the closing line / call-to-action",
    "pace": "fast | medium | slow",
    "narration_voice": "male | female | unclear",
    "narration_style": "AI-tts | real-human | unknown"
  },
  "viral_factors": {
    "score_0_100": 78,
    "factors_present": ["strong second-person hook", "controversial take", "..."],
    "factors_missing": ["no music drop", "..."],
    "comments_bait": "what makes people comment"
  },
  "thumbnail_or_caption_in_video": "any on-screen text shown in the video (the big bold title overlay)",
  "summary_one_sentence": "single-sentence summary of what the creator's claim is",
  "transcript_quality_check": "If a transcript is provided, point out anything Whisper got wrong"
}

Be concise. If you can't tell something, use null. Respond with ONLY valid JSON, no markdown fences."""


def _wait_for_file_active(client: genai.Client, name: str,
                          timeout_sec: int = 90) -> bool:
    """Gemini File API: uploaded files start in 'PROCESSING' state."""
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        f = client.files.get(name=name)
        if f.state.name == "ACTIVE":
            return True
        if f.state.name == "FAILED":
            return False
        time.sleep(2)
    return False


def analyze_video(video_path: Path, transcript: str | None = None) -> dict:
    """Upload the video to Gemini, ask for structured analysis, return dict."""
    client = get_client()

    logger.info("Uploading %s to Gemini File API...", video_path.name)
    uploaded = client.files.upload(file=str(video_path))

    if not _wait_for_file_active(client, uploaded.name):
        return {"error": "file_processing_failed",
                "name": uploaded.name}

    parts = [uploaded]
    prompt_with_transcript = PROMPT
    if transcript:
        snippet = transcript[:4000]
        prompt_with_transcript += (
            f"\n\nWhisper transcript (provided to help identify the original movie / catch quotes):\n{snippet}"
        )
    parts.append(prompt_with_transcript)

    response_text = None
    last_err = None
    for attempt in range(config.GEMINI_MAX_RETRIES):
        # On retries, alternate model to dodge per-model overload
        model = (config.GEMINI_MODEL if attempt % 2 == 0
                 else config.GEMINI_MODEL_FALLBACK)
        try:
            response = client.models.generate_content(
                model=model,
                contents=parts,
                config=types.GenerateContentConfig(
                    temperature=0.4,
                    response_mime_type="application/json",
                    http_options=types.HttpOptions(timeout=120 * 1000),
                ),
            )
            response_text = response.text
            break
        except Exception as exc:
            last_err = exc
            msg = str(exc)
            logger.warning("Gemini attempt %d/%d on %s failed: %s",
                           attempt + 1, config.GEMINI_MAX_RETRIES, model, msg[:200])
            # Only retry on transient errors
            if not any(s in msg for s in ("503", "UNAVAILABLE", "RESOURCE_EXHAUSTED",
                                          "429", "deadline", "timeout")):
                break
            time.sleep(config.GEMINI_RETRY_BACKOFF_SEC * (attempt + 1))

    if response_text is None:
        try: client.files.delete(name=uploaded.name)
        except Exception: pass
        return {"error": "gemini_call_failed", "detail": str(last_err)}

    raw = response_text

    # Always clean up the uploaded file (free quota: 50 GB cumulative)
    try:
        client.files.delete(name=uploaded.name)
    except Exception:
        pass

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Strip code fences if Gemini wrapped it
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```", 2)[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.strip("` \n")
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return {"error": "json_parse_failed", "raw": raw[:2000]}
