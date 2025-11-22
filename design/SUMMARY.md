# Holocene Design Summary (Tier 0)

> **Your personal geological record of the present**

**Read this file first in every Claude session.** This is Tier 0 - optimized for AI context efficiency.

---

## What is Holocene?

Holocene is a **privacy-first personal knowledge management and activity tracking system** with two operating modes:

1. **Autonomous Mode** - Background agent with continuous monitoring
2. **On-Demand Mode** - Interactive assistant for research and analysis

**Core Philosophy:**
- Track behavior, not content
- Privacy by design (3-tier model)
- Human-in-the-loop for all consequential actions
- Tool that assists rather than agent that acts

---

## Two Operating Modes

### Mode 1: Autonomous (Background Monitoring)
**Status:** Planned (not yet implemented)

Continuous daemon that:
- Auto-logs activities every 30-60 seconds from multiple data sources
- Sends periodic check-ins to LLM (~30-50/day via DeepSeek V3)
- Executes IFTTT-style automation rules (user-approved)
- Generates daily/weekly summaries automatically
- Vibrates Mi Band for break reminders

**Data Sources (future):**
- Browser extension (Chrome/Edge, unpublished)
- Window focus tracking (OS-level)
- System metrics (CPU/RAM patterns)
- Home Assistant sensors (temp, humidity, presence)
- Google Calendar events
- Mi Band (heart rate, sleep, activity)
- journel logs ✅ (implemented)
- Git activity ✅ (implemented)

### Mode 2: On-Demand (Interactive)
**Status:** Implemented ✅

User-initiated queries and tasks:
- `holo status` - Activity summary
- `holo analyze --week` - AI pattern analysis
- `holo research start "topic"` - Deep research compilation
- `holo books`, `holo papers`, `holo links` - Knowledge management
- `holo print` - Thermal printing via Spinitex

---

## LLM Strategy (NanoGPT $8/month)

**Model Routing** - Specialized LLMs for different tasks:
- **DeepSeek V3** (primary) - Daily synthesis, pattern detection, general tasks (128K context)
- **Qwen 3 Coder** - Code generation/review (often better than DS V3 for coding)
- **DeepSeek R1** - Complex reasoning chains, step-by-step thinking
- **Hermes 4 Large** - Verification, cross-checking DS V3 outputs
- **Llama 3B** (canary) - Lightweight injection detection, pre-screening
- **Math specialists** - Geostatistical calculations

**Budget:** 2,000 prompts/day (60,000/month) - currently using ~25/day (0.04%)

---

## Privacy Architecture

### Three-Tier Privacy Model

**Tier 1: Safe for External APIs (NanoGPT)**
- Generic activity descriptions
- Personal project details (open-source work)
- Time patterns, categories
- Home Assistant data, Google Calendar, Mi Band data

**Tier 2: Local Only (Future M4 Mac Mini)**
- Specific work context
- Screenshot analysis (manual only, vision models)
- Gmail content
- Detailed documents

**Tier 3: Never Logged**
- Financial data, production numbers
- Unreleased exploration results
- Confidential work information
- Anything marked sensitive

### Sanitization Layer
Every activity filtered BEFORE storage:
- Blocked domains → rejected
- Blacklisted keywords → redacted to `[REDACTED]`
- Sensitive paths → rejected
- URLs → stripped to `[URL]`

---

## Task Scheduler System

**Status:** Planned (not yet implemented)

Three task types:
1. **One-shot** - Single LLM call, immediate response
2. **Long-running** - Multi-day execution with state persistence (e.g., process 3000 links over 60 days)
3. **Background** - Low priority, scheduled execution

**Features:**
- Checkpoint/resume capability
- Priority queue
- Daily budget limits (e.g., 50 items/day)
- State tracking in database

---

## Current Implementation Status

### ✅ Implemented (On-Demand Mode)
- Manual activity logging with privacy sanitization
- SQLite storage with full CRUD
- **Database migrations** (6 migrations applied, auto-run on startup)
- CLI interface (`holo` command via Click)
- **DeepSeek V3.1 integration** via NanoGPT API
- Budget tracking (2000 calls/day monitored)
- **journel integration** (reads 8 active projects)
- **Git activity tracking** (scans local repos)
- **Internet Archive integration** (1,153+ links with trust tiers)
- **Link management** (extraction, deduplication, bookmarks import, URL unwrapping)
- **Book collection** (77 books from IA + LibraryThing)
- **Book enrichment** (LLM-generated summaries/tags)
- **Dewey Decimal Classification** (AI-powered with Cutter numbers, full call numbers)
- **Deep research mode** (overnight compilation, markdown reports)
- **PDF handling** (text extraction + OCR fallback)
- **Thermal printing** (Spinitex renderer + Paperang P1)
- **Wikipedia search** (free API integration)
- **Academic papers** (arXiv integration complete, Crossref planned)
- **Inventory management** (items with EAV attributes, normalized tags)
- **Mercado Livre integration** (OAuth, favorites sync, auto-classification via DeepSeek)
- **Telegram bot** (mobile capture for papers, links, DOIs, classification queries)

### ⏳ Not Yet Implemented (Autonomous Mode)
- Background daemon
- Browser extension for passive tracking
- Window focus monitoring
- Home Assistant integration
- Mi Band notifications
- Google Calendar integration
- IFTTT rule engine
- Automated daily/weekly summaries
- Task scheduler with long-running tasks

---

## Security & Safety

### Prompt Injection Defense (Layered)

1. **Architectural** - Don't fetch full web content, use structured APIs
2. **Quarantine System** - All external summaries reviewed by user before entering context
3. **Multi-model Verification** - DS V3 → Llama 3B canary → Hermes 4 → User approval
4. **Heuristic Pre-filters** - Regex patterns for common injection attempts
5. **Honeypot Tools** - Fake tools that trigger red flags if LLM tries to use them

### Automation Boundaries

**Allowed:**
- IFTTT-style rules (user-approved)
- Mi Band vibrations for reminders
- Home Assistant service calls (whitelisted)
- Daily/weekly summary generation

**Not Allowed:**
- Autonomous code execution without approval
- Self-modification of rules/behavior
- Recursive agent creation
- File system access outside designated zones
- POST/PUT/DELETE requests to external APIs

---

## Current Priorities (from ROADMAP.md)

**Phase 4.1 - Free Knowledge APIs (In Progress):**
1. Wikipedia integration into research reports
2. Crossref academic papers (165M papers, FREE)
3. Internet Archive public domain book discovery

**Future:**
- Kagi Universal Summarizer (PDF/link summaries, ~$3-15/month)
- Calibre library integration (when library migrated)
- Autonomous background monitoring mode
- Browser extension development

---

## Technology Stack

**Core:**
- Python 3.11+
- SQLite 3
- Click (CLI framework)
- Rich (beautiful terminal output)

**LLM:**
- NanoGPT API (OpenAI-compatible)
- 200+ models available via subscription

**Integrations (implemented):**
- Internet Archive API (link archival, book downloads)
- Wikipedia REST API (article summaries)
- Crossref REST API (academic papers - planned)
- pyusb (Paperang P1 thermal printer)
- PDFPlumber + pytesseract (PDF text extraction + OCR)

**Future:**
- Home Assistant REST API
- Google Calendar API
- Browser extension (JavaScript, Manifest V3)

---

## Key Integrations

### Spinitex - Thermal Printing Typography Engine
**Location:** `src/holocene/integrations/paperang/spinitex.py`

TeX-inspired markdown renderer for thermal printers (named after spinifex texture in komatiites - geology pun on "ultra-basic TeX").

**Features:**
- Markdown with inline styles (bold, italic, code)
- Text alignment (left, center, right) + split with `\hfill`
- Image embedding with 8 dithering algorithms
- Non-breaking headers (auto font-size reduction)
- Physical dimensions (PPI, margins in mm)
- Ligature support (Fira Code, JetBrains Mono, Iosevka)

**See:** `design/integrations/thermal_printing.md` for details

### Deep Research Mode
**Command:** `holo research start "topic"`

Overnight research compilation using spare API credits:
- Searches book collection, papers, Wikipedia
- LLM analysis and synthesis
- Generates comprehensive markdown reports
- Pre-LLM source prioritization (trust tiers)

**See:** `design/integrations/research_mode.md` for details

---

## Trust Tier System (Security Feature)

Links categorized by Internet Archive snapshot date:

- **🟢 pre-llm** (before Nov 2022) - Lowest injection risk, ideal for LLM analysis
- **🟡 early-llm** (Nov 2022 - Jan 2024) - Medium risk
- **🔴 recent** (Jan 2024+) - Highest risk, requires careful sanitization
- **⚪ unknown** - No archive date, treat with maximum caution

**Purpose:** Safer LLM-based content analysis by preferring pre-LLM era sources.

---

## File Organization

```
holocene/
├── src/holocene/              # Main package
│   ├── cli/                  # Command-line interface
│   ├── core/                 # Domain models, sanitizer
│   ├── storage/              # SQLite database layer
│   ├── llm/                  # LLM integrations (NanoGPT)
│   ├── research/             # Research compilation system
│   ├── config/               # Configuration management
│   ├── plugins/              # Daemon mode plugins
│   └── integrations/         # External services
│       ├── paperang/        # Thermal printer (Spinitex + client)
│       ├── calibre.py       # Calibre e-book library
│       ├── internet_archive.py  # IA archiving & book downloads
│       ├── mercadolivre.py  # ML favorites sync & enrichment
│       ├── arxiv.py         # arXiv paper metadata
│       ├── crossref_client.py  # Crossref academic papers
│       ├── apify.py         # Apify web scraping client
│       ├── telegram_bot.py  # Telegram bot for mobile capture
│       ├── journel.py       # journel integration
│       └── git_scanner.py   # Git activity tracking
├── design/                    # Design documentation (THIS)
│   ├── SUMMARY.md            # Tier 0 (always read)
│   ├── architecture/         # Tier 1 (core system)
│   ├── integrations/         # Tier 2 (specific features)
│   ├── features/             # Tier 2 (feature concepts)
│   └── security/             # Tier 2 (security)
├── docs/                      # Feature-specific documentation
│   └── ROADMAP.md            # Current priorities & next steps
├── tests/                     # Test suite
├── CLAUDE.md                  # Project guide for Claude sessions
└── README.md                  # User-facing README

User directories:
~/.config/holocene/config.yaml  # Configuration
~/.holocene/holocene.db         # SQLite database
~/.holocene/books/              # Book library
~/.holocene/research/           # Research compilations
```

---

## Development Priorities (from original design)

### MVP (Must Have)
1. ✅ Activity logging (manual)
2. ✅ CLI (status, analyze, show)
3. ✅ DeepSeek V3 integration
4. ✅ Privacy sanitization
5. ⏳ Daily summaries (manual via `holo analyze`)
6. ✅ SQLite storage

### Should Have
7. ⏳ Home Assistant integration
8. ⏳ Mi Band notifications
9. ⏳ Task system
10. ⏳ Weekly review generation

### Could Have
11. ⏳ Calendar integration
12. ⏳ Verification system (multi-model)
13. ⏳ IFTTT rule engine
14. ✅ Quarantine for web content (trust tiers)

### Won't Have (Yet)
- Web UI/dashboard
- Mobile app
- Local inference (waiting for M4 Mac Mini)
- Gmail integration

---

## Deployment Phases

**Phase 1 (Current):** Development on local machine, NanoGPT API
**Phase 2 (Q1-Q2 2026):** Background daemon, full IFTTT rules, weekly reviews
**Phase 3 (Q2 2026+):** M4 Mac Mini with local DeepSeek V3, vision models, no rate limits

---

## For Next Steps

**See:**
- `docs/ROADMAP.md` - Current priorities (Wikipedia, Crossref, Kagi)
- `CLAUDE.md` - Project conventions, helpful commands, common pitfalls
- `design/architecture/` - Deep dive into system architecture
- `design/integrations/` - Specific integration details

**Working on specific features?** Load only the relevant Tier 2 files to preserve context budget.

---

**Version:** 1.1
**Last Updated:** 2025-11-21
**Purpose:** Tier 0 overview for efficient AI assistant context loading
**Next Tier:** Read specific `design/architecture/` or `design/integrations/` files as needed
