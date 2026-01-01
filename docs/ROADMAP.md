# Holocene Roadmap

**Last Major Update:** 2025-11-21 (Implementation audit & documentation update)

## Important Design Documents

Before implementing features, review these foundational docs:

1. **`design/integrations/aedb_scavenge.md`** - AEDB analysis, architecture decisions, phased plan
2. **`design/features/extended_dewey_classification.md`** - Universal classification system
3. **`design/integrations/mercadolivre_favorites.md`** - Mercado Livre integration spec
4. **`CLAUDE.md`** - Project conventions and agent collaboration guide

## Current Status (Phase 4 - 60% Complete - Nov 21, 2025)

**Implementation Progress:** Phase 4.1-4.3 mostly complete, Phase 4.5 partially complete

### ✅ Fully Implemented Features

#### Core Library Management
- ✅ Activity tracking with privacy controls
- ✅ Link collection with Internet Archive integration (1,160+ links)
- ✅ Trust tier system (pre-LLM / early-LLM / recent)
- ✅ Book collection management (77 books imported)
- ✅ **Book enrichment** - LLM-generated summaries and tags (batch processing)
- ✅ Deep research mode with book integration
- ✅ PDF text extraction with OCR fallback
- ✅ Markdown report generation
- ✅ NanoGPT subscription usage tracking
- ✅ Bookmark import (Chrome, Edge, Firefox)

#### Dewey Decimal Classification (Phase 3.7)
- ✅ AI-powered classification with Cutter numbers
- ✅ Full call number generation - IGc Library-style format (e.g., "550.182 I10a")
- ✅ Configurable classification system - Dewey or UDC via config
- ✅ Classification repair tool - Auto-fix missing Cutter numbers
- ✅ Library catalog view - `--by-dewey` sorting for shelf order browsing

#### Free Knowledge APIs (Phase 4.1)
- ✅ **Wikipedia integration** - REST API client with caching (`holo wikipedia`)
- ✅ **Crossref integration** - 165M papers, search/DOI lookup (`holo papers search/add`)
- ✅ **arXiv integration** - 2.4M+ preprints, smart ID detection (`holo papers add`)
- ✅ **Internet Archive books** - Discovery and download (`holo books discover-ia/add-ia`)
- ✅ **OpenAlex integration** - 250M+ academic works (BONUS, not in original roadmap)
- ✅ **Unpaywall integration** - Find Open Access PDFs (BONUS, not in original roadmap)

#### Infrastructure & Integrations (Phase 4.2)
- ✅ **HTTPFetcher** - Proxy support, HTML caching, rate limiting
- ✅ **Mercado Livre integration** - OAuth, favorites sync, AI classification (10+ commands)
- ✅ **Telegram bot** - Mobile interface for paper/link capture
- ✅ **Apify client** - Web scraping automation
- ✅ **Bright Data proxy** - Web Unlocker integration
- ✅ **Inventory system** - EAV attributes, normalized tags, search

#### Daemon & Authentication (Phase 4.6 - Nov 22-23, 2025)
- ✅ **holod REST API** - Background daemon with Flask (port 5555)
- ✅ **Passwordless authentication** - Magic links via Telegram/CLI
- ✅ **API token system** - Bearer tokens for programmatic access
- ✅ **Cloudflare Tunnel deployment** - Secure remote access at holo.stdgeo.com
- ✅ **Session management** - 7-day cookies, single-use magic links
- ✅ **Bot detection** - Telegram link preview protection
- ✅ **Multi-auth support** - Session cookies OR API tokens

#### Config & UX (Phase 4.3)
- ✅ **`holo config`** - Configuration management (8+ subcommands)
- ✅ **`holo stats`** - Analytics dashboard (8+ analytics commands)
- ✅ **Thermal printing** - Paperang P1 integration with Spinitex renderer

#### Library Experience (Phase 4.5)
- ✅ **`holo ask`** - AI Librarian for natural language queries (Nov 21, 2025)
- ✅ **Metadata enrichment** - LLM-generated summaries (partial implementation)

---

## Phase 4: Enhanced Research Capabilities

### Priority 1: Free Knowledge APIs 🌟 (IN PROGRESS)

**Wikipedia + Internet Archive Integration**

**Why Start Here:**
- Both completely free
- No API keys needed (for IA public domain)
- Immediate value for research
- Stable, trustworthy sources

#### 4.1a: Wikipedia Integration ✅ IMPLEMENTED

**Status:** Fully implemented (Nov 2025)

**Implemented Features:**
```bash
holo wikipedia "Python programming"  # Search and display summaries
holo research start "topic" --include-wikipedia  # Integrated into research
```

**Implementation Details:**
- ✅ Wikipedia REST API client (`src/holocene/research/wikipedia_client.py`)
- ✅ Article summary fetching
- ✅ Local caching support
- ✅ Search functionality
- ✅ Integrated into research reports

**API Details:**
- Endpoint: `https://en.wikipedia.org/api/rest_v1/`
- Rate limit: 200 req/sec (very generous)
- No authentication needed
- Returns: JSON with article text, summary, metadata

**Cost:** FREE

---

#### 4.1b: Crossref Academic Papers ✅ IMPLEMENTED

**Status:** Fully implemented (Nov 2025)

**Implemented Features:**
```bash
# Search academic papers
holo papers search "geostatistics kriging"
holo papers search "geostatistics" --from 1990 --until 2022

# Add paper to research collection
holo papers add <DOI>

# List papers
holo papers list
holo papers list --search "pattern recognition"

# Research includes relevant papers
holo research start "topic" --include-papers
```

**What We Have Access To:**
- **165 MILLION academic works:**
  - Journal articles
  - Conference papers
  - Books & chapters
  - Preprints
  - Research datasets

**Implementation Details:**
- ✅ Crossref REST API client (`src/holocene/research/crossref_client.py`)
- ✅ Search with date filtering (pre-LLM focus: before 2022-11)
- ✅ DOI-based lookups
- ✅ Metadata extraction (title, authors, abstract, references, citations)
- ✅ Papers table in database with source tracking
- ✅ Integrated into research reports

**API Details:**
- Endpoint: `https://api.crossref.org/works`
- No authentication needed
- Free, generous rate limits
- Full JSON metadata
- Returns: titles, authors, DOIs, abstracts, references, citations

**Database Schema:**
- ✅ Papers table implemented with DOI, title, authors, abstract, journal, citations
- ✅ Source tracking (crossref, arxiv, openalex)
- ✅ Reference storage (JSON array of DOIs)

**Cost:** FREE

---

#### 4.1c: Internet Archive Public Domain Books ✅ MOSTLY IMPLEMENTED

**Status:** Core features implemented, batch import not yet built (Nov 2025)

**Implemented Features:**
```bash
# Search IA for public domain books
holo books discover-ia "geostatistics"

# Download public domain book
holo books add-ia <identifier>

# Archive links to prevent link rot
holo archive <url>
```

**Not Yet Implemented:**
```bash
# Batch import classic texts on topic
holo research expand-library "mining engineering" --era=1900-1980  # TODO
```

**What We Have Access To:**
- 10,000,000+ books and texts
- **Current collection:** 77 books imported from IA + LibraryThing

**Implementation Details:**
- ✅ IA API client (`src/holocene/integrations/internet_archive.py`)
- ✅ Search metadata API
- ✅ Public domain book discovery
- ✅ PDF download and storage
- ✅ Text extraction with PDFHandler
- ✅ LLM enrichment pipeline integration
- ✅ Books database storage
- ❌ Batch import feature (planned but not coded)

**API Details:**
- Search: `https://archive.org/advancedsearch.php?q=...&output=json`
- Metadata: `https://archive.org/metadata/{identifier}`
- Download: `https://archive.org/download/{identifier}/{filename}`
- All FREE, no authentication for public domain

**Cost:** FREE

**Storage:** PDFs stored in `~/.holocene/books/internet_archive/`

---

#### 4.1d: Research Repository Integration 📚

**Goal:** Support multiple research paper repositories beyond Crossref.

**✅ Implemented Repositories:**

**arXiv** (Nov 2025) - 2.4M+ preprints
- ✅ XML API integration (`src/holocene/research/arxiv_client.py`)
- ✅ Smart ID detection (URLs, plain IDs, versioned IDs)
- ✅ Metadata extraction (title, authors, abstract, categories)
- ✅ Automatic DOI linking when available
- ✅ Rate limiting (3 sec between requests per arXiv policy)
- ✅ Telegram bot integration for mobile capture
- ✅ Commands: `holo papers add <arxiv_id>` (auto-detects arXiv format)

**OpenAlex** (Nov 2025) - 250M+ academic works (BONUS)
- ✅ Full API client (`src/holocene/research/openalex_client.py`)
- ✅ Query by DOI, author, title
- ✅ Year filtering
- ✅ Citation metrics
- ✅ Alternative paper search beyond Crossref

**Unpaywall** (Nov 2025) - Open Access discovery (BONUS)
- ✅ Find free PDFs for papers (`src/holocene/research/unpaywall_client.py`)
- ✅ OA status detection
- ✅ Multiple OA location discovery
- ✅ License information
- ✅ Commands: `holo papers download <doi>` (uses Unpaywall to find OA versions)

**❌ Planned Repositories (Not Yet Implemented):**

**PubMed / PubMed Central (PMC)**
- 36M+ biomedical citations, 9M+ full-text articles
- NCBI E-utilities API (free, no API key for basic use)
- Focus: Medical, biology, life sciences
- Why: Pre-LLM biomedical research, patient education materials
- Implementation: Similar to arXiv client, XML parsing

**bioRxiv / medRxiv**
- Biology and medicine preprints
- REST API available
- Why: Pre-LLM biology research, early pandemic papers
- Similar API pattern to arXiv

**SSRN (Social Science Research Network)**
- 1M+ social science papers
- API availability: TBD (may require scraping)
- Focus: Economics, law, political science
- Why: Social science research (if user expands interests)

**CORE**
- 200M+ open access papers aggregated from repositories worldwide
- REST API available (free tier: 10k requests/day)
- Why: Aggregator that fills gaps from other sources
- Implementation: Unified search across repositories

**SemanticScholar**
- 200M+ papers with citation graph
- Free API (rate limited but generous)
- Focus: Computer science, neuroscience, biomedical
- Why: Citation network analysis, paper recommendations
- Unique feature: Influence metrics, citation context

**Features to Build:**
```bash
# Unified paper search across repositories
holo papers search "geostatistics kriging" --repo arxiv,crossref,core

# Auto-detect paper source from URL/ID
holo papers add "https://www.biorxiv.org/content/10.1101/2021.01.01.123456"
holo papers add "PMC8675309"  # PubMed Central ID
holo papers add "2103.12345"  # arXiv ID (already works)

# Repository-specific commands
holo papers search-arxiv "neural networks"
holo papers search-pubmed "covid-19 treatment"

# Import from references
holo papers import-citations <paper_id>  # Add all cited papers
```

**Implementation Strategy:**
1. Create base `PaperRepository` interface
2. Implement repository-specific clients (like `ArxivClient`)
3. Unified detection/routing based on URL/ID patterns
4. Common metadata normalization (all repos → standardized paper dict)
5. Repository source tracking in database
6. Telegram bot auto-detection for all supported repos

**Database Changes:**
```sql
-- Add source field to papers table
ALTER TABLE papers ADD COLUMN source TEXT;  -- 'arxiv', 'crossref', 'pubmed', etc.
ALTER TABLE papers ADD COLUMN source_id TEXT;  -- arXiv ID, PMID, etc.

-- Index for efficient source queries
CREATE INDEX idx_papers_source ON papers(source);
```

**Priority Order:**
1. ✅ arXiv (implemented)
2. PubMed (high value, free, easy API)
3. SemanticScholar (citation network analysis)
4. bioRxiv (if user expands to biology)
5. CORE (aggregator, fills gaps)

**Cost:** All FREE APIs

---

### Priority 2: Kagi Universal Summarizer Integration 💰

**Why:** Perfect complement to existing PDF + link collection. Capped cost ($0.30/doc max).

**Features to Build:**
```bash
holo books summarize <book_id>     # Summarize book PDFs
holo links summarize <url>         # Quick link preview/summary
holo research enrich-pdfs          # Batch summarize PDFs in collection
```

**Implementation Notes:**
- Integrate with existing `PDFHandler`
- Store summaries in database (new `summaries` table or add to existing)
- Cache summaries to avoid re-processing
- Add summary display to `holo books list` and research reports

**Cost Estimate:** $0.03/1000 tokens, max $0.30/document
- Ultimate subscriber discount: $0.025/1000 tokens

**Technical Details:**
- API: https://help.kagi.com/kagi/api/summarizer.html
- Multiple engines: Cecil (fast), Agnes (balanced), Muriel (enterprise)
- Supports: PDF, text, video, audio
- Can translate outputs

**Database Schema Changes:**
```sql
-- Option 1: New summaries table (if we want summaries for multiple types)
CREATE TABLE summaries (
    id INTEGER PRIMARY KEY,
    content_type TEXT,  -- 'book', 'link', 'pdf'
    content_id INTEGER, -- Foreign key to books/links
    summary TEXT,
    engine TEXT,        -- 'cecil', 'agnes', 'muriel'
    token_count INTEGER,
    cost REAL,
    created_at TEXT
);

-- Option 2: Add to books table (simpler for books only)
ALTER TABLE books ADD COLUMN kagi_summary TEXT;
ALTER TABLE books ADD COLUMN kagi_summary_date TEXT;

-- Add to links table
ALTER TABLE links ADD COLUMN kagi_summary TEXT;
ALTER TABLE links ADD COLUMN kagi_summary_date TEXT;
```

---

### Priority 2: Kagi Enrichment API (Small Web Discovery)

**Why:** Discover non-commercial, authentic sources. Perfect for finding pre-LLM content.

**Features to Build:**
```bash
holo links discover <topic>         # Find small web sources
holo research expand --small-web    # Add small web sources to research
```

**Implementation Notes:**
- Use **Teclis index** for non-commercial websites, forums
- Use **TinyGem index** for non-mainstream news
- Auto-add discovered links to collection with source tracking
- Filter/rank by relevance before importing

**Cost Estimate:** $0.002/search ($2 per 1000)

**Use Cases:**
- Expanding link collection with quality sources
- Finding authentic discussions/forums on research topics
- Discovering pre-LLM blog posts and articles

**Technical Details:**
- API: https://help.kagi.com/kagi/api/enrich.html
- Two endpoints: `/v0/enrich/web` and `/v0/enrich/news`
- Returns URLs, titles, snippets from Teclis/TinyGem indices

---

## Phase 4.5: Library Experience & Visualization 🎨

**Vision:** Transform the digital library into an immersive, intelligent experience that rivals (and exceeds) physical libraries.

### Priority 1: Metadata Enrichment Pipeline 🔍 - PARTIAL

**Status:** LLM enrichment implemented, multi-source lookup not yet built

**✅ Implemented:**
```bash
holo books enrich              # Batch enrich books with LLM
holo books enrich <book_id>    # Single book enrichment
```

**Implementation Details:**
- ✅ LLM-generated summaries using DeepSeek V3 (`src/holocene/research/book_enrichment.py`)
- ✅ Tag extraction from book content
- ✅ Batch processing support
- ✅ Database storage of enrichment data

**❌ Not Yet Implemented:**
```bash
holo books enrich --missing-authors    # Fix books with no author (TODO)
```

**Multi-Source Strategy (Planned but not coded):**
1. ❌ OpenLibrary API (ISBN/title lookup)
2. ❌ Google Books API (title/author matching)
3. ❌ WorldCat API (bibliographic database)
4. ✅ LLM inference (implemented)

**Missing Features:**
- Multi-source waterfall approach
- Confidence scoring for LLM-inferred data
- Manual review interface for uncertain matches
- External API integration (OpenLibrary, Google Books, WorldCat)

---

### Priority 2: 3D Virtual Library (Three.js) 🎮 - NOT IMPLEMENTED

**Status:** ❌ Not started (design-only)

**Planned Features:**
```bash
holo books serve --3d    # Start web server with 3D view (TODO)
# Opens browser to http://localhost:8080
```

**Envisioned 3D Experience:**
- First-person camera controls (WASD + mouse)
- Books on shelves, organized by call number
- Click book to pull off shelf → show metadata
- "Sections" labeled by Dewey class:
  - Computer Science (000s) - Blue shelves
  - Earth Sciences (550s) - Brown/Earth-toned shelves
  - Arts (700s) - Colorful shelves
- Search bar to highlight/navigate to books
- Bookmarks for favorite sections
- Export/share shelf views as images

**Technical Stack (Planned):**
- **Three.js** for 3D rendering
- **Flask/FastAPI** for web server
- **WebGL** shader for realistic book spines
- **Procedural generation** for book covers based on metadata
- **LOD (Level of Detail)** for performance with large libraries

**Why This Would Rock:**
- Stunning visual showcase
- Makes browsing fun (not just functional)
- "Library tourism" - share screenshots of your collection
- Not as hard as it sounds with Three.js!

**Estimated Effort:** 2-3 days for MVP, polish over time

---

### Priority 3: AI Librarian Chat 🤖 ✅ IMPLEMENTED

**Status:** ✅ Fully implemented (Nov 21, 2025)

**Implemented Features:**
```bash
holo ask "What books do I have about spatial statistics?"
holo ask "Which geology books were published before 1995?"
holo ask "Recommend books that combine programming and earth sciences"
holo ask "What's the oldest book in my collection?"
holo ask --include-links "Find resources about Python"  # Future enhancement
```

**Implementation Details:**
- ✅ LLM-powered queries using DeepSeek V3 (`src/holocene/cli/ask_commands.py`)
- ✅ Complete collection context (books + papers metadata sent to LLM)
- ✅ Titles, authors, classifications, summaries included
- ✅ Rich formatted output with call numbers
- ✅ Budget tracking display (2,000 prompts/day)
- ✅ Comprehensive error handling

**Features Working:**
- ✅ Natural language book/paper queries
- ✅ Reading path generation: "Learn structural geology" → ordered list
- ✅ Cross-reference recommendations
- ✅ Collection gap analysis suggestions

**Why It's Powerful:**
- Leverages existing LLM infrastructure (NanoGPT)
- Makes library "conversational" not just searchable
- Enriched summaries make recommendations smarter
- Natural way to discover connections between books

**Successfully Tested With:**
- Factual queries: "What books do I have about data science?"
- Search queries: "Which papers discuss pattern recognition?"
- Recommendation queries: "What should I read to learn about geostatistics?"

---

### Future Enhancements

#### Collection Gap Analysis 📊
**What:**
- Visualize Dewey distribution (heatmap of your collection)
- Identify underrepresented areas
- Suggest classic works to fill gaps
- Track collection growth over time

**Use Case:**
"You have 15 books in earth sciences (550s) and 12 in programming (005s), but only 1 book in mathematics (510s). Since many of your books involve statistics, you might want these foundational math texts..."

---

#### Reading List Generator 📖
**What:**
```bash
holo reading-list "learn structural geology"
holo reading-list "understand geostatistics" --from-collection
```

**Output:**
```
Recommended Reading Path: Structural Geology
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Foundation (Start here):
1. [551.1] Earth's Shifting Crust - Hapgood (1958)
   → Core concepts of earth structure

Intermediate:
2. [551.8] Techniques of Modern Structural Geology - Ramsay (1984)
   → Advanced strain analysis methods

Applied:
3. [624.15132] Block Theory and Rock Engineering - Goodman (1985)
   → Real-world applications

Estimated total: ~1,200 pages, 3-4 months
```

---

#### Physical Shelf Label Generator 🏷️
**What:**
Print actual spine labels for physical books.

**Features:**
```bash
holo labels generate --format avery-5160    # Avery label sheets
holo labels generate --format thermal       # Thermal printer (Paperang!)
holo labels print 37                        # Print label for book ID 37
```

**Output:**
```
┌─────────────────┐
│   550.182 I10a  │
│                 │
│  GEOSTATISTICS  │
│     Isaaks      │
└─────────────────┘
```

**Thermal Printer Integration:**
- Use existing Paperang printer!
- Perfect size for book spines
- Print on demand when organizing physical books

---

#### Citation Network Mapper 🕸️
**For Academic Papers:**
- Visualize which papers cite each other
- Find "missing links" in citation chains
- Identify foundational papers to read first
- Export as graph (NetworkX → Graphviz)

**Use Case:**
"These 5 geostatistics papers all cite Matheron (1963), but you don't have it. This is a foundational work you should add."

---

#### Dewey-Based Recommendations 💡
**Smart Recommendations Using Classification:**
```bash
holo recommend --based-on 37    # Based on book ID
```

**Logic:**
- Book 37 is 550.182 (geostatistics)
- Nearby: 519.5 (statistics), 551 (geology)
- "Since you liked this book in 550.182, try these in 519.5 that use similar methods..."

**Why Better Than Generic Recommendations:**
- Uses library classification hierarchy
- Leverages centuries of librarian expertise
- Finds conceptual connections, not just keywords

---

#### Printed Library Catalog 📑
**Beautiful PDF Catalog:**
```bash
holo catalog generate --output my_library.pdf
```

**Contents:**
- Title page with collection stats
- Table of contents by Dewey class
- Full listings with call numbers, summaries
- Author index
- Title index
- Subject index

**Like:** Old library card catalogs, but gorgeous typography (LaTeX?)

**Use Case:**
- Impressive showcase of collection
- Offline reference
- Gift for fellow book lovers
- Historical record as collection grows

---

#### Smart Duplicate Detection 🔍
**Beyond Exact Matches:**
- Different editions: "Intro to Geostatistics (1990)" vs "Intro to Geostatistics 2nd ed (2010)"
- Translations: "Sapiens" vs "Sapiens (Portuguese)"
- Reprints: Same book, different publisher/year

**Features:**
```bash
holo books find-duplicates
holo books merge-editions 37 42    # Merge as editions of same work
```

**Implementation:**
- Fuzzy title matching (Levenshtein distance)
- ISBN family detection (same base, different edition codes)
- Author + title similarity scoring
- LLM verification for uncertain matches

---

#### Normalization Passes 🔧
**Data Cleaning Features:**
```bash
holo books normalize --authors     # Fix author name formats
holo books normalize --titles      # Consistent title formatting
holo books normalize --publishers  # Publisher name standardization
```

**Examples:**
- "Smith, John" vs "John Smith" → standardize
- "TITLE IN ALL CAPS" → "Title in Title Case"
- "Addison-Wesley" vs "Addison Wesley" vs "AW" → canonical form

**Why Important:**
- Better sorting and grouping
- Cleaner UI presentation
- More accurate duplicate detection
- Professional appearance

---

## Phase 5: Advanced Features (Future Considerations)

### Calibre Library Integration (Deferred)

**Why Deferred:** User will revisit when Calibre library is migrated to new machine.

**Features to Build (Future):**
```bash
# Import Calibre library metadata
holo books import-calibre ~/.config/calibre

# Sync with Calibre
holo books sync-calibre

# Search both Holocene + Calibre
holo books search "machine learning" --include-calibre
```

**Implementation Options:**
- Option 1: `calibredb` CLI with `--for-machine` JSON output (simplest)
- Option 2: Undocumented `/ajax` endpoints (if Content Server running)
- Option 3: `calibre-rest` wrapper (if need full REST API)

**When to Implement:** After user migrates Calibre library to current machine.

---

### Book PDF Management
- Track which books have PDFs available
- Local PDF storage/organization
- Integration with summarization for research prep

### Research Workspace
- Save/organize multiple research sessions
- Compare research findings across topics
- Export research collections (Obsidian, Notion, etc.)

### Enhanced Trust Verification
- Cross-reference sources with Internet Archive dates
- Flag potentially AI-generated content
- Source quality scoring beyond date-based tiers

### LLM Cost Optimization
- Implement response caching
- Use cheaper models for simple tasks
- Track cost per research session
- Monthly budget alerts via NanoGPT API

### Browser Extension (Long-term)
- Auto-capture links from browsing
- One-click "add to Holocene"
- Reading time tracking

---

## Deferred/Not Recommended

### ❌ Web Search APIs (Removed)
**Decision:** Curated link collection (1,153+ sources) is better than random web search.

**Considered & Rejected:**
- ✗ **DuckDuckGo scraping libraries** - Violates ToS
- ✗ **LangSearch** - Too new (6 weeks old), unknown sustainability
- ✗ **Kagi Search API** - Too expensive ($0.025/search = $25/1000)
- ✗ **Brave Search API** - Limited free tier (67/day), unnecessary

**Why:** Quality > Quantity. Your curated, trust-tiered sources are more valuable.

### ❌ NanoGPT Search Endpoint
**Decision:** Not part of subscription, pricing unknown, index quality unclear.

**Alternative:** Stick with NanoGPT for LLM calls, use Kagi for specialized search needs.

### ❌ Project Gutenberg (Superseded by Internet Archive)
**Decision:** Internet Archive is vastly superior for technical/research needs.

**Comparison:**
- Project Gutenberg: 70,000 books (classic literature focus)
- Internet Archive: 10,000,000+ books (includes technical/academic)

**Why IA Instead:**
- Classic mining/geology textbooks (1900s-1970s)
- Historical geostatistics papers
- Older programming/CS texts
- Much larger technical collection
- Same public domain access

---

## Cost Analysis (Monthly Budget Planning)

### Current Costs
- **NanoGPT Subscription:** Usage-based
  - Daily limit: 2,000 calls
  - Monthly limit: 60,000 calls
  - Current usage: ~25 calls/day (0.04% of monthly limit)

### Projected Costs (Phase 4)

**Kagi Universal Summarizer:**
- Scenario 1: Summarize 10 PDFs/month = ~$3/month
- Scenario 2: Summarize 50 PDFs/month = ~$15/month
- Scenario 3: Heavy usage (100 docs/month) = ~$30/month

**Kagi Enrichment API:**
- Scenario 1: 100 searches/month = $0.20/month
- Scenario 2: 500 searches/month = $1/month
- Scenario 3: Heavy usage (2000 searches/month) = $4/month

**Combined Budget Estimate:**
- Light usage: $3-5/month
- Moderate usage: $15-20/month
- Heavy usage: $30-35/month

**Note:** All Kagi APIs are post-paid with no subscription requirement.

---

## Implementation Order

### Completed Phases
1. ✅ **Phase 3.5** - Book enrichment, research integration
2. ✅ **Phase 3.7** - Dewey Decimal Classification with Cutter numbers 🎉

### Current Phase (Week of Nov 18-25, 2025)
3. 🚧 **Phase 4.2 - Infrastructure & Foundation** ⭐ IN PROGRESS
   - ✅ HTTPFetcher abstraction (proxy + caching support)
   - ✅ HTML caching infrastructure for paid services
   - ✅ Mercado Livre integration (favorites + enrichment)
   - ✅ Bright Data Web Unlocker integration
   - ✅ Apify integration (for future automation)
   - 🔄 Inventory/taxonomy system integration
   - See: `design/integrations/aedb_scavenge.md`

### ✅ Architecture Review Session - COMPLETED (Nov 21, 2025)

**Status:** ✅ **COMPLETED** - Audit report available at `ARCHITECTURE_AUDIT_2025-11-21.md`

**Verdict:** **PROCEED WITH CONFIDENCE** - No blocking issues found

**Key Findings:**
- ✅ Database schema in good health (6 migrations applied)
- ✅ Migration system working well (metadata JSON pattern adopted)
- ✅ Integration patterns mostly consistent
- ✅ Foreign keys enabled, WAL mode enabled, proper indexes
- ⚠️ Minor technical debt noted (legacy columns, tag storage inconsistency)
- 🔴 **Blockers:** None

**Completed Cleanup Tasks:**
- ✅ Added deprecation comments to legacy book columns in `database.py`
- ✅ Updated `design/SUMMARY.md` with recent integrations
- ✅ Removed debug prints from spinitex.py
- ✅ Created `design/architecture/integration_guidelines.md`

**Database Schema Decisions Made:**
- **Stay on SQLite** - Good for years (up to 1GB+), WAL mode handles concurrency
- **Use metadata JSON** - New pattern for flexible attributes (Migration 6)
- **Keep legacy columns** - Deprecated but kept for backwards compatibility until Phase 6+
- **Tag storage** - Defer standardization to Phase 6+ (not blocking)
- **Foreign keys** - Already enabled via Migration 1
- **Migration strategy** - Custom system working well, no need for Alembic yet

**Questions Answered:**
- ✅ Database schema sustainable? **Yes, proceed with confidence**
- ✅ Need background daemon now? **Defer to Phase 6**
- ✅ SQLite vs PostgreSQL? **Stay on SQLite for now**
- ✅ Schema evolution strategy? **Metadata JSON + migrations working well**

**Full Report:** See `ARCHITECTURE_AUDIT_2025-11-21.md` for comprehensive analysis

---

### Near-Term Phases
4. **Phase 4.3 - Config & UX** (Week of Nov 25)
   - `holo config` command group
   - `holo stats` analytics dashboard
   - Rich terminal output (tables, progress bars)
   - Fuzzy search for books/papers
   - Mercado Livre favorites integration
   - Bookmark import (Chrome, Firefox, Edge)

5. **Phase 4.4 - Crossref Integration** (Week of Dec 2)
   - Crossref API client (165M papers, FREE!)
   - `holo papers` command group
   - Paper metadata storage
   - Research mode integration
   - Citation tracking

6. **Phase 4.5 - Smart Features** (Week of Dec 9)
   - LLM-based tag extraction
   - Book/paper similarity (semantic)
   - Research-focused recommendations
   - Reading queue management
   - Analytics visualizations

### Mid-Term Phases (Q1 2026)
7. **Phase 5 - Vault Integration** (Jan 2026)
   - Obsidian vault sync (one-way with diff ingestion)
   - Knowledge graph export
   - Wikilink support in research reports
   - "Patchwork passes" for auto-linking
   - See: `design/integrations/aedb_scavenge.md` (vault sync section)

8. **Phase 6 - Autonomous Mode** (Q1 2026)
   - Background daemon architecture
   - Browser extension for activity tracking
   - Task scheduler with priorities
   - IFTTT-style automation rules
   - Automated daily summaries

### Deferred / Future
9. **Kagi Integration** - Deferred (good but not essential)
   - Universal Summarizer for PDFs/links
   - Enrichment API for small web discovery
10. **Calibre Integration** - When library migrated
11. **3D Vault Visualization** - Phase 6+ (nice-to-have)

---

## Notes & Decisions

### Why Kagi?
- **Trustworthy:** Established company, clear pricing, privacy-focused
- **Sustainable:** Real business model (paying users), won't disappear
- **Quality:** Premium search index, non-commercial focus
- **Predictable costs:** Capped maximums, no surprise bills
- **You already use it:** Personal familiarity with quality

### Design Principles
- **Quality over quantity** - Curated sources > random web results
- **Cost-conscious** - Batch operations, caching, clear budget tracking
- **Privacy-first** - Local storage, no data sharing
- **Trust-aware** - Pre-LLM content prioritization
- **Incremental** - Build features as needed, test before scaling

### Future Experiments
- Compare Kagi summaries vs DeepSeek summaries (quality/cost)
- Test small web discovery for research quality improvements
- Explore Kagi's translation features for international sources

### Local Inference & The Laney Council (Phase 7+)

**Vision:** Run Laney locally on M4 Mac Mini with intelligent cloud escalation.

**Architecture:**
1. **Local Model** (Llama 3.3 70B / Qwen 2.5 72B)
   - Fast, free, private
   - Handles routine queries, collection searches, simple summaries
   - All data stays on local network

2. **Cloud Escalation** (NanoGPT - DeepSeek V3, Kimi K2)
   - Complex reasoning, long documents, research synthesis
   - Only when local model recognizes it needs help
   - Sanitized data only - sensitive info never leaves

3. **The Laney Council** (Multi-Agent Routing)
   - Lightweight "inner council" that votes before main task execution
   - Multiple specialized Laney perspectives with different system prompts:
     - 🔒 **Privacy Laney** - Evaluates data safety for cloud escalation
     - 🧠 **Complexity Laney** - Decides if task needs more powerful model
     - 📚 **Archivist Laney** - Checks collection first before external search
     - ⚡ **Efficiency Laney** - Prevents overthinking simple lookups
     - ✅ **Reviewer Laney** - Verifies task completion (see below)
   - Fast local inference (~500ms) routes the main request appropriately
   - Disagreement = uncertainty signal → ask the human

4. **Reviewer Laney** (Task Verification Agent)
   - Post-task verification: Did Laney actually do what she claimed?
   - Checks for "hallucinated completions" (e.g., claims to create files that don't exist)
   - Verification types:
     - 🔍 **File existence** - Do referenced files actually exist?
     - 📊 **Output validation** - Does sandbox output match claims?
     - 📧 **Delivery confirmation** - Were emails/messages actually sent?
     - 🔗 **Link verification** - Do added items exist in DB?
   - Runs automatically after background tasks complete
   - Can re-queue failed tasks or notify user of discrepancies
   - Uses cheap/fast model (verification is mostly rule-based + spot checks)
   - Triggered by: task completion, user request, scheduled audits

**Why "Council" not true MoE:**
- Same base weights, different prompts → correlated blind spots
- But: consensus = high confidence, disagreement = interesting edge case
- Cheap uncertainty detection with anime-style charm (萌え)
- "Not as strong as actual MoE, but still moe in both senses"

**Implementation Notes:**
- Current fallback chain (DeepSeek → Kimi → Hermes) is stepping stone
- Council adds privacy/complexity triage layer before model selection
- GCU aesthetic: technically sound self-aware AI deciding its own limits

---

*Last Updated: 2025-12-30*
*Current Phase: 4.1-4.6 (70% Complete - Free APIs, Infrastructure, Authentication, Library Experience)*

## Recent Wins 🎉

**Phase 4.6 - Passwordless Authentication & API Access (2025-11-22 to 23)**
- ✅ **holod REST API** - Background daemon serving Flask API on port 5555
- ✅ **Magic link authentication** - Zero passwords, 5-min expiry, single-use tokens
  - Generate via Telegram `/login` command
  - Generate via CLI `holo auth link`
  - Bot detection prevents Telegram link previews from consuming tokens
- ✅ **API token system** - Bearer tokens for programmatic access
  - `holo auth token create --name "My Laptop"` - Generate tokens with `hlc_` prefix
  - `holo auth token list` - View active tokens with last_used_at tracking
  - `holo auth token revoke <id>` - Revoke compromised tokens
- ✅ **Dual authentication** - `@require_auth` decorator supports both:
  - Session cookies (7-day lifetime from magic link login)
  - Bearer tokens via `Authorization` header
- ✅ **Cloudflare Tunnel deployment** - Secure remote access at holo.stdgeo.com
- ✅ **Database Migration 7** - Added `users`, `auth_tokens`, `api_tokens` tables
- Successfully tested magic link flow end-to-end
- Successfully tested API token authentication with `curl`

**Technical Highlights:**
- User-Agent detection for bot link previews (Telegram, Discord, Slack)
- Automatic `last_used_at` tracking for API tokens
- Revocation support for compromised tokens
- Request context stores user info for audit trails
- Beautiful Rich-formatted CLI output with usage examples

**Phase 4.5 - AI Librarian (`holo ask`) (2025-11-21)**
- ✅ Implemented natural language queries over personal library
- ✅ Queries 77 books + 19 papers using DeepSeek V3
- ✅ Reading path generation, cross-reference recommendations
- ✅ Collection gap analysis built-in
- ✅ Budget tracking display (2,000 prompts/day)
- Successfully tested with factual, search, and recommendation queries

**Phase 4.1 - Free Knowledge APIs (2025-11 Complete)**
- ✅ Wikipedia integration - REST API with caching
- ✅ Crossref integration - 165M papers searchable
- ✅ arXiv integration - 2.4M+ preprints
- ✅ OpenAlex integration - 250M+ works (bonus!)
- ✅ Unpaywall integration - Find Open Access PDFs (bonus!)

**Phase 4.2 - Infrastructure (2025-11 Complete)**
- ✅ Mercado Livre integration - OAuth, favorites sync, AI classification
- ✅ Telegram bot - Mobile paper/link capture
- ✅ HTTPFetcher - Proxy support, caching
- ✅ Inventory system - EAV attributes, tags

**Phase 3.7 - Dewey Decimal Classification (2025-11-18)**
- Implemented AI-powered Dewey classification using DeepSeek V3
- Added Cutter-Sanborn number generation for unique shelf positions
- Full call number support (e.g., "550.182 I10a" - exactly like IGc Library!)
- Configurable classification system (Dewey/UDC)
- Classification repair tool for missing metadata
- Library catalog view with `--by-dewey` sorting
- Successfully classified 77-book collection with high accuracy
- Your 550.182 geostatistics section is now beautifully organized! 📚
