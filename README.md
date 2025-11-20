# Holocene

> Your personal geological record of the present.

Holocene is a privacy-focused activity tracking and AI assistant system designed to help you understand your behavior patterns without judgment.

## Quick Deploy (Proxmox) - Recommended

Deploy Holocene to a Proxmox LXC container in one command:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/endarthur/holocene/main/scripts/setup-holocene-lxc.sh)
```

This will:
- Create an Ubuntu 22.04 LXC container
- Install holod daemon with systemd service
- Configure mDNS for `holocene-rei.local` access
- Set up the REST API on port 5555
- Enable automatic startup on boot

See [DEPLOYMENT.md](docs/DEPLOYMENT.md) for complete instructions and customization options.

## Status: Plugin Architecture Complete ✅

**Core System:**
- ✅ **holod daemon** - Background service for 24/7 plugin execution
- ✅ **Plugin architecture** - Event-driven, channel-based messaging
- ✅ **REST API** - Flask server on port 5555 for multi-device coordination
- ✅ **Multi-device support** - rei (server), wmut (CLI), eunice (mobile)
- ✅ **Database migrations** - Lightweight schema evolution system
- ✅ **SQLite storage** - Metadata JSON pattern, no ALTER TABLE drift

**Working Plugins:**
- ✅ **book_enricher** - LLM-powered book metadata extraction (NanoGPT)
- ✅ **book_classifier** - Dewey Decimal Classification with Cutter numbers
- ✅ **link_status_checker** - Link health monitoring, rot detection
- ✅ **telegram_bot** - Mobile notifications and commands (eunice device)

**Legacy Features:**
- ✅ Manual activity logging
- ✅ Privacy sanitization layer
- ✅ Beautiful CLI with rich formatting
- ✅ Journel integration (reads 8 active projects)
- ✅ Git activity tracking (scans local repos)
- ✅ Internet Archive integration
- ✅ Smart link management
- ✅ Trust tier security (time-based prompt injection risk assessment)

**Next steps:**

**Phase 3: Vision & Context**
- SenseCap Watcher integration (manual-only screen capture with vision AI)
- Manual screenshot analysis using vision models
- Context-aware activity suggestions
- Weekly trend analysis

**Phase 3.5: Deep Research Mode** ⭐ NEW
- Overnight research compilation using spare API credits
- `/next-episode` slash command for research topics
- PDF & OCR handling for academic papers
- Vision model analysis of figures/diagrams
- LibraryCat book collection integration
- Pre-LLM source prioritization
- Wake up to comprehensive markdown reports

**Phase 4: Visualization**
- Web dashboard with holographic UI effects
- Activity timeline visualization
- Trading card achievements (with holographic gradients!)
- Mobile PWA with face-tracking parallax

**Phase 5: Polish**
- Holographic stickers (because why not?)
- Browser extension for passive tracking (optional)
- Window focus tracking (optional)

**Privacy Constraint:** Screenshot/vision capture MUST always be manual/user-initiated. Automatic capture will NEVER be implemented to maintain privacy-by-design principles.

## Installation

Holocene uses optional dependency groups for flexible installation:

```bash
# Clone the repository
git clone https://github.com/endarthur/holocene
cd holocene

# Option 1: Full installation (recommended for servers)
pip install -e ".[all]"

# Option 2: Core only (minimal CLI)
pip install -e .

# Option 3: Daemon + specific features
pip install -e ".[daemon,pdf,telegram]"

# Initialize
holo init
```

### Dependency Groups

- **Core** (always installed): CLI, config, storage, basic integrations
- **daemon**: holod background service + REST API (Flask)
- **pdf**: PDF processing for books, papers, and BibTeX
- **mercadolivre**: MercadoLivre integration
- **telegram**: Telegram bot for mobile notifications
- **paperang**: Paperang thermal printer support
- **research**: Vector embeddings and advanced search (ChromaDB)
- **integrations**: External services (Apify, etc.)
- **all**: Everything above
- **dev**: Development tools (pytest, black, ruff)

## Quick Start

```bash
# Initialize Holocene (creates config and database)
holo init

# Log an activity manually
holo log "working on GGR kriging validation" \
  --tags python,geostatistics \
  --type coding \
  --context open_source \
  --duration 45

# See today's status
holo status

# Show detailed view
holo show --today
holo show --week
```

## Configuration

Edit `~/.config/holocene/config.yml` or set environment variables:

```yaml
privacy:
  tier: external_api  # or local_only

  blacklist_domains:
    - "*.vale.com"
    - "mail.google.com"

  blacklist_keywords: []  # Add sensitive keywords
  blacklist_paths: []     # Add sensitive paths

llm:
  provider: nanogpt
  # Set NANOGPT_API_KEY env var or add here
  daily_budget: 2000

  # Available models
  primary: deepseek-ai/DeepSeek-V3.1
  primary_cheap: deepseek-chat-cheaper
  coding: qwen/qwen3-coder
  reasoning: deepseek-r1
```

## Link Archiving with Exponential Backoff

Holocene automatically manages failed archive attempts using **exponential backoff**:

- **1st failure**: Retry after 1 day
- **2nd failure**: Retry after 2 days
- **3rd failure**: Retry after 4 days
- **4th failure**: Retry after 8 days
- **Maximum**: 30 days between retries

Failed attempts are tracked with:
- Error messages from Internet Archive
- Attempt count and timestamps
- Calculated next retry date

**Behavior:**
- `holo links archive` - Respects backoff by default (skips links not ready for retry)
- `holo links archive --force` - Ignores backoff, retries all failed links immediately
- `holo links archive --retry-failed` - Only processes failed links that are ready

This prevents hammering the Internet Archive with repeated failures (e.g., dead pages) while still allowing eventual retry.

## Trust Tiers: Time-Based Security for LLM Analysis

Holocene implements **trust tier classification** based on Internet Archive snapshot dates to reduce prompt injection risks:

### Trust Tier Categories

**🟢 pre-llm** (before Nov 2022)
- Archived before ChatGPT's public release
- No deliberate LLM-targeted attacks
- Lowest risk for prompt injection
- Ideal for safe LLM-based content analysis

**🟡 early-llm** (Nov 2022 - Jan 2024)
- Early public LLM awareness
- Some experimental attacks
- Medium risk

**🔴 recent** (Jan 2024+)
- Widespread prompt injection knowledge
- Adversarial examples common
- Highest risk - requires careful sanitization

**⚪ unknown**
- No archive date available
- Treat with maximum caution

### Use Cases

This security feature enables **safer LLM-based research** in Phase 3:
- Analyzing web content for context (prefer pre-LLM snapshots)
- Extracting information from archived pages
- Research on historical web content
- Reduced risk of adversarial prompt injection

**Note:** While pre-LLM content significantly reduces deliberate attacks, accidental injection patterns can still occur (the "Bobby Tables" problem). Always apply appropriate sanitization.

## Privacy by Design

Holocene implements a **three-tier privacy model**:

**Tier 1: Safe for External APIs**
- Generic activity descriptions
- Personal project details
- Time patterns and categories

**Tier 2: Local Only (Future)**
- Specific work context
- Screenshot analysis
- Detailed documents

**Tier 3: Never Logged**
- Financial data
- Confidential information
- Production numbers

### Sanitization

Every activity goes through privacy filters BEFORE storage:
- Blocked domains → activity rejected
- Blacklisted keywords → redacted to `[REDACTED]`
- Sensitive paths → activity rejected
- URLs → stripped to `[URL]`

## Available Models (NanoGPT)

217 models available including:

**Primary Analysis:**
- `deepseek-ai/DeepSeek-V3.1` - Latest DeepSeek (128K context)
- `deepseek-chat-cheaper` - Budget-friendly for high volume

**Specialized:**
- `qwen/qwen3-coder` - Code-specific tasks
- `deepseek-r1` - Complex reasoning
- `nousresearch/hermes-4-70b` - Verification/alternative perspective

**Vision (Phase 3):**
- `qwen25-vl-72b-instruct` - Multimodal analysis
- `meta-llama/llama-3.2-90b-vision-instruct` - Powerful vision model

## Architecture

```
holocene/
├── src/holocene/
│   ├── cli/          # Click-based CLI
│   ├── core/         # Data models, sanitizer
│   ├── storage/      # SQLite database
│   ├── llm/          # LLM integration (TODO)
│   ├── config/       # Configuration management
│   └── integrations/ # External services (TODO)
├── tests/            # Test suite
└── scripts/          # Utility scripts
```

## Testing

```bash
# Run test suite
pytest tests/ -v

# All tests should pass:
# - Privacy sanitizer (8 tests)
# - Storage layer (6 tests)
```

## Design Philosophy

Inspired by:
- **journel** - ADHD-friendly project tracking
- **tsuredure** - Slow, contemplative AI companionship
- **wabisabi** - Embrace imperfection, ship iteratively

Core principles:
- **Privacy by design** - Sanitize first, store second
- **Human-in-the-loop** - Assist, don't automate
- **Observation, not judgment** - Patterns without shame
- **Constraint as feature** - Budget limits encourage thoughtful LLM use
- **Joy in the mundane** - Optional XKCD references for levity (because Randall Munroe gets it)

## Commands Reference

```bash
# Initialization
holo init                    # Create config and database

# Logging
holo log "description"       # Log activity
  --tags tag1,tag2          # Add tags
  --type coding             # Activity type
  --context personal        # Context
  --duration 45             # Duration in minutes

# Querying
holo status                  # Today's summary
holo show --today            # Detailed today view
holo show --yesterday        # Yesterday's activities
holo show --week             # This week
holo show --limit 20         # Limit results

# Analysis
holo analyze --today         # AI analysis of today
holo analyze --week          # Weekly patterns
holo analyze --cheap         # Use faster/cheaper model
holo analyze --no-journel    # Skip journel integration
holo analyze --xkcd          # Include relevant XKCD comic (fun!)

# Internet Archive
holo archive URL [URL2 ...]  # Archive URLs to prevent link rot
  --check-only              # Just check if archived
  --force                   # Re-archive even if exists

# Link Management
holo links list              # List all tracked links
  --archived/--unarchived   # Filter by archive status
  --source SOURCE           # Filter by source (activity, journel, bookmarks)
  --limit N                 # Limit results

holo links scan              # Scan activities and journel for links
  --today                   # Scan only today
  --week                    # Scan this week
  --all                     # Scan all activities
  --no-journel              # Skip journel scanning

holo links import-bookmarks  # Import browser bookmarks
  --browser auto|edge|chrome # Choose browser (default: auto)

holo links archive           # Archive tracked links to Internet Archive
  --limit N                 # Limit number to archive
  --force                   # Ignore exponential backoff, retry failed links
  --retry-failed            # Only retry failed links that are ready

# Activity types:
# coding, research, documentation, meeting, communication,
# learning, planning, break, other

# Contexts:
# work, personal, open_source, unknown
```

## Data Storage

```
~/.holocene/
└── holocene.db              # SQLite database

~/.config/holocene/
└── config.yml               # User configuration
```

## License

MIT

## Credits

Built with Claude Code and inspired by the need for ADHD-friendly tools that observe without judging.
