# Holocene Roadmap

**Last Major Update:** 2025-11-18 (AEDB scavenge & architecture redesign)

## Important Design Documents

Before implementing features, review these foundational docs:

1. **`design/integrations/aedb_scavenge.md`** - AEDB analysis, architecture decisions, phased plan
2. **`design/features/extended_dewey_classification.md`** - Universal classification system
3. **`design/integrations/mercadolivre_favorites.md`** - Mercado Livre integration spec
4. **`CLAUDE.md`** - Project conventions and agent collaboration guide

## Current Status (Phase 4.2 In Progress - Nov 18, 2025)

### Implemented Features
- ✅ Activity tracking with privacy controls
- ✅ Link collection with Internet Archive integration (1,153+ links)
- ✅ Trust tier system (pre-LLM / early-LLM / recent)
- ✅ Book collection management (77 books imported)
- ✅ **Book enrichment** - LLM-generated summaries and tags (batch processing)
- ✅ Deep research mode with book integration
- ✅ PDF text extraction with OCR fallback
- ✅ Markdown report generation
- ✅ NanoGPT subscription usage tracking
- ✅ **Dewey Decimal Classification** - AI-powered classification with Cutter numbers (Phase 3.7)
- ✅ **Full call number generation** - IGc Library-style format (e.g., "550.182 I10a")
- ✅ **Configurable classification system** - Dewey or UDC via config
- ✅ **Classification repair tool** - Auto-fix missing Cutter numbers
- ✅ **Library catalog view** - `--by-dewey` sorting for shelf order browsing

---

## Phase 4: Enhanced Research Capabilities

### Priority 1: Free Knowledge APIs 🌟 (IN PROGRESS)

**Wikipedia + Internet Archive Integration**

**Why Start Here:**
- Both completely free
- No API keys needed (for IA public domain)
- Immediate value for research
- Stable, trustworthy sources

#### 4.1a: Wikipedia Integration

**Features to Build:**
```bash
holo research start "topic" --include-wikipedia
# Adds Wikipedia overview to research report
```

**Implementation:**
- Use Wikipedia REST API
- Fetch article summary (first section)
- Cache results locally
- Add as "Background" section in research reports
- Include Wikipedia references/citations

**API Details:**
- Endpoint: `https://en.wikipedia.org/api/rest_v1/`
- Rate limit: 200 req/sec (very generous)
- No authentication needed
- Returns: JSON with article text, summary, metadata

**Cost:** FREE

---

#### 4.1b: Crossref Academic Papers 🔥 NEW!

**Features to Build:**
```bash
# Search academic papers
holo papers search "geostatistics kriging"

# Add paper to research collection
holo papers add <DOI>

# Research includes relevant papers
holo research start "topic" --include-papers
```

**What We Can Access:**
- **165 MILLION academic works:**
  - Journal articles
  - Conference papers
  - Books & chapters
  - Preprints
  - Research datasets

**Perfect for Your Research:**
- Mining engineering papers
- Geostatistics research
- Computer science papers
- Mathematics papers
- ALL with DOIs, authors, citations, abstracts

**Implementation:**
- Search Crossref REST API
- Filter by date (focus on pre-LLM: before 2022-11)
- Store metadata in new `papers` table
- Link papers to research topics
- Include in research reports

**API Details:**
- Endpoint: `https://api.crossref.org/works`
- No authentication needed
- Free, generous rate limits
- Full JSON metadata
- Returns: titles, authors, DOIs, abstracts, references, citations

**Example Searches:**
```
# By topic and date range
/works?query=geostatistics&filter=from-pub-date:1990,until-pub-date:2022

# By author
/works?query.author=Smith

# Get full metadata
/works/{DOI}
```

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

**Cost:** FREE

**Why This Is HUGE:**
- Primary source for recent academic research
- Pre-LLM papers easily filtered by date
- Citations show research lineage
- Complements classic books from IA

---

#### 4.1c: Internet Archive Public Domain Books

**Features to Build:**
```bash
# Search IA for public domain books
holo books discover-ia "geostatistics"

# Download public domain book
holo books add-ia <identifier>

# Batch import classic texts on topic
holo research expand-library "mining engineering" --era=1900-1980
```

**What We Can Access:**
- 10,000,000+ books and texts
- **Focus areas for your research:**
  - Classic mining engineering textbooks (1900s-1970s)
  - Historical geostatistics papers
  - Older CS/programming texts
  - Mathematical treatises
  - Geology/earth science classics

**Implementation:**
- Search IA metadata API
- Filter for public domain only (no lending)
- Download PDFs directly: `https://archive.org/download/{id}/{file}.pdf`
- Extract text with existing PDFHandler
- Enrich with LLM (existing pipeline)
- Add to books database

**API Details:**
- Search: `https://archive.org/advancedsearch.php?q=...&output=json`
- Metadata: `https://archive.org/metadata/{identifier}`
- Download: `https://archive.org/download/{identifier}/{filename}`
- All FREE, no authentication for public domain

**Example Search:**
```json
// Find public domain mining books
q=subject:mining AND mediatype:texts AND date:[1900 TO 1980]
```

**Cost:** FREE

**Storage:** User's choice - reference only, or download PDFs locally

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

### Priority 1: Metadata Enrichment Pipeline 🔍

**Goal:** Automatically fill missing author/metadata from multiple sources.

**Features:**
```bash
holo books enrich --missing-authors    # Fix books with no author
holo books enrich --all                # Full metadata enrichment
holo books enrich <book_id>            # Single book enrichment
```

**Multi-Source Strategy:**
1. OpenLibrary API (ISBN/title lookup)
2. Google Books API (title/author matching)
3. WorldCat API (bibliographic database)
4. LLM inference (e.g., "O Design do Dia a Dia" → Don Norman)

**Why Priority 1:**
- Solves immediate problem (9 books without authors)
- Enables full call number generation for all books
- Foundation for other features (all need good metadata)

**Implementation:**
- Waterfall approach: try each source until match found
- Confidence scoring for LLM-inferred data
- Manual review interface for uncertain matches
- Cache successful lookups to avoid re-querying

---

### Priority 2: 3D Virtual Library (Three.js) 🎮

**Goal:** Walk through your library in 3D space, organized by Dewey classification.

**Features:**
```bash
holo books serve --3d    # Start web server with 3D view
# Opens browser to http://localhost:8080
```

**3D Experience:**
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

**Technical Stack:**
- **Three.js** for 3D rendering
- **Flask/FastAPI** for web server
- **WebGL** shader for realistic book spines
- **Procedural generation** for book covers based on metadata
- **LOD (Level of Detail)** for performance with large libraries

**Why This Rocks:**
- Stunning visual showcase
- Makes browsing fun (not just functional)
- "Library tourism" - share screenshots of your collection
- Not as hard as it sounds with Three.js!

**Estimated Effort:** 2-3 days for MVP, polish over time

---

### Priority 3: AI Librarian Chat 🤖

**Goal:** Natural language interface to your collection.

**Features:**
```bash
holo ask "What books do I have about spatial statistics?"
holo ask "Which geology books were published before 1995?"
holo ask "Recommend books that combine programming and earth sciences"
holo ask "What's the oldest book in my collection?"
```

**Implementation:**
- Use LLM (DeepSeek V3) with function calling
- Provide book database as context (titles, authors, classifications, summaries)
- Generate SQL queries or filter logic based on questions
- Return formatted results with call numbers
- Follow-up questions for refinement

**Advanced Features:**
- "Reading path" generation: "I want to learn structural geology" → ordered list from basics to advanced
- Cross-reference recommendations: "Books similar to Isaaks' geostatistics book"
- Gap analysis: "You have lots of 550s and 005s, but nothing bridging them - try these..."

**Why Powerful:**
- Leverages your existing LLM infrastructure
- Makes library "conversational" not just searchable
- Enriched summaries make recommendations smarter
- Natural way to discover connections between books

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

### CRITICAL: Architecture Review Session 🏗️
**Status:** SCHEDULED - Before Phase 4.3
**Priority:** ⚠️ HIGH - Must complete before continuing major implementation

**Why Now:**
We've been in deep implementation mode (ML integration, proxy setup, caching, inventory) without stepping back to review overall architecture. Need to ensure system coherence before building more features.

**Scope - Review & Document:**

1. **Data Flow Architecture**
   - Input sources (APIs, web scraping, files, user commands)
   - Processing pipeline (fetch → cache → parse → enrich → store)
   - Output formats (CLI, reports, exports, visualizations)
   - Where does each integration fit?
   - How do integrations interact? (e.g., ML → Inventory → Classification)

2. **Storage Strategy**
   - Database schema evolution (when to add columns vs new tables)
   - Caching policy (HTML, API responses, LLM results)
   - File storage organization (PDFs, cached HTML, exports)
   - Cleanup/rotation policies for cached data
   - Backup and migration strategy

3. **Operating Modes Reconciliation**
   - On-demand mode (current: `holo <command>`)
   - Autonomous daemon mode (planned: background processing)
   - How do these coexist?
   - Shared infrastructure needs
   - Command queue vs direct execution
   - When to use which mode?

4. **Processing & Enrichment**
   - LLM usage patterns (when to batch, when to real-time)
   - API call optimization (rate limiting, retries, cost tracking)
   - Proxy routing decisions (when to proxy, when not to)
   - Enrichment pipelines (metadata → classification → summaries)
   - Dependency chains (e.g., need description before categorizing)

5. **Task & Queue Management**
   - Background job architecture (if needed)
   - Priority handling (urgent vs batch)
   - Failure recovery (retries, dead letter queue)
   - Progress tracking and resumability
   - User notification of long-running tasks

6. **Integration Abstraction Patterns**
   - BaseAPIClient needs (common to all APIs)
   - HTTPFetcher usage guidelines
   - When to create new integrations/ vs extending existing
   - Configuration organization (per-integration vs global)
   - Testing strategy for integrations

7. **Configuration Management**
   - Config file organization as features grow
   - Secrets management (API keys, tokens)
   - Per-integration settings vs global settings
   - Migration strategy for config changes
   - Validation and error reporting

8. **LLM Personality & Voice Design**
   - System prompt strategy (default tone/personality)
   - Context-specific voices (research vs thermal receipts vs enrichment)
   - Tone guidelines (direct/grounded vs creative vs formal)
   - Consistency across commands
   - User preference configuration
   - OS-tan for Holocene? (character design if going full weeb)

**Deliverables:**
- 📄 **`design/architecture/SYSTEM_OVERVIEW.md`** - High-level architecture diagram + explanations
- 📄 **`design/architecture/data_flows.md`** - Data flow diagrams for major operations
- 📄 **`design/architecture/operating_modes.md`** - Daemon vs CLI mode reconciliation
- 📄 **`design/architecture/integration_guidelines.md`** - How to add new integrations
- 📄 **`design/architecture/storage_strategy.md`** - Database, cache, files organization
- 📄 **`design/architecture/task_queue.md`** - Background job design (if needed)
- 🔄 **Updated ROADMAP.md** - Reprioritized based on architectural decisions

**Questions to Answer:**
- Do we need a background daemon now, or can we defer?
- Should we implement a task queue system before more integrations?
- Is our database schema sustainable as features grow?
- Do we need a proper ETL pipeline abstraction?
- How do we handle long-running enrichment operations?
- Should proxy routing be configurable per-command?
- What's the right balance between LLM creativity and directness?
- Should we have different LLM personalities for different command contexts?

**Estimated Time:** 1-2 full sessions (4-6 hours)
**Outcome:** Clear architectural vision before Phase 4.3+

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

---

*Last Updated: 2025-11-18*
*Current Phase: 3.7 Complete (Dewey Classification + Cutter Numbers), Continuing Phase 4.1 (Free Knowledge APIs)*

## Recent Wins 🎉

**Phase 3.7 - Dewey Decimal Classification (2025-11-18)**
- Implemented AI-powered Dewey classification using DeepSeek V3
- Added Cutter-Sanborn number generation for unique shelf positions
- Full call number support (e.g., "550.182 I10a" - exactly like IGc Library!)
- Configurable classification system (Dewey/UDC)
- Classification repair tool for missing metadata
- Library catalog view with `--by-dewey` sorting
- Successfully classified 77-book collection with high accuracy
- Your 550.182 geostatistics section is now beautifully organized! 📚
