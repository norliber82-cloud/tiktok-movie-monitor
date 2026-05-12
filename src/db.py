"""SQLite persistence layer."""

import os
import sqlite3
import time
from typing import Iterable, Optional

DB_PATH = os.getenv("DB_PATH", "videos.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    video_id        TEXT PRIMARY KEY,
    author_id       TEXT,
    author_unique   TEXT,
    caption         TEXT,
    hashtags        TEXT,
    create_time     INTEGER,
    play_count      INTEGER,
    like_count      INTEGER,
    comment_count   INTEGER,
    share_count     INTEGER,
    duration        INTEGER,
    video_url       TEXT,
    cover_url       TEXT,
    matched_tag     TEXT,
    first_seen_at   INTEGER,
    last_checked_at INTEGER,
    alerted         INTEGER DEFAULT 0,
    alert_tier      INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_create_time ON videos(create_time);
CREATE INDEX IF NOT EXISTS idx_play_count  ON videos(play_count);
CREATE INDEX IF NOT EXISTS idx_alerted     ON videos(alerted);
"""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def upsert_video(row: dict) -> None:
    now = int(time.time())
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO videos (
                video_id, author_id, author_unique, caption, hashtags,
                create_time, play_count, like_count, comment_count,
                share_count, duration, video_url, cover_url, matched_tag,
                first_seen_at, last_checked_at
            ) VALUES (
                :video_id, :author_id, :author_unique, :caption, :hashtags,
                :create_time, :play_count, :like_count, :comment_count,
                :share_count, :duration, :video_url, :cover_url, :matched_tag,
                :first_seen_at, :last_checked_at
            )
            ON CONFLICT(video_id) DO UPDATE SET
                play_count      = excluded.play_count,
                like_count      = excluded.like_count,
                comment_count   = excluded.comment_count,
                share_count     = excluded.share_count,
                caption         = excluded.caption,
                hashtags        = excluded.hashtags,
                last_checked_at = excluded.last_checked_at
            """,
            {**row, "first_seen_at": now, "last_checked_at": now},
        )


def fetch_unalerted(min_views: int) -> list[sqlite3.Row]:
    with get_conn() as conn:
        cur = conn.execute(
            """
            SELECT * FROM videos
            WHERE alerted = 0 AND play_count >= ?
            ORDER BY play_count DESC
            """,
            (min_views,),
        )
        return cur.fetchall()


def mark_alerted(video_ids: Iterable[str], tier: Optional[int] = None) -> None:
    if not video_ids:
        return
    with get_conn() as conn:
        for vid in video_ids:
            conn.execute(
                "UPDATE videos SET alerted = 1, alert_tier = COALESCE(?, alert_tier) WHERE video_id = ?",
                (tier, vid),
            )


def recent_stats() -> dict:
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) AS n FROM videos").fetchone()["n"]
        alerted = conn.execute(
            "SELECT COUNT(*) AS n FROM videos WHERE alerted = 1"
        ).fetchone()["n"]
    return {"total": total, "alerted": alerted}
