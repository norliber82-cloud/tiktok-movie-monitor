"""Extract the original movie/show title from TikTok video comments.

Uses Apify's `clockworks/tiktok-comments-scraper` actor to fetch comments
(reliable on GitHub Actions, since it runs on Apify's infrastructure).

Strategy:
1. Pull top N comments per video via Apify (single batch call for many videos)
2. Heavily prioritize:
   - Author-pinned comments (the gold standard for movie titles)
   - Author-liked comments (author confirmed the answer)
3. Apply pattern matching for titles:
   - 《...》 or 「...」 (CJK title brackets)
   - "..." or '...' (quoted titles)
   - Lines starting with "Movie:", "Film:", "Title:", "片名："
4. Return the best candidate or empty string
"""

from __future__ import annotations

import logging
import os
import re
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ============================================================
# Title pattern matching
# ============================================================

_TITLE_BRACKETS = re.compile(r'[《「]([^》」]{2,60})[》」]')
_TITLE_QUOTES = re.compile(r'[""\'\'「」]([A-Za-z0-9\s\-\':\.]{3,60})[""\'\'「」]')
_TITLE_PREFIX = re.compile(
    r'(?:movie|film|title|name|片名|原片|电影名|映画)\s*[:：]\s*(.{2,60})',
    re.IGNORECASE,
)
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
      - text: str
      - user: str
      - likes: int
      - is_author: bool (commenter == video author)
      - pinned_by_author: bool
      - liked_by_author: bool
    """
    if not comments:
        return ""

    # Priority 1: Author's own comment, especially if pinned
    for c in comments:
        if c.get("pinned_by_author") or c.get("is_author"):
            title = _try_extract(c.get("text", ""))
            if title:
                return title

    # Priority 2: Comments the author has liked
    for c in comments:
        if c.get("liked_by_author"):
            title = _try_extract(c.get("text", ""))
            if title:
                return title

    # Priority 3: ANY comment with high-confidence patterns
    # (explicit "title:" prefix or 《CJK brackets》) — sorted by likes
    for c in sorted(comments, key=lambda x: x.get("likes", 0), reverse=True):
        text = c.get("text", "")
        if any(q in text.lower() for q in _QUESTION_PATTERNS):
            continue
        title = _try_extract_high_confidence(text)
        if title:
            return title

    # Priority 4: Frequency-based — multiple commenters mention the same
    # CJK proper noun → likely the movie/show title
    title = _frequency_based_extract(comments)
    if title:
        return title

    # Priority 5: Quoted strings (lowest confidence — could be slang)
    for c in sorted(comments, key=lambda x: x.get("likes", 0), reverse=True):
        text = c.get("text", "")
        if any(q in text.lower() for q in _QUESTION_PATTERNS):
            continue
        title = _try_extract(text)
        if title:
            return title

    return ""


def _try_extract_high_confidence(text: str) -> str:
    """Only the patterns we're highly confident about — title prefix + CJK brackets."""
    if not text:
        return ""
    m = _TITLE_PREFIX.search(text)
    if m:
        candidate = m.group(1).strip().rstrip(".,!?。！？")
        if len(candidate) >= 2:
            return candidate
    m = _TITLE_BRACKETS.search(text)
    if m:
        return m.group(1).strip()
    return ""


# Match short CJK strings that look like proper nouns (movie/show titles).
# Only picks up things like "キサラギ", "如月", "三体" — not full sentences.
_CJK_TITLE_CANDIDATE = re.compile(
    r'(?<![\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF])'
    r'([\u30A0-\u30FF\u4E00-\u9FFF]{2,10})'
    r'(?![\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF])'
)


def _frequency_based_extract(comments: list[dict]) -> str:
    """Find a CJK proper noun mentioned in multiple comments — likely the
    movie/show title."""
    from collections import Counter

    counter: Counter[str] = Counter()
    for c in comments:
        text = c.get("text", "") or ""
        # Skip very short comments and replies
        if len(text) < 2:
            continue
        for m in _CJK_TITLE_CANDIDATE.finditer(text):
            cand = m.group(1).strip()
            # Filter: skip common everyday words
            if cand in _COMMON_CJK_NOISE:
                continue
            counter[cand] += 1

    if not counter:
        return ""
    most_common, count = counter.most_common(1)[0]
    # Need at least 2 mentions across different comments to trust it
    if count >= 2:
        return most_common
    return ""


# Common CJK words that aren't movie titles
_COMMON_CJK_NOISE = {
    "映画", "電影", "电影", "好看", "面白", "ありがと", "感動", "好き",
    "見たい", "見ました", "教え", "知りたい", "観たい", "ネタバレ",
    "好きで", "好きな", "観た", "見た", "好きすぎ", "ほんと", "本当",
    "今日", "明日", "昨日", "最近", "最高", "最後", "最初",
    "什么", "什麽", "推荐", "好看", "解说", "解說", "电影名",
}


def _try_extract(text: str) -> str:
    if not text:
        return ""

    # Priority 1: explicit "title:" / "片名：" prefix (highest confidence)
    m = _TITLE_PREFIX.search(text)
    if m:
        candidate = m.group(1).strip().rstrip(".,!?。！？")
        if len(candidate) >= 2:
            return candidate

    # Priority 2: CJK title brackets — 《电影名》 or 「映画名」
    m = _TITLE_BRACKETS.search(text)
    if m:
        return m.group(1).strip()

    # Priority 3: Quoted English titles (lowest confidence — could be slang)
    m = _TITLE_QUOTES.search(text)
    if m:
        candidate = m.group(1).strip()
        # Filter out: too short, generic phrases, single word lower-case
        # (titles usually capitalized or have multiple words)
        if (len(candidate) >= 4
                and not _is_generic(candidate)
                and (candidate[0].isupper() or " " in candidate)):
            return candidate

    return ""


def _is_generic(text: str) -> bool:
    generic = {
        "thank you", "thanks", "please", "follow me", "like and share",
        "part 1", "part 2", "part 3", "check out", "link in bio",
    }
    return text.lower().strip() in generic


# ============================================================
# Apify integration
# ============================================================

APIFY_ACTOR = "clockworks~tiktok-comments-scraper"
APIFY_API = f"https://api.apify.com/v2/acts/{APIFY_ACTOR}/run-sync-get-dataset-items"


def fetch_comments_via_apify(video_urls: list[str], comments_per_post: int = 10
                             ) -> dict[str, list[dict]]:
    """Pull comments for many videos in a single Apify run.

    Returns {video_url: [{text, user, likes, is_author, pinned_by_author,
                          liked_by_author}, ...]}.

    The video_urls must be full TikTok URLs like:
      https://www.tiktok.com/@username/video/12345
    """
    token = os.getenv("APIFY_API_TOKEN", "").strip()
    if not token:
        logger.warning("APIFY_API_TOKEN not set — comments will be empty")
        return {}
    if not video_urls:
        return {}

    body = {
        "postURLs": video_urls,
        "commentsPerPost": comments_per_post,
        "maxRepliesPerComment": 0,  # we only need top-level
    }
    url = f"{APIFY_API}?token={token}"
    try:
        r = requests.post(url, json=body, timeout=600)
        r.raise_for_status()
        items = r.json()
    except Exception as exc:
        logger.warning("Apify comments call failed: %s", exc)
        return {}

    # Group comments by submitted video URL
    grouped: dict[str, list[dict]] = {u: [] for u in video_urls}
    for it in items:
        submitted = it.get("submittedVideoUrl") or it.get("input")
        if not submitted or submitted not in grouped:
            continue
        # Determine the video author from the actual videoWebUrl
        video_web = it.get("videoWebUrl", "")
        video_author = ""
        if video_web:
            m = re.search(r"@([^/]+)/", video_web)
            if m:
                video_author = m.group(1)
        commenter = it.get("uniqueId") or ""
        grouped[submitted].append({
            "text": (it.get("text") or "").strip(),
            "user": commenter,
            "likes": int(it.get("diggCount") or 0),
            "is_author": commenter.lower() == video_author.lower() if video_author else False,
            "pinned_by_author": bool(it.get("pinnedByAuthor")),
            "liked_by_author": bool(it.get("likedByAuthor")),
        })

    logger.info("Apify pulled comments for %d/%d videos",
                sum(1 for v in grouped.values() if v), len(video_urls))
    return grouped


def extract_titles_via_apify(video_urls_with_authors: list[tuple[str, str]],
                             comments_per_post: int = 10
                             ) -> dict[str, str]:
    """Convenience wrapper: takes (video_url, author_unique) pairs,
    fetches comments via Apify, extracts titles.

    Returns {video_url: title}, only including non-empty titles.
    """
    if not video_urls_with_authors:
        return {}
    urls = [pair[0] for pair in video_urls_with_authors]
    author_map = {pair[0]: pair[1] for pair in video_urls_with_authors}

    comments_by_url = fetch_comments_via_apify(urls, comments_per_post)

    titles: dict[str, str] = {}
    for url, comments in comments_by_url.items():
        if not comments:
            continue
        author = author_map.get(url, "")
        title = extract_title_from_comments(comments, author_unique=author)
        if title:
            titles[url] = title
    return titles


# ============================================================
# TikTokApi fallback (kept for compatibility but unused now)
# ============================================================

async def fetch_comments_for_video(api, video_id: str, count: int = 20,
                                   author_unique: str = "") -> list[dict]:
    """Legacy fallback. Apify is preferred."""
    comments = []
    try:
        video = api.video(id=video_id)
        async for comment in video.comments(count=count):
            try:
                text = (getattr(comment, "text", "") or "").strip()
                if not text:
                    continue
                likes = int(getattr(comment, "likes_count", 0) or 0)
                author_obj = getattr(comment, "author", None)
                commenter = ""
                if author_obj is not None:
                    commenter = (getattr(author_obj, "username", "")
                                 or getattr(author_obj, "user_id", "") or "")
                comments.append({
                    "text": text,
                    "user": commenter,
                    "likes": likes,
                    "is_author": (commenter.lower() == author_unique.lower()
                                  if author_unique and commenter else False),
                    "pinned_by_author": False,
                    "liked_by_author": False,
                })
            except Exception:
                continue
    except Exception as exc:
        logger.warning("comments for %s failed: %s", video_id, str(exc)[:120])
    return comments
