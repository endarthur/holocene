# Future Integrations (Planned)

This document tracks integrations planned but not yet implemented.

See `docs/ROADMAP.md` for current priorities and timeline.

---

## Phase 4.1: Free Knowledge APIs (In Progress)

### Wikipedia Integration
**Status:** Basic search implemented ✅, research integration planned

**Command:**
```bash
holo wikipedia search "topic"          # ✅ Implemented
holo research start "topic" --include-wikipedia  # ⏳ Planned
```

**API Details:**
- Endpoint: `https://en.wikipedia.org/api/rest_v1/`
- Rate limit: 200 req/sec (very generous)
- No authentication needed
- Cost: FREE

**Implementation:**
- Use Wikipedia REST API
- Fetch article summary (first section)
- Cache results locally
- Add as "Background" section in research reports
- Include Wikipedia references/citations

---

### Crossref Academic Papers
**Status:** Planned

**Command:**
```bash
holo papers search "geostatistics kriging"
holo papers add <DOI>
holo research start "topic" --include-papers
```

**What We Get:**
- **165 MILLION academic works** with DOIs
- Journal articles, conference papers, books, preprints
- Full metadata: authors, abstracts, citations, references

**API Details:**
- Endpoint: `https://api.crossref.org/works`
- No authentication needed
- Free, generous rate limits
- Cost: FREE

**Perfect for:**
- Mining engineering papers
- Geostatistics research
- Computer science papers
- Pre-LLM filtering by publication date

**Database Schema:**
```sql
CREATE TABLE papers (
    id INTEGER PRIMARY KEY,
    doi TEXT UNIQUE,
    title TEXT,
    authors TEXT,  -- JSON array
    abstract TEXT,
    publication_date TEXT,
    journal TEXT,
    url TEXT,
    references TEXT,  -- JSON array of DOIs
    cited_by_count INTEGER,
    added_at TEXT
);
```

---

### Internet Archive Public Domain Books
**Status:** Partially implemented (search + download works, needs expansion)

**Command:**
```bash
holo books discover-ia "geostatistics"        # ✅ Implemented
holo books add-ia <identifier> --download-pdf # ✅ Implemented
holo research expand-library "mining" --era=1900-1980  # ⏳ Planned
```

**What We Get:**
- 10,000,000+ books and texts
- Classic mining/geology textbooks (1900s-1970s)
- Historical geostatistics papers
- Mathematical treatises

**API Details:**
- Search: `https://archive.org/advancedsearch.php`
- Metadata: `https://archive.org/metadata/{id}`
- Download: `https://archive.org/download/{id}/{file}.pdf`
- Cost: FREE

---

## Phase 4.2: Kagi APIs (Paid, Future)

### Kagi Universal Summarizer
**Status:** Planned (after free APIs)

**Cost:** $0.03/1k tokens, max $0.30/document (Ultimate: $0.025/1k)

**Command:**
```bash
holo books summarize <book_id>
holo links summarize <url>
holo research enrich-pdfs
```

**Use Cases:**
- Summarize book PDFs
- Quick link preview/summary
- Batch PDF summarization

**API:**
- https://help.kagi.com/kagi/api/summarizer.html
- Multiple engines: Cecil (fast), Agnes (balanced), Muriel (enterprise)
- Supports: PDF, text, video, audio

**Estimated Monthly Cost:**
- Light: 10 docs/month = $3
- Moderate: 50 docs/month = $15
- Heavy: 100 docs/month = $30

---

### Kagi Enrichment API (Small Web Discovery)
**Status:** Planned (after free APIs)

**Cost:** $0.002/search ($2 per 1000)

**Command:**
```bash
holo links discover <topic>
holo research expand --small-web
```

**Use Cases:**
- Discover non-commercial, authentic sources
- Find pre-LLM content from small web
- Forums, personal blogs, niche communities

**API:**
- https://help.kagi.com/kagi/api/enrich.html
- Teclis index (non-commercial websites)
- TinyGem index (non-mainstream news)

**Estimated Monthly Cost:**
- 100 searches = $0.20
- 500 searches = $1
- 2000 searches = $4

---

## Autonomous Mode Integrations (Future)

### Browser Extension
**Status:** Designed, not implemented

**Platform:** Chrome/Edge (Manifest V3)
**Permissions:** tabs, storage only (no content scripts)

**What it tracks:**
- Active tab URL and title
- Tab switches and navigation
- Time spent per domain
- Aggregated by category

**Privacy:**
- Blacklist for sensitive domains
- Never accesses incognito/private tabs
- Domain-level only, not full URLs
- Sanitization before storage

**Communication:**
- WebSocket or HTTP POST every 30s to `localhost:8765`
- Local Holocene daemon receives and sanitizes

---

### Home Assistant Integration
**Status:** Designed, not implemented

**API:** Home Assistant REST API

**What it tracks:**
- Temperature, humidity, light levels
- Presence detection (office occupancy)
- Office door state
- Any enabled sensors

**Output to Home Assistant:**
- Trigger Mi Band vibrations
- Control lights/environment

**Use cases:**
- Correlate environment with productivity
- "You've been at desk for 3 hours" notifications
- Adjust environment based on activity

**Implementation:**
```python
class HomeAssistantIntegration:
    def __init__(self, url, token):
        self.url = url
        self.token = token

    def get_sensor_state(self, entity_id):
        # GET /api/states/entity_id

    def call_service(self, domain, service, data):
        # POST /api/services/domain/service
```

---

### Google Calendar Integration
**Status:** Designed, not implemented

**API:** Google Calendar API (requires OAuth)

**What it tracks:**
- Events (personal calendar only, not work Outlook)
- Time blocks
- Meeting patterns
- Focus blocks

**Use cases:**
- Daily focus block reminders
- Integrate events into activity analysis
- Detect scheduling patterns

**Implementation:**
```python
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

class CalendarIntegration:
    def __init__(self, credentials):
        self.service = build('calendar', 'v3', credentials=credentials)

    def get_todays_events(self):
        # List events

    def detect_focus_blocks(self):
        # Find scheduled focus time
```

---

### Mi Band Integration (via Home Assistant)
**Status:** Designed, not implemented

**Platform:** Via Home Assistant Bluetooth integration

**What it tracks:**
- Heart rate patterns (stress vs. calm)
- Sleep quality/duration
- Steps/activity level

**Output:**
- Gentle vibration notifications
- Break reminders
- Focus block starts

**Implementation:**
```python
def vibrate_miband(self):
    # Via Home Assistant notify service
    self.home_assistant.call_service(
        'notify', 'mobile_app',
        {'message': 'Take a break!'}
    )
```

---

## Deferred/Not Recommended

### ❌ Calibre Integration
**Decision:** Deferred until library migrated to new machine

**Future command:**
```bash
holo books import-calibre ~/.config/calibre
holo books sync-calibre
```

**Implementation options:**
- `calibredb` CLI with `--for-machine` JSON output (simplest)
- `/ajax` endpoints if Content Server running
- `calibre-rest` wrapper for full REST API

---

### ❌ Web Search APIs
**Decision:** Removed - Curated link collection (1,153+ sources) is better

**Why rejected:**
- DuckDuckGo scraping - Violates ToS
- LangSearch - Too new (6 weeks old), unknown sustainability
- Kagi Search API - Too expensive ($0.025/search = $25/1000)
- Brave Search API - Limited free tier, unnecessary

**Quality > Quantity** - Trust-tiered curated sources are more valuable.

---

### ❌ Project Gutenberg
**Decision:** Superseded by Internet Archive

**Comparison:**
- Project Gutenberg: 70,000 books (classic literature focus)
- Internet Archive: 10,000,000+ books (includes technical/academic)

Internet Archive has the classic mining/geology textbooks we need.

---

## Integration Priorities

**Current Phase (4.1):**
1. Wikipedia research integration
2. Crossref academic papers
3. Internet Archive book discovery expansion

**Next Phase (4.2):**
4. Kagi Universal Summarizer
5. Kagi Enrichment API

**Future Autonomous Mode:**
6. Browser extension
7. Home Assistant integration
8. Google Calendar integration
9. Mi Band notifications

**Long-term:**
10. Calibre integration (when library migrated)
11. Local inference on M4 Mac Mini
12. Gmail integration (Tier 2 privacy)

---

**Last Updated:** 2025-11-17
**See also:** `docs/ROADMAP.md` for detailed timeline and cost analysis
