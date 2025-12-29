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
    {
        'version': 6,
        'name': 'migrate_books_to_metadata_json',
        'description': 'Migrate books enrichment and classification data to metadata JSON',
        'up': """
            -- This migration is handled specially in apply_migration_6()
            -- because we need to construct JSON from existing columns
        """,
        'requires_column_check': True,
    },
    {
        'version': 7,
        'name': 'add_passwordless_auth_tables',
        'description': 'Add authentication tables for passwordless auth (magic links + API tokens)',
        'up': """
            -- Users table (no passwords!)
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_user_id INTEGER UNIQUE NOT NULL,
                telegram_username TEXT,
                created_at TEXT NOT NULL,
                last_login_at TEXT,
                is_admin INTEGER DEFAULT 1
            );

            -- Magic link tokens (short-lived, single-use)
            CREATE TABLE IF NOT EXISTS auth_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                used_at TEXT,
                ip_address TEXT,
                user_agent TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            -- Long-lived API tokens (for CLI/scripts)
            CREATE TABLE IF NOT EXISTS api_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token TEXT UNIQUE NOT NULL,
                name TEXT,
                created_at TEXT NOT NULL,
                last_used_at TEXT,
                revoked_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            -- Indexes for auth performance
            CREATE INDEX IF NOT EXISTS idx_auth_tokens_token ON auth_tokens(token);
            CREATE INDEX IF NOT EXISTS idx_auth_tokens_expires ON auth_tokens(expires_at);
            CREATE INDEX IF NOT EXISTS idx_api_tokens_token ON api_tokens(token);
            CREATE INDEX IF NOT EXISTS idx_users_telegram ON users(telegram_user_id);
        """,
    },
    {
        'version': 8,
        'name': 'add_archive_snapshots_table',
        'description': 'Create archive_snapshots table for multi-service archiving and time-series snapshots',
        'up': """
            -- Archive snapshots table - supports multiple services and historical snapshots
            CREATE TABLE IF NOT EXISTS archive_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                link_id INTEGER NOT NULL,
                service TEXT NOT NULL,  -- 'internet_archive', 'archive_is', 'archive_today'
                snapshot_url TEXT,
                archive_date TEXT,  -- Service's timestamp (e.g., IA's YYYYMMDDhhmmss)
                status TEXT NOT NULL,  -- 'success', 'failed', 'pending'
                attempts INTEGER DEFAULT 0,
                last_attempt TEXT,
                next_retry_after TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata TEXT DEFAULT '{}',
                FOREIGN KEY(link_id) REFERENCES links(id) ON DELETE CASCADE
            );

            -- Indexes for efficient queries
            CREATE INDEX IF NOT EXISTS idx_snapshots_latest ON archive_snapshots(link_id, service, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_snapshots_status ON archive_snapshots(status);
            CREATE INDEX IF NOT EXISTS idx_snapshots_next_retry ON archive_snapshots(next_retry_after);
            CREATE INDEX IF NOT EXISTS idx_snapshots_link_id ON archive_snapshots(link_id);

            -- Migrate existing archive data from links table to archive_snapshots
            -- Only migrate rows that have an archive_url
            INSERT INTO archive_snapshots (
                link_id,
                service,
                snapshot_url,
                archive_date,
                status,
                attempts,
                last_attempt,
                next_retry_after,
                error_message,
                created_at,
                updated_at
            )
            SELECT
                id AS link_id,
                'internet_archive' AS service,
                archive_url AS snapshot_url,
                archive_date,
                CASE
                    WHEN archived = 1 THEN 'success'
                    WHEN archive_attempts > 0 THEN 'failed'
                    ELSE 'pending'
                END AS status,
                COALESCE(archive_attempts, 0) AS attempts,
                last_archive_attempt AS last_attempt,
                next_retry_after,
                last_archive_error AS error_message,
                COALESCE(created_at, datetime('now')) AS created_at,
                COALESCE(created_at, datetime('now')) AS updated_at
            FROM links
            WHERE archive_url IS NOT NULL OR archive_attempts > 0;

            -- Note: We keep the old columns in links table for backwards compatibility
            -- They will be deprecated in future versions but not removed yet
        """,
    },
    {
        'version': 9,
        'name': 'add_clean_title_columns',
        'description': 'Add clean_title column for de-SEOed titles to mercadolivre_favorites and links',
        'up': """
            -- Add clean_title to mercadolivre_favorites (de-SEOed product names)
            ALTER TABLE mercadolivre_favorites ADD COLUMN clean_title TEXT;

            -- Add clean_title to links (de-SEOed page titles)
            ALTER TABLE links ADD COLUMN clean_title TEXT;
        """,
    },
    {
        'version': 10,
        'name': 'add_laney_notes_table',
        'description': 'Create laney_notes table for Laney AI assistant memory/notebook',
        'up': """
            -- Laney's notebook - persistent memory for the AI assistant
            CREATE TABLE IF NOT EXISTS laney_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                tags TEXT DEFAULT '[]',
                note_type TEXT DEFAULT 'note',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            -- Indexes for efficient search
            CREATE INDEX IF NOT EXISTS idx_laney_notes_slug ON laney_notes(slug);
            CREATE INDEX IF NOT EXISTS idx_laney_notes_type ON laney_notes(note_type);
            CREATE INDEX IF NOT EXISTS idx_laney_notes_updated ON laney_notes(updated_at DESC);
        """,
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


def apply_migration_6(conn: sqlite3.Connection):
    """Special handler for migration 6 (migrate books data to metadata JSON).

    Migrates enrichment, classification, access, and reading data from
    individual columns to metadata JSON structure.

    Structure:
    {
      "enrichment": {"summary": "...", "tags": [...], "enriched_at": "..."},
      "classification": {"system": "dewey", "udc": "...", "confidence": "...", ...},
      "access": {"status": "...", "url": "...", "has_local_pdf": true, ...},
      "reading": {"started_at": "...", "finished_at": "..."},
      "references": {"list": [...]}
    }

    Args:
        conn: SQLite connection
    """
    import json

    cursor = conn.cursor()

    # Check if books table exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='books'
    """)
    if not cursor.fetchone():
        logger.debug("Books table doesn't exist, skipping migration 6")
        return

    logger.info("Migrating books data to metadata JSON...")

    # Get all books
    cursor.execute("SELECT * FROM books")
    books = cursor.fetchall()

    # Get column names
    column_names = [description[0] for description in cursor.description]

    migrated_count = 0

    for book_row in books:
        book = dict(zip(column_names, book_row))
        book_id = book['id']

        # Parse existing metadata (might be empty or have data)
        existing_metadata = json.loads(book.get('metadata') or '{}')

        # Build metadata structure
        metadata = existing_metadata.copy()

        # Enrichment data
        if book.get('enriched_summary') or book.get('enriched_tags') or book.get('enriched_at'):
            enrichment = {}
            if book.get('enriched_summary'):
                enrichment['summary'] = book['enriched_summary']
            if book.get('enriched_tags'):
                try:
                    enrichment['tags'] = json.loads(book['enriched_tags'])
                except (json.JSONDecodeError, TypeError):
                    enrichment['tags'] = []
            if book.get('enriched_at'):
                enrichment['enriched_at'] = book['enriched_at']

            if enrichment:
                metadata['enrichment'] = enrichment

        # Classification data
        classification = {}
        if book.get('udc_classification'):
            classification['udc'] = book['udc_classification']
        if book.get('classification_system'):
            classification['system'] = book['classification_system']
        if book.get('classification_confidence'):
            classification['confidence'] = book['classification_confidence']
        if book.get('classified_at'):
            classification['classified_at'] = book['classified_at']
        if book.get('cutter_number'):
            classification['cutter_number'] = book['cutter_number']
        if book.get('call_number'):
            classification['call_number'] = book['call_number']

        if classification:
            metadata['classification'] = classification

        # Access data
        access = {}
        if book.get('access_status'):
            access['status'] = book['access_status']
        if book.get('access_url'):
            access['url'] = book['access_url']
        if book.get('has_local_pdf'):
            access['has_local_pdf'] = bool(book['has_local_pdf'])
        if book.get('local_pdf_path'):
            access['local_pdf_path'] = book['local_pdf_path']
        if book.get('downloaded_at'):
            access['downloaded_at'] = book['downloaded_at']

        if access:
            metadata['access'] = access

        # Reading tracking
        reading = {}
        if book.get('started_reading_at'):
            reading['started_at'] = book['started_reading_at']
        if book.get('finished_reading_at'):
            reading['finished_at'] = book['finished_reading_at']

        if reading:
            metadata['reading'] = reading

        # References
        if book.get('ref_list'):
            try:
                ref_list = json.loads(book['ref_list'])
                metadata['references'] = {'list': ref_list}
            except (json.JSONDecodeError, TypeError):
                pass

        # Only update if we have metadata to add
        if metadata and metadata != existing_metadata:
            cursor.execute("""
                UPDATE books
                SET metadata = ?
                WHERE id = ?
            """, (json.dumps(metadata), book_id))
            migrated_count += 1

    conn.commit()
    logger.info(f"Migrated {migrated_count} books to metadata JSON")


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
                elif version == 6:
                    apply_migration_6(conn)
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
