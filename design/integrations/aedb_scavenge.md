# AEDB Scavenge: Architecture Analysis & Integration Plan

**Date:** 2025-11-18
**Status:** Planning / Pre-Implementation
**Context:** Reviewing aedb_lib (mature knowledge management system) for ideas to integrate into Holocene

---

## Executive Summary

AEDB is a well-tested (87% coverage, 418 tests) knowledge management system built 3 weeks ago for link collection and Obsidian integration. While it has excellent features, **we must not blindly port code**. AEDB was built before agent-collaboration workflows; Holocene has different architecture needs.

**Key insight:** Take the *patterns and ideas*, redesign for Holocene's architecture.

---

## Analysis by Feature

### 1. ✅ Rate Limiter (APPROVED - Port with adaptations)

**AEDB Implementation:**
- Token bucket algorithm (174 lines)
- Per-domain rate limiting
- Thread-safe, global instance pattern

**Holocene Needs:**
- Same core algorithm
- Integration with all API clients (base class)
- Config-driven domain rates
- Support for NanoGPT rate limits (2000/day)

**Decision:** Port to `src/holocene/core/rate_limiter.py`, integrate with `BaseAPIClient`

**Architecture notes:**
```python
# Base client uses rate limiter
class BaseAPIClient:
    def __init__(self, rate_limiter=None):
        self.rate_limiter = rate_limiter or get_global_limiter()

    def request(self, url):
        if self.rate_limiter:
            self.rate_limiter.wait_for_token(url)
        return requests.get(url)

# All clients inherit
class CrossrefClient(BaseAPIClient):
    # Auto-gets rate limiting
```

---

### 2. ⚠️ Quality Scorer (QUESTION - What's it for?)

**User insight:** "More for pages than papers/books, right?"

**Correct!** Papers have peer review, books have established reputation. Quality scoring makes most sense for:
- ✅ Links (web content quality varies wildly)
- ✅ Research sources (rank which to read first)
- ❌ Books (Dewey + enrichment is sufficient)
- 🤔 Papers (citation count is better quality proxy)

**Holocene adaptation:**
- Use for link collection (when we add link management properly)
- Use in research mode to rank sources
- **NOT** for book/paper quality (different metrics apply)

**Decision:** Defer until we add comprehensive link management (Phase 5+)

**Alternative for papers:** Use citation count, journal impact factor, h-index

---

### 3. ✅ Retry Queue (APPROVED - Generalize existing)

**User insight:** "We already do exponential backoff for IA, right?"

**Correct!** We have ad-hoc retry logic in some places. Need to generalize:

**Current state:**
- IA client has basic retry
- No centralized retry queue
- No persistent failure tracking

**AEDB pattern:**
- Centralized retry queue (CSV-based)
- Error type tracking
- Configurable retry strategies
- Export/import for persistence

**Holocene design:**
```python
# src/holocene/core/retry_queue.py
class RetryQueue:
    """Centralized retry management for all operations"""

    def add_failed_operation(self, operation_type, details, error):
        # Store in SQLite, not CSV
        pass

    def get_retryable_items(self, operation_type, max_attempts=3):
        # Exponential backoff based on attempt count
        pass
```

**Use cases:**
- Failed Crossref API calls
- Timeout IA book downloads
- Network errors during batch enrichment
- Rate limit exceeded (retry after cooldown)

**Decision:** Implement in `src/holocene/core/retry_queue.py`, SQLite-backed, integrated with all API clients

---

### 4. 🤔 Analytics Dashboard (NEEDS DESIGN)

**Holocene-specific analytics:**

**For books:**
- Dewey distribution heatmap (which sections are full/sparse)
- Missing metadata breakdown (no author, no Dewey, etc.)
- Collection growth over time
- Top authors, publishers, publication years

**For papers:**
- Citation count distribution
- Publication year timeline
- Top authors/journals
- Pre-LLM vs post-LLM ratio

**For links:**
- Trust tier distribution (pre-LLM / early-LLM / recent)
- Top domains
- Dead link percentage
- Archive availability

**For activity (autonomous mode future):**
- Time by category
- Focus patterns
- Productivity metrics

**Decision:** Design custom analytics for Holocene's data model (books/papers/links/activity), inspired by AEDB but not copied

**Implementation:** `src/holocene/cli/stats.py` → `holo stats` command group

---

### 5. 🤔 Recommender System (QUESTION - Does it work?)

**User question:** "Do you think that could work?"

**Analysis:**

**Works well for:**
- ✅ Links (large collection, varied quality, browsing behavior)
- ✅ Papers (find related work, diversify reading)
- 🤔 Books (collection may be too small, reading is intentional not browsing)

**For Holocene:**
- **Books:** 77 items is too small for statistical recommendations. Better: manual "books like this" based on Dewey proximity
- **Papers:** Good fit! "Related papers" by citation/topic
- **Research mode:** Excellent fit - suggest sources for deep dive

**Holocene adaptation:**
```python
# Different strategies for different content types

# Books: Dewey-based similarity
holo books related 42  # Books near 550.182 in classification

# Papers: Citation + topic similarity
holo papers related DOI  # Papers that cite this + similar topics

# Research: Multi-source recommendations
holo research suggest "topic"  # Best books + papers + links
```

**Decision:** Implement simplified version focused on research mode, not general browsing

---

### 6. 💭 Vault Manager (DEEP QUESTION - Architecture decision)

**User insights:**
- "Never managed to use Obsidian that much"
- "Patchwork passes concept" - scan vault, find connections
- "Junction holo's data with vault, or create notes in vault?"

**Key architectural question:** Is Holocene an Obsidian plugin, or standalone?

**Option A: Standalone with optional Obsidian export**
```
~/.holocene/
  holocene.db          # Source of truth (SQLite)
  books/
  research/            # Markdown reports
  papers/

~/Documents/Obsidian/  # Optional, if user has it
  [junction to ~/.holocene/research/]  # Read-only
```

**Pros:**
- Independent of Obsidian
- Works for non-Obsidian users
- SQLite is source of truth
- Clean separation

**Cons:**
- Can't leverage Obsidian's graph view
- No native wikilink support

**Option B: Obsidian-first with database cache**
```
~/Documents/Obsidian/
  .holocene/           # Database + config
  Books/               # Markdown notes for each book
  Papers/              # Markdown notes for each paper
  Research/            # Research reports
  Daily/               # Activity logs (future)
```

**Pros:**
- Native Obsidian integration
- Wikilinks work [[like this]]
- Graph view built-in
- Patchwork passes are natural

**Cons:**
- Requires Obsidian
- More complex (markdown + DB sync)
- Potential conflicts if user edits

**Option C: Hybrid (Recommended)**
```
~/.holocene/
  holocene.db          # Source of truth
  config.yaml

  # Optional: vault_path in config
  vault_path: ~/Documents/Obsidian/Holocene/

# If vault_path set:
~/Documents/Obsidian/Holocene/
  Books/               # Generated from DB
  Papers/              # Generated from DB
  Research/            # Research reports
  _meta/               # Holocene metadata (gitignored)
```

**Pros:**
- Works standalone OR with Obsidian
- DB is source of truth
- Optional vault generation
- User choice

**Decision:** Implement Option C (Hybrid)

**"Patchwork passes" concept:**
```python
# Scan vault periodically, suggest connections
holo vault scan           # Index all markdown files
holo vault link-suggest   # Find potential [[wikilinks]] to add
holo vault graph          # Export knowledge graph

# Example: "Book #42 (Geostatistics) mentions 'kriging'
# → Paper #15 is about kriging → Suggest linking"
```

**Junctions vs. direct creation:**
- **Research reports:** Direct creation in vault (user might edit)
- **Book/paper notes:** Generated (single source of truth = DB)
- Use junctions if available, symlinks otherwise, or just direct writes

---

### 7. ✅ Archive Manager Caching (APPROVED)

**User insight:** "Better to have very good caching where we don't expect responses to change"

**AEDB has:** Disk-based JSON cache for IA availability checks

**Holocene needs:**
- Cache IA availability (doesn't change often)
- Cache Crossref metadata (stable after publication)
- Cache Wikipedia summaries (update periodically)
- **DON'T cache:** Book enrichment (may improve with better prompts)

**Architecture:**
```python
# src/holocene/core/cache.py
class APICache:
    """Flexible caching for API responses"""

    def __init__(self, cache_dir, ttl_seconds=None):
        self.cache_dir = cache_dir
        self.ttl = ttl_seconds  # None = forever

    def get(self, key):
        # Check if cached and not expired
        pass

    def set(self, key, value):
        # Store with timestamp
        pass

# Usage in clients
class InternetArchiveClient:
    def __init__(self, cache=True):
        self.cache = APICache("~/.holocene/cache/ia", ttl=None)  # Forever

    def check_availability(self, url):
        cached = self.cache.get(url)
        if cached:
            return cached
        result = self._fetch(url)
        self.cache.set(url, result)
        return result
```

**Cache strategy by API:**
- **IA availability:** Forever (URL archived = permanent)
- **Crossref metadata:** Forever (DOIs are stable)
- **Wikipedia:** 7 days (updated regularly)
- **NanoGPT enrichment:** Never (always fresh)
- **Book PDFs:** Local storage, not cache

**Decision:** Implement flexible caching in `BaseAPIClient`, configurable per-client

---

### 8. 🤔 Vector Database (ARCHITECTURE DECISION)

**User question:** "Necessary or good idea to have vector DB? Lightweight embedded? File-based for now?"

**Use cases needing vectors:**
- Book similarity ("books like this")
- Paper similarity (topic matching)
- Research topic clustering
- Auto-linking in vault

**Options:**

**A. No vectors (keep it simple)**
- Use TF-IDF + cosine similarity (sklearn)
- Store in SQLite as JSON blobs
- Good enough for <10,000 items

**B. Lightweight embedded (sqlite-vss, chromadb-lite)**
- SQLite extension for vectors
- No separate server
- ~100K items

**C. Full vector DB (Qdrant, Milvus, Weaviate)**
- Overkill for personal use
- More complexity

**Current collection size:**
- Books: 77
- Papers: 0 (will grow to hundreds/thousands)
- Links: 1,153
- **Total vectors needed:** <5,000 for now

**Recommendation:** **Start with file-based (sklearn embeddings in SQLite)**

**When to switch to vector DB:**
- Paper collection > 10,000
- Link collection > 50,000
- Performance becomes an issue

**Architecture:**
```python
# Store embeddings in SQLite for now
CREATE TABLE book_embeddings (
    book_id INTEGER PRIMARY KEY,
    embedding BLOB,  -- Numpy array serialized
    model TEXT,      -- e.g., "all-mpnet-base-v2"
    created_at TEXT
);

# Compute similarity in Python
def find_similar_books(book_id, top_k=5):
    target_emb = get_embedding(book_id)
    all_embs = get_all_embeddings()
    similarities = cosine_similarity([target_emb], all_embs)
    return top_k_indices(similarities)
```

**Decision:** File-based vectors in SQLite (phase 1), revisit vector DB if collection grows >10K items

---

### 9. ✅ Tag Extractor (APPROVED - Useful)

**Auto-extract tags from:**
- Book titles/summaries (programming languages, topics)
- Paper abstracts (methods, techniques)
- Research reports (key concepts)

**Pattern:**
- Programming languages: Python, JavaScript, C++, etc.
- Technical topics: ML, DevOps, Cloud, Geostatistics
- Named entities: (defer to DeepSeek V3 instead of spaCy)

**Holocene approach:** **Use DeepSeek V3 for tag extraction, not regex**

**Why:**
- Already have NanoGPT subscription
- More accurate than regex
- Understands context
- Can extract domain-specific tags (geology terms, mining concepts)

**Decision:** Implement LLM-based tag extraction, fallback to keyword patterns

---

### 10. ✅ Error Handling (APPROVED - Go deeper)

**Current state:** Ad-hoc error handling

**AEDB pattern:**
- Configurable error limits (`--max-errors 50`)
- Graceful degradation
- Error tracking and reporting

**Holocene needs:**
```python
# src/holocene/core/error_handler.py
class ErrorHandler:
    def __init__(self, max_errors=None, max_warnings=None):
        self.max_errors = max_errors
        self.max_warnings = max_warnings
        self.errors = []
        self.warnings = []

    def add_error(self, context, exception):
        self.errors.append({...})
        if self.max_errors and len(self.errors) >= self.max_errors:
            raise TooManyErrorsException()

    def report(self):
        # Summary at end of batch operation
        pass
```

**Use cases:**
- Batch book enrichment (stop after 50 failures)
- Crossref bulk import (continue on individual failures)
- Research compilation (warn but don't stop)

**Decision:** Implement centralized error handling for batch operations

---

### 11. ✅ Notify.run (APPROVED - Already done!)

**Status:** ✅ Already implemented `src/holocene/integrations/notify_run.py`

**Integration TODO:**
- Add to config (`notifications.enabled`, `notifications.channel`)
- Use in long-running operations
- Batch completion notifications

---

### 12. ✅ Source Extractors (APPROVED - Important)

**AEDB has extractors for:**
- Telegram exports
- RSS feeds
- YouTube playlists
- Browser history/bookmarks

**Holocene needs (by priority):**

**Phase 4.3 (Config & UX):**
- Browser bookmarks import (Chrome, Firefox, Edge)
- **Mercado Livre favorites** (NEW! 2025-11-18)
  - OAuth 2.0 integration
  - Sync favorited items
  - Classify as W prefix (web/commerce)
  - Price tracking (future)
  - See: `design/integrations/mercadolivre_favorites.md`
- Manual link import (CSV, JSON)

**Phase 5+ (daemon mode):**
- Browser history tracking (passive)
- RSS feeds for paper preprints (arXiv)
- YouTube educational content
- Telegram for mobile capture

**Decision:** Implement bookmark import + Mercado Livre in Phase 4.3, design extractor plugin architecture

---

### 13. ⚠️ Fuzzy Search (DEFER - Complexity vs. benefit)

**User question:** "Can we do it? How hard? Aren't we doing it already?"

**Current state:** Basic search in CLI (title/author matching)

**AEDB fuzzy search:**
- Levenshtein distance for typos
- Weighted ranking (fuzzy 40%, quality 30%, recency 20%, tags 10%)

**Complexity:** Medium (needs `fuzzywuzzy` or similar)

**Benefit for Holocene:**
- 77 books - easy to browse, fuzzy not critical
- Papers - helpful once collection grows
- Links - very helpful (1,153 items)

**Decision:**
- **Now:** Add basic fuzzy matching for `holo books search` (simple Levenshtein)
- **Later:** Weighted ranking when collections grow

**Simple implementation:**
```python
from difflib import SequenceMatcher

def fuzzy_match(query, text, threshold=0.6):
    ratio = SequenceMatcher(None, query.lower(), text.lower()).ratio()
    return ratio >= threshold
```

---

### 14. ✅ Reading Queue (APPROVED - Fits task system)

**User insight:** "Holo will have task queues anyway"

**Correct!** Reading queues are a special case of task queues.

**Holocene task architecture:**
```python
# General task queue (for autonomous mode)
holo tasks list
holo tasks add enrich-books
holo tasks run

# Reading queues (special case)
holo papers queue create dissertation
holo papers queue add dissertation DOI1 DOI2
holo papers queue next dissertation  # Mark as reading
holo papers queue done DOI1  # Mark complete
```

**Decision:** Implement reading queues as part of broader task system

**Table schema:**
```sql
CREATE TABLE reading_queues (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE,
    created_at TEXT
);

CREATE TABLE reading_queue_items (
    id INTEGER PRIMARY KEY,
    queue_id INTEGER,
    item_type TEXT,  -- 'book', 'paper', 'link'
    item_id INTEGER,
    status TEXT,     -- 'pending', 'reading', 'done'
    added_at TEXT,
    completed_at TEXT,
    FOREIGN KEY (queue_id) REFERENCES reading_queues(id)
);
```

---

### 15. ✅ Error Tracking (APPROVED - Pretty useful)

**Covered under #10 (Error Handling)**

---

## Architectural Principles for Integration

### Don't Copy-Paste, Redesign

**AEDB was built:**
- 3 weeks ago
- Before agent collaboration workflows
- For link-focused Obsidian integration
- With CSV/JSON files as primary storage

**Holocene is built:**
- Now, with agent collaboration
- For multi-modal knowledge management (books/papers/links/activity)
- With SQLite as source of truth
- With future daemon mode in mind
- With NanoGPT integration (not local Ollama)

### Core Architectural Decisions

**1. Storage: SQLite, not CSV/JSON**
- Single source of truth
- ACID transactions
- Better for concurrent access (daemon mode)
- Easier querying

**2. LLM: DeepSeek V3 via NanoGPT, not local Ollama**
- Already paying for it (<1% usage!)
- Better quality than Llama 3.2 3B
- Per-prompt pricing = send large contexts
- Ollama as fallback for offline/privacy-sensitive

**3. CLI-first, vault-optional**
- `holo` works standalone
- Obsidian vault is optional feature
- Users can generate vault or not

**4. Unified API client architecture**
- `BaseAPIClient` with rate limiting, caching, retry
- All integrations inherit
- Consistent behavior

**5. Task-oriented design**
- Everything is a task (one-shot, long-running, background)
- Supports future daemon mode
- Checkpoint/resume capability

---

## Integration Architecture Map

```
┌─────────────────────────────────────────────────────────┐
│                    Holocene Core                        │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────────┐  ┌───────────────┐  ┌─────────────┐ │
│  │ BaseAPIClient│  │  RetryQueue   │  │ErrorHandler │ │
│  │              │  │               │  │             │ │
│  │ - Rate limit │  │ - Exponential │  │ - Max errors│ │
│  │ - Caching    │  │   backoff     │  │ - Reporting │ │
│  │ - Retry logic│  │ - SQLite queue│  │             │ │
│  └──────────────┘  └───────────────┘  └─────────────┘ │
│                                                         │
├─────────────────────────────────────────────────────────┤
│                  API Integrations                       │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────────┐  ┌───────────────┐  ┌─────────────┐ │
│  │   Crossref   │  │ Internet      │  │  NanoGPT    │ │
│  │              │  │ Archive       │  │             │ │
│  │ (inherits    │  │ (+ caching)   │  │ (rate aware)│ │
│  │  base)       │  │               │  │             │ │
│  └──────────────┘  └───────────────┘  └─────────────┘ │
│                                                         │
├─────────────────────────────────────────────────────────┤
│                   Data Layer                            │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │             holocene.db (SQLite)                 │  │
│  │                                                  │  │
│  │  books │ papers │ links │ embeddings │ queues  │  │
│  │  activity │ tasks │ retry_queue │ cache       │  │
│  └──────────────────────────────────────────────────┘  │
│                                                         │
├─────────────────────────────────────────────────────────┤
│              Optional: Vault Layer                      │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  If config.vault_path set:                             │
│                                                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │         ~/Documents/Obsidian/Holocene/          │  │
│  │                                                  │  │
│  │  Books/    - Generated from DB                  │  │
│  │  Papers/   - Generated from DB                  │  │
│  │  Research/ - Direct creation (user editable)    │  │
│  │  _meta/    - Holocene metadata (gitignored)     │  │
│  │                                                  │  │
│  │  "Patchwork pass": Scan + suggest connections  │  │
│  └──────────────────────────────────────────────────┘  │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## Phased Implementation Plan

### Phase 4.2: Infrastructure (THIS SPRINT - Week of Nov 18)

**Goal:** Build foundation for all future features

**Tasks:**
1. ✅ Port rate limiter → `src/holocene/core/rate_limiter.py`
2. ✅ Create `BaseAPIClient` with rate limiting
3. ✅ Implement `APICache` for flexible caching
4. ✅ Implement `RetryQueue` (SQLite-backed)
5. ✅ Implement `ErrorHandler` for batch operations
6. ✅ Add notify.run to config
7. ✅ Update all existing clients to inherit BaseAPIClient

**Success criteria:**
- All API clients use rate limiting
- IA calls are cached
- Failed operations can be retried
- Error handling is consistent

---

### Phase 4.3: Config & UX (Week of Nov 25)

**Goal:** Better configuration and user experience

**Tasks:**
1. Implement `holo config` command group
2. Add `holo stats` for collection analytics
3. Implement rich terminal output (tables, progress bars)
4. Add fuzzy search to `holo books search`
5. Bookmark import (Chrome, Firefox)

**Success criteria:**
- Users can manage config via CLI
- Beautiful, informative output
- Easy to find books with typos
- Can import existing bookmarks

---

### Phase 4.4: Crossref Integration (Week of Dec 2)

**Goal:** Add comprehensive paper management

**Tasks:**
1. Implement `CrossrefClient` (with rate limiting, caching)
2. `holo papers search`, `add`, `list`, `show`
3. Paper metadata storage
4. Integration with research mode
5. Retry queue for failed fetches

**Success criteria:**
- Can search 165M papers
- Add papers to collection
- Research mode includes papers
- Robust to API failures

---

### Phase 4.5: Smart Features (Week of Dec 9)

**Goal:** Intelligence and recommendations

**Tasks:**
1. Implement tag extraction (LLM-based)
2. Book/paper embeddings for similarity
3. Simple recommender for research mode
4. Reading queue management
5. Analytics dashboard with visualizations

**Success criteria:**
- Auto-tag books and papers
- Find similar items
- Smart research suggestions
- Track reading progress

---

### Phase 5: Vault Integration (Jan 2026)

**Goal:** Optional Obsidian integration

**Tasks:**
1. Vault path configuration
2. Generate markdown notes from DB
3. "Patchwork pass" - scan and suggest links
4. Knowledge graph export
5. Wikilink support in research reports

**Success criteria:**
- Works with or without Obsidian
- Generated notes have wikilinks
- Can visualize knowledge graph
- Research reports link to books/papers

---

### Phase 6: Autonomous Mode (Q1 2026)

**Goal:** Background monitoring and automation

**Tasks:**
1. Daemon architecture
2. Browser extension for activity tracking
3. Task scheduler with priorities
4. IFTTT-style rules
5. Automated daily summaries

**Success criteria:**
- Runs in background
- Tracks activities automatically
- Executes scheduled tasks
- Generates insights

---

## Critical Design Questions to Resolve

Before implementing anything, we need to decide:

### ✅ ALL DECISIONS RESOLVED:

1. **Storage:** SQLite (not CSV/JSON) ✅
2. **LLM:** DeepSeek V3 primary, Ollama fallback ✅
3. **Architecture:** Unified API clients with shared infrastructure ✅
4. **Vault sync:** One-way with smart diff ingestion ✅
5. **Vector DB:** ChromaDB embedded (all-mpnet-base-v2) ✅
6. **Quality scoring:** Links only, not books/papers ✅
7. **Recommender:** Research-focused first ✅
8. **Classification:** Extended Dewey for all content types ✅

### ✅ DECISIONS MADE (2025-11-18):

4. **Vault integration:** ✅ One-way sync with smart diff ingestion
   - Source of truth: `~/.holocene/research/`
   - Vault gets copies, user can edit
   - Smart diff to merge changes back
   - Section-based conflict resolution
   - See vault sync architecture below

5. **Vector DB:** ✅ ChromaDB embedded with all-mpnet-base-v2
   - Semantic search (much better than TF-IDF)
   - ChromaDB manages models automatically
   - ~400MB model, ~300KB data for 77 books
   - Not a resource hog

6. **Quality scoring:** ✅ Only for links/web content, NOT books/papers
   - Books: Dewey + enrichment sufficient
   - Papers: Citation count is better metric
   - Links: Quality varies wildly, scoring helpful

7. **Recommender:** ✅ Research-focused (Phase 4.5), browsing later (Phase 6)
   - Phase 4.5: `holo research suggest "topic"`
   - Phase 4.5: `holo books related 42` (simple similarity)
   - Phase 6: Serendipity/diversity for larger collections

8. **Extended Dewey:** ✅ APPROVED - Unified classification across all content
   - Books: `550.182 I10a` (standard Dewey)
   - Papers: `P550.182 M63` (P prefix)
   - Web: `W550.182` (W prefix)
   - Research: `R550.182` (R prefix)
   - See `design/features/extended_dewey_classification.md`

---

## Vault Sync Architecture (Detailed Design)

### Overview

**Source of truth:** `~/.holocene/research/` (Holocene app directory)
**Vault:** Optional copy at `~/Documents/Obsidian/Holocene/`
**Sync direction:** Primary one-way (Holocene → Vault), with smart ingestion of user edits

### File Locations

```
~/.holocene/
  research/
    2025-11-18_structural_geology.md          # PRIMARY (source of truth)
    2025-11-15_geostatistics_methods.md

  .vault_sync/
    last_sync.json                             # Sync state tracking
    diffs/                                     # Staged user changes
      structural_geology_2025-11-18.diff

~/Documents/Obsidian/Holocene/
  Research/
    2025-11-18_structural_geology.md          # COPY (user can edit)

  .holocene/
    sync_manifest.json                         # Sync metadata
```

### Sync Workflow

**1. Initial sync (new report):**
```bash
holo research start "structural geology"
# → Creates ~/.holocene/research/2025-11-18_structural_geology.md

holo vault sync
# → Copies to ~/Documents/Obsidian/Holocene/Research/
# → Records hash in sync manifest
```

**2. User edits in Obsidian:**
```
User opens file in Obsidian, adds:
- Field observations
- Personal notes
- Links to other notes [[like this]]
- Saves changes
```

**3. Next sync detects changes:**
```bash
holo vault sync
# → Computes hash of vault file
# → Compares with last sync hash
# → Detects change
# → Stages diff in ~/.holocene/.vault_sync/diffs/
# → Logs: "User changes detected, run 'holo vault ingest'"
```

**4. Review and merge:**
```bash
holo vault check-changes
# → "Found 1 modified report: structural_geology"
# → "15 lines added, 2 lines modified"

holo vault show-diff structural_geology
# → Shows unified diff with context

holo vault ingest structural_geology --interactive
# → Section-by-section merge UI
# → User accepts/rejects/edits changes
# → Updates ~/.holocene/research/ (source of truth)
```

**5. Future syncs use merged version:**
```bash
holo vault sync
# → Source includes user changes now
# → Copies merged version to vault
# → Updates sync hash
```

### Implementation

```python
# src/holocene/integrations/vault_sync.py

import hashlib
import difflib
from pathlib import Path

class VaultSync:
    """One-way sync with smart diff ingestion"""

    def __init__(self, vault_path):
        self.vault_path = Path(vault_path)
        self.holocene_dir = Path.home() / ".holocene"
        self.research_dir = self.holocene_dir / "research"
        self.sync_dir = self.holocene_dir / ".vault_sync"
        self.diff_dir = self.sync_dir / "diffs"

        self.sync_dir.mkdir(exist_ok=True)
        self.diff_dir.mkdir(exist_ok=True)

    def sync_to_vault(self):
        """Copy research reports from Holocene → Vault"""
        reports = self.get_research_reports()

        for report in reports:
            vault_path = self.vault_path / "Research" / report.name

            if not vault_path.exists():
                # New file - just copy
                shutil.copy(report, vault_path)
                self.mark_synced(report, vault_path)
                logger.info(f"Synced new report: {report.name}")

            else:
                # Check if user modified vault copy
                if self.has_user_changes(vault_path):
                    # Don't overwrite! Stage diff
                    self.stage_diff(report, vault_path)
                    logger.warning(f"User changes detected: {report.name}")
                else:
                    # Safe to update
                    shutil.copy(report, vault_path)
                    self.mark_synced(report, vault_path)

    def has_user_changes(self, vault_file):
        """Check if user edited vault copy"""
        manifest = self.load_sync_manifest()
        file_key = str(vault_file.relative_to(self.vault_path))

        if file_key not in manifest:
            return False  # Never synced

        last_hash = manifest[file_key]["hash"]
        current_hash = self.file_hash(vault_file)

        return last_hash != current_hash

    def file_hash(self, path):
        """SHA256 hash of file content"""
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def stage_diff(self, source, modified):
        """Create diff for manual review"""
        source_lines = source.read_text().splitlines()
        modified_lines = modified.read_text().splitlines()

        diff = difflib.unified_diff(
            source_lines,
            modified_lines,
            fromfile=f"holocene/{source.name}",
            tofile=f"vault/{modified.name}",
            lineterm=''
        )

        diff_file = self.diff_dir / f"{source.stem}.diff"
        diff_file.write_text('\n'.join(diff))
        logger.info(f"Diff staged: {diff_file}")

    def check_changes(self):
        """Check for user-modified files"""
        changes = []
        reports = self.get_research_reports()

        for report in reports:
            vault_path = self.vault_path / "Research" / report.name
            if vault_path.exists() and self.has_user_changes(vault_path):
                changes.append({
                    'name': report.name,
                    'source': report,
                    'modified': vault_path,
                    'diff_file': self.diff_dir / f"{report.stem}.diff"
                })

        return changes

    def show_diff(self, report_name):
        """Display diff for a report"""
        diff_file = self.diff_dir / f"{Path(report_name).stem}.diff"

        if not diff_file.exists():
            logger.error(f"No diff found for {report_name}")
            return

        # Pretty print diff with Rich
        from rich.syntax import Syntax
        from rich.console import Console

        console = Console()
        diff_text = diff_file.read_text()
        syntax = Syntax(diff_text, "diff", theme="monokai")
        console.print(syntax)

    def ingest_changes(self, report_name, interactive=True):
        """Merge user changes back to source"""
        changes = [c for c in self.check_changes() if c['name'] == report_name]

        if not changes:
            logger.error(f"No changes found for {report_name}")
            return

        change = changes[0]

        if interactive:
            self.interactive_merge(change['source'], change['modified'])
        else:
            # Auto-merge (overwrite source with modified)
            shutil.copy(change['modified'], change['source'])
            logger.info(f"Auto-merged changes for {report_name}")

    def interactive_merge(self, source, modified):
        """Interactive section-by-section merge"""
        source_sections = parse_markdown_sections(source)
        modified_sections = parse_markdown_sections(modified)

        merged = {}

        for section_name in source_sections:
            if section_name not in modified_sections:
                # User deleted section
                print(f"\n🗑️  Section '{section_name}' was deleted")
                keep = input("Keep deleted? [y/N]: ").lower() == 'y'
                if not keep:
                    merged[section_name] = source_sections[section_name]

            elif source_sections[section_name] == modified_sections[section_name]:
                # No change
                merged[section_name] = source_sections[section_name]

            else:
                # Modified section
                print(f"\n✏️  Section '{section_name}' was modified")
                print("Original:")
                print(source_sections[section_name][:200])
                print("\nModified:")
                print(modified_sections[section_name][:200])

                choice = input("\n[A]ccept changes, [K]eep original, [E]dit: ").upper()

                if choice == 'A':
                    merged[section_name] = modified_sections[section_name]
                elif choice == 'E':
                    # Open editor
                    edited = open_in_editor(modified_sections[section_name])
                    merged[section_name] = edited
                else:
                    merged[section_name] = source_sections[section_name]

        # Check for new sections user added
        for section_name in modified_sections:
            if section_name not in source_sections:
                print(f"\n✨ New section '{section_name}' added")
                add = input("Include this section? [Y/n]: ").lower() != 'n'
                if add:
                    merged[section_name] = modified_sections[section_name]

        # Write merged result
        write_markdown_sections(source, merged)
        logger.info(f"Merged changes into {source}")
```

### Conflict Resolution Strategies

**1. Section-based merging** (recommended)
- Parse markdown by `##` headers
- Compare section-by-section
- User approves/rejects each change

**2. Three-way merge** (advanced)
- Common ancestor: last synced version
- Theirs: user's vault edits
- Ours: Holocene regenerated version
- Use standard merge algorithms

**3. Append strategy** (simple)
- Reserve `## User Notes` section
- User edits only this section
- Never regenerate it
- Auto-merge on sync

### CLI Commands

```bash
# Sync to vault
holo vault sync                    # Copy all reports to vault

# Check for changes
holo vault check-changes           # List modified reports

# Show diffs
holo vault show-diff <report>      # Display unified diff
holo vault diff <report>           # Alias

# Ingest changes
holo vault ingest <report>         # Interactive merge
holo vault ingest <report> --auto  # Auto-merge (overwrite)
holo vault ingest --all            # Merge all pending changes

# Status
holo vault status                  # Sync status, pending changes
```

### Safety Features

**1. Never lose data:**
- Original always in `~/.holocene/research/`
- Vault is a copy
- Diffs staged before any changes
- User must explicitly merge

**2. Obsidian Sync compatibility:**
- Vault files are normal markdown
- No special formats Obsidian can't handle
- Sync happens at filesystem level
- No conflicts with Obsidian's sync

**3. Rollback capability:**
```bash
holo vault rollback <report>       # Undo last merge
# Restores from git history or backup
```

---

## Next Steps

**Before writing ANY code:**

1. **Review this document with user** - Get decisions on open questions
2. **Update ROADMAP.md** - Add Phase 4.2-4.5 with these plans
3. **Create design docs for each major component:**
   - `design/architecture/api_client.md` - BaseAPIClient architecture
   - `design/architecture/vault_integration.md` - Vault strategy
   - `design/architecture/task_system.md` - Task queue design

4. **THEN start implementing Phase 4.2**

---

**Philosophy:** "Measure twice, cut once" - Spend time on design now, save time debugging later.

---

**Last Updated:** 2025-11-18
**Next Review:** After user feedback on open questions
