"""SQLite database operations for Holocene."""

import sqlite3
import re
import unicodedata
from pathlib import Path
from typing import List, Optional, Dict
from datetime import datetime, timedelta
from ..core.models import Activity


def calculate_trust_tier(archive_date: Optional[str]) -> str:
    """
    Calculate trust tier based on archive date.

    Args:
        archive_date: ISO format date string or IA timestamp (YYYYMMDDhhmmss)

    Returns:
        Trust tier: 'pre-llm', 'early-llm', 'recent', or 'unknown'
    """
    if not archive_date:
        return 'unknown'

    try:
        # Handle IA timestamp format (YYYYMMDDhhmmss)
        if len(archive_date) == 14 and archive_date.isdigit():
            year = int(archive_date[:4])
            month = int(archive_date[4:6])
            day = int(archive_date[6:8])
            date = datetime(year, month, day)
        else:
            # ISO format
            date = datetime.fromisoformat(archive_date.split('T')[0])

        # ChatGPT released Nov 30, 2022
        chatgpt_release = datetime(2022, 11, 1)
        early_llm_end = datetime(2024, 1, 1)

        if date < chatgpt_release:
            return 'pre-llm'
        elif date < early_llm_end:
            return 'early-llm'
        else:
            return 'recent'

    except (ValueError, AttributeError):
        return 'unknown'


def normalize_text(text: str) -> str:
    """
    Normalize text for comparison (handles unicode, punctuation, case).

    Args:
        text: Input text to normalize

    Returns:
        Normalized lowercase text with accents removed
    """
    if not text:
        return ""

    # Normalize unicode (NFD = decompose accents, then filter them out)
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')

    # Lowercase
    text = text.lower()

    # Remove punctuation except spaces
    text = re.sub(r'[^\w\s]', ' ', text)

    # Normalize whitespace
    text = ' '.join(text.split())

    return text


def normalize_author_name(author: str) -> str:
    """
    Normalize author name for comparison.

    Handles formats like:
    - "Last, First" -> "first last"
    - "First Last" -> "first last"
    - "Last, F." -> "f last"

    Args:
        author: Author name string

    Returns:
        Normalized author name
    """
    if not author:
        return ""

    # Handle "Last, First" format
    if ',' in author:
        parts = author.split(',', 1)
        if len(parts) == 2:
            last, first = parts
            author = f"{first.strip()} {last.strip()}"

    # Normalize text
    normalized = normalize_text(author)

    # Remove middle initials and extra spaces
    normalized = re.sub(r'\b\w\b', '', normalized)  # Remove single letters
    normalized = ' '.join(normalized.split())  # Clean whitespace

    return normalized


def generate_normalized_key(title: str, first_author: str, year: Optional[int]) -> str:
    """
    Generate normalized composite key for paper identification.

    Format: "normalized_title|normalized_first_author|year"

    Args:
        title: Paper title
        first_author: First author name
        year: Publication year

    Returns:
        Normalized composite key
    """
    norm_title = normalize_text(title)
    norm_author = normalize_author_name(first_author)
    year_str = str(year) if year else "unknown"

    return f"{norm_title}|{norm_author}|{year_str}"


class Database:
    """SQLite database manager for Holocene."""

    def __init__(self, db_path: Path):
        """Initialize database connection."""
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _init_db(self):
        """Initialize database schema."""
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row  # Access columns by name

        cursor = self.conn.cursor()

        # Create activities table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS activities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                activity_type TEXT NOT NULL,
                context TEXT NOT NULL,
                description TEXT NOT NULL,
                tags TEXT,
                duration_minutes INTEGER,
                source TEXT NOT NULL DEFAULT 'manual',
                metadata TEXT,
                created_at TEXT NOT NULL
            )
        """)

        # Create links table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL UNIQUE,
                title TEXT,
                source TEXT NOT NULL,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                archived BOOLEAN DEFAULT 0,
                archive_url TEXT,
                last_checked TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                archive_attempts INTEGER DEFAULT 0,
                last_archive_attempt TEXT,
                last_archive_error TEXT,
                next_retry_after TEXT,
                trust_tier TEXT,
                archive_date TEXT
            )
        """)

        # Create books table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                author TEXT,
                subtitle TEXT,
                isbn TEXT,
                isbn13 TEXT,
                publication_year INTEGER,
                publisher TEXT,
                subjects TEXT,
                lc_classification TEXT,
                dewey_decimal TEXT,
                udc_classification TEXT,
                classification_system TEXT,
                classification_confidence TEXT,
                classified_at TEXT,
                owned BOOLEAN DEFAULT 1,
                source TEXT DEFAULT 'librarycat',
                date_added TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                enriched_summary TEXT,
                enriched_tags TEXT,
                enriched_at TEXT
            )
        """)

        # Add enriched columns if they don't exist (for existing databases)
        try:
            cursor.execute("ALTER TABLE books ADD COLUMN enriched_summary TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists

        try:
            cursor.execute("ALTER TABLE books ADD COLUMN enriched_tags TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists

        try:
            cursor.execute("ALTER TABLE books ADD COLUMN enriched_at TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists

        # Add classification columns if they don't exist
        try:
            cursor.execute("ALTER TABLE books ADD COLUMN udc_classification TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists

        try:
            cursor.execute("ALTER TABLE books ADD COLUMN classification_system TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists

        try:
            cursor.execute("ALTER TABLE books ADD COLUMN classification_confidence TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists

        try:
            cursor.execute("ALTER TABLE books ADD COLUMN classified_at TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists

        try:
            cursor.execute("ALTER TABLE books ADD COLUMN cutter_number TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists

        try:
            cursor.execute("ALTER TABLE books ADD COLUMN call_number TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists

        # Create papers table (Crossref academic papers)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS papers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doi TEXT UNIQUE,
                arxiv_id TEXT,
                pmid TEXT,
                openalex_id TEXT,
                semantic_scholar_id TEXT,
                normalized_key TEXT,
                title TEXT,
                authors TEXT,
                abstract TEXT,
                publication_date TEXT,
                journal TEXT,
                url TEXT,
                reference_dois TEXT,
                cited_by_count INTEGER DEFAULT 0,
                added_at TEXT NOT NULL,
                notes TEXT,
                is_open_access BOOLEAN DEFAULT 0,
                pdf_url TEXT,
                oa_status TEXT,
                oa_color TEXT,
                access_status TEXT,
                access_url TEXT,
                has_local_pdf BOOLEAN DEFAULT 0,
                local_pdf_path TEXT,
                downloaded_at TEXT,
                ref_list TEXT,
                reading_status TEXT,
                started_reading_at TEXT,
                finished_reading_at TEXT,
                summary TEXT,
                analysis_pages INTEGER,
                total_pages INTEGER,
                full_text_analyzed BOOLEAN DEFAULT 0,
                last_analyzed_at TEXT
            )
        """)

        # Create mercadolivre_favorites table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS mercadolivre_favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id TEXT NOT NULL UNIQUE,
                title TEXT,
                price REAL,
                currency TEXT,
                category_id TEXT,
                category_name TEXT,
                url TEXT,
                thumbnail_url TEXT,
                condition TEXT,
                available_quantity INTEGER,

                dewey_class TEXT,
                call_number TEXT,
                tags TEXT,
                user_notes TEXT,

                bookmarked_date TEXT,
                first_synced TEXT NOT NULL,
                last_checked TEXT,
                is_available BOOLEAN DEFAULT 1,

                created_at TEXT NOT NULL
            )
        """)

        # Create inventory items table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                -- User input (minimal friction)
                name TEXT NOT NULL,
                description TEXT,
                category TEXT,

                -- Linking
                mercadolivre_item_id TEXT,

                -- Status & Location
                status TEXT DEFAULT 'owned',
                location TEXT,

                -- Quantity (for bulk items)
                quantity REAL,
                unit TEXT,

                -- Financial
                acquired_date TEXT,
                acquired_price REAL,
                current_value REAL,

                -- Media
                photo_path TEXT,

                -- Enrichment tracking
                enriched_at TEXT,
                needs_confirmation BOOLEAN DEFAULT 0,

                -- Timestamps
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (mercadolivre_item_id) REFERENCES mercadolivre_favorites(item_id)
            )
        """)

        # Create item attributes table (EAV)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS item_attributes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,

                -- The attribute
                key TEXT NOT NULL,
                value TEXT,
                value_type TEXT DEFAULT 'string',

                -- Provenance
                source TEXT DEFAULT 'user',
                confidence REAL,
                confirmed BOOLEAN DEFAULT 0,

                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
            )
        """)

        # Create item tags table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS item_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                tag TEXT NOT NULL,

                FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
            )
        """)

        # Create pending confirmations table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pending_confirmations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,

                suggestion_type TEXT,
                suggested_data TEXT,
                reasoning TEXT,

                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
            )
        """)

        # Create indices
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_activities_timestamp
            ON activities(timestamp)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_activities_type
            ON activities(activity_type)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_activities_source
            ON activities(source)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_links_url
            ON links(url)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_links_archived
            ON links(archived)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_books_title
            ON books(title)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_books_author
            ON books(author)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_books_subjects
            ON books(subjects)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_papers_doi
            ON papers(doi)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_papers_title
            ON papers(title)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_papers_date
            ON papers(publication_date)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_items_name
            ON items(name)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_items_category
            ON items(category)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_items_status
            ON items(status)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_item_attrs
            ON item_attributes(item_id, key)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_item_attrs_key
            ON item_attributes(key)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_item_tags_item
            ON item_tags(item_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_pending_conf_item
            ON pending_confirmations(item_id)
        """)

        # Add OA columns if they don't exist (for existing databases)
        try:
            cursor.execute("ALTER TABLE papers ADD COLUMN is_open_access BOOLEAN DEFAULT 0")
        except sqlite3.OperationalError:
            pass  # Column already exists

        try:
            cursor.execute("ALTER TABLE papers ADD COLUMN pdf_url TEXT")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE papers ADD COLUMN oa_status TEXT")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE papers ADD COLUMN oa_color TEXT")
        except sqlite3.OperationalError:
            pass

        # Create OA index AFTER adding column
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_papers_oa
            ON papers(is_open_access)
        """)

        # Add unified access model fields to BOOKS
        try:
            cursor.execute("ALTER TABLE books ADD COLUMN access_status TEXT")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE books ADD COLUMN access_url TEXT")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE books ADD COLUMN has_local_pdf BOOLEAN DEFAULT 0")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE books ADD COLUMN local_pdf_path TEXT")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE books ADD COLUMN downloaded_at TEXT")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE books ADD COLUMN ref_list TEXT")
        except sqlite3.OperationalError:
            pass

        # Add unified access model fields to PAPERS
        try:
            cursor.execute("ALTER TABLE papers ADD COLUMN access_status TEXT")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE papers ADD COLUMN access_url TEXT")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE papers ADD COLUMN has_local_pdf BOOLEAN DEFAULT 0")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE papers ADD COLUMN local_pdf_path TEXT")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE papers ADD COLUMN downloaded_at TEXT")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE papers ADD COLUMN ref_list TEXT")
        except sqlite3.OperationalError:
            pass

        # Add reading status tracking to BOOKS
        try:
            cursor.execute("ALTER TABLE books ADD COLUMN reading_status TEXT")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE books ADD COLUMN started_reading_at TEXT")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE books ADD COLUMN finished_reading_at TEXT")
        except sqlite3.OperationalError:
            pass

        # Add reading status tracking to PAPERS
        try:
            cursor.execute("ALTER TABLE papers ADD COLUMN reading_status TEXT")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE papers ADD COLUMN started_reading_at TEXT")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE papers ADD COLUMN finished_reading_at TEXT")
        except sqlite3.OperationalError:
            pass

        # Add alternative identifier fields
        try:
            cursor.execute("ALTER TABLE papers ADD COLUMN arxiv_id TEXT")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE papers ADD COLUMN pmid TEXT")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE papers ADD COLUMN openalex_id TEXT")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE papers ADD COLUMN semantic_scholar_id TEXT")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE papers ADD COLUMN normalized_key TEXT")
        except sqlite3.OperationalError:
            pass

        # Add analysis and summary tracking fields
        try:
            cursor.execute("ALTER TABLE papers ADD COLUMN summary TEXT")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE papers ADD COLUMN analysis_pages INTEGER")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE papers ADD COLUMN total_pages INTEGER")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE papers ADD COLUMN full_text_analyzed BOOLEAN DEFAULT 0")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE papers ADD COLUMN last_analyzed_at TEXT")
        except sqlite3.OperationalError:
            pass

        # Create indices for new fields
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_books_access_status
            ON books(access_status)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_books_has_local_pdf
            ON books(has_local_pdf)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_books_reading_status
            ON books(reading_status)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_papers_access_status
            ON papers(access_status)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_papers_has_local_pdf
            ON papers(has_local_pdf)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_papers_reading_status
            ON papers(reading_status)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_papers_arxiv_id
            ON papers(arxiv_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_papers_pmid
            ON papers(pmid)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_papers_openalex_id
            ON papers(openalex_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_papers_normalized_key
            ON papers(normalized_key)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_papers_full_text_analyzed
            ON papers(full_text_analyzed)
        """)

        # Migrate papers table to make DOI nullable (if needed)
        self._migrate_papers_doi_nullable(cursor)

        self.conn.commit()

    def _migrate_papers_doi_nullable(self, cursor):
        """Migrate papers table to make DOI nullable instead of NOT NULL."""
        # Check if migration is needed by inspecting schema
        cursor.execute("PRAGMA table_info(papers)")
        columns = {row[1]: row for row in cursor.fetchall()}

        # Check if doi column exists and is NOT NULL
        if 'doi' in columns:
            doi_col = columns['doi']
            is_not_null = doi_col[3]  # notnull is index 3 in PRAGMA table_info

            if is_not_null == 1:
                # Need to migrate - DOI is currently NOT NULL
                print("Migrating papers table to make DOI optional...")

                # Create new table with correct schema
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS papers_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        doi TEXT UNIQUE,
                        arxiv_id TEXT,
                        pmid TEXT,
                        openalex_id TEXT,
                        semantic_scholar_id TEXT,
                        normalized_key TEXT,
                        title TEXT,
                        authors TEXT,
                        abstract TEXT,
                        publication_date TEXT,
                        journal TEXT,
                        url TEXT,
                        reference_dois TEXT,
                        cited_by_count INTEGER DEFAULT 0,
                        added_at TEXT NOT NULL,
                        notes TEXT,
                        is_open_access BOOLEAN DEFAULT 0,
                        pdf_url TEXT,
                        oa_status TEXT,
                        oa_color TEXT,
                        access_status TEXT,
                        access_url TEXT,
                        has_local_pdf BOOLEAN DEFAULT 0,
                        local_pdf_path TEXT,
                        downloaded_at TEXT,
                        ref_list TEXT,
                        reading_status TEXT,
                        started_reading_at TEXT,
                        finished_reading_at TEXT,
                        summary TEXT,
                        analysis_pages INTEGER,
                        total_pages INTEGER,
                        full_text_analyzed BOOLEAN DEFAULT 0,
                        last_analyzed_at TEXT
                    )
                """)

                # Get list of columns from old table
                cursor.execute("PRAGMA table_info(papers)")
                old_columns = [row[1] for row in cursor.fetchall()]

                # Build INSERT statement with only existing columns
                common_columns = [col for col in old_columns if col in [
                    'id', 'doi', 'arxiv_id', 'pmid', 'openalex_id', 'semantic_scholar_id',
                    'normalized_key', 'title', 'authors', 'abstract', 'publication_date',
                    'journal', 'url', 'reference_dois', 'cited_by_count', 'added_at', 'notes',
                    'is_open_access', 'pdf_url', 'oa_status', 'oa_color', 'access_status',
                    'access_url', 'has_local_pdf', 'local_pdf_path', 'downloaded_at',
                    'ref_list', 'reading_status', 'started_reading_at', 'finished_reading_at',
                    'summary', 'analysis_pages', 'total_pages', 'full_text_analyzed', 'last_analyzed_at'
                ]]

                columns_str = ', '.join(common_columns)

                # Copy data from old table, providing defaults for missing columns
                if 'added_at' not in old_columns:
                    # Old schema didn't have added_at, use datetime.now()
                    cursor.execute(f"""
                        INSERT INTO papers_new ({columns_str}, added_at)
                        SELECT {columns_str}, datetime('now')
                        FROM papers
                    """)
                else:
                    cursor.execute(f"""
                        INSERT INTO papers_new ({columns_str})
                        SELECT {columns_str}
                        FROM papers
                    """)

                # Drop old table
                cursor.execute("DROP TABLE papers")

                # Rename new table
                cursor.execute("ALTER TABLE papers_new RENAME TO papers")

                # Recreate indices
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_papers_doi
                    ON papers(doi)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_papers_arxiv_id
                    ON papers(arxiv_id)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_papers_pmid
                    ON papers(pmid)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_papers_openalex_id
                    ON papers(openalex_id)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_papers_normalized_key
                    ON papers(normalized_key)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_papers_access_status
                    ON papers(access_status)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_papers_has_local_pdf
                    ON papers(has_local_pdf)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_papers_reading_status
                    ON papers(reading_status)
                """)

                print("✓ Migration complete!")

    def insert_activity(self, activity: Activity) -> int:
        """Insert a new activity and return its ID."""
        cursor = self.conn.cursor()
        data = activity.to_dict()

        # Remove id if present (it's auto-generated)
        data.pop("id", None)

        cursor.execute("""
            INSERT INTO activities (
                timestamp, activity_type, context, description,
                tags, duration_minutes, source, metadata, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["timestamp"],
            data["activity_type"],
            data["context"],
            data["description"],
            data["tags"],
            data["duration_minutes"],
            data["source"],
            data["metadata"],
            data["created_at"],
        ))

        self.conn.commit()
        return cursor.lastrowid

    def get_activity(self, activity_id: int) -> Optional[Activity]:
        """Get activity by ID."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM activities WHERE id = ?", (activity_id,))
        row = cursor.fetchone()

        if row is None:
            return None

        return Activity.from_dict(dict(row))

    def get_activities(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        activity_type: Optional[str] = None,
        source: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Activity]:
        """Get activities with optional filters."""
        cursor = self.conn.cursor()

        query = "SELECT * FROM activities WHERE 1=1"
        params = []

        if start_date:
            query += " AND timestamp >= ?"
            params.append(start_date.isoformat())

        if end_date:
            query += " AND timestamp <= ?"
            params.append(end_date.isoformat())

        if activity_type:
            query += " AND activity_type = ?"
            params.append(activity_type)

        if source:
            query += " AND source = ?"
            params.append(source)

        query += " ORDER BY timestamp DESC"

        if limit:
            query += " LIMIT ?"
            params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()

        return [Activity.from_dict(dict(row)) for row in rows]

    def get_activities_today(self) -> List[Activity]:
        """Get all activities from today."""
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = today + timedelta(days=1)
        return self.get_activities(start_date=today, end_date=tomorrow)

    def get_activities_this_week(self) -> List[Activity]:
        """Get all activities from this week."""
        now = datetime.now()
        # Start of week (Monday)
        start = now - timedelta(days=now.weekday())
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        return self.get_activities(start_date=start)

    def delete_activity(self, activity_id: int) -> bool:
        """Delete an activity by ID. Returns True if deleted."""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM activities WHERE id = ?", (activity_id,))
        self.conn.commit()
        return cursor.rowcount > 0

    def count_activities(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> int:
        """Count activities in date range."""
        cursor = self.conn.cursor()

        query = "SELECT COUNT(*) FROM activities WHERE 1=1"
        params = []

        if start_date:
            query += " AND timestamp >= ?"
            params.append(start_date.isoformat())

        if end_date:
            query += " AND timestamp <= ?"
            params.append(end_date.isoformat())

        cursor.execute(query, params)
        return cursor.fetchone()[0]

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None

    def __enter__(self):
        """Context manager entry."""
        return self

    def insert_link(self, url: str, source: str, title: str = None, notes: str = None) -> int:
        """Insert or update a link. Returns link ID."""
        cursor = self.conn.cursor()
        now = datetime.now().isoformat()

        # Try to insert, update if exists
        cursor.execute("""
            INSERT INTO links (url, title, source, first_seen, last_seen, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                last_seen = ?,
                title = COALESCE(?, title),
                notes = COALESCE(?, notes)
        """, (url, title, source, now, now, now, now, title, notes))

        self.conn.commit()

        # Get the link ID
        cursor.execute("SELECT id FROM links WHERE url = ?", (url,))
        return cursor.fetchone()[0]

    def get_links(
        self,
        archived: Optional[bool] = None,
        source: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict]:
        """Get links with optional filters."""
        cursor = self.conn.cursor()

        query = "SELECT * FROM links WHERE 1=1"
        params = []

        if archived is not None:
            query += " AND archived = ?"
            params.append(1 if archived else 0)

        if source:
            query += " AND source = ?"
            params.append(source)

        query += " ORDER BY last_seen DESC"

        if limit:
            query += " LIMIT ?"
            params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()

        return [dict(row) for row in rows]

    def update_link_archive_status(self, url: str, archived: bool, archive_url: str = None, archive_date: str = None):
        """Update archive status for a link (successful archive)."""
        cursor = self.conn.cursor()
        now = datetime.now().isoformat()

        # Calculate trust tier from archive date
        trust_tier = calculate_trust_tier(archive_date)

        cursor.execute("""
            UPDATE links
            SET archived = ?, archive_url = ?, last_checked = ?,
                last_archive_attempt = ?, last_archive_error = NULL,
                archive_date = ?, trust_tier = ?
            WHERE url = ?
        """, (1 if archived else 0, archive_url, now, now, archive_date, trust_tier, url))

        self.conn.commit()

    def record_archive_failure(self, url: str, error_message: str):
        """Record a failed archive attempt with exponential backoff."""
        cursor = self.conn.cursor()
        now = datetime.now()

        # Get current attempt count
        cursor.execute("SELECT archive_attempts FROM links WHERE url = ?", (url,))
        row = cursor.fetchone()
        attempts = row[0] if row else 0
        attempts += 1

        # Calculate next retry time using exponential backoff
        # Base delay: 1 day, max: 30 days
        # Formula: min(1 * 2^attempts, 30) days
        delay_days = min(1 * (2 ** (attempts - 1)), 30)
        next_retry = now + timedelta(days=delay_days)

        cursor.execute("""
            UPDATE links
            SET archive_attempts = ?,
                last_archive_attempt = ?,
                last_archive_error = ?,
                last_checked = ?,
                next_retry_after = ?
            WHERE url = ?
        """, (attempts, now.isoformat(), error_message, now.isoformat(),
              next_retry.isoformat(), url))

        self.conn.commit()

        return {
            "attempts": attempts,
            "next_retry_after": next_retry,
            "delay_days": delay_days
        }

    def get_links_ready_for_retry(self) -> List[Dict]:
        """Get links that failed but are ready to retry based on backoff."""
        cursor = self.conn.cursor()
        now = datetime.now().isoformat()

        query = """
            SELECT * FROM links
            WHERE archived = 0
            AND archive_attempts > 0
            AND (next_retry_after IS NULL OR next_retry_after <= ?)
            ORDER BY archive_attempts ASC, last_archive_attempt ASC
        """

        cursor.execute(query, (now,))
        rows = cursor.fetchall()

        return [dict(row) for row in rows]

    def insert_book(
        self,
        title: str,
        author: Optional[str] = None,
        subtitle: Optional[str] = None,
        isbn: Optional[str] = None,
        isbn13: Optional[str] = None,
        publication_year: Optional[int] = None,
        publisher: Optional[str] = None,
        subjects: Optional[List[str]] = None,
        notes: Optional[str] = None
    ) -> int:
        """Insert a book into the database."""
        cursor = self.conn.cursor()
        now = datetime.now().isoformat()

        # Convert subjects list to JSON string
        import json
        subjects_json = json.dumps(subjects) if subjects else None

        cursor.execute("""
            INSERT INTO books (
                title, author, subtitle, isbn, isbn13,
                publication_year, publisher, subjects, notes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            title, author, subtitle, isbn, isbn13,
            publication_year, publisher, subjects_json, notes, now
        ))

        self.conn.commit()
        return cursor.lastrowid

    def get_books(
        self,
        search: Optional[str] = None,
        author: Optional[str] = None,
        subject: Optional[str] = None,
        limit: Optional[int] = None,
        order_by: str = "title"
    ) -> List[Dict]:
        """
        Get books from database.

        Args:
            search: Search in title, author, subjects
            author: Filter by author
            subject: Filter by subject
            limit: Maximum results
            order_by: Sort order ("title", "dewey", "author", "year")

        Returns:
            List of book dictionaries
        """
        cursor = self.conn.cursor()

        query = "SELECT * FROM books WHERE 1=1"
        params = []

        if search:
            query += " AND (title LIKE ? OR author LIKE ? OR subjects LIKE ?)"
            search_term = f"%{search}%"
            params.extend([search_term, search_term, search_term])

        if author:
            query += " AND author LIKE ?"
            params.append(f"%{author}%")

        if subject:
            query += " AND subjects LIKE ?"
            params.append(f"%{subject}%")

        # Order by specified column
        if order_by == "dewey":
            # Sort by call_number if available, otherwise by udc_classification
            # Put unclassified books at the end
            query += " ORDER BY CASE WHEN call_number IS NULL THEN 1 ELSE 0 END, call_number ASC, udc_classification ASC"
        elif order_by == "author":
            query += " ORDER BY author ASC"
        elif order_by == "year":
            query += " ORDER BY publication_year DESC"
        else:  # default to title
            query += " ORDER BY title ASC"

        if limit:
            query += " LIMIT ?"
            params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()

        return [dict(row) for row in rows]

    def get_book(self, book_id: int) -> Optional[Dict]:
        """
        Get a book by ID.

        Args:
            book_id: Book ID

        Returns:
            Book dictionary or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM books WHERE id = ?", (book_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def search_books_for_research(self, keywords: List[str], limit: int = 5) -> List[Dict]:
        """
        Search books for research topics.

        Args:
            keywords: List of keywords to search
            limit: Maximum results

        Returns:
            List of relevant books with scores
        """
        all_books = self.get_books(limit=1000)

        scored_books = []
        for book in all_books:
            score = 0
            title_lower = (book.get("title") or "").lower()
            author_lower = (book.get("author") or "").lower()
            subjects_lower = (book.get("subjects") or "").lower()
            enriched_summary_lower = (book.get("enriched_summary") or "").lower()
            enriched_tags_lower = (book.get("enriched_tags") or "").lower()

            for keyword in keywords:
                keyword_lower = keyword.lower()
                if keyword_lower in title_lower:
                    score += 3
                if keyword_lower in author_lower:
                    score += 1
                if keyword_lower in subjects_lower:
                    score += 2
                # Prioritize enriched fields highly
                if keyword_lower in enriched_summary_lower:
                    score += 4
                if keyword_lower in enriched_tags_lower:
                    score += 5

            if score > 0:
                scored_books.append((score, book))

        # Sort by score
        scored_books.sort(reverse=True, key=lambda x: x[0])

        return [book for score, book in scored_books[:limit]]

    def update_book_enrichment(self, book_id: int, summary: str, tags: List[str]) -> bool:
        """
        Update enriched metadata for a book.

        Args:
            book_id: Book ID
            summary: Enriched summary
            tags: List of tags/topics

        Returns:
            True if updated successfully
        """
        cursor = self.conn.cursor()
        now = datetime.now().isoformat()

        import json
        tags_json = json.dumps(tags) if tags else None

        cursor.execute("""
            UPDATE books
            SET enriched_summary = ?,
                enriched_tags = ?,
                enriched_at = ?
            WHERE id = ?
        """, (summary, tags_json, now, book_id))

        self.conn.commit()
        return cursor.rowcount > 0

    def update_book_classification(
        self,
        book_id: int,
        udc_number: str,
        classification_system: str = "UDC",
        confidence: str = "medium",
        cutter_number: Optional[str] = None,
        call_number: Optional[str] = None
    ) -> bool:
        """
        Update classification for a book.

        Args:
            book_id: Book ID
            udc_number: Classification number (UDC, Dewey, etc.)
            classification_system: Classification system used (default: UDC)
            confidence: Confidence level (high/medium/low)
            cutter_number: Optional Cutter number for unique shelf position
            call_number: Optional full call number (e.g., "550.182 I73a")

        Returns:
            True if updated successfully
        """
        cursor = self.conn.cursor()
        now = datetime.now().isoformat()

        cursor.execute("""
            UPDATE books
            SET udc_classification = ?,
                classification_system = ?,
                classification_confidence = ?,
                classified_at = ?,
                cutter_number = ?,
                call_number = ?
            WHERE id = ?
        """, (udc_number, classification_system, confidence, now, cutter_number, call_number, book_id))

        self.conn.commit()
        return cursor.rowcount > 0

    def get_unclassified_books(self) -> List[Dict]:
        """
        Get all books that haven't been classified yet.

        Returns:
            List of unclassified books
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT * FROM books
            WHERE udc_classification IS NULL
            ORDER BY created_at DESC
        """)

        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def get_unenriched_books(self) -> List[Dict]:
        """
        Get all books that haven't been enriched yet.

        Returns:
            List of unenriched books
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT * FROM books
            WHERE enriched_summary IS NULL OR enriched_tags IS NULL
            ORDER BY created_at DESC
        """)

        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    # Papers management

    def add_book(
        self,
        title: str,
        author: Optional[str] = None,
        subtitle: Optional[str] = None,
        isbn: Optional[str] = None,
        isbn13: Optional[str] = None,
        publication_year: Optional[int] = None,
        publisher: Optional[str] = None,
        subjects: Optional[str] = None,
        lc_classification: Optional[str] = None,
        dewey_decimal: Optional[str] = None,
        owned: bool = True,
        source: str = 'manual',
        date_added: Optional[str] = None,
        notes: Optional[str] = None
    ) -> int:
        """
        Add a book to the database.

        Args:
            title: Book title
            author: Book author(s)
            subtitle: Book subtitle
            isbn: ISBN-10
            isbn13: ISBN-13
            publication_year: Year published
            publisher: Publisher name
            subjects: Subjects/categories (JSON string or comma-separated)
            lc_classification: Library of Congress classification
            dewey_decimal: Dewey Decimal classification
            owned: Whether the book is owned
            source: Source of the book entry
            date_added: Date added (defaults to now)
            notes: User notes

        Returns:
            Book ID
        """
        cursor = self.conn.cursor()
        now = datetime.now().isoformat()

        if not date_added:
            date_added = now

        cursor.execute("""
            INSERT INTO books (
                title, author, subtitle, isbn, isbn13,
                publication_year, publisher, subjects,
                lc_classification, dewey_decimal, owned,
                source, date_added, notes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            title, author, subtitle, isbn, isbn13,
            publication_year, publisher, subjects,
            lc_classification, dewey_decimal, 1 if owned else 0,
            source, date_added, notes, now
        ))

        self.conn.commit()
        return cursor.lastrowid

    def add_paper(
        self,
        title: str,
        authors: Optional[List[str]] = None,
        doi: Optional[str] = None,
        arxiv_id: Optional[str] = None,
        pmid: Optional[str] = None,
        openalex_id: Optional[str] = None,
        abstract: Optional[str] = None,
        publication_date: Optional[str] = None,
        journal: Optional[str] = None,
        url: Optional[str] = None,
        references: Optional[List[str]] = None,
        cited_by_count: int = 0,
        notes: Optional[str] = None,
        is_open_access: bool = False,
        pdf_url: Optional[str] = None,
        oa_status: Optional[str] = None,
        oa_color: Optional[str] = None,
        summary: Optional[str] = None,
        analysis_pages: Optional[int] = None,
        total_pages: Optional[int] = None,
        full_text_analyzed: bool = False
    ) -> int:
        """
        Add a paper to the database.

        Args:
            title: Paper title (REQUIRED)
            authors: List of author names
            doi: Paper DOI (optional)
            arxiv_id: ArXiv ID (optional)
            pmid: PubMed ID (optional)
            openalex_id: OpenAlex ID (optional)
            abstract: Paper abstract
            publication_date: Publication date
            journal: Journal name
            url: Paper URL
            references: List of referenced DOIs
            cited_by_count: Number of citations
            notes: User notes
            is_open_access: Whether paper is Open Access
            pdf_url: Direct PDF URL (if available)
            oa_status: OA status from Unpaywall (e.g., 'gold', 'green', 'hybrid')
            oa_color: OA color category

        Returns:
            Paper ID
        """
        import json

        cursor = self.conn.cursor()
        now = datetime.now().isoformat()

        # Convert lists to JSON
        authors_json = json.dumps(authors) if authors else None
        references_json = json.dumps(references) if references else None

        # Generate normalized key for duplicate detection
        first_author = authors[0] if authors else ""

        # Extract year from publication_date if available
        year = None
        if publication_date:
            try:
                # Handle various date formats
                if len(publication_date) >= 4:
                    year = int(publication_date[:4])
            except (ValueError, TypeError):
                pass

        normalized_key = generate_normalized_key(title, first_author, year)

        # Set last_analyzed_at if summary is provided
        last_analyzed_at = now if summary else None

        cursor.execute("""
            INSERT INTO papers (
                doi, arxiv_id, pmid, openalex_id, normalized_key,
                title, authors, abstract, publication_date,
                journal, url, reference_dois, cited_by_count, added_at, notes,
                is_open_access, pdf_url, oa_status, oa_color,
                summary, analysis_pages, total_pages, full_text_analyzed, last_analyzed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            doi, arxiv_id, pmid, openalex_id, normalized_key,
            title, authors_json, abstract, publication_date,
            journal, url, references_json, cited_by_count, now, notes,
            1 if is_open_access else 0, pdf_url, oa_status, oa_color,
            summary, analysis_pages, total_pages, 1 if full_text_analyzed else 0, last_analyzed_at
        ))

        self.conn.commit()
        return cursor.lastrowid

    def get_papers(
        self,
        search: Optional[str] = None,
        from_date: Optional[str] = None,
        until_date: Optional[str] = None,
        oa_only: bool = False,
        limit: int = 20
    ) -> List[Dict]:
        """
        Get papers from database with filtering.

        Args:
            search: Search term for title/abstract
            from_date: Minimum publication date
            until_date: Maximum publication date
            oa_only: Only return Open Access papers
            limit: Maximum results

        Returns:
            List of papers
        """
        import json

        cursor = self.conn.cursor()

        query = "SELECT * FROM papers WHERE 1=1"
        params = []

        if search:
            query += " AND (title LIKE ? OR abstract LIKE ?)"
            search_term = f"%{search}%"
            params.extend([search_term, search_term])

        if from_date:
            query += " AND publication_date >= ?"
            params.append(from_date)

        if until_date:
            query += " AND publication_date <= ?"
            params.append(until_date)

        if oa_only:
            query += " AND is_open_access = 1"

        query += " ORDER BY publication_date DESC, cited_by_count DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()

        papers = []
        for row in rows:
            paper = dict(row)
            # Parse JSON fields
            if paper.get("authors"):
                paper["authors"] = json.loads(paper["authors"])
            if paper.get("reference_dois"):
                paper["references"] = json.loads(paper["reference_dois"])
                del paper["reference_dois"]  # Rename to references for consistency
            papers.append(paper)

        return papers

    def get_paper(self, paper_id: int) -> Optional[Dict]:
        """
        Get a paper by ID.

        Args:
            paper_id: Paper ID

        Returns:
            Paper dictionary or None if not found
        """
        import json
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM papers WHERE id = ?", (paper_id,))
        row = cursor.fetchone()
        
        if not row:
            return None
            
        paper = dict(row)
        # Parse JSON fields
        if paper.get("authors"):
            paper["authors"] = json.loads(paper["authors"])
        if paper.get("reference_dois"):
            paper["references"] = json.loads(paper["reference_dois"])
            del paper["reference_dois"]
        return paper

    def get_paper_by_doi(self, doi: str) -> Optional[Dict]:
        """
        Get a paper by its DOI.

        Args:
            doi: Paper DOI

        Returns:
            Paper dict or None
        """
        import json

        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM papers WHERE doi = ?", (doi,))
        row = cursor.fetchone()

        if not row:
            return None

        paper = dict(row)
        # Parse JSON fields
        if paper.get("authors"):
            paper["authors"] = json.loads(paper["authors"])
        if paper.get("reference_dois"):
            paper["references"] = json.loads(paper["reference_dois"])
            del paper["reference_dois"]  # Rename to references for consistency

        return paper

    def find_duplicate_paper(
        self,
        doi: Optional[str] = None,
        arxiv_id: Optional[str] = None,
        pmid: Optional[str] = None,
        openalex_id: Optional[str] = None,
        title: Optional[str] = None,
        first_author: Optional[str] = None,
        year: Optional[int] = None
    ) -> Optional[Dict]:
        """
        Find duplicate paper using fallback hierarchy.

        Checks in order:
        1. DOI (if provided)
        2. Alternative IDs (ArXiv, PMID, OpenAlex)
        3. Normalized composite key (title + first_author + year)

        Args:
            doi: Paper DOI
            arxiv_id: ArXiv ID
            pmid: PubMed ID
            openalex_id: OpenAlex ID
            title: Paper title
            first_author: First author name
            year: Publication year

        Returns:
            Existing paper dict or None
        """
        import json

        cursor = self.conn.cursor()

        # 1. Check DOI first (most reliable)
        if doi:
            cursor.execute("SELECT * FROM papers WHERE doi = ?", (doi,))
            row = cursor.fetchone()
            if row:
                paper = dict(row)
                if paper.get("authors"):
                    paper["authors"] = json.loads(paper["authors"])
                return paper

        # 2. Check alternative IDs
        if arxiv_id:
            cursor.execute("SELECT * FROM papers WHERE arxiv_id = ?", (arxiv_id,))
            row = cursor.fetchone()
            if row:
                paper = dict(row)
                if paper.get("authors"):
                    paper["authors"] = json.loads(paper["authors"])
                return paper

        if pmid:
            cursor.execute("SELECT * FROM papers WHERE pmid = ?", (pmid,))
            row = cursor.fetchone()
            if row:
                paper = dict(row)
                if paper.get("authors"):
                    paper["authors"] = json.loads(paper["authors"])
                return paper

        if openalex_id:
            cursor.execute("SELECT * FROM papers WHERE openalex_id = ?", (openalex_id,))
            row = cursor.fetchone()
            if row:
                paper = dict(row)
                if paper.get("authors"):
                    paper["authors"] = json.loads(paper["authors"])
                return paper

        # 3. Check normalized composite key (title + first_author + year)
        if title and first_author:
            normalized_key = generate_normalized_key(title, first_author, year)
            cursor.execute("SELECT * FROM papers WHERE normalized_key = ?", (normalized_key,))
            row = cursor.fetchone()
            if row:
                paper = dict(row)
                if paper.get("authors"):
                    paper["authors"] = json.loads(paper["authors"])
                return paper

        return None

    def search_papers_for_research(self, keywords: List[str], limit: int = 5) -> List[Dict]:
        """
        Search papers for research purposes.

        Args:
            keywords: List of keywords to search for
            limit: Maximum results

        Returns:
            List of relevant papers with scores
        """
        import json

        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM papers")
        all_papers = cursor.fetchall()

        scored_papers = []
        for paper in all_papers:
            score = 0
            title_lower = (paper["title"] or "").lower()
            abstract_lower = (paper["abstract"] or "").lower()

            for keyword in keywords:
                keyword_lower = keyword.lower()
                if keyword_lower in title_lower:
                    score += 5
                if keyword_lower in abstract_lower:
                    score += 3

            if score > 0:
                paper_dict = dict(paper)
                # Parse JSON fields
                if paper_dict.get("authors"):
                    paper_dict["authors"] = json.loads(paper_dict["authors"])
                if paper_dict.get("reference_dois"):
                    paper_dict["references"] = json.loads(paper_dict["reference_dois"])
                    del paper_dict["reference_dois"]  # Rename to references for consistency
                scored_papers.append((score, paper_dict))

        # Sort by score
        scored_papers.sort(reverse=True, key=lambda x: x[0])
        return [paper for score, paper in scored_papers[:limit]]

    def insert_mercadolivre_favorite(
        self,
        item_id: str,
        title: str = None,
        price: float = None,
        currency: str = None,
        category_id: str = None,
        category_name: str = None,
        url: str = None,
        thumbnail_url: str = None,
        condition: str = None,
        available_quantity: int = None,
        bookmarked_date: str = None,
        is_available: bool = True,
        user_notes: str = None,
    ):
        """Insert or update Mercado Livre favorite.

        Args:
            item_id: Mercado Livre item ID
            title: Item title
            price: Current price
            currency: Currency (e.g., "BRL")
            category_id: Mercado Livre category ID
            category_name: Human-readable category
            url: Product URL
            thumbnail_url: Thumbnail image URL
            condition: "new" or "used"
            available_quantity: Stock quantity
            bookmarked_date: When user favorited (ISO format)
            is_available: Whether item is still for sale
            user_notes: User's notes about the item
        """
        cursor = self.conn.cursor()
        now = datetime.utcnow().isoformat()

        # Check if exists
        cursor.execute("SELECT id, first_synced FROM mercadolivre_favorites WHERE item_id = ?", (item_id,))
        existing = cursor.fetchone()

        if existing:
            # Update existing
            cursor.execute(
                """
                UPDATE mercadolivre_favorites
                SET title = ?, price = ?, currency = ?, category_id = ?, category_name = ?,
                    url = ?, thumbnail_url = ?, condition = ?, available_quantity = ?,
                    is_available = ?, last_checked = ?,
                    user_notes = COALESCE(?, user_notes)
                WHERE item_id = ?
                """,
                (
                    title,
                    price,
                    currency,
                    category_id,
                    category_name,
                    url,
                    thumbnail_url,
                    condition,
                    available_quantity,
                    is_available,
                    now,
                    user_notes,
                    item_id,
                ),
            )
        else:
            # Insert new
            cursor.execute(
                """
                INSERT INTO mercadolivre_favorites (
                    item_id, title, price, currency, category_id, category_name,
                    url, thumbnail_url, condition, available_quantity,
                    bookmarked_date, first_synced, last_checked, is_available,
                    user_notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item_id,
                    title,
                    price,
                    currency,
                    category_id,
                    category_name,
                    url,
                    thumbnail_url,
                    condition,
                    available_quantity,
                    bookmarked_date,
                    now,
                    now,
                    is_available,
                    user_notes,
                    now,
                ),
            )

        self.conn.commit()

    def get_mercadolivre_favorites(
        self,
        category: str = None,
        available_only: bool = False,
        limit: int = None,
    ) -> List[Dict]:
        """Get Mercado Livre favorites.

        Args:
            category: Filter by category name
            available_only: Only show items still for sale
            limit: Maximum number of results

        Returns:
            List of favorite dicts
        """
        cursor = self.conn.cursor()

        query = "SELECT * FROM mercadolivre_favorites WHERE 1=1"
        params = []

        if category:
            query += " AND category_name LIKE ?"
            params.append(f"%{category}%")

        if available_only:
            query += " AND is_available = 1"

        query += " ORDER BY bookmarked_date DESC"

        if limit:
            query += " LIMIT ?"
            params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()

        return [dict(row) for row in rows]

    def get_mercadolivre_favorite(self, item_id: str) -> Optional[Dict]:
        """Get a specific Mercado Livre favorite by item ID.

        Args:
            item_id: Mercado Livre item ID

        Returns:
            Favorite dict or None
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM mercadolivre_favorites WHERE item_id = ?", (item_id,))
        row = cursor.fetchone()

        return dict(row) if row else None

    def delete_mercadolivre_favorite(self, item_id: str):
        """Delete a Mercado Livre favorite.

        Args:
            item_id: Mercado Livre item ID
        """
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM mercadolivre_favorites WHERE item_id = ?", (item_id,))
        self.conn.commit()

    def update_mercadolivre_favorite_notes(self, item_id: str, notes: str):
        """Update user notes for a favorite.

        Args:
            item_id: Mercado Livre item ID
            notes: User's notes
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE mercadolivre_favorites SET user_notes = ? WHERE item_id = ?",
            (notes, item_id),
        )
        self.conn.commit()

    # ========================================================================
    # Inventory Management
    # ========================================================================

    def insert_item(
        self,
        name: str,
        description: str = None,
        category: str = None,
        status: str = 'owned',
        location: str = None,
        quantity: float = None,
        unit: str = None,
        acquired_date: str = None,
        acquired_price: float = None,
        current_value: float = None,
        photo_path: str = None,
        mercadolivre_item_id: str = None,
    ) -> int:
        """Insert a new inventory item.

        Args:
            name: Item name (required)
            description: Freeform description
            category: Category (tool, component, material, consumable, etc.)
            status: owned, wishlist, on_loan, broken, sold
            location: Where the item is stored
            quantity: Amount (for bulk items)
            unit: Unit of measurement (pcs, kg, m, L, etc.)
            acquired_date: When acquired (ISO format)
            acquired_price: Purchase price
            current_value: Current estimated value
            photo_path: Path to photo
            mercadolivre_item_id: Link to ML favorite if applicable

        Returns:
            Item ID
        """
        cursor = self.conn.cursor()
        now = datetime.utcnow().isoformat()

        cursor.execute(
            """
            INSERT INTO items (
                name, description, category, status, location,
                quantity, unit, acquired_date, acquired_price, current_value,
                photo_path, mercadolivre_item_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name, description, category, status, location,
                quantity, unit, acquired_date, acquired_price, current_value,
                photo_path, mercadolivre_item_id, now, now
            ),
        )

        self.conn.commit()
        return cursor.lastrowid

    def get_item(self, item_id: int) -> Optional[Dict]:
        """Get an inventory item by ID.

        Args:
            item_id: Item ID

        Returns:
            Item dict or None
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM items WHERE id = ?", (item_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_items(
        self,
        category: str = None,
        status: str = None,
        location: str = None,
        limit: int = None,
    ) -> List[Dict]:
        """Get inventory items with optional filters.

        Args:
            category: Filter by category
            status: Filter by status
            location: Filter by location (supports wildcards)
            limit: Max results

        Returns:
            List of item dicts
        """
        cursor = self.conn.cursor()

        query = "SELECT * FROM items WHERE 1=1"
        params = []

        if category:
            query += " AND category = ?"
            params.append(category)

        if status:
            query += " AND status = ?"
            params.append(status)

        if location:
            query += " AND location LIKE ?"
            params.append(location)

        query += " ORDER BY created_at DESC"

        if limit:
            query += " LIMIT ?"
            params.append(limit)

        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def update_item(self, item_id: int, **kwargs):
        """Update an inventory item.

        Args:
            item_id: Item ID
            **kwargs: Fields to update

        Supported fields: name, description, category, status, location,
                         quantity, unit, acquired_date, acquired_price,
                         current_value, photo_path
        """
        if not kwargs:
            return

        cursor = self.conn.cursor()
        now = datetime.utcnow().isoformat()

        # Build update query
        allowed_fields = {
            'name', 'description', 'category', 'status', 'location',
            'quantity', 'unit', 'acquired_date', 'acquired_price',
            'current_value', 'photo_path', 'mercadolivre_item_id'
        }

        fields = {k: v for k, v in kwargs.items() if k in allowed_fields}
        if not fields:
            return

        set_clause = ", ".join([f"{k} = ?" for k in fields.keys()])
        set_clause += ", updated_at = ?"

        values = list(fields.values()) + [now, item_id]

        cursor.execute(
            f"UPDATE items SET {set_clause} WHERE id = ?",
            values
        )
        self.conn.commit()

    def delete_item(self, item_id: int):
        """Delete an inventory item.

        Args:
            item_id: Item ID
        """
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM items WHERE id = ?", (item_id,))
        self.conn.commit()

    def set_item_attribute(
        self,
        item_id: int,
        key: str,
        value: str,
        value_type: str = 'string',
        source: str = 'user',
        confidence: float = None,
        confirmed: bool = True,
    ):
        """Set an item attribute (EAV).

        Args:
            item_id: Item ID
            key: Attribute key (e.g., "brand", "model")
            value: Attribute value
            value_type: string, number, boolean, json
            source: user, ml_match, ai_deepseek, etc.
            confidence: AI confidence score (0.0-1.0)
            confirmed: Whether user has confirmed
        """
        cursor = self.conn.cursor()
        now = datetime.utcnow().isoformat()

        # Check if attribute exists
        cursor.execute(
            "SELECT id FROM item_attributes WHERE item_id = ? AND key = ?",
            (item_id, key)
        )
        existing = cursor.fetchone()

        if existing:
            # Update
            cursor.execute(
                """
                UPDATE item_attributes
                SET value = ?, value_type = ?, source = ?, confidence = ?, confirmed = ?
                WHERE id = ?
                """,
                (value, value_type, source, confidence, 1 if confirmed else 0, existing[0])
            )
        else:
            # Insert
            cursor.execute(
                """
                INSERT INTO item_attributes (
                    item_id, key, value, value_type, source, confidence, confirmed, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (item_id, key, value, value_type, source, confidence, 1 if confirmed else 0, now)
            )

        self.conn.commit()

    def get_item_attributes(self, item_id: int) -> Dict[str, str]:
        """Get all attributes for an item.

        Args:
            item_id: Item ID

        Returns:
            Dict of key: value pairs
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT key, value FROM item_attributes WHERE item_id = ? AND confirmed = 1",
            (item_id,)
        )
        return {row['key']: row['value'] for row in cursor.fetchall()}

    def add_item_tag(self, item_id: int, tag: str):
        """Add a tag to an item.

        Args:
            item_id: Item ID
            tag: Tag string
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO item_tags (item_id, tag) VALUES (?, ?)",
            (item_id, tag)
        )
        self.conn.commit()

    def get_item_tags(self, item_id: int) -> List[str]:
        """Get all tags for an item.

        Args:
            item_id: Item ID

        Returns:
            List of tags
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT tag FROM item_tags WHERE item_id = ?", (item_id,))
        return [row['tag'] for row in cursor.fetchall()]

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
