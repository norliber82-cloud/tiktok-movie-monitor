"""Movie-commentary, language and creator-eligibility classifiers."""

from statistics import median
from typing import Optional

from .config import (
    CREATOR_CADENCE_14D_MIN,
    CREATOR_CADENCE_30D_MIN,
    CREATOR_MEDIAN_MAX,
    CREATOR_MEDIAN_MIN,
    CREATOR_VERTICAL_RATIO_MIN,
    CREATOR_VIRAL_MIN,
    CREATOR_VIRAL_MULTIPLIER,
    CREATOR_VIRAL_WINDOW_DAY,
    DISCOVERY_HASHTAGS,
    HASHTAGS,
    HASHTAGS_JA,
    HASHTAGS_ZH,
    KEYWORDS_IN,
    KEYWORDS_OUT,
    TIERS,
)

_HASHTAG_WHITELIST = {h.lower() for h in (HASHTAGS + DISCOVERY_HASHTAGS)} | {
    "movie", "film", "cinema", "movies", "films", "映画", "电影", "影视",
}


# ------------------------- movie commentary -------------------------

def is_movie_commentary(caption: str, hashtags: list[str]) -> bool:
    cap_lower = f" {(caption or '').lower()} "
    if any(bad in cap_lower for bad in KEYWORDS_OUT):
        return False
    if any(good in cap_lower for good in KEYWORDS_IN):
        return True
    tag_set = {t.lower() for t in (hashtags or [])}
    if tag_set & _HASHTAG_WHITELIST:
        return True
    return False


# ------------------------- tier detection -------------------------

def classify_tier(create_time: int, play_count: int, now_ts: int) -> Optional[str]:
    """Return 'RED'/'ORANGE'/'YELLOW' or None. First matching tier wins,
    and tiers are iterated from strictest (highest views) to loosest."""
    age_h = (now_ts - create_time) / 3600.0
    for code, _, _, min_views, max_age_h, _ in TIERS:
        if play_count >= min_views and age_h <= max_age_h:
            return code
    return None


def tier_meta(code: str) -> dict:
    for c, label, color, min_views, max_age_h, rank in TIERS:
        if c == code:
            return {
                "code": c, "label": label, "color": color,
                "min_views": min_views, "max_age_h": max_age_h, "rank": rank,
            }
    return {}


# ------------------------- language detection -------------------------

_JA_HASHTAGS = {h.lower() for h in HASHTAGS_JA}
_ZH_HASHTAGS = {h.lower() for h in HASHTAGS_ZH}


def detect_language(api_lang: str, caption: str, hashtags: list[str]) -> str:
    """Use TikTok's declared textLanguage when present, otherwise guess."""
    if api_lang:
        api_lang = api_lang.lower()
        # normalize to 2-letter codes we care about
        if api_lang.startswith("en"): return "en"
        if api_lang.startswith("ja"): return "ja"
        if api_lang.startswith("zh"): return "zh"
        if api_lang.startswith("ko"): return "ko"
        if api_lang.startswith("es"): return "es"
        if api_lang.startswith("pt"): return "pt"
        return api_lang[:2]

    # Hashtag-based hint
    tag_set = {t.lower() for t in (hashtags or [])}
    if tag_set & _JA_HASHTAGS:
        return "ja"
    if tag_set & _ZH_HASHTAGS:
        return "zh"

    # Character-based quick check
    text = caption or ""
    if _has_cjk_japanese(text):
        return "ja"
    if _has_cjk_chinese(text):
        return "zh"

    # langdetect fallback (imported lazily; optional)
    try:
        from langdetect import detect, DetectorFactory
        DetectorFactory.seed = 0
        if text.strip():
            lang = detect(text)
            if lang.startswith("en"): return "en"
            if lang.startswith("ja"): return "ja"
            if lang.startswith("zh"): return "zh"
            return lang[:2]
    except Exception:
        pass

    return "en"  # default assumption


def _has_cjk_japanese(s: str) -> bool:
    # Hiragana or Katakana ⇒ definitely Japanese
    for ch in s:
        o = ord(ch)
        if 0x3040 <= o <= 0x309F or 0x30A0 <= o <= 0x30FF:
            return True
    return False


def _has_cjk_chinese(s: str) -> bool:
    # CJK Unified Ideographs without kana ⇒ Chinese
    for ch in s:
        o = ord(ch)
        if 0x4E00 <= o <= 0x9FFF:
            return True
    return False


# ------------------------- creator eligibility -------------------------

def evaluate_creator(videos: list[dict], now_ts: int) -> dict:
    """Given recent videos as dicts (keys: play_count, create_time, caption, hashtags),
    return a dict with computed metrics + status + reason.

    With small samples (1-2 videos), we use relaxed criteria:
    - Must be movie-commentary (vertical check)
    - Median plays in the 10K-100K band
    - At least one video qualifies as "viral" relative to the median
    """
    if not videos:
        return {
            "status": "REJECTED", "reason": "no_videos",
            "median_plays": None, "max_plays_7d": None,
            "posts_14d": 0, "posts_30d": 0, "vertical_ratio": None,
        }

    plays = [v["play_count"] or 0 for v in videos]
    median_plays = int(median(plays)) if plays else 0

    window_7d = now_ts - CREATOR_VIRAL_WINDOW_DAY * 86400
    window_14d = now_ts - 14 * 86400
    window_30d = now_ts - 30 * 86400

    recent_7d_plays = [v["play_count"] or 0 for v in videos
                       if v["create_time"] >= window_7d]
    max_plays_7d = max(recent_7d_plays) if recent_7d_plays else 0
    posts_14d = sum(1 for v in videos if v["create_time"] >= window_14d)
    posts_30d = sum(1 for v in videos if v["create_time"] >= window_30d)

    vertical_hits = sum(
        1 for v in videos
        if is_movie_commentary(v.get("caption", ""), v.get("hashtags", []))
    )
    vertical_ratio = vertical_hits / len(videos)

    # Gate checks — relaxed for small samples
    reasons = []
    if not (CREATOR_MEDIAN_MIN <= median_plays <= CREATOR_MEDIAN_MAX):
        reasons.append(f"median_out_of_range({median_plays})")

    # For small samples (1-2 videos), skip cadence check and relax viral threshold
    if len(videos) >= 3:
        if max_plays_7d < CREATOR_VIRAL_MIN or max_plays_7d < median_plays * CREATOR_VIRAL_MULTIPLIER:
            reasons.append(f"no_viral_7d(max={max_plays_7d})")
        if posts_14d < CREATOR_CADENCE_14D_MIN and posts_30d < CREATOR_CADENCE_30D_MIN:
            reasons.append(f"low_cadence(14d={posts_14d},30d={posts_30d})")
    else:
        # Small sample: just check if the video(s) we have show viral potential
        if max_plays_7d < CREATOR_MEDIAN_MIN * 3:
            reasons.append(f"no_viral_signal(max={max_plays_7d})")

    if vertical_ratio < CREATOR_VERTICAL_RATIO_MIN:
        reasons.append(f"low_vertical({vertical_ratio:.2f})")

    status = "MONITORED" if not reasons else "REJECTED"

    return {
        "status": status,
        "reason": ";".join(reasons) if reasons else "ok",
        "median_plays": median_plays,
        "max_plays_7d": max_plays_7d,
        "posts_14d": posts_14d,
        "posts_30d": posts_30d,
        "vertical_ratio": round(vertical_ratio, 3),
    }
