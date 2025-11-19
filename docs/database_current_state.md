# Holocene Database Current State

**Purpose:** Snapshot of current database schema for Architecture Review
**Database:** SQLite 3.x
**Location:** `~/.holocene/holocene.db`
**Last Updated:** 2025-11-19

---

## Overview

**Current Size:** ~884 ML favorites, 77 books, 17 papers, 1,145 links, 2 inventory items
**Tables:** 6 main tables (activities, links, books, papers, mercadolivre_favorites, items)
**Indexes:** ~25 indexes across tables
**Foreign Keys:** None enforced (SQLite doesn't enforce by default)

---

## Tables & Schema

### 1. `activities` - Activity Tracking
```sql
CREATE TABLE activities (
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
);

-- Indexes
CREATE INDEX idx_activities_timestamp ON activities(timestamp);
CREATE INDEX idx_activities_type ON activities(activity_type);
CREATE INDEX idx_activities_source ON activities(source);
```

**Issues:**
- `tags` and `metadata` stored as TEXT (should be JSON?)
- No user_id (single-user assumption baked in)
- `timestamp` vs `created_at` - redundant?

---

### 2. `links` - Link Collection with Trust Tiers
```sql
CREATE TABLE links (
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
    -- Added later via ALTER TABLE
    archive_attempts INTEGER DEFAULT 0,
    last_archive_attempt TEXT,
    last_archive_error TEXT,
    next_retry_after TEXT,
    trust_tier TEXT,
    archive_date TEXT
);

-- Indexes
CREATE INDEX idx_links_url ON links(url);
CREATE INDEX idx_links_archived ON links(archived);
```

**Issues:**
- 1,145 links (large table, needs optimization)
- No index on `trust_tier` (but we filter by it)
- No index on `source` (but we query by it)
- `archive_attempts` column added ad-hoc (schema drift)
- Timestamps inconsistent: `first_seen`, `last_seen`, `last_checked`, `created_at` all TEXT

---

### 3. `books` - Book Collection with Dewey Classification
```sql
CREATE TABLE books (
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
    owned BOOLEAN DEFAULT 1,
    source TEXT DEFAULT 'librarycat',
    date_added TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    -- Added later via ALTER TABLE
    enriched_summary TEXT,
    enriched_tags TEXT,
    enriched_at TEXT,
    access_status TEXT,
    access_url TEXT,
    has_local_pdf BOOLEAN DEFAULT 0,
    local_pdf_path TEXT,
    downloaded_at TEXT,
    ref_list TEXT,
    reading_status TEXT,
    started_reading_at TEXT,
    finished_reading_at TEXT,
    udc_classification TEXT,
    classification_system TEXT,
    classification_confidence TEXT,
    classified_at TEXT,
    cutter_number TEXT,
    call_number TEXT
);

-- Indexes (6 indexes)
CREATE INDEX idx_books_title ON books(title);
CREATE INDEX idx_books_author ON books(author);
CREATE INDEX idx_books_subjects ON books(subjects);
CREATE INDEX idx_books_access_status ON books(access_status);
CREATE INDEX idx_books_has_local_pdf ON books(has_local_pdf);
CREATE INDEX idx_books_reading_status ON books(reading_status);
```

**Issues:**
- **Extreme schema drift** - 14 columns added ad-hoc after initial creation
- `subjects`, `enriched_tags`, `ref_list` stored as TEXT (should be proper lists/JSON?)
- Many nullable timestamp columns with inconsistent naming (`enriched_at`, `classified_at`, `downloaded_at`, `date_added`)
- No foreign keys to `papers` table (despite `ref_list` referencing paper DOIs)
- ISBN not UNIQUE constraint (could have duplicates)
- Denormalized: author as TEXT (what if multiple authors? what about author disambiguation?)

---

### 4. `papers` - Academic Papers
```sql
CREATE TABLE papers (
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
    -- Added later
    summary TEXT,
    analysis_pages INTEGER,
    total_pages INTEGER,
    full_text_analyzed BOOLEAN DEFAULT 0,
    last_analyzed_at TEXT
);

-- Indexes (12 indexes!)
CREATE INDEX idx_papers_doi ON papers(doi);
CREATE INDEX idx_papers_arxiv_id ON papers(arxiv_id);
CREATE INDEX idx_papers_pmid ON papers(pmid);
CREATE INDEX idx_papers_openalex_id ON papers(openalex_id);
CREATE INDEX idx_papers_normalized_key ON papers(normalized_key);
CREATE INDEX idx_papers_access_status ON papers(access_status);
CREATE INDEX idx_papers_has_local_pdf ON papers(has_local_pdf);
CREATE INDEX idx_papers_reading_status ON papers(reading_status);
CREATE INDEX idx_papers_title ON papers(title);
CREATE INDEX idx_papers_date ON papers(publication_date);
CREATE INDEX idx_papers_oa ON papers(is_open_access);
CREATE INDEX idx_papers_full_text_analyzed ON papers(full_text_analyzed);
```

**Issues:**
- `authors`, `reference_dois`, `ref_list` stored as TEXT (should be proper structures)
- 12 indexes (might be over-indexed for 17 papers!)
- No foreign keys between papers (despite `reference_dois` field)
- `normalized_key` used for deduplication but not clear what algorithm generates it
- Many empty nullable fields (only 17 papers)

---

### 5. `mercadolivre_favorites` - Mercado Livre Products
```sql
CREATE TABLE mercadolivre_favorites (
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

    created_at TEXT NOT NULL,

    -- Added later (enrichment)
    description TEXT,
    original_price REAL,
    specifications TEXT,
    seller_nickname TEXT,
    seller_reputation TEXT,
    reviews_rating REAL,
    reviews_total INTEGER,
    warranty TEXT,
    free_shipping BOOLEAN,
    enriched_at TEXT,
    cached_html_path TEXT,
    brightdata_blocked BOOLEAN DEFAULT 0
);
```

**Issues:**
- 884 items (large table, needs optimization)
- `specifications` stored as TEXT (Python dict repr: `"{'key': 'value'}"`)
- No index on `enriched_at` (but we filter unenriched items)
- No index on `brightdata_blocked` (but we filter by it)
- `tags` as TEXT (should be JSON array?)
- Mixing product data with personal classification (`dewey_class`, `call_number`, `user_notes`)
- No foreign key to `items` table (should link ML favorites to inventory?)

---

### 6. `items` - Personal Inventory
```sql
CREATE TABLE items (
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

    -- Classification
    dewey_class TEXT,
    call_number TEXT,
    tags TEXT,

    -- Timestamps
    created_at TEXT NOT NULL,
    updated_at TEXT
);

-- Additional tables for item metadata
CREATE TABLE item_attributes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
);

CREATE TABLE item_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,
    tag TEXT NOT NULL,
    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
);
```

**Issues:**
- Only 2 items (very new feature)
- `mercadolivre_item_id` as TEXT (should be foreign key?)
- `tags` in main table AND separate `item_tags` table (inconsistent!)
- `category` vs `dewey_class` (which classification system to use?)
- No indexes yet (too small to matter)
- **Has foreign keys!** (only table with proper relationships)

---

## Current Problems & Pain Points

### Schema Evolution Issues

1. **Ad-hoc ALTER TABLE everywhere**
   - `brightdata_blocked` just added today
   - `cached_html_path` added yesterday
   - `enriched_at`, `classified_at` added over time
   - No migration tracking (don't know what was added when)

2. **Inconsistent naming conventions**
   - `enriched_at` vs `enrichment_date`
   - `created_at` vs `date_added`
   - `is_available` vs `has_local_pdf` (boolean naming)
   - `mercadolivre_item_id` vs `item_id`

3. **No constraints**
   - No UNIQUE constraints (except implicit on PRIMARY KEY)
   - No NOT NULL enforcement (many should be required)
   - No CHECK constraints (e.g., price > 0, quantity >= 0)
   - No foreign key enforcement (SQLite has it disabled by default)

### Data Integrity Issues

4. **TEXT columns for structured data**
   - `specifications TEXT` = `"{'key': 'value'}"` (Python repr)
   - `authors TEXT` = comma-separated list
   - `tags TEXT` = comma-separated list
   - `metadata TEXT` in activities (should be JSON)
   - Should use JSON1 extension or proper tables

5. **No relationships enforced**
   - Books reference papers via `ref_list` (TEXT) but no foreign keys
   - Papers reference other papers via `reference_dois` (TEXT) but no foreign keys
   - ML favorites → inventory via `mercadolivre_item_id` but no foreign key
   - Can't CASCADE deletes, can't JOIN efficiently

6. **Timestamp chaos**
   - All timestamps stored as TEXT (ISO format strings)
   - Mix of `CURRENT_TIMESTAMP` (SQLite function) and Python datetime.now()
   - Some use `created_at`, others `date_added`, others `first_synced`
   - No timezone information (assumes local time? UTC?)

### Performance Issues

7. **Missing indexes**
   - `trust_tier` on links (we filter by it!)
   - `enriched_at` on mercadolivre_favorites (we filter by it!)
   - `brightdata_blocked` on mercadolivre_favorites (we filter by it!)
   - `source` on links (we group by it!)

8. **Over-indexing**
   - Papers table has 12 indexes for 17 rows (overkill)
   - Every ID field indexed separately (doi, arxiv_id, pmid, etc.)

9. **No full-text search**
   - Searching books/papers/links by text is slow
   - Could use SQLite FTS5 extension
   - Or migrate to PostgreSQL for better full-text search

### Query Patterns

10. **Common queries not optimized**
    ```sql
    -- Unenriched ML favorites (no index on enriched_at)
    SELECT * FROM mercadolivre_favorites WHERE enriched_at IS NULL;

    -- Pre-LLM links (no index on trust_tier)
    SELECT * FROM links WHERE trust_tier = 'pre-llm';

    -- Books by classification (no index on dewey_decimal)
    SELECT * FROM books ORDER BY dewey_decimal;
    ```

---

## Schema Design Pattern Questions (The Real Issue)

**SQLite is fine.** The real question is: **What schema patterns should we use consistently?**

### Current Inconsistencies

**Problem 1: Tags Storage - Three Different Approaches**
```sql
-- Approach 1: TEXT column with comma-separated values
books.enriched_tags TEXT  -- "geology,mining,geostatistics"

-- Approach 2: Separate table with foreign keys
item_tags(item_id, tag)  -- Proper many-to-many

-- Approach 3: TEXT column (used for tags but stored differently)
activities.tags TEXT  -- Could be CSV or JSON
```

**Problem 2: Attributes - EAV vs Fixed Columns**
```sql
-- EAV Pattern (flexible, used for items)
item_attributes(item_id, key, value)  -- Can store ANY attribute

-- Fixed Columns (rigid, used for ML favorites)
mercadolivre_favorites.seller_nickname TEXT
mercadolivre_favorites.seller_reputation TEXT
mercadolivre_favorites.reviews_rating REAL
-- What if ML adds new fields? ALTER TABLE again?

-- JSON Blob (hybrid, but stored as Python repr)
mercadolivre_favorites.specifications TEXT  -- "{'Brand': 'Sony', 'Model': 'PS5'}"
```

**Problem 3: Relationships - Denormalized Text vs Foreign Keys**
```sql
-- Denormalized (current approach for books/papers)
books.ref_list TEXT  -- "10.1234/abc, 10.5678/def"
papers.reference_dois TEXT  -- "10.1234/abc, 10.5678/def"

-- Proper relationship (only used in items)
item_attributes.item_id INTEGER FOREIGN KEY REFERENCES items(id)

-- Orphaned reference (no enforcement)
items.mercadolivre_item_id TEXT  -- Should be FK but isn't
```

### Questions We Need to Answer

#### 1. When to use EAV (Entity-Attribute-Value)?

**Current:** Only `item_attributes` table uses EAV
```sql
item_attributes(item_id, key, value)
-- Flexible: Can store ANY attribute without schema changes
-- Query: SELECT value WHERE item_id=1 AND key='Brand'
```

**Pros:**
- ✅ Extreme flexibility (add any attribute without ALTER TABLE)
- ✅ Good for user-defined metadata
- ✅ Works well for sparse data (not every item has every attribute)

**Cons:**
- ❌ Harder to query (can't do `SELECT Brand FROM items`)
- ❌ No type safety (everything is TEXT)
- ❌ Harder to index efficiently
- ❌ JOIN-heavy queries

**When to use EAV?**
- User-defined custom fields
- Sparse attributes (most items don't have them)
- Attributes vary wildly across item types

**When NOT to use EAV?**
- Core fields everyone has (name, description)
- Need type safety (numbers, dates, booleans)
- Need fast queries on the attribute
- Need aggregations (AVG, SUM, etc.)

#### 2. How to store tags/categories?

**Option A: Separate table (many-to-many)**
```sql
CREATE TABLE tags (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE item_tags (
    item_id INTEGER,
    tag_id INTEGER,
    FOREIGN KEY (item_id) REFERENCES items(id),
    FOREIGN KEY (tag_id) REFERENCES tags(id)
);
```
**Pros:** Proper normalization, can query "all items with tag X", can count tag usage
**Cons:** More tables, more JOINs, more complexity

**Option B: JSON array in column**
```sql
items.tags TEXT  -- '["geology", "mining", "geostatistics"]'
-- Query: json_each(tags) for SQLite JSON1 extension
```
**Pros:** Simple, single column, good for read-heavy workloads
**Cons:** Harder to query "all items with tag X", no tag reuse/normalization

**Option C: Comma-separated TEXT**
```sql
items.tags TEXT  -- "geology,mining,geostatistics"
```
**Pros:** Simplest to implement
**Cons:** No data integrity, hard to query, no type safety, fragile

**Recommendation needed:** Pick ONE approach and use consistently

#### 3. How to handle variable attributes (ML specifications, book metadata)?

**Current mess:**
```sql
-- Python dict repr as TEXT
mercadolivre_favorites.specifications TEXT
-- "{'Brand': 'Sony', 'Model': 'PS5', 'Year': 2020}"

-- Multiple fixed columns
mercadolivre_favorites.seller_nickname TEXT
mercadolivre_favorites.seller_reputation TEXT
mercadolivre_favorites.reviews_rating REAL

-- EAV table
item_attributes(item_id, key, value)
```

**Option A: JSON column (SQLite JSON1)**
```sql
mercadolivre_favorites.specifications TEXT  -- Proper JSON
-- Store: {"Brand": "Sony", "Model": "PS5"}
-- Query: json_extract(specifications, '$.Brand')
```

**Option B: EAV table**
```sql
ml_attributes(item_id, key, value)
```

**Option C: Fixed columns for common fields + JSON for extras**
```sql
-- Common fields everyone has
mercadolivre_favorites.title TEXT NOT NULL
mercadolivre_favorites.price REAL NOT NULL

-- Variable fields as JSON
mercadolivre_favorites.extra_attributes TEXT  -- JSON
```

**Recommendation needed:** When to use which pattern?

#### 4. How to handle relationships between entities?

**Current:** Almost no foreign keys, lots of TEXT references

**Example: Books reference Papers**
```sql
-- Current (denormalized)
books.ref_list TEXT  -- "10.1234/abc, 10.5678/def"

-- Option A: Many-to-many table
CREATE TABLE book_paper_citations (
    book_id INTEGER,
    paper_id INTEGER,
    FOREIGN KEY (book_id) REFERENCES books(id),
    FOREIGN KEY (paper_id) REFERENCES papers(id)
);

-- Option B: Keep denormalized but use JSON
books.ref_list TEXT  -- '["10.1234/abc", "10.5678/def"]'
```

**Trade-offs:**
- Normalization = Data integrity, easier queries, can JOIN
- Denormalization = Simpler schema, faster reads, no JOINs

**When to normalize?**
- Frequently queried relationships
- Need CASCADE deletes
- Need to prevent orphans
- Need bidirectional queries

**When to keep denormalized?**
- Rarely queried
- Read-only references (won't delete)
- Simpler is better (personal use)

#### 5. How to handle flexible metadata that changes over time?

**Example:** Mercado Livre might add new product fields tomorrow.

**Option A: Schemaless (JSON)**
```sql
-- Everything in JSON, ultra-flexible
mercadolivre_favorites.data TEXT  -- Entire product as JSON
```

**Option B: Core fields + flexible extras**
```sql
-- Fixed columns for what we always need
mercadolivre_favorites.title TEXT NOT NULL
mercadolivre_favorites.price REAL NOT NULL

-- JSON for variable stuff
mercadolivre_favorites.extra_data TEXT  -- JSON
```

**Option C: ALTER TABLE as needed**
```sql
-- Add columns when we see new fields
ALTER TABLE mercadolivre_favorites ADD COLUMN new_field TEXT
```

**Current:** We're doing Option C (ALTER TABLE) which causes schema drift

### Proposed Schema Pattern Guidelines

**For Architecture Review - Need to Decide:**

1. **Tags/Categories Pattern**
   - ⬜ Separate `tags` table (normalized, many-to-many)
   - ⬜ JSON array in column (denormalized, simple)
   - ⬜ Hybrid: Core tags normalized, user tags as JSON

2. **Flexible Attributes Pattern**
   - ⬜ EAV tables for user-defined attributes
   - ⬜ JSON columns for variable external data (ML specs)
   - ⬜ Fixed columns for common fields + JSON for extras

3. **Relationships Pattern**
   - ⬜ Normalize critical relationships (books ↔ papers)
   - ⬜ Keep denormalized for references (less critical)
   - ⬜ Enable foreign key enforcement (PRAGMA foreign_keys = ON)

4. **Schema Evolution Pattern**
   - ⬜ Stop ad-hoc ALTER TABLE, use migration system
   - ⬜ JSON for new/variable fields from integrations
   - ⬜ Fixed columns only for core, stable fields

5. **Type Safety Pattern**
   - ⬜ Use proper SQL types (INTEGER, REAL, BOOLEAN) when possible
   - ⬜ Store timestamps consistently (ISO TEXT? INTEGER Unix? REAL Julian?)
   - ⬜ JSON for truly variable/nested data

**Goal:** Pick patterns and apply consistently across all tables

---

## Proposed Improvements (For Architecture Review)

### Short-term (Phase 4.3)

1. **Add missing indexes**
   ```sql
   CREATE INDEX idx_links_trust_tier ON links(trust_tier);
   CREATE INDEX idx_links_source ON links(source);
   CREATE INDEX idx_ml_enriched_at ON mercadolivre_favorites(enriched_at);
   CREATE INDEX idx_ml_brightdata_blocked ON mercadolivre_favorites(brightdata_blocked);
   ```

2. **Standardize timestamp columns**
   - Decide on naming: `created_at`, `updated_at`, `*_at` pattern
   - Document timezone (UTC vs local)
   - Consider using INTEGER for Unix timestamps (faster comparisons)

3. **Add NOT NULL constraints** (where appropriate)
   ```sql
   -- Can't alter existing columns, but can enforce in code
   -- New tables should have proper constraints
   ```

4. **Use JSON1 extension**
   ```sql
   -- Instead of: specifications TEXT = "{'key': 'value'}"
   -- Use: specifications TEXT with JSON1 functions
   SELECT json_extract(specifications, '$.key') FROM mercadolivre_favorites;
   ```

### Medium-term (Phase 5)

5. **Implement schema migrations**
   - Use Alembic (heavy) or custom migration scripts
   - Track migrations in `schema_migrations` table
   - Can rollback/forward

6. **Add FTS5 full-text search**
   ```sql
   CREATE VIRTUAL TABLE books_fts USING fts5(title, author, subjects);
   ```

7. **Consider foreign keys** (enable enforcement)
   ```sql
   PRAGMA foreign_keys = ON;
   -- Add foreign keys to new tables
   -- Retrofit existing tables (requires recreate)
   ```

8. **Normalize repeated data**
   - Authors table (many-to-many with books/papers)
   - Tags table (many-to-many with items/books/ML)
   - Categories table (for ML items)

### Long-term (Phase 6+)

9. **Evaluate PostgreSQL migration**
   - Only if we hit SQLite limits
   - Or if adding multi-user support
   - Use pgloader for migration

10. **Add audit trail** (if needed)
    ```sql
    CREATE TABLE audit_log (
        id INTEGER PRIMARY KEY,
        table_name TEXT NOT NULL,
        record_id INTEGER NOT NULL,
        action TEXT NOT NULL, -- INSERT, UPDATE, DELETE
        old_values TEXT,
        new_values TEXT,
        changed_at TEXT NOT NULL
    );
    ```

---

## Migration Strategy Options

### Option 1: Continue Ad-hoc (Current)
**Pros:** Fast, flexible, no overhead
**Cons:** No tracking, hard to reproduce, schema drift

### Option 2: Alembic
**Pros:** Industry standard, versioned, auto-generated
**Cons:** Heavy dependency, designed for SQLAlchemy ORM

### Option 3: Custom Migration System
**Pros:** Lightweight, tailored to our needs
**Cons:** Need to build it, maintain it

### Option 4: Hybrid
**Pros:** Best of both worlds
**Implementation:**
```python
# migrations/001_add_brightdata_blocked.py
def upgrade(db):
    db.execute("ALTER TABLE mercadolivre_favorites ADD COLUMN brightdata_blocked BOOLEAN DEFAULT 0")

def downgrade(db):
    # SQLite doesn't support DROP COLUMN easily
    pass
```

**Recommended:** Option 4 (Hybrid) - Lightweight custom system with migration tracking

---

## Questions for Architecture Review

1. **SQLite vs PostgreSQL?** Stay on SQLite or migrate now?
2. **Schema migrations?** Alembic, custom, or continue ad-hoc?
3. **Foreign keys?** Enable enforcement? Add relationships?
4. **JSON storage?** Use JSON1 extension? Store as TEXT?
5. **Full-text search?** FTS5, external search, or simple LIKE queries?
6. **Indexing strategy?** Add missing indexes? Remove redundant ones?
7. **Normalization?** Separate authors/tags tables? Or keep denormalized?
8. **Timestamp format?** TEXT (ISO), INTEGER (Unix), or REAL (Julian)?
9. **Column naming?** Standardize conventions across tables?
10. **Data integrity?** Add constraints retroactively?

---

## Related Documents

- `docs/ROADMAP.md` - Architecture Review Session planning
- `src/holocene/storage/database.py` - Current database implementation
- `design/architecture/database_schema.md` - (TBD) Proposed schema design

---

**Last Updated:** 2025-11-19
**Status:** Current State Snapshot - For Review
**Next Steps:** Architecture Review Session → Decide on improvements
