# Task Scheduler Architecture

**For complete details, see `holocene_design.md` lines 312-395.**

---

## Task Types

### 1. One-Shot Tasks
- Single LLM call
- Immediate response
- Example: "What did I work on yesterday?"

### 2. Long-Running Tasks
- Multi-day execution
- State persistence with checkpoints
- Resume capability
- Example: Processing 3000 Telegram links over 60 days

### 3. Background Tasks
- Low priority
- Scheduled execution
- Example: Daily link processing

---

## Implementation

```python
class Task:
    id: str
    type: Literal["one_shot", "long_running", "background"]
    state: dict  # Progress tracking
    schedule: Literal["daily", "on_demand", "background"]
    priority: int
    checkpoint: dict  # For resume
    created_at: datetime
    updated_at: datetime

class HoloceneScheduler:
    def __init__(self):
        self.active_task = None
        self.queue = PriorityQueue()
        self.background_tasks = []  # Max 2-3

    def step(self):
        # 1. Autonomous monitoring
        # 2. Check IFTTT triggers
        # 3. Work on active task
        # 4. Background tasks (low priority)
```

---

## Example: Long-Running Task

```python
task = LongRunningTask(
    name="process_telegram_links",
    input_file="~/telegram_links.txt",
    daily_budget=50,  # Process 50/day
    actions=[
        "check_link_validity",  # HEAD request
        "fetch_title",          # Via Bing Search API
        "summarize",           # DS V3 in read-only mode
        "verify_summary",      # Hermes 4 verification
        "categorize",          # Based on domain + title
    ],
    output_dir="~/holocene/quarantine/"
)

# State after Day 1:
# {processed: 50, remaining: 2950, last_index: 50}
# Estimated completion: 60 days
```

---

**Last Updated:** 2025-11-17
**Status:** Planned (not yet implemented)
