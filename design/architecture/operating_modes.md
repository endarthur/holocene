# Operating Modes Architecture

Holocene operates in two modes: **Autonomous** (background monitoring) and **On-Demand** (interactive assistant).

For complete details, see `holocene_design.md` lines 257-395.

---

## Mode 1: Autonomous (Background Monitoring)

**Status:** Planned (not yet implemented)

**What it does:**
- Continuous monitoring of data sources (browser, window, system, sensors)
- Auto-logging activities every 30-60 seconds
- Trigger-based IFTTT automation rules
- Periodic LLM check-ins (~30-50/day via DeepSeek V3)
- Automated daily/weekly summary generation

**Example Flow:**
```
Every 30 sec: Log current activity locally
Every 30 min: Send aggregated activity to DS V3 for categorization
Every 2 hours: Check if break reminder needed (via IFTTT rule)
End of day: Generate daily summary (saved to ~/holocene/summaries/)
Weekly: Comprehensive review for user + Claude analysis
```

**LLM Budget:** ~30-50 calls/day for autonomous operations (leaves ~1,950/day for on-demand)

---

## Mode 2: On-Demand (Interactive)

**Status:** ✅ Implemented

**What it does:**
- User-initiated explicit queries
- Multi-step agentic research tasks
- Activity analysis and pattern detection
- Knowledge management (books, papers, links)
- Thermal printing via Spinitex

**Example Commands:**
```bash
# Analysis
holo status                              # Today's summary
holo analyze --week                      # Weekly patterns
holo ask "what should I prioritize?"     # AI recommendations

# Knowledge Management
holo books search "topic"
holo papers search "topic"               # Planned (Crossref)
holo links list --unarchived

# Research
holo research start "topic"              # Deep research compilation
holo wikipedia search "topic"

# Thermal Printing
holo print research <research_id>        # Print via Spinitex
```

---

## Task Scheduler (Part of Autonomous Mode)

**Status:** Planned

**See:** `design/architecture/task_scheduler.md` for detailed implementation.

**Task Types:**
1. **One-Shot** - Single LLM call, immediate response
2. **Long-Running** - Multi-day execution with checkpoints (e.g., process 3000 links over 60 days)
3. **Background** - Low priority, scheduled execution

**Key Features:**
- State persistence and checkpoint/resume
- Priority queue management
- Daily budget limits
- Progress tracking

---

## Deployment Strategy

**Phase 1 (Current):** On-demand mode only, manual activity logging
**Phase 2 (Q1-Q2 2026):** Add background daemon with autonomous monitoring
**Phase 3 (Q2 2026+):** Local inference on M4 Mac Mini, no rate limits

---

## Implementation Notes

**Daemon Architecture:**
```python
class HoloceneScheduler:
    def __init__(self):
        self.active_task = None
        self.queue = PriorityQueue()
        self.background_tasks = []  # Max 2-3

    def step(self):
        # 1. Handle autonomous monitoring (quick)
        self.log_current_state()

        # 2. Check IFTTT triggers
        self.check_rules()

        # 3. Work on active task if exists
        if self.active_task:
            self.active_task.step()

        # 4. Background tasks (low priority)
        for bg_task in self.background_tasks:
            if bg_task.should_run():
                bg_task.step(budget=small)
```

**See `holocene_design.md` lines 349-372 for complete implementation.**

---

**Last Updated:** 2025-11-17
**Status:** On-Demand implemented ✅, Autonomous planned
