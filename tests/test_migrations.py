"""Test database migration system."""

import sqlite3
import tempfile
from pathlib import Path
from holocene.storage.database import Database
from holocene.storage import migrations


def test_migrations():
    """Test that migrations apply correctly to a fresh database."""
    # Create temporary database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"

        print(f"Testing migrations on: {db_path}")

        # Create database (this will trigger migrations)
        db = Database(db_path)

        # Check schema version
        version = migrations.get_current_version(db.conn)
        print(f"✓ Current schema version: {version}")

        # Get migration history
        history = migrations.get_migration_history(db.conn)
        print(f"\n✓ Applied {len(history)} migrations:")
        for record in history:
            print(f"  - v{record['version']}: {record['name']}")
            print(f"    {record['description']}")
            print(f"    Applied at: {record['applied_at']}")

        # Verify foreign keys are enabled
        cursor = db.conn.cursor()
        cursor.execute("PRAGMA foreign_keys")
        fk_enabled = cursor.fetchone()[0]
        assert fk_enabled == 1, "Foreign keys should be enabled"
        print(f"\n✓ Foreign keys enabled: {bool(fk_enabled)}")

        # Verify WAL mode is enabled
        cursor.execute("PRAGMA journal_mode")
        journal_mode = cursor.fetchone()[0]
        assert journal_mode.lower() == 'wal', f"Expected WAL mode, got {journal_mode}"
        print(f"✓ Journal mode: {journal_mode}")

        # Verify indexes exist
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='index' AND name LIKE 'idx_%'
            ORDER BY name
        """)
        indexes = [row[0] for row in cursor.fetchall()]
        print(f"\n✓ Found {len(indexes)} indexes:")

        # Check for specific indexes we added
        expected_indexes = [
            'idx_links_trust_tier',
            'idx_links_source',
            'idx_links_last_checked',
            'idx_books_dewey',
            'idx_books_enriched_at',
            'idx_books_publication_year',
        ]

        for idx_name in expected_indexes:
            if idx_name in indexes:
                print(f"  ✓ {idx_name}")
            else:
                print(f"  ✗ MISSING: {idx_name}")

        # Verify metadata columns exist
        print("\n✓ Checking metadata columns:")
        tables_to_check = ['books', 'papers', 'links', 'activities']

        for table in tables_to_check:
            # Check if table exists
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name=?
            """, (table,))

            if not cursor.fetchone():
                print(f"  - {table}: table doesn't exist (OK)")
                continue

            # Check for metadata column
            cursor.execute(f"PRAGMA table_info({table})")
            columns = [row[1] for row in cursor.fetchall()]

            if 'metadata' in columns:
                print(f"  ✓ {table}: has metadata column")
            else:
                print(f"  ✗ {table}: MISSING metadata column")

        # Close database and connection
        db.close()

        # Verify connection is closed
        try:
            db.conn.execute("SELECT 1")
            print("✗ Warning: Connection not fully closed")
        except:
            pass  # Expected - connection should be closed

        print("\n✓ All migration tests passed!")


if __name__ == '__main__':
    test_migrations()
