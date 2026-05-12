"""SQLite persistence layer."""

import os
import sqlite3
import time
from typing import Iterable, Optional

DB_PATH = os.getenv("DB_PATH", "videos.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    video_id         TEXT PRIMARY KEY,
    author_id        TEXT,
    author_unique    TEXT,
    caption          TEXT,
    hashtags         TEXT,
    create_time      INTEGER,
    play_count       INTEGER,
    like_count       INTEGER,
    comment_count    INTEGER,
    share_count      INTEGER,
    duration         INTEGER,
    video_url        TEXT,
    cover_url        TEXT,
    matched_tag      TEXT,
    language         TEXT,
    tier             TEXT,
    first_seen_at    INTEGER,
    last_checked_at  INTEGER,
    alerted          INTEGER DEFAULT 0,
    bitable_synced   INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_create_time ON videos(create_time);
CREATE INDEX IF NOT EXISTS idx_play_count  ON videos(play_count);
CREATE INDEX IF NOT EXISTS idx_alerted     ON videos(alerted);
CREATE INDEX IF NOT EXISTS idx_bitable     ON videos(bitable_synced);

CREATE TABLE IF NOT EXISTS authors (
    author_unique         TEXT PRIMARY KEY,
    author_id             TEXT,
    nickname              TEXT,
    follower_count        INTEGER,
    median_plays          INTEGER,
    max_plays_7d          INTEGER,
    posts_14d             INTEGER,
    posts_30d             INTEGER,
    vertical_ratio        REAL,
    language              TEXT,
    status                TEXT,    -- NEW / REJECTED / MONITORED
    reason                TEXT,
    last_evaluated_at     INTEGER,
    first_seen_at         INTEGER,
    bitable_synced        INTEGER DEFAULT 0,
    alerted               INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_author_status  ON authors(status);
CREATE INDEX IF NOT EXISTS idx_author_last    ON authors(last_evaluated_at);
"""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)


def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns that newer versions of the schema introduced but old
    databases don't yet have. Safe to run repeatedly."""
    wanted = {
        "videos": [
            ("language",       "TEXT"),
            ("tier",           "TEXT"),
            ("bitable_synced", "INTEGER DEFAULT 0"),
        ],
        "authors": [],  # created fresh; nothing to migrate
    }
    for table, cols in wanted.items():
        existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        for name, decl in cols:
            if name not in existing:
                try:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
                except sqlite3.OperationalError:
                    pass


# ---------- videos ----------

def upsert_video(row: dict) -> None:
    now = int(time.time())
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO videos (
                video_id, author_id, author_unique, caption, hashtags,
                create_time, play_count, like_count, comment_count,
                share_count, duration, video_url, cover_url, matched_tag,
                language, tier, first_seen_at, last_checked_at
            ) VALUES (
                :video_id, :author_id, :author_unique, :caption, :hashtags,
                :create_time, :play_count, :like_count, :comment_count,
                :share_count, :duration, :video_url, :cover_url, :matched_tag,
                :language, :tier, :first_seen_at, :last_checked_at
            )
            ON CONFLICT(video_id) DO UPDATE SET
                play_count      = excluded.play_count,
                like_count      = excluded.like_count,
                comment_count   = excluded.comment_count,
                share_count     = excluded.share_count,
                caption         = excluded.caption,
                hashtags        = excluded.hashtags,
                language        = excluded.language,
                tier            = CASE
                                    WHEN excluded.tier IS NULL THEN videos.tier
                                    WHEN videos.tier IS NULL THEN excluded.tier
                                    ELSE excluded.tier
                                  END,
                last_checked_at = excluded.last_checked_at
            """,
            {**row, "first_seen_at": now, "last_checked_at": now},
        )


def fetch_unalerted_videos() -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT * FROM videos
            WHERE alerted = 0 AND tier IS NOT NULL
            ORDER BY
              CASE tier WHEN 'RED' THEN 1 WHEN 'ORANGE' THEN 2 WHEN 'YELLOW' THEN 3 ELSE 4 END,
              play_count DESC
            """
        ).fetchall()


def mark_videos_alerted(video_ids: Iterable[str]) -> None:
    if not video_ids:
        return
    with get_conn() as conn:
        conn.executemany(
            "UPDATE videos SET alerted = 1 WHERE video_id = ?",
            [(v,) for v in video_ids],
        )


def fetch_unsynced_videos(limit: int = 200) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT * FROM videos
            WHERE bitable_synced = 0 AND tier IS NOT NULL
            ORDER BY create_time DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()


def mark_videos_synced(video_ids: Iterable[str]) -> None:
    if not video_ids:
        return
    with get_conn() as conn:
        conn.executemany(
            "UPDATE videos SET bitable_synced = 1 WHERE video_id = ?",
            [(v,) for v in video_ids],
        )


# ---------- authors ----------

def touch_author_candidate(
    author_unique: str,
    author_id: str,
    nickname: Optional[str] = None,
    language: Optional[str] = None,
) -> None:
    """Called whenever we encounter an author in a scanned video.
    Inserts a NEW candidate if we've never seen this author."""
    now = int(time.time())
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO authors (
                author_unique, author_id, nickname, language,
                status, first_seen_at
            ) VALUES (?, ?, ?, ?, 'NEW', ?)
            ON CONFLICT(author_unique) DO UPDATE SET
                author_id = COALESCE(authors.author_id, excluded.author_id),
                nickname  = COALESCE(excluded.nickname, authors.nickname),
                language  = COALESCE(excluded.language, authors.language)
            """,
            (author_unique, author_id, nickname, language, now),
        )


def update_author_profile(row: dict) -> None:
    now = int(time.time())
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE authors SET
                nickname          = COALESCE(:nickname, nickname),
                follower_count    = :follower_count,
                median_plays      = :median_plays,
                max_plays_7d      = :max_plays_7d,
                posts_14d         = :posts_14d,
                posts_30d         = :posts_30d,
                vertical_ratio    = :vertical_ratio,
                language          = COALESCE(:language, language),
                status            = :status,
                reason            = :reason,
                last_evaluated_at = :now,
                alerted = CASE
                    WHEN :status = 'MONITORED' AND alerted = 0 THEN 0
                    ELSE alerted
                END
            WHERE author_unique = :author_unique
            """,
            {**row, "now": now},
        )


def fetch_authors_to_evaluate(limit: int, reject_reeval_seconds: int,
                              monitored_refresh_seconds: int) -> list[sqlite3.Row]:
    """Pick authors to (re)evaluate: new first, then stale monitored,
    then stale rejected."""
    now = int(time.time())
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT * FROM authors
            WHERE
              (status = 'NEW') OR
              (status = 'MONITORED' AND (last_evaluated_at IS NULL OR
                    ? - last_evaluated_at > ?)) OR
              (status = 'REJECTED' AND (last_evaluated_at IS NULL OR
                    ? - last_evaluated_at > ?))
            ORDER BY
              CASE status
                WHEN 'NEW' THEN 0
                WHEN 'MONITORED' THEN 1
                WHEN 'REJECTED' THEN 2
                ELSE 3
              END,
              COALESCE(last_evaluated_at, 0) ASC
            LIMIT ?
            """,
            (now, monitored_refresh_seconds,
             now, reject_reeval_seconds, limit),
        ).fetchall()


def fetch_unalerted_monitored_authors() -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM authors WHERE status = 'MONITORED' AND alerted = 0"
        ).fetchall()


def mark_authors_alerted(author_uniques: Iterable[str]) -> None:
    if not author_uniques:
        return
    with get_conn() as conn:
        conn.executemany(
            "UPDATE authors SET alerted = 1 WHERE author_unique = ?",
            [(u,) for u in author_uniques],
        )


def fetch_unsynced_monitored_authors(limit: int = 200) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT * FROM authors
            WHERE status = 'MONITORED' AND bitable_synced = 0
            ORDER BY last_evaluated_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()


def mark_authors_synced(author_uniques: Iterable[str]) -> None:
    if not author_uniques:
        return
    with get_conn() as conn:
        conn.executemany(
            "UPDATE authors SET bitable_synced = 1 WHERE author_unique = ?",
            [(u,) for u in author_uniques],
        )


def recent_stats() -> dict:
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) AS n FROM videos").fetchone()["n"]
        alerted = conn.execute(
            "SELECT COUNT(*) AS n FROM videos WHERE alerted = 1"
        ).fetchone()["n"]
        monitored = conn.execute(
            "SELECT COUNT(*) AS n FROM authors WHERE status = 'MONITORED'"
        ).fetchone()["n"]
    return {"total": total, "alerted": alerted, "monitored": monitored}
