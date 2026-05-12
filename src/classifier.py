"""Decide whether a given video is movie commentary."""

from .config import KEYWORDS_IN, KEYWORDS_OUT, HASHTAGS

# Hashtag whitelist is the hashtag pool itself plus a couple of broad ones.
_HASHTAG_WHITELIST = {h.lower() for h in HASHTAGS} | {
    "movie", "film", "cinema", "movies", "films",
}


def is_movie_commentary(caption: str, hashtags: list[str]) -> bool:
    """Classify a video based on caption text and hashtags.

    Logic:
        - If any exclusion keyword matches caption, reject.
        - If any inclusion keyword matches caption, accept.
        - If any whitelisted hashtag is present, accept.
        - Otherwise reject.
    """
    cap_lower = f" {(caption or '').lower()} "
    if any(bad in cap_lower for bad in KEYWORDS_OUT):
        return False

    if any(good in cap_lower for good in KEYWORDS_IN):
        return True

    tag_set = {t.lower() for t in (hashtags or [])}
    if tag_set & _HASHTAG_WHITELIST:
        return True

    return False
