# Design Documentation Navigation

This directory contains Holocene's design documentation organized in **tiers** for efficient AI assistant context management and human navigation.

## Tier System

### **Tier 0: SUMMARY.md** - ALWAYS READ FIRST
**Context priority:** ⭐⭐⭐ CRITICAL - Load in every session
- High-level "What is Holocene?" overview
- Operating modes (autonomous + on-demand)
- Core architecture components
- Technology stack summary
- ~200-300 lines, optimized for context window efficiency

**When to read:** Every new Claude session, before reading anything else

---

### **Tier 1: Architecture (architecture/)** - READ WHEN NEEDED
**Context priority:** ⭐⭐ Important - Load based on task
- **operating_modes.md** - Autonomous vs on-demand modes, task scheduler
- **data_sources.md** - Browser, journel, git, Home Assistant, Mi Band, etc.
- **privacy_model.md** - 3-tier privacy, sanitization layer
- **llm_strategy.md** - Model routing (DeepSeek V3, Qwen Coder, etc.)
- **task_scheduler.md** - Long-running tasks, state persistence

**When to read:**
- Working on core system architecture
- Building daemon/background monitoring
- Implementing new data sources
- Modifying LLM integrations

---

### **Tier 2: Integrations & Features** - READ SELECTIVELY
**Context priority:** ⭐ Task-specific - Load only what you're working on

#### integrations/
- **thermal_printing.md** - Spinitex renderer + Paperang P1 protocol
- **research_mode.md** - Deep research overnight compilation
- **librarycat.md** - LibraryCat book collection integration
- **sensecap_watcher.md** - Manual vision capture integration
- **future_integrations.md** - Planned integrations (Wikipedia, Crossref, etc.)

#### features/
- **trading_cards.md** - Achievement card system concept
- *(more feature designs as needed)*

#### security/
- **injection_defense.md** - Prompt injection protection strategies
- **quarantine_system.md** - Web content quarantine and verification
- **automation_boundaries.md** - What can/cannot be automated

**When to read:**
- Only load the specific file you're working on
- Example: Working on thermal printing → Read integrations/thermal_printing.md
- Example: Adding Wikipedia → Read integrations/future_integrations.md

---

## For AI Assistants (Claude)

### Recommended Context Loading Strategy

**Every session:**
1. Read `design/SUMMARY.md` (Tier 0) - ~5-10k tokens
2. Read `CLAUDE.md` (project guide) - ~10-15k tokens
3. Read `docs/ROADMAP.md` (current priorities) - ~5-10k tokens

**Total base context:** ~20-35k tokens (leaves 165k+ for work)

**Task-specific additions:**
- Add Tier 1 architecture files as needed (~10-20k tokens each)
- Add specific Tier 2 files for the feature you're working on (~5-15k tokens each)

**Example Context Budget:**
```
Base (always):
- design/SUMMARY.md                    ~10k tokens
- CLAUDE.md                            ~15k tokens
- docs/ROADMAP.md                      ~10k tokens
Total: ~35k tokens

Working on thermal printing:
+ design/integrations/thermal_printing.md  ~10k tokens
Total: ~45k tokens (leaves 155k for code/conversation)

Working on daemon mode:
+ design/architecture/operating_modes.md   ~15k tokens
+ design/architecture/task_scheduler.md    ~10k tokens
Total: ~70k tokens (leaves 130k for code/conversation)
```

### Don't Load Everything!

**Anti-pattern:** Reading all of design/ at once → Context bloat, information loss

**Better:** Tier 0 + task-specific Tier 1/2 → Focused, efficient context use

---

## For Humans

**Quick orientation:**
1. Start with `SUMMARY.md` (5 min read)
2. Check `docs/ROADMAP.md` for current priorities
3. Dive into specific architecture/ or integrations/ files as needed

**Finding something specific:**
- Core system architecture → `architecture/`
- External integrations → `integrations/`
- Feature concepts → `features/`
- Security/safety → `security/`

---

## Directory Structure

```
design/
├── README.md                    # This file - navigation guide
├── SUMMARY.md                   # Tier 0 - High-level overview
│
├── architecture/                # Tier 1 - Core system architecture
│   ├── operating_modes.md
│   ├── data_sources.md
│   ├── privacy_model.md
│   ├── llm_strategy.md
│   └── task_scheduler.md
│
├── integrations/                # Tier 2 - External integrations
│   ├── thermal_printing.md
│   ├── research_mode.md
│   ├── librarycat.md
│   ├── sensecap_watcher.md
│   └── future_integrations.md
│
├── features/                    # Tier 2 - Feature concepts
│   └── trading_cards.md
│
└── security/                    # Tier 2 - Security architecture
    ├── injection_defense.md
    ├── quarantine_system.md
    └── automation_boundaries.md
```

---

## Migration Notes

This tiered structure was created 2025-11-17 to improve AI assistant context management after experiencing information loss across multiple context compactions. The original `holocene_design.md` (1,036 lines) was split into focused, modular documents.

**Original location of content:**
- holocene_design.md → Split into SUMMARY.md + architecture/ files
- docs/thermal_printer_architecture.md → integrations/thermal_printing.md
- docs/deep_research_mode.md → integrations/research_mode.md
- docs/*.md → integrations/ or features/ as appropriate

---

**Last Updated:** 2025-11-17
**Pattern:** wabisabi tiered documentation system
**Purpose:** Efficient AI context management + human navigation
