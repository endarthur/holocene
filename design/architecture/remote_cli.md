# Remote CLI Architecture Design

**Status:** Planning (Phase 5)
**Created:** 2025-11-23
**Complexity:** High (2-3 weeks implementation)

---

## Problem Statement

Currently, `holo` requires direct database access (SQLite at `~/.holocene/holocene.db`). This means:
- ❌ Must SSH to holocene-rei to run commands
- ❌ Can't use from laptop/phone/other devices
- ❌ Can't build mobile apps or web dashboards easily
- ❌ Underutilizes the holod API we just built

**Goal:** Make `holo` work seamlessly whether running locally (on holocene-rei) or remotely (laptop, CI/CD, scripts).

---

## Architecture Options

### **Option A: Database Abstraction Layer** ⭐ RECOMMENDED

**Concept:** Abstract all database access behind a repository pattern.

```python
# Before (direct database access)
db = Database(config.db_path)
books = db.get_books(limit=10)

# After (abstraction layer)
repo = get_repository(config)  # Returns LocalRepo or RemoteRepo
books = repo.books.list(limit=10)
```

**Implementation:**
```python
# src/holocene/storage/repository.py

class Repository(ABC):
    """Abstract repository interface."""

    @property
    @abstractmethod
    def books(self) -> BookRepository:
        pass

    @property
    @abstractmethod
    def papers(self) -> PaperRepository:
        pass

    # ... links, activities, etc.

class LocalRepository(Repository):
    """Direct SQLite access (current behavior)."""

    def __init__(self, db: Database):
        self._db = db
        self._books = LocalBookRepository(db)

    @property
    def books(self) -> BookRepository:
        return self._books

class RemoteRepository(Repository):
    """API proxy access."""

    def __init__(self, api_client: HolodClient):
        self._client = api_client
        self._books = RemoteBookRepository(api_client)

    @property
    def books(self) -> BookRepository:
        return self._books
```

**Pros:**
- ✅ Clean separation of concerns
- ✅ Both modes use identical interface
- ✅ Testable (can mock repository)
- ✅ Future-proof (can add PostgreSQL, cloud backends)

**Cons:**
- ❌ Large refactoring effort (60+ commands)
- ❌ Must implement both Local and Remote for each operation
- ❌ Migration path complex

---

### **Option B: API-First (Rewrite CLI)**

**Concept:** CLI becomes thin wrapper around API. Even local commands use API.

```python
# ALL commands go through API
client = HolodClient(base_url=config.api_url, token=config.api_token)
books = client.books.list(limit=10)

# holod runs locally on holocene-rei, CLI connects to localhost:5555
# Or remotely via holo.stdgeo.com
```

**Pros:**
- ✅ Single code path (no dual implementation)
- ✅ Forces complete API coverage
- ✅ Local and remote work identically

**Cons:**
- ❌ Requires holod running even for local use
- ❌ Performance overhead (HTTP vs direct SQLite)
- ❌ More complex for simple scripts
- ❌ Doesn't work offline

---

### **Option C: Hybrid Detection (Smart Routing)**

**Concept:** CLI auto-detects mode and routes accordingly.

```python
def get_books(limit=10):
    if is_local():
        # Direct database access (fast path)
        db = Database(config.db_path)
        return db.get_books(limit=limit)
    else:
        # API proxy (remote path)
        client = HolodClient(config.api_url, config.api_token)
        return client.get('/books', params={'limit': limit})

def is_local():
    """Detect if running on holocene-rei with direct DB access."""
    return config.db_path.exists() and not config.force_remote
```

**Pros:**
- ✅ Best of both worlds (fast local, works remote)
- ✅ Gradual migration (can implement per-command)
- ✅ Offline-capable when local

**Cons:**
- ❌ Two code paths to maintain
- ❌ Behavioral differences between local/remote
- ❌ Harder to test (must test both modes)

---

## Recommended Approach: **Hybrid with Abstraction**

Combine Option A + Option C:

1. **Abstract database layer** (repository pattern)
2. **Auto-detect mode** at startup
3. **Fall back gracefully** (local → remote if DB locked, remote → error with helpful message)

```python
# CLI initialization
def init_holo():
    config = load_config()

    # Try local first (if database exists and accessible)
    if config.db_path.exists() and not config.get('force_remote'):
        try:
            db = Database(config.db_path)
            return LocalRepository(db)
        except sqlite3.OperationalError:
            # Database locked or inaccessible, try remote
            pass

    # Fall back to remote
    if config.get('api_url') and config.get('api_token'):
        client = HolodClient(config.api_url, config.api_token)
        return RemoteRepository(client)

    # Neither works
    raise ConfigError(
        "Cannot access Holocene:\n"
        "- Local database not found or locked\n"
        "- No remote API configured\n\n"
        "Run: holo config set api_url https://holo.stdgeo.com\n"
        "     holo config set api_token <your-token>"
    )
```

---

## Configuration Schema

**Local config** (`~/.config/holocene/config.yaml`):
```yaml
# Local mode (current)
data_dir: ~/.holocene
db_path: ~/.holocene/holocene.db

# Remote mode (new)
api_url: https://holo.stdgeo.com
api_token: hlc_abc123xyz...

# Behavior
force_remote: false  # Force remote even if local DB exists
prefer_local: true   # Try local first, fall back to remote
```

---

## API Coverage Requirements

### ✅ **Already Implemented:**
- `GET /books` - List books
- `GET /books/<id>` - Get book details
- `POST /books` - Add book
- `GET /links` - List links
- `GET /papers` - List papers (TODO: check if exists)
- `GET /plugins` - List plugins
- `GET /status` - Daemon status
- `GET /health` - Health check

### ❌ **Must Implement:**

**Books:**
- `POST /books/<id>/enrich` - Enrich with LLM
- `POST /books/<id>/classify` - Dewey classification
- `GET /books/search?q=<query>` - Search books
- `DELETE /books/<id>` - Remove book
- `PATCH /books/<id>` - Update metadata

**Papers:**
- `POST /papers/search` - Search papers (arXiv, Crossref, etc.)
- `POST /papers/add-arxiv` - Add from arXiv ID
- `POST /papers/add-doi` - Add from DOI
- `GET /papers/<id>` - Get paper details
- `DELETE /papers/<id>` - Remove paper

**Research:**
- `POST /research/sessions` - Start research session
- `GET /research/sessions/<id>` - Get session details
- `POST /research/sessions/<id>/add-source` - Add source to session

**AI Operations:**
- `POST /ask` - AI Librarian queries
- `POST /classify` - Generic classification
- `POST /summarize` - Summarize text/PDF

**Wikipedia:**
- `GET /wikipedia/search?q=<query>` - Search Wikipedia
- `GET /wikipedia/article/<title>` - Get article

**Stats:**
- `GET /stats/collection` - Collection statistics
- `GET /stats/usage` - Usage analytics

**File Operations:**
- `POST /files/upload` - Upload PDF
- `GET /files/<id>/download` - Download PDF
- `POST /books/<id>/pdf` - Attach PDF to book

---

## File Handling Strategy

**Challenge:** Books/papers have local PDFs. How to handle remotely?

### **Option 1: Upload/Download on Demand**
```bash
# Remote add with PDF
holo books add-ia <id> --download-pdf
# → Uploads PDF to holod server
# → Server stores in ~/.holocene/books/<id>.pdf
# → Client doesn't keep local copy

# Remote read
holo books read <id>
# → Downloads PDF to temp dir
# → Opens in local PDF viewer
```

**Pros:** Server is source of truth
**Cons:** Large files, bandwidth usage

### **Option 2: Metadata-Only Remote**
```bash
# Remote mode only syncs metadata
holo books add-ia <id>  # Metadata only, no PDF

# PDFs only on local mode
ssh holocene-rei
holo books add-ia <id> --download-pdf  # PDF saved locally
```

**Pros:** Simple, low bandwidth
**Cons:** PDFs not accessible remotely

### **Option 3: Hybrid with S3/Cloud Storage** ⭐
```bash
# Server uploads PDFs to S3/Cloudflare R2
holo books add-ia <id> --download-pdf
# → holod downloads PDF
# → Uploads to cloud storage (encrypted)
# → Stores S3 URL in database
# → Deletes local copy (optional)

# Remote read
holo books read <id>
# → Generates presigned S3 URL
# → Downloads to temp dir
# → Opens in PDF viewer
```

**Pros:** Scalable, accessible anywhere
**Cons:** Requires cloud storage ($), complexity

**Recommendation for v1:** Option 2 (metadata-only remote). Add file sync in Phase 6.

---

## Authentication Flow

### **Initial Setup (One-time):**
```bash
# On holocene-rei
holo auth token create --name "My Laptop"
# → hlc_abc123xyz...

# On laptop
holo config set api_url https://holo.stdgeo.com
holo config set api_token hlc_abc123xyz...

# Test
holo books list  # Should work!
```

### **Security Considerations:**
- Store `api_token` in OS keychain (not plaintext YAML)
- Support environment variable: `HOLO_API_TOKEN`
- Detect token expiration, prompt for refresh
- Support multiple profiles (work, personal, etc.)

---

## Command Routing Logic

### **Read Operations (Easy):**
```python
@click.command()
def list_books():
    repo = get_repository()  # Auto-detects local vs remote
    books = repo.books.list()
    # Display logic (same for both modes)
    display_books_table(books)
```

### **Write Operations (Complex):**
```python
@click.command()
def enrich_book(book_id: int):
    repo = get_repository()

    # Different behavior based on mode
    if isinstance(repo, LocalRepository):
        # Local: Run LLM call directly, update DB
        llm_client = NanoGPTClient(config.llm.api_key)
        summary = llm_client.summarize(book.content)
        repo.books.update(book_id, summary=summary)

    elif isinstance(repo, RemoteRepository):
        # Remote: Trigger async job on server
        job_id = repo.books.enrich(book_id)
        console.print(f"Enrichment job started: {job_id}")
        console.print("Check status: holo jobs status {job_id}")
```

**Implication:** Long-running operations become async when remote!

---

## Migration Path

### **Phase 5.1: Foundation (Week 1)**
- ✅ Create `Repository` abstraction
- ✅ Implement `LocalRepository` (wrap existing Database)
- ✅ Add config support for `api_url`, `api_token`
- ✅ Create `HolodClient` (API wrapper)
- ✅ Implement `RemoteRepository` (basic read operations)

### **Phase 5.2: Read Operations (Week 2)**
- ✅ Migrate all GET commands to use repository
- ✅ Implement missing GET endpoints in holod API
- ✅ Test dual-mode for books, papers, links
- ✅ Add error handling, fallback logic

### **Phase 5.3: Write Operations (Week 3)**
- ✅ Migrate POST/PATCH/DELETE commands
- ✅ Implement async job system for long-running tasks
- ✅ Add job status tracking
- ✅ File upload/download (if doing Option 1)

### **Phase 5.4: Polish (Week 4)**
- ✅ Keychain integration for token storage
- ✅ Better error messages
- ✅ Progress indicators for remote operations
- ✅ Performance optimization (caching, batching)
- ✅ Documentation and examples

---

## Alternative: Quick Win First

Before full remote CLI, build **`holo-remote`** (separate package):

```bash
pip install holo-remote

# Read-only remote client
holo-remote config set url https://holo.stdgeo.com
holo-remote config set token hlc_...

holo-remote books list
holo-remote papers search "quantum"
holo-remote ask "geology books"
```

**Scope:** 1-2 days
**Benefits:**
- Validates API design
- Provides immediate value
- Informs full remote CLI design
- Can be absorbed into main `holo` later

---

## Open Questions

1. **Job System:** How to handle async operations (enrichment, classification)?
   - Option A: Polling (`holo jobs status <id>`)
   - Option B: Webhooks (callback URL)
   - Option C: WebSockets (real-time updates)

2. **Caching:** Should remote client cache responses?
   - Pro: Faster, works offline briefly
   - Con: Stale data, cache invalidation

3. **Batch Operations:** How to handle `holo books enrich --all`?
   - Start 77 jobs? One bulk job? Stream results?

4. **Conflict Resolution:** If both local and remote modified same book?
   - Last-write-wins? Manual merge? Prevent concurrent edits?

5. **Offline Mode:** Should remote client support offline operation?
   - Cache metadata locally? Sync on reconnect?

---

## Success Metrics

**Phase 5 Complete When:**
- ✅ Can run `holo books list` from laptop (via API)
- ✅ Can run `holo ask "..."` remotely (with reasonable latency)
- ✅ Can add books/papers remotely
- ✅ Local and remote modes feel identical to user
- ✅ Error messages are helpful ("No API token, run: holo auth token create")
- ✅ Documentation complete with setup guide

---

## Related Documents

- `design/architecture/operating_modes.md` - Autonomous vs on-demand modes
- `design/architecture/task_scheduler.md` - Job system for async operations
- `ROADMAP.md` - Phase 5 planning
- `src/holocene/daemon/api.py` - Current API implementation

---

**Last Updated:** 2025-11-23
**Status:** Planning document, not yet implemented
**Estimated Effort:** 3-4 weeks (Phase 5)
