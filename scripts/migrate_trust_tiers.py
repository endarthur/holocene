#!/usr/bin/env python3
"""
Migrate links table to add trust tier columns.

Usage:
    python scripts/migrate_trust_tiers.py
"""

import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from holocene.config import load_config
from holocene.storage.database import calculate_trust_tier
import sqlite3


def migrate():
    """Add trust tier columns to links table and calculate tiers for existing archives."""
    config = load_config()
    db_path = config.db_path

    print(f"Migrating database: {db_path}")

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Check if migration is needed
    cursor.execute("PRAGMA table_info(links)")
    columns = {row[1] for row in cursor.fetchall()}

    new_columns = {
        "trust_tier": "TEXT",
        "archive_date": "TEXT",
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

    # Update trust tiers for existing archived links
    if migrated:
        print("\nUpdating trust tiers for existing archived links...")

        # Get all archived links
        cursor.execute("SELECT id, url, archive_url FROM links WHERE archived = 1")
        archived_links = cursor.fetchall()

        updated_count = 0
        for link_id, url, archive_url in archived_links:
            if archive_url:
                # Try to extract timestamp from archive URL
                # Format: https://web.archive.org/web/YYYYMMDDhhmmss/url
                import re
                match = re.search(r'/web/(\d{14})/', archive_url)
                if match:
                    archive_date = match.group(1)
                    trust_tier = calculate_trust_tier(archive_date)

                    cursor.execute("""
                        UPDATE links
                        SET archive_date = ?, trust_tier = ?
                        WHERE id = ?
                    """, (archive_date, trust_tier, link_id))

                    updated_count += 1

        conn.commit()
        print(f"✓ Updated {updated_count} archived links with trust tiers")

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
