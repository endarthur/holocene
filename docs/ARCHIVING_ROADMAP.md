# Holocene "Full Gwern" Archiving Roadmap

**Goal:** Implement Gwern-style comprehensive web archiving for long-term preservation

**Inspiration:** https://gwern.net/archiving

---

## Current State (Already Implemented ✓)

### Infrastructure We Have
- ✅ **Internet Archive integration** (`integrations/internet_archive.py`)
  - `save_url()`, `check_availability()`, `archive_urls_batch()`
  - Rate limiting (0.5 req/sec)
  - Exponential backoff for failures

- ✅ **Link tracking database** (14 columns in `links` table)
  - `archived`, `archive_url`, `archive_date`
  - `archive_attempts`, `last_archive_error`, `next_retry_after`
  - `trust_tier` (pre-llm / early-llm / recent)

- ✅ **URL unwrapping** (`database.py:_unwrap_url()`)
  - Follows redirects to canonical URLs
  - Unwraps shorteners (bit.ly, t.co, etc.)

- ✅ **Link rot detection** (`plugins/link_status_checker.py`)
  - HTTP status checking
  - 24-hour cooldown
  - Status: alive / dead / timeout / connection_error

- ✅ **Link discovery**
  - `holo links scan` - Extract URLs from activities/journel
  - `holo links import-bookmarks` - Browser bookmark import
  - Telegram bot - Mobile link capture

- ✅ **CLI archiving** (`holo links archive`)
  - Batch archiving with retry
  - `--retry-failed`, `--force`, `--limit N`

### Collection Stats (Current)
- **1,160 links** tracked
- Sources: activities, journel, bookmarks, telegram
- Trust tiers calculated from archive dates

---

## Missing Pieces (vs. Gwern)

❌ **Local full-page snapshots** (SingleFile-style HTML + resources)
❌ **PDF archiving** for research papers (OCR + PDF/A + compression)
❌ **Multi-service redundancy** (Archive.is, WebCite)
❌ **Automated periodic archiving** (daemon task scheduler)
❌ **Archive review workflow** (quality check snapshots)
❌ **Headless deployment** (holocene-rei server considerations)

---

## Implementation Plan

### Phase 1: Manual Workflows (Week 1) 🎯 **CURRENT PHASE**

**Goal:** Document and streamline existing manual workflows

**Tasks:**
1. **Document cron-based archiving** (no scheduler needed)
   ```bash
   # Add to crontab on holocene-rei:
   0 2 * * * /usr/bin/holo links scan >> /var/log/holocene/scan.log 2>&1
   0 3 * * * /usr/bin/holo links archive --retry-failed --limit 50 >> /var/log/holocene/archive.log 2>&1
   0 4 * * 0 /usr/bin/holo links check-stale >> /var/log/holocene/check.log 2>&1  # Weekly
   ```

2. **Add `holo links auto-archive` command**
   - Scans for new links
   - Archives unarchived links
   - Retries failed links (respects backoff)
   - Single command for cron

3. **Telegram bot immediate archiving**
   - When link captured via Telegram
   - Insert link to database
   - Call `internet_archive.save_url()` immediately
   - Don't wait for daily scan

4. **Archive statistics dashboard**
   ```bash
   holo stats archives
   ```
   - Total links: 1,160
   - Archived: 847 (73%)
   - Failed: 23 (2%)
   - Pending: 290 (25%)
   - Last run: 2 hours ago

**Deliverables:**
- Cron setup documentation
- Auto-archive CLI command
- Telegram immediate archiving
- Statistics dashboard

#### Phase 1: Implementation Summary ✅ **COMPLETED**

**What Was Built:**

**1. `holo links auto-archive` - Automated Archiving Command**

Location: `src/holocene/cli/main.py:877-1057`

Single command combining scanning and archiving for cron automation:

```bash
# Basic usage (default: scan today, archive up to 50 links)
holo links auto-archive

# Custom limit
holo links auto-archive --limit 100

# Scan different periods
holo links auto-archive --scan-period week   # Scan this week's activities
holo links auto-archive --scan-period all    # Scan all activities

# Skip scanning (only archive existing links)
holo links auto-archive --no-scan
```

**Features:**
- Step 1: Scans activities and journel for new links (configurable period)
- Step 2: Archives unarchived links to Internet Archive
- Respects exponential backoff for previously failed links
- Rate-limited to avoid overwhelming IA servers
- Suitable for automated cron jobs

**Cron Setup (holocene-rei):**
```bash
# Daily at 3 AM - scan today's activity and archive up to 50 links
0 3 * * * /usr/bin/holo links auto-archive --limit 50 >> /var/log/holocene/archive.log 2>&1

# Or weekly scan on Sundays
0 3 * * 0 /usr/bin/holo links auto-archive --scan-period week --limit 100 >> /var/log/holocene/archive.log 2>&1
```

**Implementation Notes:**
- Uses existing `InternetArchiveClient` from `integrations/internet_archive.py`
- Uses existing `extract_urls()` and `should_archive_url()` from `core/link_utils.py`
- Database methods: `db.insert_link()`, `db.update_link_archive_status()`, `db.record_archive_failure()`
- Exponential backoff logic handled by existing `db.record_archive_failure()` (1, 2, 4, 8... 30 days max)

---

**2. Telegram Bot Immediate Archiving**

Location: `src/holocene/plugins/telegram_bot.py:971-1085`

When user sends URL to Telegram bot (eunice device), immediately archive to IA:

**Flow:**
1. User sends URL to bot (e.g., `https://example.com/article`)
2. Bot saves link to database (unwrapping shorteners automatically)
3. **Immediately archives to Internet Archive** (don't wait for daily scan)
4. Updates database with archive status and trust tier
5. Sends notification with result

**Notification Examples:**

```
✅ Link Added

https://example.com/article

Link ID: 1234
Source: Telegram

📦 Archived to IA
Snapshot: https://web.archive.org/web/20251123/example.com
```

```
✅ Link Added

🔗 Original: https://bit.ly/3abc123
📍 Unwrapped: https://realsite.com/actual-page

Link ID: 1235
Source: Telegram

📦 Already archived (pre-llm)
Snapshot: https://web.archive.org/web/20180415/realsite.com
```

```
✅ Link Added

https://brokensite.com/page

Link ID: 1236
Source: Telegram

⚠️ Archive failed (will retry later)
```

**Implementation Notes:**
- Integration point: `_add_link_from_url()` method in `TelegramBotPlugin`
- Uses same `InternetArchiveClient` as CLI commands
- Archives immediately in background thread (doesn't block bot responses)
- Failure handling: Records failure with `db.record_archive_failure()` for exponential backoff
- Trust tier calculation: Uses `calculate_trust_tier(archive_date)` from `storage/database.py`
- URL unwrapping: Handled automatically by `db.insert_link()` calling `_unwrap_url()`

---

**3. `holo stats archives` - Archive Statistics Dashboard**

Location: `src/holocene/cli/main.py:3165-3337`

Visual dashboard showing comprehensive archiving metrics:

```bash
holo stats archives
```

**Output Example:**
```
╭──────────────── Archive Statistics ────────────────╮
│                                                     │
│ Total Links: 1,160                                  │
│                                                     │
│ Coverage:                                           │
│   Internet Archive:     847 ( 73.0%)  ██████████████████████░░░░░░░░   │
│   Failed:                23 (  2.0%)  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   │
│   Pending:              290 ( 25.0%)  ███████░░░░░░░░░░░░░░░░░░░░░░░   │
│                                                     │
│ Link Health:                                        │
│   Alive:                987 ( 85.1%)                   │
│   Dead:                  23 (  2.0%)                   │
│   Unchecked:            150 ( 12.9%)                   │
│                                                     │
│ Trust Tier Distribution (Archived):                │
│   Pre-LLM:              234 (high value)                │
│   Early-LLM:            412 (medium value)             │
│   Recent:               201 (low value)                │
│                                                     │
│ Recent Archiving Activity (last 7 days):           │
│   2025-11-23:   12 archived                         │
│   2025-11-22:    8 archived                         │
│   2025-11-21:   15 archived                         │
│                                                     │
│ Last Archive: 2 hours ago                         │
╰─────────────────────────────────────────────────────╯

Tip: Run holo links auto-archive to archive 290 pending link(s)
```

**Metrics Displayed:**
- **Coverage**: Archived/Failed/Pending with ASCII progress bars
- **Link Health**: Alive/Dead/Unchecked percentages (from link status checker plugin)
- **Trust Tiers**: Distribution of archived links by historical value
  - Pre-LLM (< 2022-11-30): High value, rare pre-ChatGPT content
  - Early-LLM (2022-11-30 to 2024-01-01): Medium value
  - Recent (> 2024-01-01): Low value (can likely re-archive)
- **Recent Activity**: Archives per day for last 7 days
- **Last Archive**: Time since most recent archiving
- **Actionable Tips**: Suggests commands to run based on current state

**Implementation Notes:**
- Pure SQL queries on `links` table (no API calls)
- Uses box-drawing characters (╭─╮│╰╯) for clean ASCII art
- Progress bars use block characters (█░)
- Rich library for colored output
- Handles empty states gracefully (no links, no archived links, etc.)

---

**Integration with Existing Infrastructure:**

All Phase 1 implementations leverage existing code:

✅ **Internet Archive Client** (`integrations/internet_archive.py`)
- `save_url()` - Submit URL for archiving
- `check_availability()` - Check if URL already archived
- Rate limiting (0.5 req/sec default)
- Exponential backoff on failures

✅ **Database Schema** (no changes needed!)
- `links` table already has all required columns:
  - `archived`, `archive_url`, `archive_date`
  - `archive_attempts`, `last_archive_error`, `next_retry_after`
  - `trust_tier`, `status` (from link status checker)

✅ **URL Utilities** (`core/link_utils.py`)
- `extract_urls()` - Extract URLs from text
- `unwrap_url()` - Follow redirects, unwrap shorteners
- `should_archive_url()` - Filter out localhost, private IPs

✅ **Database Methods** (`storage/database.py`)
- `insert_link()` - Auto-unwraps URLs via `_unwrap_url()`
- `update_link_archive_status()` - Mark as archived
- `record_archive_failure()` - Exponential backoff (1, 2, 4, 8... 30 days)
- `get_links_ready_for_retry()` - Get failed links past backoff period
- `calculate_trust_tier()` - Classify by archive date

**No Breaking Changes:**
- Existing `holo links scan` and `holo links archive` commands unchanged
- Auto-archive is additive (combines their functionality)
- Telegram bot maintains backwards compatibility
- Stats command is new, doesn't affect existing stats

---

### Phase 2: Local Snapshots (Week 2-3)

**Goal:** SingleFile-style complete HTML preservation

**Architecture:**
```
~/.holocene/archives/
├── links/
│   ├── {domain}/
│   │   ├── {sha1_of_url}.html
│   │   ├── {sha1_of_url}.meta.json
```

**Tools (Headless-compatible):**
1. **SingleFile CLI** (via Node.js)
   ```bash
   npm install -g single-file-cli
   single-file --browser-headless true $URL
   ```

2. **Playwright** (headless browser automation)
   ```python
   from playwright.sync_api import sync_playwright
   with sync_playwright() as p:
       browser = p.chromium.launch(headless=True)
       page = browser.new_page()
       page.goto(url)
       html = page.content()
   ```

3. **wget** (fallback, static HTML only)
   ```bash
   wget --page-requisites --convert-links --adjust-extension $URL
   ```

**Database Schema Addition:**
```sql
ALTER TABLE links ADD COLUMN local_snapshot_path TEXT;
ALTER TABLE links ADD COLUMN local_snapshot_date TEXT;
ALTER TABLE links ADD COLUMN local_snapshot_hash TEXT;  -- SHA1
ALTER TABLE links ADD COLUMN snapshot_method TEXT;  -- 'singlefile', 'playwright', 'wget'
```

**New Commands:**
```bash
holo links snapshot <url>                    # Manual snapshot
holo links snapshot-batch --limit 50         # Batch snapshot
holo links snapshot-all --trust-tier pre-llm # Prioritize old content
```

**Deployment Notes (holocene-rei):**
- Install Node.js for SingleFile CLI
- Install Chromium for Playwright: `playwright install --with-deps chromium`
- Configure headless mode (no display server needed)
- Storage estimate: ~3.8GB initial, +2GB/year

---

### Phase 3: Paper Archiving (Week 4)

**Goal:** Full PDF preservation with OCR + archival formatting

**Current State:**
- ✅ 19 papers tracked (arXiv, Crossref, OpenAlex, Unpaywall)
- ✅ Paper metadata in database
- ❌ No PDF storage
- ❌ No OCR or PDF/A conversion

**Storage Structure:**
```
~/.holocene/papers/
├── arxiv/
│   ├── {arxiv_id}.pdf          # Original download
│   ├── {arxiv_id}.ocr.pdf     # OCR'd (searchable text)
│   ├── {arxiv_id}.pdfa.pdf    # PDF/A (archival format)
├── doi/
│   ├── {safe_doi}.pdf
```

**Processing Pipeline:**
1. Download PDF (arXiv/Unpaywall/DOI)
2. OCR with `ocrmypdf` (adds searchable text layer)
3. Convert to PDF/A (ISO standard for long-term preservation)
4. Compress with JBIG2 (~40% size reduction, Gwern's method)

**Tools:**
- `ocrmypdf`: OCR + PDF/A conversion
- `tesseract-ocr`: OCR engine (system package)
- `jbig2enc`: PDF compression (optional)

**Database Schema:**
```sql
ALTER TABLE papers ADD COLUMN local_pdf_path TEXT;
ALTER TABLE papers ADD COLUMN pdf_hash TEXT;  -- SHA256
ALTER TABLE papers ADD COLUMN ocr_completed BOOLEAN DEFAULT 0;
ALTER TABLE papers ADD COLUMN pdfa_version TEXT;  -- 'PDF/A-1b', 'PDF/A-2b'
ALTER TABLE papers ADD COLUMN original_size_bytes INTEGER;
ALTER TABLE papers ADD COLUMN archived_size_bytes INTEGER;
```

**New Commands:**
```bash
holo papers download <arxiv_id>       # Fetch + archive paper
holo papers archive-all                # Process all unarchived
holo papers ocr <path>                 # OCR existing PDF
holo papers compress <path>            # Compress with JBIG2
```

**Deployment:**
```bash
# On holocene-rei (headless)
apt-get install tesseract-ocr tesseract-ocr-eng
pip install ocrmypdf
```

---

### Phase 4: Multi-Service Redundancy (Week 5)

**Goal:** Gwern's "prevention > cure" via distributed archiving

**Services:**
1. **Internet Archive** (already implemented ✓)
2. **Archive.is** (archive.today)
   - Fast snapshots
   - Works when IA doesn't
   - API: `https://archive.is/submit/`
3. **WebCite** (academic archiving, if still operational)

**New Table: `link_archives`**
```sql
CREATE TABLE link_archives (
    id INTEGER PRIMARY KEY,
    link_id INTEGER REFERENCES links(id),
    service TEXT,  -- 'internet_archive', 'archive_is', 'webcite', 'local_snapshot'
    archive_url TEXT,
    archived_at TEXT,
    status TEXT,  -- 'success', 'failed', 'pending'
    response_metadata TEXT,  -- JSON
    UNIQUE(link_id, service)
);
```

**Redundancy Strategy (by trust tier):**
```python
ARCHIVING_STRATEGY = {
    'pre-llm': ['internet_archive', 'archive_is', 'local_snapshot'],  # 3 services
    'early-llm': ['internet_archive', 'local_snapshot'],               # 2 services
    'recent': ['internet_archive'],                                    # 1 service
    'unknown': ['internet_archive'],
}
```

**New Commands:**
```bash
holo links archive --services all              # Submit to all services
holo links archive --services ia,archive.is    # Specific services
holo links verify-redundancy                   # Check coverage
holo links redundancy-report                   # Show stats
```

---

### Phase 5: Review Workflow (Week 6)

**Goal:** Gwern's manual review (10-60s/page) for quality

**Features:**
1. **Review Queue**
   - Flag new snapshots for review
   - Show original URL + snapshot preview
   - Extracted metadata (title, description)

2. **TUI Interface** (Rich-based)
   ```
   ╭─────────────── Snapshot Review (23 pending) ───────────────╮
   │                                                             │
   │ URL: https://example.com/article                            │
   │ Archived: 2025-11-23 14:30:15                               │
   │ Title: Example Article Title                                │
   │ Size: 2.3 MB (HTML + resources)                             │
   │                                                             │
   │ [Preview unavailable in headless mode]                      │
   │                                                             │
   │ Actions:                                                    │
   │   [A]pprove  [R]eject & Re-snapshot  [E]dit metadata        │
   │   [D]elete   [S]kip                  [Q]uit                 │
   ╰─────────────────────────────────────────────────────────────╯
   ```

3. **Headless Workflow**
   - Generate thumbnail previews during snapshot
   - Store preview images for remote review
   - Or: Review via web interface (holoterm)

**Database:**
```sql
ALTER TABLE links ADD COLUMN reviewed BOOLEAN DEFAULT 0;
ALTER TABLE links ADD COLUMN review_notes TEXT;
ALTER TABLE links ADD COLUMN review_date TEXT;
ALTER TABLE links ADD COLUMN snapshot_quality INTEGER;  -- 1-5 rating
```

**Commands:**
```bash
holo links review                   # Interactive TUI
holo links review --batch 10        # Review 10 snapshots
holo links review --web             # Launch web interface
```

---

### Phase 6: Analytics & Monitoring (Week 7)

**Goal:** Gwern-style stats and health monitoring

**Dashboard:**
```bash
holo stats archives

╭──────────────── Archive Statistics ────────────────╮
│                                                     │
│ Total Links: 1,160                                  │
│                                                     │
│ Coverage:                                           │
│   Internet Archive:    847 (73%)  ████████████▁▁   │
│   Archive.is:          412 (36%)  ██████▁▁▁▁▁▁▁▁   │
│   Local Snapshots:     623 (54%)  ████████▁▁▁▁▁▁   │
│   Multi-service (>2):  398 (34%)  █████▁▁▁▁▁▁▁▁▁   │
│                                                     │
│ Link Health:                                        │
│   Alive:               987 (85%)  ████████████▁▁   │
│   Dead:                 23 (2%)   ▁▁▁▁▁▁▁▁▁▁▁▁▁▁   │
│   Unchecked:           150 (13%)  ██▁▁▁▁▁▁▁▁▁▁▁▁   │
│                                                     │
│ Storage Usage:                                      │
│   Links (HTML):        3.8 GB                       │
│   Papers (PDF):        0.5 GB                       │
│   Total:               4.3 GB                       │
│                                                     │
│ Last Archive Run: 2 hours ago                       │
│ Next Scheduled: in 22 hours                         │
╰─────────────────────────────────────────────────────╯
```

**Additional Stats:**
```bash
holo stats link-rot        # Dead link report
holo stats trust-tiers     # Distribution by tier
holo stats storage         # Disk usage breakdown
holo stats archive-gaps    # Unarchived critical links
```

---

## Success Criteria

✓ **Local ownership:** All high-priority links have local snapshots
✓ **Redundancy:** Critical links (trust tier pre-llm) on ≥3 services
✓ **Automation:** Zero-touch archiving via cron (no daemon needed initially)
✓ **Monitoring:** Weekly link health checks
✓ **Preservation:** Papers in PDF/A with OCR
✓ **Visibility:** Comprehensive archive statistics

---

## Storage Estimates

Based on Gwern's numbers (14,352 items = 47GB):

**Current (1,160 links):**
- Projected: ~3.8GB local snapshots
- Papers (19 PDFs): +0.5GB (assuming ~25MB/paper)
- **Total: ~4.3GB initial**

**Annual Growth (50 links/month):**
- 600 new links/year × 3.3MB avg = ~2GB/year
- Very manageable on modern storage

---

## Deployment Considerations (holocene-rei)

**Headless Server Requirements:**
- No display server (X11/Wayland)
- All tools must run in headless mode:
  - Playwright: `browser.launch(headless=True)`
  - SingleFile: `--browser-headless true`
  - Chromium: `--headless --disable-gpu`

**System Packages:**
```bash
# Node.js for SingleFile
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
apt-get install -y nodejs

# Playwright dependencies
pip install playwright
playwright install --with-deps chromium

# OCR for PDFs
apt-get install tesseract-ocr tesseract-ocr-eng
pip install ocrmypdf

# SingleFile
npm install -g single-file-cli
```

**Cron Setup:**
```bash
# /etc/cron.d/holocene-archiving
SHELL=/bin/bash
PATH=/usr/local/bin:/usr/bin:/bin
HOLOCENE_CONFIG=/home/arthur/.config/holocene/config.yaml

# Daily link discovery (2 AM)
0 2 * * * arthur /usr/bin/holo links scan >> /var/log/holocene/scan.log 2>&1

# Daily archiving (3 AM)
0 3 * * * arthur /usr/bin/holo links archive --retry-failed --limit 50 >> /var/log/holocene/archive.log 2>&1

# Weekly health check (Sunday 4 AM)
0 4 * * 0 arthur /usr/bin/holo links check-stale >> /var/log/holocene/check.log 2>&1

# Weekly snapshots (Sunday 5 AM)
0 5 * * 0 arthur /usr/bin/holo links snapshot-batch --limit 20 >> /var/log/holocene/snapshot.log 2>&1
```

---

## Next Steps

1. **Immediate (This Session):** ✅ **COMPLETED**
   - [x] Document current archiving infrastructure
   - [x] Add URL unwrapping (already exists ✓)
   - [x] Create `holo links auto-archive` command
   - [x] Add Telegram immediate archiving
   - [x] Create archive statistics dashboard

2. **Short Term (Week 1):**
   - [ ] Set up cron jobs on holocene-rei
   - [ ] Test archiving workflow end-to-end
   - [ ] Monitor for failures and adjust retry logic

3. **Medium Term (Weeks 2-4):**
   - [ ] Implement local snapshots (SingleFile)
   - [ ] Add PDF archiving for papers
   - [ ] Configure headless deployment

4. **Long Term (Weeks 5-7):**
   - [ ] Multi-service redundancy
   - [ ] Review workflow (TUI or web)
   - [ ] Full analytics dashboard

---

**References:**
- Gwern's archiving setup: https://gwern.net/archiving
- Design docs: `design/SUMMARY.md`, `design/architecture/task_scheduler.md`
- Link rot study: 3% annual decay → 16% survive 60 years

---

*Last Updated: 2025-11-23*
*Status: Phase 1 completed ✅ (auto-archive, Telegram archiving, stats dashboard)*
