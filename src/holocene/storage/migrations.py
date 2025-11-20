"""Database migration system for Holocene.

A lightweight migration system designed for SQLite with the following goals:
- Track schema versions in the database
- Apply migrations automatically on startup
- Support adding indexes, columns, and enabling pragmas
- No dependencies (no Alembic needed for single-user tool)

Why not Alembic?
- Single-user tool (not a team project)
- metadata JSON reduces migration need by 90%
- Custom system is simpler, no dependencies
- Can upgrade to Alembic later if needed
"""

import sqlite3
import logging
from datetime import datetime
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


# Migration definitions
# Each migration has: version, name, description, and up SQL
MIGRATIONS: List[Dict] = [
    {
        'version': 1,
        'name': 'enable_foreign_keys_and_wal',
        'description': 'Enable foreign key enforcement and WAL mode for better performance',
        'up': """
            PRAGMA foreign_keys = ON;
            PRAGMA journal_mode = WAL;
        """,
    },
    {
        'version': 2,
        'name': 'add_missing_indexes_links',
        'description': 'Add performance indexes to links table',
        'up': """
            CREATE INDEX IF NOT EXISTS idx_links_trust_tier ON links(trust_tier);
            CREATE INDEX IF NOT EXISTS idx_links_source ON links(source);
            CREATE INDEX IF NOT EXISTS idx_links_last_checked ON links(last_checked);
        """,
    },
    {
        'version': 3,
        'name': 'add_missing_indexes_books',
        'description': 'Add performance indexes to books table',
        'up': """
            CREATE INDEX IF NOT EXISTS idx_books_dewey ON books(dewey_decimal);
            CREATE INDEX IF NOT EXISTS idx_books_enriched_at ON books(enriched_at);
            CREATE INDEX IF NOT EXISTS idx_books_publication_year ON books(publication_year);
        """,
    },
    {
        'version': 4,
        'name': 'add_missing_indexes_mercadolivre',
        'description': 'Add performance indexes to mercadolivre_favorites table',
        'up': """
            -- Note: enriched_at and brightdata_blocked columns don't exist yet
            -- This migration reserved for when those columns are added
            -- For now, add index on commonly queried fields
            CREATE INDEX IF NOT EXISTS idx_ml_category ON mercadolivre_favorites(category_name);
            CREATE INDEX IF NOT EXISTS idx_ml_bookmarked ON mercadolivre_favorites(bookmarked_date);
        """,
    },
    {
        'version': 5,
        'name': 'add_metadata_columns',
        'description': 'Add metadata JSON column to all content tables',
        'up': """
            -- Add metadata column to tables that don't have it yet
            -- Use ALTER TABLE ADD COLUMN (safe, doesn't require table recreation)
        """,
        # Note: This migration is handled specially in apply_migrations()
        # because we need to check if columns exist first
        'requires_column_check': True,
    },
]


def get_current_version(conn: sqlite3.Connection) -> int:
    """Get the current schema version from database.

    Args:
        conn: SQLite connection

    Returns:
        Current schema version (0 if no migrations applied yet)
    """
    cursor = conn.cursor()

    # Check if schema_version table exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='schema_version'
    """)

    if not cursor.fetchone():
        return 0

    # Get highest version number
    cursor.execute("SELECT MAX(version) FROM schema_version")
    result = cursor.fetchone()

    return result[0] if result[0] is not None else 0


def create_schema_version_table(conn: sqlite3.Connection):
    """Create the schema_version table if it doesn't exist.

    Args:
        conn: SQLite connection
    """
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT
        )
    """)
    conn.commit()


def column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    """Check if a column exists in a table.

    Args:
        conn: SQLite connection
        table: Table name
        column: Column name

    Returns:
        True if column exists
    """
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in cursor.fetchall()]
    return column in columns


def apply_migration_5(conn: sqlite3.Connection):
    """Special handler for migration 5 (add metadata columns).

    This migration needs special handling because we need to check
    if columns exist before adding them.

    Args:
        conn: SQLite connection
    """
    cursor = conn.cursor()

    # Tables that should have metadata column
    tables = ['books', 'papers', 'links', 'mercadolivre_favorites', 'activities']

    for table in tables:
        # Check if table exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name=?
        """, (table,))

        if not cursor.fetchone():
            logger.debug(f"Table {table} doesn't exist, skipping metadata column")
            continue

        # Check if metadata column exists
        if not column_exists(conn, table, 'metadata'):
            logger.info(f"Adding metadata column to {table}")
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN metadata TEXT DEFAULT '{{}}'")
        else:
            logger.debug(f"Table {table} already has metadata column")

    conn.commit()


def apply_migrations(conn: sqlite3.Connection, target_version: Optional[int] = None):
    """Apply pending migrations to database.

    This function is called automatically on database initialization.

    Args:
        conn: SQLite connection
        target_version: If specified, only migrate up to this version
    """
    # Create schema_version table if needed
    create_schema_version_table(conn)

    # Get current version
    current_version = get_current_version(conn)
    logger.info(f"Current database schema version: {current_version}")

    # Determine target
    if target_version is None:
        target_version = max(m['version'] for m in MIGRATIONS)

    # Apply pending migrations
    pending_migrations = [
        m for m in MIGRATIONS
        if current_version < m['version'] <= target_version
    ]

    if not pending_migrations:
        logger.info("Database schema is up to date")
        return

    logger.info(f"Applying {len(pending_migrations)} pending migration(s)...")

    for migration in pending_migrations:
        version = migration['version']
        name = migration['name']
        description = migration['description']

        logger.info(f"Applying migration {version}: {name}")
        logger.debug(f"  {description}")

        try:
            # Special handling for migrations that need column checks
            if migration.get('requires_column_check'):
                if version == 5:
                    apply_migration_5(conn)
            else:
                # Execute migration SQL
                cursor = conn.cursor()
                # Split by semicolon and execute each statement
                for statement in migration['up'].split(';'):
                    statement = statement.strip()
                    if statement:
                        cursor.execute(statement)

            # Record migration
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO schema_version (version, applied_at, name, description)
                VALUES (?, ?, ?, ?)
            """, (version, datetime.now().isoformat(), name, description))

            conn.commit()
            logger.info(f"✓ Migration {version} applied successfully")

        except Exception as e:
            logger.error(f"✗ Migration {version} failed: {e}")
            conn.rollback()
            raise

    logger.info("All migrations completed successfully")


def get_migration_history(conn: sqlite3.Connection) -> List[Dict]:
    """Get list of applied migrations.

    Args:
        conn: SQLite connection

    Returns:
        List of migration records with version, name, applied_at, description
    """
    cursor = conn.cursor()

    # Check if schema_version table exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='schema_version'
    """)

    if not cursor.fetchone():
        return []

    cursor.execute("""
        SELECT version, name, applied_at, description
        FROM schema_version
        ORDER BY version ASC
    """)

    return [
        {
            'version': row[0],
            'name': row[1],
            'applied_at': row[2],
            'description': row[3]
        }
        for row in cursor.fetchall()
    ]
