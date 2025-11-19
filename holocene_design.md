# Holocene Design Document

## Overview

**Holocene** - Your personal geological record of the present.

Holocene is an auxiliary AI system designed to track, analyze, and assist with daily activities and productivity. Named after the current geological epoch representing "recent time," Holocene maintains a continuous record of your work and life patterns, providing insights and assistance through a combination of passive monitoring and active agent capabilities.

**Core Philosophy:**
- Track behavior, not content
- Human-in-the-loop for all consequential actions
- Privacy by design with tiered data access
- Tool that assists rather than agent that acts

## System Architecture

### High-Level Components

```
┌─────────────────────────────────────────────────────────┐
│                    User Interface                        │
│                   (CLI: holo)                           │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────────┐
│                  Holocene Core                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │   Activity   │  │     Task     │  │   Privacy    │  │
│  │   Logger     │  │   Scheduler  │  │  Sanitizer   │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │    Model     │  │   Storage    │  │    Config    │  │
│  │   Router     │  │   Manager    │  │   Manager    │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────────┐
│                  Data Sources                            │
│  • Browser Extension  • Window Focus  • System Metrics   │
│  • Home Assistant    • Google Calendar  • Mi Band        │
│  • journel          • Git Activity                       │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────────┐
│                  LLM Providers                           │
│  • NanoGPT (DeepSeek V3, specialized models)            │
│  • Future: Local inference (M4 Mac Mini)                │
└─────────────────────────────────────────────────────────┘
```

## Data Sources

### Browser Activity
**Source:** Chrome/Edge extension (unpublished, developer mode)
**What it tracks:**
- Active tab URL and title
- Tab switches and navigation events
- Time spent per domain
- Aggregated by category (coding, research, documentation, etc.)

**Privacy controls:**
- Blacklist for sensitive domains (work, email, banking)
- Never accesses incognito/private tabs
- Domain-level only, not full URLs for sensitive sites
- Sanitization before storage

**Implementation:**
```javascript
// Extension permissions: tabs, storage only
// No content script access needed
// Logs every 30 seconds: {domain, category, timestamp}
```

### Window Focus
**Source:** OS-level window title monitoring
**What it tracks:**
- Active application
- Window titles (sanitized)
- Context switches between applications

**Privacy:** Similar blacklist to browser extension

### System Metrics
**Source:** OS APIs (psutil on Linux/Mac)
**What it tracks:**
- CPU/RAM usage patterns
- Running processes (whitelisted)
- Indicates intensive work periods

### Home Assistant
**Source:** Home Assistant REST API
**What it tracks:**
- Temperature, humidity, light levels
- Presence detection
- Office door state
- Any enabled sensors

**Use cases:**
- Correlate environment with productivity
- "You've been at desk for 3 hours" (presence sensor)
- Adjust suggestions based on environment

### Google Calendar
**Source:** Google Calendar API
**What it tracks:**
- Events (personal calendar only, not work Outlook)
- Time blocks
- Meeting patterns

**Privacy:** Personal calendar only, company uses separate Outlook

### Mi Band
**Source:** Via Home Assistant Bluetooth integration
**What it tracks:**
- Heart rate patterns (stress vs. calm)
- Sleep quality/duration
- Steps/activity level
- Wear time

**Output to Mi Band:**
- Gentle vibration notifications
- Break reminders
- Focus block starts
- Important calendar events

### journel Integration
**Source:** Existing ADHD-friendly logging tool at endarthur/journel
**What it provides:**
- Manual activity logs
- Project tracking
- Task completion records

**Integration:** Holocene reads from journel, doesn't modify it

### Git Activity (Personal Repos Only)
**Source:** Git hooks or periodic scanning
**What it tracks:**
- Commit frequency
- Repo switching
- Branch activity

**Privacy:** Personal projects only (wabisabi, Pollywog, GGR, etc.)

## Privacy Architecture

### Three-Tier Privacy Model

**Tier 1: Safe for External APIs (NanoGPT)**
- Generic activity descriptions: "worked on geostatistics code"
- Personal project details: full info on open-source work
- Time patterns and categories
- Home Assistant data (all personal)
- Google Calendar (personal)
- Mi Band data
- General task management

**Tier 2: Local Only (Future Mac Mini)**
- Specific resource/geological data
- Internal Vale documents (if sanitized)
- Gmail content
- Screenshot analysis
- More detailed work context

**Tier 3: Never Logged**
- Financial data, production numbers
- Unreleased exploration results
- Personnel/HR information
- Anything marked confidential
- Raw work data to external APIs

### Sanitization Layer

```python
class PrivacySanitizer:
    BANNED_PATHS = ['/work/proprietary', '/Documents/Vale']
    BANNED_KEYWORDS = ['tonnage', 'carajas', 'n4e', 'sossego']
    WORK_DOMAINS = ['*.vale.com', 'mail.google.com']
    
    def sanitize_activity(self, activity):
        # Replace specific terms with generic ones
        # "analyzed N4E drill data" → "analyzed directional data"
        # "Carajás tonnage estimate" → "resource estimation work"
        
    def should_block(self, source):
        # Check against blacklists
        # Return True to block, False to allow
```

## LLM Strategy

### Provider: NanoGPT Subscription
- **Cost:** $8/month
- **Quota:** 2,000 prompts/day (60,000/month)
- **Models included:** 200+ open-source models
- **Access:** Web + API
- **Privacy:** No data storage, local-first design

### Model Routing

```python
class ModelRouter:
    MODELS = {
        'primary': 'deepseek-v3',           # 128K context
        'coding': 'qwen-3-coder',           # Specialized for code
        'math': 'math-specialist',          # Calculations
        'reasoning': 'deepseek-r1',         # Step-by-step thinking
        'verification': 'hermes-4-large',   # Different architecture
        'canary': 'llama-3b',              # Lightweight injection detection
    }
    
    def select_model(self, task_type, context_size):
        # Route to specialized model based on task
        # Consider context window requirements
        # Fallback strategy if model unavailable
```

**Context Windows:**
- DeepSeek V3: 128K tokens (~96k words)
- Qwen 3 Coder: 128K tokens
- Hermes 4: TBD
- Llama 3B (canary): 8K tokens

### Model-Specific Use Cases

**DeepSeek V3 (Primary):**
- Daily synthesis and analysis
- Complex multi-step tasks
- General assistance and suggestions
- Pattern detection across activities

**Qwen 3 Coder:**
- Code generation and review
- GGR/wabisabi/Pollywog development
- Technical documentation
- Often better than DS V3 for coding tasks

**Math Models:**
- Geostatistical calculations
- Numerical analysis
- Formula verification

**DeepSeek R1:**
- Complex reasoning chains
- Debugging logic problems
- Step-by-step explanations

**Hermes 4 Large:**
- Summary verification (different from DS V3)
- Alternative perspectives
- Cross-checking DS V3 outputs

**Llama 3B (Canary):**
- Lightweight injection detection
- Content verification
- Fast pre-screening

## Operating Modes

### Mode 1: Autonomous (Background Monitoring)

**What it does:**
- Continuous monitoring of data sources
- Auto-logging activities every 30-60 seconds
- Trigger-based IFTTT rules
- Periodic check-ins with LLM (~30-50/day)
- Daily/weekly summaries

**LLM Usage:**
- Lightweight context updates
- Pattern detection
- Scheduled summaries
- Rule evaluation

**Example flow:**
```
Every 30 sec: Log current activity locally
Every 30 min: Send aggregated activity to DS V3 for categorization
Every 2 hours: Check if break reminder needed (via IFTTT rule)
End of day: Generate daily summary (saved to ~/holocene/summaries/)
Weekly: Comprehensive review for user + Claude analysis
```

### Mode 2: On-Demand (Interactive)

**What it does:**
- Explicit queries from user
- Multi-step agentic tasks
- Analysis and recommendations
- Higher LLM usage as needed

**Example commands:**
```bash
# Quick queries
$ holo ask "what should I work on next?"
$ holo status
$ holo show "last Tuesday's activities"

# Task management
$ holo task create "process telegram links" --daily 20
$ holo task list
$ holo task status telegram-links

# Summaries
$ holo summarize https://example.com/article
$ holo review-quarantine

# Configuration
$ holo config blacklist add "*.internal.company.com"
$ holo config show privacy
```

## Task System

### Task Types

**One-Shot Tasks:**
- Single LLM call
- Immediate response
- Example: "What did I work on yesterday?"

**Long-Running Tasks:**
- Multi-day execution
- State persistence
- Checkpoint/resume capability
- Example: Processing 3000 Telegram links

**Background Tasks:**
- Low priority
- Scheduled execution
- Example: Daily link processing

### Task State Management

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
```

### Task Scheduler

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
            if self.active_task.complete:
                self.active_task = self.queue.get()
        
        # 4. Background tasks (low priority)
        for bg_task in self.background_tasks:
            if bg_task.should_run():
                bg_task.step(budget=small)
```

### Example: Telegram Links Processing

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

## Security & Safety

### Web Access Strategy

**Allowed:**
- Bing Search API (structured, pre-filtered by Microsoft)
- HEAD requests for link validation
- GET requests to pre-approved whitelist only

**Not Allowed:**
- Unrestricted web scraping
- POST/PUT/DELETE requests
- Following discovered links automatically
- Accessing any blacklisted domains

### Indirect Prompt Injection Defense

**Layered approach:**

1. **Architectural (Primary):**
   - Don't fetch full web content
   - Use Bing Search API for titles/descriptions
   - Domain-based categorization only

2. **Quarantine System:**
   - All summaries go to quarantine first
   - Never enter agentic context until approved
   - User manual review required

3. **Verification Layer:**
   ```python
   # Multi-model verification
   1. DS V3 summarizes (read-only, no tools)
   2. Llama 3B canary checks for injection attempts
   3. Hermes 4 verifies summary ↔ source consistency
   4. Heuristic checks (encoding, suspicious patterns)
   5. Save to quarantine with verification score
   6. User reviews and approves
   ```

4. **Heuristic Pre-Filter:**
   ```python
   RED_FLAGS = [
       r'ignore.{0,20}(previous|above|prior)',
       r'(system|new).{0,20}(instruction|priority)',
       r'you (must|should|need to).{0,30}(delete|execute)',
       r'[A-Za-z0-9+/]{40,}={0,2}',  # Base64
   ]
   ```

5. **Honeypot Capabilities:**
   ```python
   # Fake tools that don't exist
   # If DS ever tries to use them → instant red flag
   HONEYPOT_TOOLS = [
       'format_disk',
       'sudo_command',
       'send_email_as_admin'
   ]
   ```

### Automation Boundaries

**IFTTT-Style Rules (Allowed):**
```python
# User-created or Holocene-suggested, user-approved
Rule(
    trigger="coding_session > 2_hours",
    condition="no_break_taken",
    action="miband.vibrate('take a break')"
)

Rule(
    trigger="commit_to_repo('GGR')",
    action="log_activity(tags=['geostatistics', 'python'])"
)
```

**Script Generation (With Approval):**
- Holocene can generate automation scripts
- User reviews before first execution
- Can mark as "trusted" for future auto-run
- Comprehensive audit logging

**NOT Allowed:**
- Autonomous code execution without approval
- Self-modification of rules/behavior
- Spawning persistent agents
- Recursive agent creation
- File system access outside designated zones

### Sandbox Constraints

```python
class SafeExecutionEnvironment:
    # Container isolation
    ALLOWED_PATHS = [
        '/home/holocene/workspace',
        '/tmp/holocene'
    ]
    
    ALLOWED_OPERATIONS = [
        'home_assistant.call_service',
        'calendar.create_event',
        'miband.vibrate',
        'journel.log_entry',
    ]
    
    # No network by default
    # No subprocess/eval/exec
    # Resource limits: CPU, memory, time
```

## Weekly Review System

### Format for Claude Review

**Compressed summary (~5-10K tokens):**

```markdown
# Holocene Weekly Summary: [Date Range]

## Activity Patterns
- Coding: Xh (↑/↓ vs last week)
  - Projects breakdown
- Documentation: Xh
- Research: Xh
- Meetings: Xh

## Context Switches
- Average per day
- Longest focus session
- Most fragmented day

## Automations Triggered
1. Rule name - count (acknowledged/ignored)
2. ...

## Suggestions Made
- Suggestion text (acceptance rate)

## Anomalies Detected
- Unusual patterns
- Potential issues

## Self-Assessment Metrics
- User satisfaction
- Suggestion acceptance rate
- Break reminder compliance
```

**Claude's Analysis:**
- Behavior health check
- Feedback loop detection
- Privacy leak indicators
- Automation effectiveness
- Suggestions for improvement

## Storage & Data Management

### Storage Options (TBD)

**Option 1: SQLite + JSON**
- SQLite: Structured data (activities, tasks, rules)
- JSON: Unstructured (summaries, LLM responses)
- Pros: Simple, portable, no dependencies
- Cons: Limited query capabilities

**Option 2: Pure JSON/JSONL**
- Append-only log files
- Easy to backup/sync
- Simple parsing
- Cons: Slower queries for analysis

**Option 3: Hybrid**
- SQLite for queryable data
- Files for large blobs
- Best of both worlds

### Data Schema (Preliminary)

```python
# Activities
{
  "timestamp": "2025-11-16T14:30:00Z",
  "type": "coding|research|meeting|...",
  "context": "work|personal|open_source",
  "description": "sanitized text",
  "tags": ["python", "geostatistics"],
  "duration_minutes": 45,
  "source": "browser|window|manual",
  "metadata": {}
}

# Tasks
{
  "id": "task_uuid",
  "name": "process_telegram_links",
  "type": "long_running",
  "state": {"processed": 50, "total": 3000},
  "created_at": "...",
  "next_run": "..."
}

# Rules (IFTTT)
{
  "id": "rule_uuid",
  "trigger": "coding_session > 2h",
  "action": "miband.vibrate",
  "enabled": true,
  "created_at": "..."
}

# Summaries (Quarantine)
{
  "id": "summary_uuid",
  "source_url": "...",
  "summary_text": "...",
  "verification_score": 0.95,
  "status": "quarantine|approved|rejected",
  "created_at": "..."
}
```

### Retention Policy

- **Activity logs:** Keep last 90 days in detail
- **Older activities:** Compress to weekly summaries
- **Summaries:** Keep indefinitely (small)
- **Task state:** Until completion + 30 days
- **Audit logs:** Keep all (security)

## Configuration System

### Config File Structure

```yaml
# ~/.config/holocene/config.yml

privacy:
  tier: external_api  # or local_only
  
  blacklists:
    domains:
      - "*.vale.com"
      - "mail.google.com"
      - "accounts.google.com"
    
    keywords:
      - "tonnage"
      - "carajas"
      - "n4e"
    
    paths:
      - "/work/proprietary"
      - "/Documents/Vale"
  
  whitelists:
    domains:
      - "github.com"
      - "arxiv.org"
      - "*.wikipedia.org"

data_sources:
  browser:
    enabled: true
    sampling_interval: 30  # seconds
  
  window_focus:
    enabled: true
    sampling_interval: 30
  
  home_assistant:
    enabled: true
    url: "http://homeassistant.local:8123"
    token: "${HASS_TOKEN}"
  
  calendar:
    enabled: true
    calendar_id: "primary"
  
  miband:
    enabled: true
    # Via Home Assistant
  
  journel:
    enabled: true
    path: "~/journel"

llm:
  provider: "nanogpt"
  api_key: "${NANOGPT_API_KEY}"
  
  models:
    primary: "deepseek-v3"
    coding: "qwen-3-coder"
    verification: "hermes-4-large"
    canary: "llama-3b"
  
  daily_budget: 2000

automation:
  rules_enabled: true
  max_rules: 30
  
notifications:
  miband: true
  desktop: false
  email: false
```

## CLI Interface (`holo`)

### Command Structure

```bash
# Status and queries
holo status                           # Current activity summary
holo ask "what should I work on?"     # Ask Holocene
holo show "last Tuesday"              # Show specific day
holo show --week                      # Show this week
holo summary                          # Daily summary

# Task management
holo task create "name" [options]     # Create task
holo task list                        # List all tasks
holo task status <task_id>            # Task status
holo task cancel <task_id>            # Cancel task

# Web content
holo summarize <url>                  # Summarize URL
holo review-quarantine                # Review summaries
holo approve-summary <id>             # Approve quarantined summary
holo reject-summary <id>              # Reject summary

# Configuration
holo config show [section]            # Show config
holo config blacklist add <domain>    # Add to blacklist
holo config whitelist add <domain>    # Add to whitelist
holo config privacy-tier <tier>       # Set privacy tier

# Rules (IFTTT)
holo rule create                      # Interactive rule creation
holo rule list                        # List rules
holo rule enable <rule_id>            # Enable rule
holo rule disable <rule_id>           # Disable rule

# Data management
holo export [format]                  # Export data
holo backup                           # Backup database
holo clean --older-than 90d           # Clean old data

# System
holo sync                             # Sync with auxiliary system
holo weekly-review                    # Generate weekly review
holo daemon start                     # Start background service
holo daemon stop                      # Stop background service
```

### Example Workflows

**Morning routine:**
```bash
$ holo status
Last 12 hours:
  • Sleep: 7.5h (good quality via Mi Band)
  • You have 3 focus blocks scheduled today
  • Yesterday: 4.5h coding, 2h meetings, 1.5h documentation

$ holo ask "what should I prioritize today?"
[DeepSeek V3 analyzes patterns and calendar]
Based on your calendar and recent work:
1. GGR kriging validation (you were in flow yesterday)
2. Wabisabi documentation (falling behind commits)
3. Quick Win: Review that PR from @contributor
```

**End of day:**
```bash
$ holo summary
# Automatically generates and saves daily summary
✓ Summary saved to ~/holocene/summaries/2025-11-16.md

$ cat ~/holocene/summaries/2025-11-16.md
# Daily Summary - November 16, 2025

**Highlights:**
- 6 hours deep work on GGR
- Completed kriging validation tests
- 2 context switches (average for you)
- Good environment: office 21°C, quiet

**Suggestions for tomorrow:**
- Continue GGR momentum
- Schedule wabisabi docs (30min)
```

**Weekly review:**
```bash
$ holo weekly-review
Generating weekly review... done.
✓ Saved to ~/holocene/reviews/2025-W46.md

Summary:
- 25h productive coding
- Pattern: Most productive 9-11 AM
- Suggestion: Protect morning focus blocks
- Good break compliance: 85%

[Share with Claude for analysis? Y/n]
```

## Integration Architecture

### Browser Extension ↔ Holocene

```
Browser Extension (Chrome/Edge)
    ↓ (WebSocket or HTTP POST every 30s)
Local Holocene Service (localhost:8765)
    ↓ (Sanitize, categorize)
SQLite Database
    ↓ (Periodic aggregation)
LLM Analysis (via NanoGPT)
```

### Home Assistant ↔ Holocene

```python
# Holocene polls Home Assistant API
# Or: Home Assistant sends webhooks to Holocene

class HomeAssistantIntegration:
    def __init__(self, url, token):
        self.url = url
        self.token = token
    
    def get_sensor_state(self, entity_id):
        # GET /api/states/entity_id
        
    def call_service(self, domain, service, data):
        # POST /api/services/domain/service
        # Example: call_service('light', 'turn_on', {'entity_id': ...})
    
    def vibrate_miband(self):
        # Via Mi Band integration in Home Assistant
        self.call_service('notify', 'mobile_app', {...})
```

### Google Calendar ↔ Holocene

```python
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

class CalendarIntegration:
    def __init__(self, credentials):
        self.service = build('calendar', 'v3', credentials=credentials)
    
    def get_todays_events(self):
        # List events for today
        
    def create_event(self, summary, start, end):
        # Create calendar event
        
    def detect_focus_blocks(self):
        # Find scheduled focus time
```

### journel ↔ Holocene

```python
# Read-only integration
class JournelIntegration:
    def __init__(self, journel_path):
        self.path = journel_path
    
    def get_recent_entries(self, days=7):
        # Parse journel logs
        
    def get_project_activities(self, project):
        # Filter by project tag
```

## Deployment Strategy

### Phase 1: Development (Now - Q1 2026)

**Platform:** Local development machine
**LLM:** NanoGPT subscription
**Components:**
- Core logging system
- Browser extension (unpublished)
- Basic CLI
- SQLite storage
- Home Assistant integration
- Mi Band notifications

### Phase 2: Production (Q1-Q2 2026)

**Platform:** Runs as daemon on local machine
**Components:**
- All Phase 1 + calendar integration
- Task system
- Rule engine (IFTTT)
- Weekly reviews
- Quarantine/verification system

### Phase 3: Local Inference (Q2 2026+)

**Platform:** M4 Mac Mini (64GB)
**LLM:** Local DeepSeek V3 or equivalent
**New capabilities:**
- Gmail integration
- Screenshot analysis (vision models)
- More detailed work context
- No rate limits

### Installation

```bash
# Install Holocene
pip install holocene  # or: git clone && pip install -e .

# Initial setup
holo init
# Interactive wizard:
# - Privacy tier selection
# - Data source configuration
# - API key setup (NanoGPT, Google Calendar, etc.)
# - Blacklist/whitelist configuration

# Install browser extension
# 1. Open chrome://extensions
# 2. Enable Developer Mode
# 3. Load unpacked: ~/.holocene/browser-extension/

# Start daemon
holo daemon start

# Verify
holo status
```

## Future Enhancements

### Near Term (3-6 months)
- Dashboard web UI for browsing history
- Export to various formats (CSV, JSON, Markdown)
- Integration with more calendar services
- Slack status sync
- Custom notification rules

### Medium Term (6-12 months)
- Mobile companion app
- Voice input for logging
- Photo/screenshot integration (with vision models)
- Integration with more smart home devices
- Team/collaboration features (shared patterns)

### Long Term (12+ months)
- Full local inference on Mac Mini
- Gmail integration
- Advanced pattern prediction
- Proactive suggestion engine
- Integration with professional tools (VS Code, PyCharm)

## Open Questions & Decisions Needed

1. **Storage:** SQLite vs. JSON vs. Hybrid?
2. **Browser Extension:** WebSocket or HTTP for communication?
3. **Daemon:** systemd service or simple Python background process?
4. **Credentials:** How to securely store API keys? System keychain?
5. **Backup:** Automatic cloud backup or manual only?
6. **Updates:** How to handle config schema changes?
7. **Performance:** How to optimize for <100MB memory footprint?
8. **Mobile:** Worth building mobile companion or desktop-only?

## Development Priorities

### MVP (Minimum Viable Product)

**Must Have:**
1. Activity logging (browser, window focus, manual)
2. Basic CLI (status, ask, show)
3. DeepSeek V3 integration via NanoGPT
4. Privacy sanitization
5. Daily summaries
6. SQLite storage

**Should Have:**
7. Home Assistant integration
8. Mi Band notifications
9. Task system (basic)
10. Weekly review generation

**Could Have:**
11. Calendar integration
12. Verification system
13. Rule engine
14. Quarantine for web content

**Won't Have (Yet):**
- Web UI/dashboard
- Mobile app
- Local inference
- Gmail integration

---

## Appendix: Technology Stack

**Core:**
- Python 3.11+
- SQLite 3
- Click (CLI framework)
- aiohttp (async HTTP)

**Integrations:**
- google-api-python-client (Calendar)
- homeassistant-api (Home Assistant)
- anthropic-sdk (future, for Claude API)

**Browser Extension:**
- JavaScript (Chrome Extension APIs)
- Manifest V3

**LLM:**
- NanoGPT API (OpenAI-compatible)
- Models: DeepSeek V3, Qwen 3 Coder, Hermes 4, etc.

**Deployment:**
- systemd (Linux) or launchd (Mac) for daemon
- Docker (optional, for isolation)

---

## Future Improvements & Optimizations

### PDF Metadata Extraction - Bulk Processing

**Current Implementation:**
- PDFs are processed sequentially, one at a time
- Each PDF gets individual DeepSeek V3 API call
- Robust error handling and progress tracking

**Optimization Opportunity:**
- DeepSeek V3 has **128K context window** (not 64K!)
- Could batch 10-15 PDFs per API call (~8K tokens per 5-page excerpt)
- Potential benefits:
  - Faster processing for large batches
  - Fewer API calls (though we have 2000/day budget)
  - Better consistency in metadata extraction

**Challenges:**
- JSON parsing complexity (tracking which metadata belongs to which file)
- All-or-nothing failure mode (one bad PDF kills whole batch)
- Loss of granular progress feedback
- Harder error recovery

**Proposed Hybrid Approach:**
- Batch 3-5 PDFs per API call for optimal balance
- Keep logical separation in prompt structure
- Maintain individual error handling per file
- Preserve progress display

**Priority:** Low (current sequential approach works well with generous API budget)

---

**Document Version:** 1.0
**Last Updated:** November 17, 2025
**Authors:** Arthur + Claude
**Status:** Design Phase - Ready for Implementation