# Database Schema Architecture

**Date:** 2025-11-19
**Status:** Approved
**Context:** Architecture Review Session

---

## Overview

Holocene uses **SQLite** as its primary database, with a schema designed for flexibility, performance, and clean evolution.

---

## Core Principles

### 1. Hybrid Tags Pattern ✅

**Decision:** Use normalized tables for taxonomy + JSON for freeform tags

**Structured Tags (Normalized):**
```sql
CREATE TABLE taxonomy_tags (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    parent_id INTEGER REFERENCES taxonomy_tags(id),
    system TEXT  -- 'dewey', 'udc', 'lc'
);

CREATE TABLE book_taxonomy_tags (
    book_id INTEGER REFERENCES books(id) ON DELETE CASCADE,
    tag_id INTEGER REFERENCES taxonomy_tags(id) ON DELETE CASCADE,
    PRIMARY KEY (book_id, tag_id)
);
```

**Freeform Tags (JSON):**
```sql
-- In content tables
enriched_tags TEXT DEFAULT '[]'  -- ["geology", "thesis-worthy", "favorite"]
```

**Why:**
- Taxonomy (Dewey/UDC) needs structure, hierarchy, queries
- User/enrichment tags need flexibility, no schema changes
- Future-proof: JSON → normalized is easy migration

---

### 2. Core Columns + metadata JSON ✅

**Decision:** Fixed columns for core fields, JSON for everything else

**Pattern:**
```sql
CREATE TABLE books (
    -- Identity
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Core fields (80%+ items, frequently queried)
    title TEXT NOT NULL,
    author TEXT,
    isbn TEXT,
    publication_year INTEGER,
    dewey_decimal TEXT,
    reading_status TEXT,
    owned BOOLEAN DEFAULT 1,

    -- Timestamps (always include)
    created_at TEXT NOT NULL,
    updated_at TEXT,

    -- Flexible data (varying, experimental, external)
    metadata TEXT DEFAULT '{}'
);
```

**What Goes in metadata:**
```json
{
  "enrichment": {
    "summary": "...",
    "tags": ["geology", "mining"],
    "enriched_at": "2025-11-19T10:00:00Z"
  },
  "access": {
    "status": "public_domain",
    "url": "https://...",
    "has_local_pdf": true,
    "local_pdf_path": "/path/to/file.pdf",
    "downloaded_at": "2025-11-15T14:30:00Z"
  },
  "classification": {
    "system": "dewey",
    "udc": "55.01",
    "confidence": 0.95,
    "classified_at": "2025-11-19T09:00:00Z",
    "cutter_number": "I10a",
    "call_number": "550.182 I10a"
  },
  "external": {
    "goodreads_rating": 4.5,
    "ia_downloads": 12543,
    "calibre_uuid": "..."
  }
}
```

**Decision Rules:**

**Use Fixed Column when:**
- ✅ Used by 80%+ of items
- ✅ Core to Holocene functionality
- ✅ Frequently filtered/sorted
- ✅ Needs indexing

**Use metadata JSON when:**
- ✅ External API data (structure varies)
- ✅ Enrichment data from LLMs
- ✅ Optional/experimental fields
- ✅ Integration-specific data

**Never Use:**
- ❌ EAV tables (too slow, overkill for personal use)
- ❌ Python dict repr as TEXT (current ML specifications - terrible!)

---

### 3. Relationships: Normalize Critical, JSON for Casual ✅

**Decision:** Use foreign keys for bidirectional relationships, JSON for casual references

**Normalize:**
```sql
-- Books ↔ Papers (bidirectional, critical)
CREATE TABLE book_paper_citations (
    book_id INTEGER REFERENCES books(id) ON DELETE CASCADE,
    paper_id INTEGER REFERENCES papers(id) ON DELETE CASCADE,
    citation_type TEXT DEFAULT 'references',
    PRIMARY KEY (book_id, paper_id)
);

-- Books ↔ Books (series, related works)
CREATE TABLE book_relations (
    book_id INTEGER REFERENCES books(id) ON DELETE CASCADE,
    related_book_id INTEGER REFERENCES books(id) ON DELETE CASCADE,
    relation_type TEXT,  -- 'sequel', 'prequel', 'companion', 'cites'
    PRIMARY KEY (book_id, related_book_id)
);
```

**Keep in metadata JSON:**
```json
{
  "external_refs": {
    "wikipedia": "https://en.wikipedia.org/wiki/...",
    "goodreads": "https://www.goodreads.com/book/show/...",
    "related_urls": ["https://...", "https://..."]
  },
  "mentions": {
    "people": ["Arthur Endlein", "Claude Shannon"],
    "places": ["MIT", "Stanford"],
    "other_books": ["TAOCP"]  // Casual mention, not tracked
  }
}
```

**Decision Rule:**

**Normalize when:**
- ✅ Relationship is **bidirectional**
- ✅ Need to **query both directions**
- ✅ Referential integrity **critical**
- ✅ Relationship has **metadata**

**Keep TEXT/JSON when:**
- ✅ Relationship is **one-way** (informational only)
- ✅ References are **external** (URLs, ISBNs not tracked)
- ✅ Casual "see also" references
- ✅ Referential integrity **not critical**

**Critical: Enable Foreign Keys!**
```python
# holocene/storage/database.py
def connect(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")  # CRITICAL!
    conn.execute("PRAGMA journal_mode = WAL")  # Better concurrency
    return conn
```

---

### 4. Schema Evolution: Stop ALTER TABLE! ✅

**Decision:** Use metadata JSON for new fields, lightweight migrations for core changes

**Default Approach (90% of cases):**
```python
# Want to track Goodreads rating? → metadata JSON
book.metadata['goodreads_rating'] = 4.5

# Want to track series info? → metadata JSON
book.metadata['series'] = {"name": "Foundation", "number": 1}

# Want to experiment with new integration? → metadata JSON
book.metadata['librarything_id'] = "12345"

# NO ALTER TABLE NEEDED!
```

**Rare: Formal Migration (10% of cases):**

Use lightweight custom migrations for:
- Adding new **core tables** (reading_queues, book_paper_citations)
- Adding **critical indexes** (performance)
- Enabling **foreign keys** (one-time)
- Restructuring **existing data** (migrate CSV tags → normalized)

**Migration System:**
```python
# holocene/storage/migrations.py
MIGRATIONS = [
    {
        'version': 1,
        'name': 'add_metadata_columns',
        'description': 'Add metadata JSON to all content tables',
        'up': """
            ALTER TABLE books ADD COLUMN metadata TEXT DEFAULT '{}';
            ALTER TABLE papers ADD COLUMN metadata TEXT DEFAULT '{}';
            ALTER TABLE links ADD COLUMN metadata TEXT DEFAULT '{}';
            ALTER TABLE mercadolivre_favorites ADD COLUMN metadata TEXT DEFAULT '{}';
            ALTER TABLE activities ADD COLUMN metadata TEXT DEFAULT '{}';
        """,
    },
    {
        'version': 2,
        'name': 'enable_foreign_keys',
        'description': 'Enable foreign key enforcement',
        'up': 'PRAGMA foreign_keys = ON;',
    },
    {
        'version': 3,
        'name': 'add_missing_indexes',
        'description': 'Add performance indexes',
        'up': """
            CREATE INDEX IF NOT EXISTS idx_links_trust_tier ON links(trust_tier);
            CREATE INDEX IF NOT EXISTS idx_links_source ON links(source);
            CREATE INDEX IF NOT EXISTS idx_books_dewey ON books(dewey_decimal);
            CREATE INDEX IF NOT EXISTS idx_ml_enriched_at ON mercadolivre_favorites(enriched_at);
        """,
    }
]

# Track in database
CREATE TABLE schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT
);

# Auto-apply on startup
def apply_migrations(db):
    current = get_current_version(db)
    for migration in MIGRATIONS:
        if migration['version'] > current:
            logger.info(f"Applying migration {migration['version']}: {migration['name']}")
            db.execute(migration['up'])
            db.execute(
                "INSERT INTO schema_version VALUES (?, ?, ?, ?)",
                (migration['version'], now(), migration['name'], migration['description'])
            )
            db.commit()
```

**Why Not Alembic?**
- Single-user tool (not a team project)
- metadata JSON reduces migration need by 90%
- Custom system is simpler, no dependencies
- Can upgrade to Alembic later if needed

---

## Database Improvements (Pending Implementation)

### Missing Indexes

**Links table (1,145 rows):**
```sql
CREATE INDEX idx_links_trust_tier ON links(trust_tier);
CREATE INDEX idx_links_source ON links(source);
CREATE INDEX idx_links_last_checked ON links(last_checked);
```

**Books table (77 rows):**
```sql
CREATE INDEX idx_books_dewey ON books(dewey_decimal);
CREATE INDEX idx_books_enriched_at ON books(enriched_at);
CREATE INDEX idx_books_publication_year ON books(publication_year);
```

**Mercado Livre (884 rows):**
```sql
CREATE INDEX idx_ml_enriched_at ON mercadolivre_favorites(enriched_at);
CREATE INDEX idx_ml_brightdata_blocked ON mercadolivre_favorites(brightdata_blocked);
```

**Estimated Impact:**
- Links queries: **10-50x faster**
- ML enrichment queries: **5-10x faster**
- Book browsing: **Instant** vs full table scan

### Enable Foreign Keys

```python
# Currently: FKs defined but not enforced!
# Fix: Enable on every connection
conn.execute("PRAGMA foreign_keys = ON")
```

**Before enabling:**
- Clean up existing broken references (migration)
- Test that nothing breaks

---

## Standard Table Template

**All new content tables should follow this pattern:**

```sql
CREATE TABLE table_name (
    -- Identity
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Core fields (stable, frequently queried)
    -- Keep minimal! Only 80%+ used fields
    title TEXT NOT NULL,
    source TEXT NOT NULL,

    -- Timestamps (always include these two)
    created_at TEXT NOT NULL,
    updated_at TEXT,

    -- Flexible data (varying, experimental, external)
    metadata TEXT DEFAULT '{}'
);

-- Indexes for core fields only
CREATE INDEX idx_table_name_source ON table_name(source);
CREATE INDEX idx_table_name_created_at ON table_name(created_at);
```

**System tables (stable, no metadata needed):**
- taxonomy_tags
- reading_queues
- queue_items
- book_paper_citations
- book_relations

---

## Migration from Current Schema

### Books Table Cleanup

**Current (Messy):**
- 14 ad-hoc ALTER TABLE additions
- Inconsistent naming
- Many nullable columns

**Target (Clean):**
```sql
CREATE TABLE books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Core (keep as columns)
    title TEXT NOT NULL,
    author TEXT,
    isbn TEXT,
    publication_year INTEGER,
    dewey_decimal TEXT,
    reading_status TEXT,
    owned BOOLEAN DEFAULT 1,

    -- Timestamps
    created_at TEXT NOT NULL,
    updated_at TEXT,

    -- Everything else → metadata JSON
    metadata TEXT DEFAULT '{}'
);
```

**Migration Strategy:**
```python
# 1. Add metadata column
ALTER TABLE books ADD COLUMN metadata TEXT DEFAULT '{}';

# 2. Migrate data to JSON
UPDATE books SET metadata = json_object(
    'enrichment', json_object(
        'summary', enriched_summary,
        'tags', json(enriched_tags),
        'enriched_at', enriched_at
    ),
    'access', json_object(
        'status', access_status,
        'url', access_url,
        'has_local_pdf', has_local_pdf,
        'local_pdf_path', local_pdf_path,
        'downloaded_at', downloaded_at
    ),
    'classification', json_object(
        'system', classification_system,
        'udc', udc_classification,
        'confidence', classification_confidence,
        'classified_at', classified_at,
        'cutter_number', cutter_number,
        'call_number', call_number
    ),
    'reading', json_object(
        'started_at', started_reading_at,
        'finished_at', finished_reading_at
    ),
    'references', json(ref_list)
);

# 3. Later: Drop old columns (SQLite requires table recreation)
# For now, just stop using them
```

---

## Performance Considerations

### SQLite JSON Performance

**Fast Operations:**
```sql
-- Extract single field
SELECT json_extract(metadata, '$.enrichment.summary') FROM books;

-- Filter on JSON field
SELECT * FROM books
WHERE json_extract(metadata, '$.external.goodreads_rating') > 4.0;

-- SQLite 3.45+: Index JSON paths
CREATE INDEX idx_books_goodreads
ON books(json_extract(metadata, '$.external.goodreads_rating'));
```

**Slow Operations (Avoid):**
```sql
-- Full-text search inside JSON (use FTS5 instead)
SELECT * FROM books WHERE metadata LIKE '%Foundation%';  -- SLOW!

-- Deep nesting (keep JSON shallow)
metadata.level1.level2.level3.level4.level5  -- Too deep!
```

**Best Practices:**
- Keep JSON depth ≤ 3 levels
- Index frequently queried JSON paths (SQLite 3.45+)
- Use FTS5 for full-text search on JSON content

---

## Related Documents

- `docs/database_current_state.md` - Current schema snapshot
- `design/architecture/holocene_architecture.md` - Overall architecture
- `docs/ROADMAP.md` - Implementation priorities

---

**Last Updated:** 2025-11-19
**Status:** Approved in Architecture Review
