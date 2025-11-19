#!/usr/bin/env python3
"""
Migrate links table to add exponential backoff columns.

Usage:
    python scripts/migrate_links_backoff.py
"""

import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from holocene.config import load_config
import sqlite3


def migrate():
    """Add exponential backoff columns to links table."""
    config = load_config()
    db_path = config.db_path

    print(f"Migrating database: {db_path}")

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Check if migration is needed
    cursor.execute("PRAGMA table_info(links)")
    columns = {row[1] for row in cursor.fetchall()}

    new_columns = {
        "archive_attempts": "INTEGER DEFAULT 0",
        "last_archive_attempt": "TEXT",
        "last_archive_error": "TEXT",
        "next_retry_after": "TEXT",
    }

    migrated = []
    for column_name, column_def in new_columns.items():
        if column_name not in columns:
            print(f"Adding column: {column_name}")
            cursor.execute(f"ALTER TABLE links ADD COLUMN {column_name} {column_def}")
            migrated.append(column_name)
        else:
            print(f"Column already exists: {column_name}")

    conn.commit()
    conn.close()

    if migrated:
        print(f"\n✓ Migration complete! Added {len(migrated)} column(s):")
        for col in migrated:
            print(f"  - {col}")
    else:
        print("\n✓ Database already up to date, no migration needed")

    return 0


if __name__ == "__main__":
    sys.exit(migrate())
