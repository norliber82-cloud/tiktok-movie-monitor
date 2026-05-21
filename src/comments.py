"""Extract the original movie/show title from TikTok video comments.

Strategy:
1. Pull top 20 comments (sorted by likes — most useful ones float up)
2. Check the author's own pinned/first comment (often contains the title)
3. Look for patterns:
   - 《...》 or 「...」 (CJK title brackets)
   - "..." or '...' (quoted titles)
   - Replies to "what movie" / "movie name" / "片名" / "なんの映画"
   - Lines starting with common prefixes: "Movie:", "Film:", "Title:"
4. Return the best candidate or empty string
"""

from __future__ import annotations

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Patterns that typically contain the movie title
_TITLE_BRACKETS = re.compile(r'[《「]([^》」]{2,60})[》」]')
_TITLE_QUOTES = re.compile(r'[""\'\'「」]([A-Za-z0-9\s\-\':\.]{3,60})[""\'\'「」]')
_TITLE_PREFIX = re.compile(
    r'(?:movie|film|title|name|片名|原片|电影名|映画)\s*[:：]\s*(.{2,60})',
    re.IGNORECASE,
)
# Common "what movie" question patterns (the REPLY to these often has the title)
_QUESTION_PATTERNS = [
    "what movie", "what film", "what's the movie", "what is this movie",
    "movie name", "film name", "name of the movie", "title?",
    "什么电影", "什么片", "片名", "哪部电影", "电影名",
    "なんの映画", "映画の名前", "タイトル",
]


def extract_title_from_comments(comments: list[dict],
                                author_unique: str = "") -> str:
    """Given a list of comment dicts, try to extract the movie title.

    Each comment dict should have:
      - text: str (comment body)
      - user: str (commenter username)
      - likes: int
      - is_author: bool (whether the commenter is the video author)

    Returns the extracted title or empty string.
    """
    if not comments:
        return ""

    # Priority 1: Author's own comment (often pinned with the title)
    for c in comments:
        if c.get("is_author"):
            title = _try_extract(c.get("text", ""))
            if title:
                return title

    # Priority 2: Most-liked comment that looks like a title
    for c in sorted(comments, key=lambda x: x.get("likes", 0), reverse=True):
        title = _try_extract(c.get("text", ""))
        if title:
            return title

    # Priority 3: Any comment that's a reply to a "what movie" question
    # (simplified: just scan all comments for title patterns)
    for c in comments:
        text = c.get("text", "")
        # If this comment IS a question, skip it — we want the answer
        if any(q in text.lower() for q in _QUESTION_PATTERNS):
            continue
        title = _try_extract(text)
        if title:
            return title

    return ""


def _try_extract(text: str) -> str:
    """Try to pull a movie title from a single comment text."""
    if not text:
        return ""

    # CJK brackets: 《电影名》 or 「映画名」
    m = _TITLE_BRACKETS.search(text)
    if m:
        return m.group(1).strip()

    # Prefix patterns: "Movie: Title" / "片名：xxx"
    m = _TITLE_PREFIX.search(text)
    if m:
        candidate = m.group(1).strip().rstrip(".,!?。！？")
        if len(candidate) >= 2:
            return candidate

    # Quoted English titles: "The Shawshank Redemption"
    m = _TITLE_QUOTES.search(text)
    if m:
        candidate = m.group(1).strip()
        # Filter out generic phrases
        if len(candidate) >= 3 and not _is_generic(candidate):
            return candidate

    return ""


def _is_generic(text: str) -> bool:
    """Filter out common phrases that aren't movie titles."""
    generic = {
        "thank you", "thanks", "please", "follow me", "like and share",
        "part 1", "part 2", "part 3", "check out", "link in bio",
    }
    return text.lower().strip() in generic


async def fetch_comments_for_video(api, video_id: str, count: int = 20,
                                   author_unique: str = "") -> list[dict]:
    """Pull comments for a video using TikTokApi.

    Returns list of {text, user, likes, is_author}.
    """
    comments = []
    try:
        video = api.video(id=video_id)
        async for comment in video.comments(count=count):
            cd = comment.as_dict
            user_info = cd.get("user", {}) or {}
            commenter = user_info.get("uniqueId") or user_info.get("unique_id") or ""
            comments.append({
                "text": cd.get("text", "") or "",
                "user": commenter,
                "likes": int(cd.get("digg_count", 0) or 0),
                "is_author": (commenter.lower() == author_unique.lower()
                              if author_unique else False),
            })
    except Exception as exc:
        logger.debug("comments for %s failed: %s", video_id, str(exc)[:80])
    return comments
