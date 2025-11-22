# Holocene Project Guide for Claude

## Project Overview

**Holocene** is a personal knowledge management and productivity tracking system with a focus on:
- Activity tracking and analysis
- Personal library management (books, papers, research)
- Integration with various tools (Internet Archive, Calibre, Wikipedia, etc.)
- Thermal printing capabilities via Paperang P1 printer
- AI-powered assistance via LLM integrations

**Philosophy:** Privacy-first, local-first, human-in-the-loop design. Named after the current geological epoch representing "recent time."

---

## 🚨 CRITICAL: Context Loading Strategy

**ALWAYS read these files first in EVERY new session:**

1. **`design/SUMMARY.md`** (Tier 0) - High-level architecture overview (~300 lines)
   - Two operating modes (autonomous + on-demand)
   - LLM strategy (DeepSeek V3, Qwen Coder, model routing)
   - Privacy architecture (3-tier model)
   - Current implementation status
   - **This is your required context foundation**

2. **`CLAUDE.md`** (this file) - Project conventions and tips

3. **`docs/ROADMAP.md`** - Current priorities and next steps (~422 lines)

**Recommended base context budget:** ~35-50k tokens (leaves 150k+ for work)

### Tiered Design Documentation

Design docs are organized in **tiers** for efficient context management:

- **Tier 0:** `design/SUMMARY.md` - ALWAYS load first
- **Tier 1:** `design/architecture/` - Load when working on core systems
- **Tier 2:** `design/integrations/`, `design/features/`, `design/security/` - Load selectively

**See `design/README.md` for complete navigation guide.**

**Why this matters:** Holocene has complex architecture (background daemon, model routing, IFTTT rules, security layers). Loading everything causes context bloat and information loss. The tier system ensures you always have the critical context while preserving budget for your actual work.

### Example Context Loading

**Working on thermal printing:**
```
Base (always): design/SUMMARY.md + CLAUDE.md + ROADMAP.md  (~35k tokens)
Task-specific: design/integrations/thermal_printing.md     (~10k tokens)
Total: ~45k tokens (leaves 155k for code/conversation)
```

**Working on autonomous daemon:**
```
Base (always): design/SUMMARY.md + CLAUDE.md + ROADMAP.md        (~35k tokens)
Task-specific: design/architecture/operating_modes.md             (~15k tokens)
               design/architecture/task_scheduler.md              (~10k tokens)
Total: ~60k tokens (leaves 140k for code/conversation)
```

**❌ Anti-pattern:** Reading all of `holocene_design.md` (1,036 lines) → Information loss in compactions

**✅ Better:** Tier 0 + task-specific Tier 1/2 → Focused, efficient context

---

## Architecture

```
holocene/
├── src/holocene/          # Main package
│   ├── cli/              # Command-line interface (`holo` command)
│   ├── config/           # Configuration management
│   ├── core/             # Core domain models and logic
│   ├── integrations/     # External service integrations
│   │   ├── paperang/    # Paperang thermal printer integration
│   │   │   ├── spinitex.py         # TeX-inspired markdown renderer
│   │   │   ├── client.py           # Paperang P1 USB protocol
│   │   │   └── protocol_p1.py      # Low-level P1 commands
│   │   ├── calibre.py   # Calibre e-book library integration
│   │   ├── internet_archive.py     # Internet Archive API
│   │   ├── bookmarks.py # Browser bookmarks import
│   │   ├── journel.py   # Integration with journel tool
│   │   └── git_scanner.py          # Git activity tracking
│   ├── llm/              # LLM provider integrations (NanoGPT, etc.)
│   ├── research/         # Research paper management
│   └── storage/          # Database and persistence layer
├── docs/                 # Documentation
├── tests/                # Test suite
├── scripts/              # Utility scripts
└── pyproject.toml        # Package configuration

User directories:
~/.config/holocene/       # Configuration files
~/.holocene/              # Data directory
  ├── books/             # Book library and metadata
  │   └── internet_archive/  # Downloaded IA books
  ├── research/          # Research papers
  ├── links/             # Saved links and bookmarks
  └── holocene.db        # SQLite database
```

## Key Components

### 1. CLI Interface (`holo` command)

**Location:** `src/holocene/cli/main.py`

Main command groups (60+ commands total):
- `holo ask` - AI Librarian for natural language queries (NEW - Nov 21, 2025)
- `holo books` - Book library management (search, add, list, enrich, classify)
- `holo papers` - Research paper management (arXiv, Crossref, OpenAlex)
- `holo links` - Link and bookmark management
- `holo wikipedia` - Wikipedia article search
- `holo research` - Research session management
- `holo print` - Thermal printing commands
- `holo config` - Configuration management (8+ subcommands)
- `holo stats` - Analytics and collection statistics (8+ subcommands)
- `holo inventory` - Inventory item management
- `holo mercadolivre` - Mercado Livre favorites integration (10+ commands)
- `holo daemon` - Background service management

**CLI Framework:** Click (Python CLI framework)
**Style:** Rich library for beautiful terminal output

### 2. Spinitex - Thermal Printing Typography Engine

**Location:** `src/holocene/integrations/paperang/spinitex.py`

A TeX-inspired markdown renderer specifically designed for thermal printers. Named after the "spinifex texture" found in komatiites (ultra-basic igneous rocks) - a geology pun on "ultra-basic TeX."

**Features:**
- Markdown parsing with inline styles (bold, italic, code)
- Text alignment (left, center, right)
- Split alignment using `\hfill` for equation numbering style
- Physical dimension support (PPI, margins in mm)
- Image embedding with 8 dithering algorithms:
  - Error diffusion: Floyd-Steinberg, Atkinson, Jarvis-Judice-Ninke, Stucki, Burkes, Sierra
  - Ordered: Bayer matrix
  - Threshold: Simple black/white
- Non-breaking headers (auto font-size reduction)
- Ligature support (programming fonts like Fira Code)

**Markdown Extensions:**
```markdown
@align:center         # Center alignment
@align:right          # Right alignment
@align:left           # Left (default)
\hfill                # Fill space (left/right split on line)
@image:path           # Embed image
@image:path:0.5       # Image at 50% width
@image:path:0.5:atkinson  # With specific dithering
---                   # Horizontal rule
```

**Typography Settings:**
- Default: 384px width (58mm thermal paper at 203 DPI)
- Target: ~32 chars/line with 16px base font
- Margins: Physical units (mm) converted to pixels via PPI
- Fonts: Supports Fira Code, JetBrains Mono Nerd Font, Iosevka Nerd Font

**Important:** Headers are non-breaking - they automatically shrink to fit on one line if needed.

### 3. Paperang P1 Integration

**Location:** `src/holocene/integrations/paperang/`

USB thermal printer integration with custom protocol implementation.

**Files:**
- `client.py` - High-level printer client
- `protocol_p1.py` - Low-level P1 protocol commands
- `spinitex.py` - Markdown renderer (described above)

**Protocol Details:**
- USB communication via pyusb
- Custom packet format with CRC8 checksums
- Handshake sequence required before printing
- Bitmap format: 48 bytes per line (384 pixels ÷ 8)
- Auto-feed support for paper advancement

**Thermal Printer Architecture:**
The design separates rendering from printer drivers:
- Spinitex outputs printer-agnostic bitmaps
- Drivers handle printer-specific protocols (Paperang custom, ESC/POS, etc.)
- Width parameter allows different paper sizes (384px/58mm, 576px/80mm, etc.)

See: `docs/thermal_printer_architecture.md`

### 4. Book Library Management

**Integration Points:**
- **Internet Archive:** Download and index books via IA API
- **Calibre:** Sync with Calibre library, import/export metadata
- **Local Storage:** `~/.holocene/books/internet_archive/`

**Workflow:**
1. Search Internet Archive: `holo books discover-ia "topic"`
2. Add book: `holo books add-ia <identifier> --download-pdf`
3. Enrich metadata: `holo books enrich` (uses LLM to extract better metadata)
4. Integration with Calibre for advanced management

### 5. Research Management

**Location:** `src/holocene/research/`

Manages research papers, notes, and research sessions.

**Features:**
- Paper search and download
- Session tracking (start/show research sessions)
- Integration with paper repositories

## Important Conventions

### 1. File Organization

**Test Files:**
- All test scripts should go in `tests/` directory
- Temporary test files go in `tests_temp/` (gitignored)
- **Never create test files in project root** - this creates clutter

**Pattern:** The `.gitignore` already excludes:
```
tests_temp/
test_*.png
*_output.png
```

### 2. Configuration

**User Config:** `~/.config/holocene/config.yaml`
**Data Directory:** `~/.holocene/`
**Database:** `~/.holocene/holocene.db` (SQLite)

### 3. Database Schema

**Storage:** SQLite with structured schema
**Location:** `src/holocene/storage/`

**Key Tables:**
- Books metadata and library
- Papers and research materials
- Links and bookmarks
- Usage statistics

### 4. Privacy & Security

**Design Principles:**
- Privacy by design - local-first
- Explicit user approval for external API calls
- Tiered data access (local vs. external APIs)
- Sanitization of sensitive data before LLM processing

**Blacklisted Domains/Keywords:**
- Work-related domains (configured per user)
- Financial/sensitive sites
- See `config/` for privacy configuration

### 5. Code Style

**Python:**
- Black formatter (line length: 100)
- Ruff linter (target: Python 3.11+)
- Type hints encouraged
- Docstrings for public APIs

**Imports:**
```python
# Standard library first
import sys
import os
from pathlib import Path

# Third-party
import click
from rich import print

# Local
from holocene.core import models
from holocene.integrations import calibre
```

## 🤖 LLM Integration Strategy - USE NANOGPT!

**⚠️ CRITICAL REMINDER: We have a NanoGPT subscription!**

**Active Subscription:** $8/month, 2,000 prompts/day via nano-gpt.com
**Daily Budget:** MASSIVELY underutilized - we're paying for it, USE IT!

**When to use NanoGPT (basically always):**
- ✅ PDF metadata extraction (DeepSeek V3 690B is PERFECT for this)
- ✅ Text analysis, summarization, enrichment
- ✅ Batch processing tasks (can handle hundreds of items/day)
- ✅ Structured data extraction (papers, books, etc.)
- ✅ Research assistance (paper summaries, topic extraction)
- ✅ Any task requiring 64K context window
- ✅ **Default assumption: Use NanoGPT unless there's a specific reason not to**

**Available Models (via config):**
```python
config.llm.primary         # deepseek-ai/DeepSeek-V3.1 (690B params, 64K ctx)
config.llm.primary_cheap   # deepseek-chat-cheaper (for simple tasks)
config.llm.coding          # qwen/qwen3-coder (code generation)
config.llm.reasoning       # deepseek-r1 (complex reasoning)
config.llm.verification    # nousresearch/hermes-4-70b (cross-checking)
```

**Cost comparison:**
- Claude Haiku: $0.25/MTok ($0.00025 per 1K tokens)
- DeepSeek V3 via NanoGPT: Already paid for, 2000 uses/day included
- **Translation: DeepSeek is essentially FREE for our use cases**

**Integration:**
```python
from holocene.llm import NanoGPTClient
from holocene.config import load_config

config = load_config()
client = NanoGPTClient(config.llm.api_key, config.llm.base_url)
response = client.simple_prompt(
    prompt="Your prompt here",
    model=config.llm.primary,  # Use DeepSeek V3
    temperature=0.1            # Low for factual tasks
)
```

**Future:** Local inference on M4 Mac Mini (for offline/privacy-sensitive tasks)

See: `holocene_design.md` for comprehensive LLM strategy

## Common Tasks

### Adding a New Integration

1. Create module in `src/holocene/integrations/<name>.py`
2. Add CLI commands in `src/holocene/cli/main.py`
3. Add tests in `tests/test_<name>.py`
4. Update this document

### Testing Thermal Printing

**Without printer:**
```python
# Create render-only script
renderer = MarkdownRenderer(width=384, ppi=203)
bitmap = renderer.render(markdown_text)
# Save preview as PNG for visual inspection
```

**With printer:**
```python
from holocene.integrations.paperang import PaperangClient
client = PaperangClient()
client.find_printer()
client.handshake()
client.print_bitmap(bitmap, autofeed=True)
```

### Rendering Documents with Spinitex

```python
from holocene.integrations.paperang.spinitex import MarkdownRenderer

renderer = MarkdownRenderer(
    width=384,        # 58mm paper
    ppi=203,          # Standard thermal printer DPI
    margin_mm=2.0,    # Physical margins
    font_name="FiraCode",
    base_size=16      # Base font size in pixels
)

# Render markdown
bitmap = renderer.render(markdown_text)

# Save preview (for debugging without printer)
from PIL import Image
height = len(bitmap) // 48
img = Image.new('1', (384, height), 1)
for y in range(height):
    line_offset = y * 48
    for x in range(384):
        byte_idx = x // 8
        bit_idx = 7 - (x % 8)
        byte_val = bitmap[line_offset + byte_idx]
        if byte_val & (1 << bit_idx):
            img.putpixel((x, y), 0)
img.save("preview.png")
```

## Development Workflow

### Setup

```bash
# Clone repository
git clone https://github.com/endarthur/holocene.git
cd holocene

# Install in development mode
pip install -e .

# Install dev dependencies
pip install -e ".[dev]"

# Verify installation
holo --help
```

### Running Tests

```bash
# Run all tests
pytest

# Run specific test
pytest tests/test_spinitex.py

# Run with coverage
pytest --cov=holocene tests/
```

### Making Changes

1. Create feature branch
2. Make changes in `src/holocene/`
3. Add tests in `tests/`
4. Test locally: `pytest`
5. **Check dependencies**: `python scripts/check_dependencies.py`
6. Format code: `black src/ tests/`
7. Lint: `ruff check src/ tests/`
8. Commit with descriptive message

### Dependency Management

**IMPORTANT:** Before committing changes that add new imports, always run:

```bash
python scripts/check_dependencies.py
```

This script scans the entire codebase for imports and validates them against `pyproject.toml`. It will catch missing dependencies before they break production deployments.

**What it does:**
- AST-based parsing of all Python files
- Filters out stdlib and internal holocene modules
- Maps import names to package names (e.g., `bs4` → `beautifulsoup4`)
- Reports missing dependencies with file locations

**Example output:**
```
❌ Missing dependencies found:
  📦 bibtexparser (imported as 'bibtexparser')
     - src/holocene/research/bibtex_importer.py
```

**Adding dependencies:** Place them in the appropriate optional dependency group in `pyproject.toml`:
- `daemon` - holod REST API, Flask
- `pdf` - PDF processing, BibTeX
- `mercadolivre` - MercadoLivre scraping
- `telegram` - Telegram bot
- `paperang` - Thermal printer
- `research` - ChromaDB embeddings
- `integrations` - External services (Apify, etc.)

Add to `[all]` group if it should be included in full server installs.

## Known Issues & Gotchas

### Thermal Printing

1. **Font Installation (Windows):**
   - User fonts: `%LOCALAPPDATA%\Microsoft\Windows\Fonts`
   - System fonts: `C:\Windows\Fonts`
   - Spinitex checks both locations

2. **Ligature Support:**
   - Requires `fribidi.dll` in Python environment
   - Set `FRIBIDI_PATH` environment variable if needed
   - See Spinitex implementation for workaround

3. **Dithering Library:**
   - `hitherdither` requires RGB images (3 channels), not grayscale
   - Convert grayscale to RGB before dithering: `img.convert('L').convert('RGB')`

4. **Printer Connection:**
   - Paperang P1 requires specific USB permissions on Linux
   - May need udev rules or run with sudo
   - Windows: Usually works without special configuration

### Internet Archive

- Rate limiting: Respect IA's rate limits
- Some books require login for download
- PDF quality varies by source

### Database

- SQLite database at `~/.holocene/holocene.db`
- Automatic migrations not yet implemented
- Backup before schema changes

## Project Status

**Current Phase:** Phase 4 - 60% Complete (Nov 21, 2025)
**Python Version:** 3.11+
**License:** MIT

**Fully Implemented (Phase 3-4):**
- ✅ Book library management (77 books from IA + LibraryThing)
- ✅ Dewey Decimal Classification with Cutter numbers
- ✅ Thermal printing (Paperang P1 + Spinitex renderer)
- ✅ Academic papers (arXiv, Crossref, OpenAlex, Unpaywall - 19 papers)
- ✅ Wikipedia integration (REST API with caching)
- ✅ Link management (1,160+ links with trust tiers, bookmark import)
- ✅ LLM integrations (DeepSeek V3, Qwen Coder via NanoGPT)
- ✅ AI Librarian (`holo ask`) - Natural language collection queries
- ✅ CLI interface (60+ commands across 12 groups)
- ✅ Config & stats commands (8+ subcommands each)
- ✅ SQLite storage with migrations
- ✅ Mercado Livre integration (OAuth, favorites sync, AI classification)
- ✅ Telegram bot (mobile paper/link capture)
- ✅ Inventory system (EAV attributes, tags)
- ✅ HTTPFetcher (proxy support, caching)

**Partially Implemented:**
- 🔨 Metadata enrichment (LLM summaries working, multi-source lookup TODO)
- 🔨 Daemon infrastructure (skeleton exists, not fully operational)

**Planned (Phase 5-6):**
- ⏳ PubMed integration (36M biomedical papers)
- ⏳ 3D Virtual Library (Three.js visualization)
- ⏳ Browser extension for activity tracking
- ⏳ Task scheduler with long-running jobs
- ⏳ Obsidian vault sync
- ⏳ Home Assistant integration

See `docs/ROADMAP.md` for detailed roadmap and implementation status.

## Documentation

- **Design Doc:** `holocene_design.md` - Comprehensive system design
- **Thermal Printer:** `docs/thermal_printer_architecture.md` - Printing architecture
- **This File:** `CLAUDE.md` - Quick reference for Claude sessions

## Tips for Claude

### When Working on This Project

1. **Don't clutter the root directory** - Use `tests/` or `tests_temp/` for test files
2. **Check existing integrations** - Look at similar modules before creating new ones
3. **Respect privacy design** - Don't add features that bypass sanitization
4. **Test without hardware** - Use preview rendering for printer testing
5. **Update docs** - Keep this file and others current with changes

### Helpful Commands

```bash
# Find implementation of a feature
grep -r "function_name" src/

# See current database schema
sqlite3 ~/.holocene/holocene.db ".schema"

# Check active CLI commands
holo --help

# Run specific integration
python -m holocene.integrations.paperang.client
```

### Common Pitfalls

- ❌ Creating test files in project root → ✅ Use `tests/` or `tests_temp/`
- ❌ Hardcoding paths → ✅ Use config system
- ❌ Printing to Paperang during debugging → ✅ Render to PNG preview first
- ❌ Using grayscale images with hitherdither → ✅ Convert to RGB first
- ❌ Forgetting to update .gitignore → ✅ Add new generated files to ignore list

## Contact & Resources

- **Repository:** https://github.com/endarthur/holocene
- **Author:** Arthur (endarthur)
- **Related Projects:**
  - journel: ADHD-friendly logging tool
  - wabisabi: (related project)
  - GGR: Geostatistics library
  - Pollywog: (related project)

---

**Last Updated:** 2025-11-17
**Version:** 1.0
**Maintainer:** Arthur + Claude
