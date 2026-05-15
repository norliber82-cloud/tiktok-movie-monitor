"""One-shot: scan videos table for tier-hit authors and promote them
to MONITORED status (with dedupe via INSERT OR IGNORE / UPDATE).

Run inside the next deep workflow once, or locally with the same DB.
"""

import logging
import sys

sys.path.insert(0, ".")
from src import db
from src.collector import logger as col_logger


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s | %(message)s",
        stream=sys.stdout,
    )
    log = logging.getLogger("backfill")

    db.init_db()

    # Get every tier-hit (RED/ORANGE/YELLOW) author from the videos table
    with db.get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
                author_unique,
                MAX(author_id) AS author_id,
                MAX(language)  AS language,
                MAX(play_count) AS max_plays,
                MAX(create_time) AS latest_create
            FROM videos
            WHERE tier IS NOT NULL
              AND author_unique IS NOT NULL
              AND author_unique != ''
            GROUP BY author_unique
            """
        ).fetchall()

    log.info("Found %d distinct tier-hit authors", len(rows))

    promoted = 0
    for r in rows:
        db.promote_viral_author(
            author_unique=r["author_unique"],
            author_id=r["author_id"] or "",
            nickname=None,                # we don't have nickname for old data
            language=r["language"],
            play_count=r["max_plays"] or 0,
            create_time=r["latest_create"] or 0,
        )
        promoted += 1

    log.info("Promoted %d authors. (Dedupe handled by PRIMARY KEY)", promoted)

    # Show final counts
    with db.get_conn() as conn:
        new_count = conn.execute(
            "SELECT COUNT(*) AS n FROM authors WHERE status='MONITORED'"
        ).fetchone()["n"]
        log.info("Total MONITORED authors now: %d", new_count)


if __name__ == "__main__":
    main()
