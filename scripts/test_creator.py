"""One-shot script: insert a fake MONITORED creator into the DB,
then trigger the notifier + bitable sync to verify the full pipeline.

Usage:  python -m scripts.test_creator
"""

import os
import sys
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from src import db, bitable
from src.notifier import push_new_creators

def main():
    db.init_db()

    # Insert a fake MONITORED author
    now = int(time.time())
    test_author = "test_movie_creator_001"

    # First ensure the author exists in the table
    db.touch_author_candidate(
        author_unique=test_author,
        author_id="fake_id_001",
        nickname="TestMovieGuy",
        language="en",
    )

    # Now update with MONITORED status and realistic metrics
    db.update_author_profile({
        "author_unique": test_author,
        "nickname": "TestMovieGuy",
        "follower_count": 45000,
        "median_plays": 35000,
        "max_plays_7d": 820000,
        "posts_14d": 7,
        "posts_30d": 14,
        "vertical_ratio": 0.85,
        "language": "en",
        "status": "MONITORED",
        "reason": "ok",
    })

    print(f"✓ Inserted test creator @{test_author} as MONITORED")

    # Push to Feishu
    pushed = push_new_creators()
    print(f"✓ Feishu push: {pushed} creator(s) sent")

    # Sync to Bitable
    if bitable.is_configured():
        synced = bitable.sync_creators()
        print(f"✓ Bitable sync: {synced} creator(s) written")
    else:
        print("⚠ Bitable not configured (missing env vars), skipping")

    print("\nDone! Check your Feishu group for a green 🌱 card,")
    print("and your Bitable 'creators' table for the new row.")


if __name__ == "__main__":
    main()
