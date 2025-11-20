# balloc + dixie Architecture

**Date:** 2025-11-19
**Status:** Approved
**Context:** Architecture Review Session - Budget optimization

---

## Overview

**balloc** (BudgetAllocator) and **dixie** (autonomous research construct) work together to maximize value from prepaid LLM credits while maintaining safety boundaries.

**Gibson Reference:**
> "Dixie was a ROM construct, a personality recording."
> — *Neuromancer* (1984)

**Metaphor:** Dixie helps Case navigate cyberspace. Our dixie helps Holocene navigate knowledge space - finding connections, improving quality, filling gaps. Always helpful, always bounded, never goes rogue.

---

## Architecture

```
┌─────────────────────────────────────────┐
│         balloc (Budget Tracker)         │
│                                          │
│  Tracks:                                 │
│  - Daily usage (NanoGPT, finn, etc.)    │
│  - Budget pressure (waste risk)         │
│  - Service types (prepaid vs pay-per-use)│
│                                          │
│  Recommends:                             │
│  - "Allocate 500 prompts to dixie"      │
│  - "High pressure, urgency: moderate"   │
│  - "Approve $2 for Bright Data?"        │
└────────────┬────────────────────────────┘
             │ recommendations every 30 min
             ▼
┌─────────────────────────────────────────┐
│      holo core (Coordinator)            │
│                                          │
│  Receives recommendations                │
│  Checks user preferences                 │
│  Delegates to dixie or requires approval │
└────────────┬────────────────────────────┘
             │ approved allocations
             ▼
┌─────────────────────────────────────────┐
│    dixie (Autonomous Construct)         │
│                                          │
│  Task registry:                          │
│  - Cross-reference discovery            │
│  - Citation chain exploration           │
│  - Topic cluster analysis               │
│  - Quality improvements                 │
│  - Research suggestions                 │
│                                          │
│  Safety levels:                          │
│  - SAFE: Read-mostly, bounded           │
│  - MODERATE: Modifies metadata          │
│  - DANGEROUS: Never autonomous          │
└─────────────────────────────────────────┘
```

---

## Core Insight: Two Service Types

### Prepaid Credits (Maximize or Waste!)

**NanoGPT:**
```python
service = {
    'type': 'prepaid_credits',
    'strategy': 'maximize',
    'daily_limit': 2000,
    'monthly_cost': 8.00,
    'wasted_if_unused': True  # Key insight!
}

# Problem: Using only 500/2000 daily = 75% waste
# Solution: Find useful work for unused credits
```

**Budget Pressure:**
```python
# 11pm, used only 500/2000 prompts
wasted = 2000 - 500 = 1500
wasted_value = (1500 / 60000) * 8 = $0.20 today

# Over a month at this rate:
monthly_waste = (2000 - 500) * 30 = 45,000 prompts
monthly_wasted_value = (45000 / 60000) * 8 = $6.00

# Paying $8/month, using $2 worth!
# balloc recommends: "Allocate to dixie for knowledge improvement"
```

---

### Pay-Per-Use (Minimize, Require Approval)

**Bright Data:**
```python
service = {
    'type': 'pay_per_use',
    'strategy': 'minimize',
    'requires_approval': True,
    'cost_per_call': 0.01,  # Approximate
    'default_mode': 'slow_trickle'  # 1 req/5min
}

# Strategy: Gate, trickle, require explicit approval
```

**Approval Flow:**
```bash
# User wants to enrich ML favorites
holo mercadolivre enrich --all

# balloc calculation:
884 items × $0.01 = ~$8.84 cost

# Requires approval:
⚠ This will cost approximately $8.84 (Bright Data)

  Options:
  1. Approve full budget [$8.84]
  2. Approve partial budget [$2.00 for ~200 items]
  3. Use slow trickle [Free, 1 item/5min, ~3 days]
  4. Cancel

  Choice: _

# After approval:
✓ Budget approved: $2.00 for Bright Data
  Enriching 200 items...
  Remaining after: 684 items (queue for later or approve more)
```

---

## balloc (Budget Allocator)

**Responsibilities:**
- Track usage across all services
- Calculate budget pressure
- Recommend allocations
- **Does NOT execute** - only advises

**File:** `holocene/core/balloc/__init__.py`

```python
class BudgetAllocator:
    """
    Budget tracking and recommendation system.
    Tracks but does not execute.
    """

    def get_budget_status(self, service='nanogpt') -> BudgetStatus:
        """Current budget state"""
        used = self._get_usage_today(service)
        limit = self.config.services[service].daily_limit

        return BudgetStatus(
            service=service,
            used=used,
            limit=limit,
            remaining=limit - used,
            time_remaining_hours=self._hours_until_midnight(),
            pressure=self._calculate_pressure(used, limit)
        )

    def get_recommendation(self) -> BudgetRecommendation:
        """Recommend budget allocation"""
        status = self.get_budget_status('nanogpt')

        if status.pressure > 0.6:
            return BudgetRecommendation(
                action='allocate_to_dixie',
                service='nanogpt',
                amount=500,
                urgency='high',
                reasoning=f'High waste risk: {status.remaining} prompts unused, {status.time_remaining_hours}h left'
            )
        elif status.pressure > 0.3:
            return BudgetRecommendation(
                action='allocate_to_dixie',
                service='nanogpt',
                amount=200,
                urgency='moderate',
                reasoning='Moderate waste risk'
            )
        else:
            return BudgetRecommendation(
                action='hold',
                reasoning='Usage on track'
            )

    def request_approval(self, service: str, amount: float, purpose: str) -> bool:
        """
        Request approval for pay-per-use services.
        Shows cost, asks user.
        """
        if self.config.services[service].type == 'pay_per_use':
            # Show prompt to user
            response = self._prompt_user(
                f"Approve ${amount:.2f} for {purpose} ({service})?"
            )
            return response == 'approved'
        else:
            # Prepaid - no approval needed
            return True

    def allocate(self, service: str, amount: float, purpose: str):
        """Record budget allocation (tracking only)"""
        allocation = BudgetAllocation(
            service=service,
            amount=amount,
            purpose=purpose,
            timestamp=now()
        )
        self.db.record_allocation(allocation)
        return allocation

    def track_usage(self, service: str, amount: float, task: str):
        """Record actual usage"""
        self.db.execute("""
            INSERT INTO llm_usage (date, provider, model, prompt_count, task, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (today(), service, 'unknown', amount, task, now()))
```

---

## Budget Pressure Algorithm

```python
# holocene/core/balloc/pressure.py
class BudgetPressure:
    """Calculate waste risk based on usage vs time"""

    def calculate_pressure(self, used: int, limit: int, time_of_day: datetime) -> float:
        """
        Pressure = Likelihood of wasting credits

        0.0 = No waste risk (on track or over-used)
        1.0 = Maximum waste risk (underused, time running out)
        """

        hours_left = 24 - time_of_day.hour
        expected_usage = self._estimate_expected_usage(time_of_day.hour, limit)

        # How far behind expected usage?
        deficit = expected_usage - used

        # How much time left to use it?
        urgency = 1.0 - (hours_left / 24)

        # Pressure score
        if deficit <= 0:
            return 0.0  # On track or ahead

        pressure = (deficit / limit) * urgency
        return max(0, min(1, pressure))

    def _estimate_expected_usage(self, hour: int, daily_limit: int) -> int:
        """
        Estimate expected usage by this hour.
        Based on typical usage patterns.
        """
        # Usage curve (empirical)
        usage_curve = {
            0: 0.02,   # 2am: 2%
            6: 0.05,   # 6am: 5%
            9: 0.15,   # 9am: 15%
            12: 0.30,  # Noon: 30%
            15: 0.50,  # 3pm: 50%
            18: 0.70,  # 6pm: 70%
            21: 0.85,  # 9pm: 85%
            23: 0.95,  # 11pm: 95%
        }

        # Interpolate
        for h in sorted(usage_curve.keys()):
            if hour <= h:
                return int(usage_curve[h] * daily_limit)

        return int(0.95 * daily_limit)

# Thresholds (start permissive, tune based on usage)
PRESSURE_THRESHOLDS = {
    'low': 0.2,      # 20% waste risk → trigger dixie
    'moderate': 0.4, # 40% waste risk → more aggressive
    'high': 0.6,     # 60% waste risk → maximize usage
}
```

---

## dixie (Autonomous Research Construct)

**Responsibilities:**
- Execute autonomous tasks safely
- Respect budget allocations
- Report results
- **Never** goes beyond approved budget

**File:** `holocene/core/dixie/__init__.py`

```python
class Dixie:
    """
    Autonomous research construct.
    Executes safe knowledge improvement tasks.
    """

    def __init__(self, core, balloc):
        self.core = core
        self.balloc = balloc
        self.registry = TaskRegistry()
        self.enabled = self.core.config.dixie.enabled

    def process_recommendation(self, recommendation: BudgetRecommendation):
        """
        Receive recommendation from balloc.
        Decide whether to act based on user preferences.
        """
        if not self.enabled:
            logger.info("dixie disabled, ignoring recommendation")
            return

        if recommendation.action != 'allocate_to_dixie':
            return

        # Check user notification preference
        if self.config.dixie.notifications.style == 'ask_permission':
            approved = self._request_permission(recommendation)
            if not approved:
                logger.info("User declined dixie recommendation")
                return

        # Execute with allocated budget
        self.execute_with_budget(
            budget=recommendation.amount,
            urgency=recommendation.urgency
        )

    def execute_with_budget(self, budget: int, urgency: str):
        """Execute tasks within allocated budget"""

        # Select tasks based on budget and urgency
        tasks = self.registry.select_tasks(
            budget=budget,
            urgency=urgency,
            safety_level=self.config.dixie.allow_moderate ? 'moderate' : 'safe'
        )

        logger.info(f"dixie executing {len(tasks)} tasks with budget {budget}")

        # Execute tasks
        results = []
        used = 0

        for task in tasks:
            if used >= budget:
                logger.info(f"Budget exhausted ({used}/{budget}), stopping")
                break

            try:
                logger.info(f"dixie running: {task.name}")
                result = task.execute(self.core)

                used += result.prompts_used
                results.append(result)

                # Track usage with balloc
                self.balloc.track_usage('nanogpt', result.prompts_used, task.name)

            except Exception as e:
                logger.error(f"dixie task failed: {task.name} - {e}")

        # Notify completion
        self._notify_completion(results, used, budget)

        return results

    def _notify_completion(self, results, used, budget):
        """Notify user of completion"""
        style = self.config.dixie.notifications.style

        if style == 'proactive':
            # Immediate notification
            self._send_notification(f"""
                dixie completed {len(results)} tasks
                Budget: {used}/{budget} prompts used

                Results:
                {self._format_results(results)}
            """)
        elif style == 'passive':
            # Store for next status check
            self.db.store_notification('dixie_completion', {
                'tasks': len(results),
                'budget_used': used,
                'results': results
            })
        # ask_permission already notified before execution
```

---

## dixie Task Safety Levels

### SAFE (Default, Always Allowed)

**Characteristics:**
- Read-mostly operations
- Creates new data (links, suggestions)
- **No deletions**
- **No modifications to existing user data**
- Bounded execution

**Examples:**

```python
class CrossReferenceDiscovery(DixieTask):
    """Find papers cited in books, create citations table entries"""
    safety_level = 'safe'

    # ✅ Reads books.metadata.references
    # ✅ Reads papers.doi
    # ✅ Creates book_paper_citations (new links)
    # ❌ Does NOT modify books or papers
    # ❌ Does NOT delete anything

class TopicClusterAnalysis(DixieTask):
    """Analyze collection, create cluster report"""
    safety_level = 'safe'

    # ✅ Reads all books/papers
    # ✅ Creates analysis report
    # ❌ Does NOT modify collection
```

---

### MODERATE (Opt-in, Modifies Metadata)

**Characteristics:**
- Modifies existing metadata
- Makes quality judgments
- Could theoretically degrade quality
- Still no deletions

**Examples:**

```python
class DeweyVerification(DixieTask):
    """Update Dewey classifications with high confidence"""
    safety_level = 'moderate'

    # ⚠️ Updates books.dewey_decimal (metadata modification)
    # ⚠️ Only if confidence > 0.95 (high threshold)
    # ✅ Flags low-confidence for human review
    # ❌ Does NOT delete

class SummaryEnhancement(DixieTask):
    """Replace old summaries with better ones"""
    safety_level = 'moderate'

    # ⚠️ Replaces metadata.enrichment.summary
    # ⚠️ Could theoretically be worse (subjective)
    # ✅ Keeps old version in metadata.previous_summary
```

**Configuration:**
```yaml
dixie:
  allow_safe: true      # Default: yes
  allow_moderate: false # Default: no (requires opt-in)
```

---

### DANGEROUS (Never Autonomous)

**Characteristics:**
- Irreversible actions
- Costs money
- External communication
- Deletions

**Examples (NEVER run autonomously):**

```python
# ❌ NEVER
class AutomaticDeletion(DixieTask):
    safety_level = 'dangerous'  # Never allowed

class AutomaticPurchase(DixieTask):
    safety_level = 'dangerous'  # Never allowed

class ExternalEmail(DixieTask):
    safety_level = 'dangerous'  # Never allowed

# These require explicit user command:
# holo books delete 123
# holo books purchase <isbn>
# NOT autonomous!
```

---

## Autonomous Task Examples

### Task 1: Cross-Reference Discovery

```python
# holocene/core/dixie/tasks/cross_reference.py
class CrossReferenceDiscovery(DixieTask):
    """Find connections between books and papers"""

    def get_metadata(self):
        return {
            'name': 'cross_reference_discovery',
            'description': 'Find papers cited in books, create citation links',
            'safety_level': 'safe',
            'estimated_prompts': 5,
            'max_runs_per_day': 2,
        }

    def should_run(self, context) -> bool:
        """Check if there's work to do"""
        unlinked = context.db.execute("""
            SELECT COUNT(*) FROM books
            WHERE json_extract(metadata, '$.references') IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM book_paper_citations WHERE book_id = books.id
              )
        """).fetchone()[0]

        return unlinked > 10

    def execute(self, core) -> TaskResult:
        """Execute task"""
        # Get books with unlinked references
        books = core.db.execute("""
            SELECT id, title, json_extract(metadata, '$.references') as refs
            FROM books
            WHERE json_extract(metadata, '$.references') IS NOT NULL
            LIMIT 20
        """).fetchall()

        # Batch prompt to Laney-chan
        prompt = f"""
        Parse references from these books and match to DOIs:

        {json.dumps([{'id': b.id, 'title': b.title, 'refs': b.refs} for b in books])}

        Return JSON array:
        [
          {{
            "book_id": 1,
            "doi": "10.1234/abc",
            "confidence": 0.95
          }}
        ]
        """

        result = core.llm.complete(prompt, task_type='enrichment')
        matches = json.loads(result)

        # Create citations (high confidence only)
        created = 0
        for match in matches:
            if match['confidence'] > 0.85:
                core.db.execute("""
                    INSERT INTO book_paper_citations (book_id, paper_id, citation_type)
                    SELECT ?, papers.id, 'references'
                    FROM papers
                    WHERE papers.doi = ?
                """, (match['book_id'], match['doi']))
                created += 1

        core.db.commit()

        return TaskResult(
            task='cross_reference_discovery',
            prompts_used=1,
            items_processed=len(books),
            items_created=created,
            message=f"Found {created} new cross-references"
        )
```

---

### Task 2: Citation Chain Exploration

```python
class CitationChainExploration(DixieTask):
    """Follow citation chains to find foundational works"""

    def execute(self, core):
        # Get papers with many citations
        papers = core.db.execute("""
            SELECT id, doi, title, json_extract(metadata, '$.references') as refs
            FROM papers
            WHERE json_array_length(json_extract(metadata, '$.references')) > 10
            LIMIT 5
        """).fetchall()

        prompt = f"""
        For each paper, identify the 3 most foundational/seminal references
        that would be valuable to acquire.

        Papers:
        {format_papers(papers)}

        Return JSON: [{{"paper_id": 1, "foundational_doi": "...", "importance": 0.95, "reason": "..."}}]
        """

        suggestions = core.llm.complete(prompt)

        # Store as acquisition suggestions
        for suggestion in suggestions:
            core.db.execute("""
                INSERT INTO acquisition_suggestions (item_type, identifier, reason, importance, source)
                VALUES ('paper', ?, ?, ?, 'dixie_citation_chain')
            """, (suggestion['foundational_doi'], suggestion['reason'], suggestion['importance']))

        return TaskResult(
            task='citation_chain_exploration',
            prompts_used=1,
            suggestions_created=len(suggestions)
        )
```

---

### Task 3: Topic Cluster Analysis

```python
class TopicClusterAnalysis(DixieTask):
    """Analyze collection for topic clusters and gaps"""

    def execute(self, core):
        # Get collection overview
        books = core.db.get_all_books(fields=['title', 'author', 'dewey', 'tags'])
        papers = core.db.get_all_papers(fields=['title', 'abstract', 'topics'])

        prompt = f"""
        Analyze this knowledge collection:

        Books ({len(books)}):
        {format_summary(books)}

        Papers ({len(papers)}):
        {format_summary(papers)}

        Identify:
        1. Major topic clusters (well-covered areas)
        2. Gaps (related topics missing)
        3. Connections between clusters
        4. Acquisition priorities to fill gaps

        Return structured JSON analysis.
        """

        analysis = core.llm.complete(prompt)

        # Store analysis
        core.db.execute("""
            INSERT INTO dixie_analyses (analysis_type, content, created_at)
            VALUES ('topic_clusters', ?, ?)
        """, (analysis, now()))

        return TaskResult(
            task='topic_cluster_analysis',
            prompts_used=1,
            analysis_stored=True
        )
```

---

## CLI Integration

### User Commands

```bash
# Check dixie status
holo dixie status

# Dixie (Autonomous Research Construct)
# Status: Active
# Tasks completed today: 3
# Budget used: 87/500 prompts (17%)
#
# Recent tasks:
#   ✓ cross_reference_discovery: 42 new links
#   ✓ citation_chain_exploration: 8 suggestions
#   ✓ topic_cluster_analysis: 5 clusters, 3 gaps
#
# Next run: In 23 minutes (when balloc checks budget)

# View suggestions from dixie
holo dixie suggestions

# Acquisition suggestions (from dixie):
# 1. Paper: DOI:10.1234/abc
#    "Foundational neural networks paper"
#    Importance: 0.95 (cited 50x in collection)
#
# 2. Book: "Pattern Recognition" by William Gibson
#    "Fills gap in Blue Ant trilogy coverage"
#    Relevance: 0.88
#
# Review: holo dixie approve 1  or  holo dixie reject 2

# Manual task execution
holo dixie run cross-reference-discovery
# Running cross-reference-discovery...
# ✓ Found 42 new connections (used 5 prompts)

# Stop autonomous operations
holo dixie stop
# Stopping dixie autonomous operations
# (Manual tasks still available)

# Enable/configure
holo dixie enable
holo dixie config allow-moderate  # Allow moderate safety tasks
```

---

### Budget Status Commands

```bash
# Check budget
holo balloc status

# Budget Status (NanoGPT)
# Today: 342 / 2000 prompts (17%)
# Remaining: 1658 prompts
# Time left: 8 hours
# Pressure: 0.45 (moderate)
#
# Recommendation: Allocate 300 prompts to dixie
#
# dixie status:
#   Queued tasks: 2
#   Available budget: 500 prompts/day
#   Used today: 87 prompts

# Usage history
holo balloc history --days 7

# Week of 2025-11-12:
# Mon: 1247/2000 (62%) - No waste risk
# Tue: 1893/2000 (95%) - Nearly full utilization ✓
# Wed: 891/2000 (45%) - Moderate pressure, dixie ran 3 tasks
# Thu: 450/2000 (23%) - High pressure, dixie ran 5 tasks
# Fri: 1654/2000 (83%) - Good utilization ✓
# Sat: 234/2000 (12%) - High waste, dixie ran 8 tasks
# Sun: 567/2000 (28%) - Moderate, dixie ran 4 tasks
#
# Average utilization: 52%
# dixie contribution: 287 prompts (24% of total usage)
# Estimated savings: $3.84/month (48% waste reduction)
```

---

## Notification Styles

### Proactive (style: 'proactive')

```bash
# 10pm on eunice (Telegram)
🤖 Holocene balloc: Budget pressure moderate (1200/2000 unused)

   dixie will run these tasks:
   - Cross-reference discovery (~5 prompts)
   - Citation chain exploration (~8 prompts)

   Stop with: holo dixie stop
```

---

### Passive (style: 'passive')

```bash
# Next morning on wmut
holo status

Last night (dixie):
  ✓ Cross-reference discovery: 42 new links
  ✓ Citation chain exploration: 8 acquisition suggestions
  ✓ Topic cluster analysis: 5 clusters identified, 3 gaps

  Budget used: 87 prompts

  📋 12 suggestions ready for review: holo dixie suggestions
```

---

### Ask Permission (style: 'ask_permission')

```bash
# 10pm on eunice (Telegram)
🤖 Holocene balloc: Budget pressure moderate (1200/2000 unused)

   dixie recommends these tasks:
   1. Cross-reference discovery (~5 prompts)
   2. Citation chain exploration (~8 prompts)
   3. Topic cluster analysis (~15 prompts)

   Run these? Reply:
   - 'yes' or 'holo dixie start' to approve
   - 'no' or 'holo dixie stop' to decline
```

---

## Configuration

```yaml
# ~/.config/holocene/config.yml

balloc:
  # Check frequency
  check_interval_minutes: 30

  # Pressure thresholds (tune based on usage)
  pressure:
    low: 0.2      # 20% waste risk → trigger dixie
    moderate: 0.4 # 40% waste risk → more tasks
    high: 0.6     # 60% waste risk → maximize

  # Service definitions
  services:
    nanogpt:
      type: 'prepaid_credits'
      strategy: 'maximize'
      daily_limit: 2000
      monthly_cost: 8.00
      wasted_if_unused: true

    brightdata:
      type: 'pay_per_use'
      strategy: 'minimize'
      requires_approval: true
      cost_per_call: 0.01
      default_mode: 'slow_trickle'

dixie:
  # Enable/disable
  enabled: true

  # Safety levels
  allow_safe: true          # Cross-refs, analysis (default: yes)
  allow_moderate: false     # Metadata modifications (default: no)

  # Budget constraints
  max_autonomous_prompts_per_day: 500  # Cap dixie usage
  min_pressure_threshold: 0.2          # Don't run below this

  # Notifications
  notifications:
    style: 'passive'  # proactive, passive, ask_permission
    channels:
      - 'cli'
      - 'telegram'
    events:
      budget_pressure: true
      task_completed: true
      suggestions_ready: true

  # Task configuration
  tasks:
    cross_reference_discovery:
      enabled: true
      max_runs_per_day: 2

    citation_chain_exploration:
      enabled: true
      max_runs_per_day: 1

    topic_cluster_analysis:
      enabled: true
      max_runs_per_day: 1
```

---

## Database Schema

```sql
-- Budget tracking
CREATE TABLE llm_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    provider TEXT NOT NULL,  -- 'nanogpt', 'finn', 'brightdata'
    model TEXT,
    prompt_count INTEGER DEFAULT 0,
    token_count INTEGER DEFAULT 0,
    cost REAL DEFAULT 0.0,
    task TEXT,  -- What used it
    created_at TEXT NOT NULL
);

CREATE INDEX idx_usage_date ON llm_usage(date, provider);

-- Budget allocations
CREATE TABLE budget_allocations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service TEXT NOT NULL,
    amount REAL NOT NULL,
    purpose TEXT NOT NULL,
    allocated_at TEXT NOT NULL
);

-- dixie task executions
CREATE TABLE dixie_executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_name TEXT NOT NULL,
    prompts_used INTEGER,
    items_processed INTEGER,
    items_created INTEGER,
    result TEXT,  -- JSON
    executed_at TEXT NOT NULL
);

-- dixie suggestions (for human review)
CREATE TABLE acquisition_suggestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_type TEXT NOT NULL,  -- 'book', 'paper', 'link'
    identifier TEXT NOT NULL,  -- DOI, ISBN, URL
    reason TEXT,
    importance REAL,  -- 0-1
    source TEXT,  -- Which task generated this
    status TEXT DEFAULT 'pending',  -- pending, approved, rejected
    created_at TEXT NOT NULL
);

-- dixie analyses
CREATE TABLE dixie_analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_type TEXT NOT NULL,
    content TEXT NOT NULL,  -- JSON
    created_at TEXT NOT NULL
);
```

---

## Implementation Phases

### Phase 1: balloc Basics (Week 1)
- Usage tracking table
- Budget status calculation
- Pressure algorithm
- Basic recommendations

### Phase 2: dixie Foundation (Week 2)
- Task registry
- Safety level enforcement
- Basic task execution
- Result reporting

### Phase 3: Core Tasks (Week 3)
- Cross-reference discovery
- Citation chain exploration
- Topic cluster analysis
- Dewey verification

### Phase 4: Integration (Week 4)
- 30-minute scheduler on rei
- Notification system
- CLI commands
- Configuration

### Phase 5: Advanced Tasks (Month 2)
- More sophisticated tasks
- Task prioritization
- Adaptive batching
- Efficiency metrics

---

## Safety Boundaries

**dixie CANNOT:**
- ❌ Delete any items
- ❌ Spend money (Bright Data, purchases)
- ❌ Send external communications
- ❌ Modify core schema
- ❌ Exceed allocated budget
- ❌ Run DANGEROUS tasks

**dixie CAN:**
- ✅ Read collection
- ✅ Create new links/suggestions
- ✅ Update metadata (if allow_moderate)
- ✅ Analyze and report
- ✅ Make suggestions for human review

**User Always in Control:**
- Stop anytime: `holo dixie stop`
- Review before approval (ask_permission mode)
- Cap budget: `max_autonomous_prompts_per_day`
- Disable entirely: `dixie.enabled: false`

---

## Related Documents

- `design/architecture/holocene_architecture.md` - Overall architecture
- `design/architecture/database_schema.md` - Database patterns
- `docs/infrastructure_naming.md` - Gibson naming schema

---

**Last Updated:** 2025-11-19
**Status:** Approved in Architecture Review Session
**Gibson Quote:** *"Dixie was a ROM construct, a personality recording."* — Neuromancer

---

## Appendix: More Task Ideas

See session transcript for 34+ autonomous task ideas across categories:
- Knowledge graph enhancement
- Research intelligence
- Collection curation
- Metadata enrichment
- Personal intelligence
- Proactive assistance
- System maintenance
- Creative synthesis
