# Holocene Overall Architecture

**Date:** 2025-11-19
**Status:** Approved
**Context:** Architecture Review Session

---

## Executive Summary

Holocene is a **privacy-first personal knowledge management system** with a **plugin-based architecture**, designed to run across multiple devices with offline support and background automation.

**Core Principles:**
1. **Single Source of Truth** - rei (Proxmox server) holds authoritative database
2. **Plugin Architecture** - Core + plugins for modularity and context management
3. **Offline-First** - Works without network, syncs when available
4. **Channel Messaging** - Decoupled integrations via pub/sub
5. **Multi-Device** - CLI (wmut), daemon (rei), mobile (eunice), local LLM (finn)

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      HOLOCENE ECOSYSTEM                          │
└─────────────────────────────────────────────────────────────────┘

╔════════════════════════════════════════════════════════════════╗
║                        REI (Proxmox Server)                     ║
║                       24/7 Daemon Process                        ║
╚════════════════════════════════════════════════════════════════╝
│
├─ CORE
│  ├─ Database (SQLite) ← Single source of truth
│  ├─ Message Bus (Channel Manager)
│  ├─ Task Queue (Background jobs)
│  ├─ LLM Router (Laney-chan, model selection)
│  └─ REST API (port 5555, optionally via Cloudflare Tunnel)
│
├─ PLUGINS (24/7 background)
│  ├─ Telegram Bot Plugin ──────► Listens for messages
│  ├─ Scheduled Enrichment Plugin ► Runs nightly enrichment
│  ├─ MQTT Publisher Plugin ─────► Publishes to Home Assistant
│  └─ Archive Monitor Plugin ────► Checks for dead links
│
└─ PLUGINS (on-demand)
   ├─ Internet Archive Plugin ───► Called by enrichment
   ├─ Calibre Sync Plugin ───────► Triggered by book_added event
   └─ Paper Fetcher Plugin ──────► Called by paper_added event

╔════════════════════════════════════════════════════════════════╗
║                    WMUT (Framework 13)                          ║
║                   Interactive CLI Client                         ║
╚════════════════════════════════════════════════════════════════╝
│
├─ CORE
│  ├─ CLI Framework (Click)
│  ├─ REST Client (talks to rei)
│  └─ Local Cache (SQLite, offline mode)
│
├─ PLUGINS (on-demand only)
│  ├─ Thermal Print Plugin ──────► Local USB printer
│  ├─ Browser Import Plugin ─────► Reads local bookmarks
│  ├─ Git Scanner Plugin ────────► Scans local repos
│  └─ Activity Tracker Plugin ───► Optional system tray
│
└─ NO DAEMON (runs only when invoked)

╔════════════════════════════════════════════════════════════════╗
║                    EUNICE (S24+ Phone)                          ║
║                Telegram Client + PWA                             ║
╚════════════════════════════════════════════════════════════════╝
│
├─ Telegram app ──► Sends to rei's Telegram Bot Plugin
└─ PWA (future) ──► Web interface with offline support

╔════════════════════════════════════════════════════════════════╗
║               FINN (Mac Mini M4, Future)                        ║
║                  Local LLM Server                                ║
╚════════════════════════════════════════════════════════════════╝
│
└─ Ollama server ──► Provides local inference endpoint
                     rei's LLM Router uses for:
                     - Privacy-sensitive content
                     - Offline fallback
                     - General use (when available)
```

---

## Device Responsibilities

### rei (Proxmox Server - Beelink U59)

**Role:** Authoritative daemon, 24/7 background processing

**Hardware:**
- Intel N5095 (11th gen, 16GB RAM)
- Proxmox VE (LXC container for Holocene)
- 24/7 uptime

**Responsibilities:**
- ✅ Database (authoritative SQLite at `/srv/holocene/holocene.db`)
- ✅ Message bus (coordinate plugins)
- ✅ Background tasks (enrichment, archiving, monitoring)
- ✅ REST API (accept requests from wmut/eunice)
- ✅ 24/7 plugins (Telegram bot, MQTT, scheduled jobs)

**Does NOT:**
- ❌ Direct user interaction (no terminal)
- ❌ USB devices (no thermal printer access)
- ❌ GUI (headless)

**Services:**
```bash
# systemd service on rei
/etc/systemd/system/holocene.service

[Unit]
Description=Holocene Daemon
After=network.target

[Service]
Type=simple
User=holocene
ExecStart=/usr/local/bin/holo daemon start
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

---

### wmut (Framework 13 - Intel i7, 40GB RAM)

**Role:** Interactive CLI client, development workstation

**Responsibilities:**
- ✅ Interactive CLI (user commands)
- ✅ Thermal printing (USB Paperang printer)
- ✅ Local file operations (git scanning, bookmark import)
- ✅ Development/testing
- ✅ Optional system tray (activity tracking)

**Communication with rei:**
- **REST API** (primary) - `http://rei:5555/api/*`
- **Local cache** - SQLite for offline work
- **Sync queue** - Uploads writes when online

**Can work offline:**
- ✅ Local SQLite cache (`~/.holocene/cache.db`)
- ✅ Reads from cache (instant)
- ✅ Writes queued for sync
- ✅ Auto-sync when rei available

**Operating Modes:**
```bash
# Online - sync with rei
wmut:~$ holo books list
✓ Synced with rei (42 updates)
[list of books]

# Offline - use cache
wmut:~$ holo books list
⚠ Offline mode - showing cached data (synced 2 hours ago)
[list of books]

# Add offline - queued
wmut:~$ holo books add "Neuromancer"
✓ Book added to local cache (will sync when online)

# Manual sync
wmut:~$ holo sync
✓ Uploading 3 queued changes to rei...
✓ Downloading 7 updates from rei...
✓ Sync complete
```

---

### eunice (S24+ Phone - Android)

**Role:** Mobile access, quick capture

**Current:**
- ✅ Telegram app (sends messages to rei's bot plugin)
- ✅ Tasker automations
- ✅ SSH client (run `holo` commands on rei)

**Future:**
- ⏳ PWA (Progressive Web App) with offline support
- ⏳ InstalleddIndexedDB cache
- ⏳ Background sync when online

**Usage:**
```
# Save link via Telegram
→ Send URL to bot
→ rei's Telegram plugin receives
→ Publishes to "link_added" channel
→ Other plugins react (archive, enrich, etc.)

# Future: PWA
→ Open web app (cached locally)
→ Browse books/papers/links offline
→ Add notes, queue changes
→ Auto-sync when online
```

---

### finn (Mac Mini M4 - Future)

**Role:** Local LLM inference server

**Hardware (Planned):**
- Mac Mini M4
- 65GB RAM
- Ollama server

**Responsibilities:**
- ✅ Local LLM inference (Ollama)
- ✅ Privacy-sensitive processing
- ✅ Offline fallback for Laney-chan
- ✅ General use (not just privacy)

**rei's LLM Router uses finn for:**
- Privacy-sensitive content (work documents, personal data)
- Offline operation (when NanoGPT unavailable)
- General inference (when finn available and faster)

---

## Plugin Architecture

### Why Plugins (Even for Personal Use)?

**Development Benefits:**
```bash
# Work on ML integration in isolation
cd plugins/mercadolivre/

# Context window stays manageable:
# - Core API: ~5K LOC
# - Plugin: ~500 LOC
# vs monolithic: ~15K LOC all at once

# Run Claude Code in plugins/ directory
# → Only sees plugin + core API
# → Focused sessions, better results
```

**Modularity:**
- Add new integration → New plugin, zero core changes
- Remove integration → Delete plugin directory
- Update integration → Only touch that plugin

---

### Plugin API

```python
# holocene/core/plugin.py
class Plugin(ABC):
    """Base class for all Holocene plugins"""

    def __init__(self, core: HoloceneCore):
        self.core = core
        self.db = core.db
        self.llm = core.llm
        self.channels = core.channels

    @abstractmethod
    def get_metadata(self) -> dict:
        """Plugin metadata"""
        return {
            "name": "plugin_name",
            "version": "1.0.0",
            "runs_on": ["rei", "wmut"],  # Where plugin runs
            "requires": []  # Python dependencies
        }

    # Lifecycle hooks
    def initialize(self):
        """Called once on plugin load"""
        pass

    def startup(self):
        """Called when daemon/CLI starts"""
        pass

    def shutdown(self):
        """Called on graceful exit"""
        pass

    # Channel messaging
    def subscribe(self, channel: str):
        """Subscribe to channel messages"""
        self.channels.subscribe(channel, self.on_message)

    def publish(self, channel: str, message: dict):
        """Publish message to channel"""
        self.channels.publish(channel, self.get_metadata()["name"], message)

    def on_message(self, channel: str, sender: str, message: dict):
        """Override to handle channel messages"""
        pass

    # Background tasks
    def run_in_background(self, task: Callable, on_complete: Callable = None):
        """Run task without blocking"""
        self.core.task_queue.submit(task, on_complete)

    # CLI commands (optional)
    def get_cli_commands(self) -> List[click.Command]:
        """Return Click commands this plugin provides"""
        return []
```

---

### Plugin Example

```python
# plugins/internet_archive/plugin.py
from holocene.core.plugin import Plugin

class InternetArchivePlugin(Plugin):
    def get_metadata(self):
        return {
            "name": "internet_archive",
            "version": "1.0.0",
            "runs_on": ["rei", "wmut"],  # Both daemon and CLI
            "requires": ["internetarchive"]
        }

    def initialize(self):
        # Subscribe to events
        self.subscribe("book_added")
        self.subscribe("link_added")

    def on_message(self, channel, sender, message):
        if channel == "book_added":
            book_id = message['book_id']

            # Check IA availability (non-blocking)
            self.run_in_background(
                lambda: self.check_ia_availability(book_id),
                self.on_ia_check_complete
            )

    def check_ia_availability(self, book_id):
        # Runs in background thread
        book = self.db.get_book(book_id)
        ia_data = search_internet_archive(book.isbn)
        return ia_data

    def on_ia_check_complete(self, ia_data):
        # Runs on main thread
        if ia_data:
            self.publish("ia_found", {"ia_id": ia_data.identifier})

    def get_cli_commands(self):
        return [discover_ia_cmd, download_book_cmd]
```

---

### Plugin Deployment Targets

**Plugins declare where they run:**

```python
class TelegramBotPlugin(Plugin):
    def get_metadata(self):
        return {
            "name": "telegram_bot",
            "runs_on": ["rei"],  # Daemon only (24/7)
        }

class ThermalPrintPlugin(Plugin):
    def get_metadata(self):
        return {
            "name": "thermal_print",
            "runs_on": ["wmut"],  # CLI only (USB device)
        }

class InternetArchivePlugin(Plugin):
    def get_metadata(self):
        return {
            "name": "internet_archive",
            "runs_on": ["rei", "wmut"],  # Both
        }
```

**Plugin loader respects targets:**
```python
# On rei daemon startup
for plugin in discover_plugins():
    if "rei" in plugin.get_metadata()["runs_on"]:
        load_plugin(plugin)

# On wmut CLI
for plugin in discover_plugins():
    if "wmut" in plugin.get_metadata()["runs_on"]:
        load_plugin(plugin)
```

---

### Plugin Scaffolding

```bash
# Create new plugin
holo plugin init mercadolivre

# Creates:
plugins/mercadolivre/
├── __init__.py
├── plugin.py        # From template
├── README.md
├── config.yml       # Plugin-specific config
└── tests/
    └── test_plugin.py
```

**Template includes:**
- Plugin class skeleton
- Example CLI commands
- Example channel subscriptions
- Config loading
- Tests

---

## Channel-Based Messaging

**Decoupled Communication via Pub/Sub:**

```python
# When a book is added
book_plugin.publish("book_added", {
    "book_id": 123,
    "title": "Neuromancer",
    "source": "internet_archive"
})

# Subscribers react (no direct coupling!)
# - IA plugin: Check if book needs download
# - Enrichment plugin: Queue for Laney-chan analysis
# - Calibre plugin: Add to Calibre library
# - MQTT plugin: Publish stats to Home Assistant
```

**Standard Channels:**
```python
CHANNELS = {
    # Content events
    "book_added", "book_updated", "book_deleted",
    "paper_added", "paper_updated", "paper_deleted",
    "link_added", "link_updated", "link_deleted",

    # Enrichment events
    "enrichment_requested", "enrichment_completed",

    # System events
    "plugin_loaded", "plugin_unloaded",
    "daemon_started", "daemon_stopped",

    # Integration events
    "telegram_message", "telegram_command",
    "print_requested", "print_completed",
    "archive_checked", "archive_saved",
}
```

**Message Persistence:**
```sql
-- Messages survive daemon restart
CREATE TABLE message_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel TEXT NOT NULL,
    sender TEXT NOT NULL,
    message TEXT NOT NULL,  -- JSON
    created_at TEXT NOT NULL,
    processed_at TEXT,
    status TEXT DEFAULT 'pending'
);
```

**On daemon restart:**
- Replay unprocessed messages
- No lost enrichment jobs
- Graceful recovery

---

## Communication Patterns

### REST API (rei ↔ wmut/eunice)

**Endpoints:**
```python
# Flask app on rei:5555
GET  /health
GET  /api/books
POST /api/books
GET  /api/books/{id}
PUT  /api/books/{id}
DELETE /api/books/{id}

# Similar for papers, links, etc.
POST /api/sync  # Batch sync from wmut
GET  /api/sync/status
```

**Authentication:**
```python
# Simple API key (like Home Assistant)
@app.before_request
def check_auth():
    api_key = request.headers.get('Authorization')
    if api_key != config.api_key:
        abort(401)

# Or bearer token
# Authorization: Bearer <secret-token>
```

**Cloudflare Tunnel (Optional):**
```bash
# Expose rei to internet (secure)
https://holocene.yourdomain.com → Cloudflare Tunnel → rei:5555

# Benefits:
# - No port forwarding
# - HTTPS automatic
# - DDoS protection
# - IP allowlist
```

---

## Offline Mode

### Three-Tier Sync Model

```
REI (Source of Truth)
  ↕ Sync when online
WMUT Cache (Local SQLite)
  ↕ Sync when online
PWA Cache (IndexedDB)
```

### wmut Offline Architecture

**Local Cache:**
```python
# ~/.holocene/cache.db
CREATE TABLE cached_books (...);  # Full book data
CREATE TABLE write_queue (...);   # Pending writes

# Read operations - always from cache (fast!)
holo books list  # Instant, uses cache

# Write operations - queue for sync
holo books add "Neuromancer"
# → Saves to cache immediately
# → Queues for upload to rei
# → Syncs when online
```

**Sync Logic:**
```python
class Database:
    def connect(self):
        """Try rei, fall back to cache"""
        try:
            self.remote = RESTClient("http://rei:5555")
            self.sync_from_remote()  # Pull latest
        except ConnectionError:
            logger.info("Offline mode - using cache")
            self.remote = None

    def add_book(self, book_data):
        # Save locally (instant)
        self.local.execute("INSERT INTO cached_books ...", book_data)

        # Queue for upload
        self.local.execute("INSERT INTO write_queue ...", book_data)

        # Try immediate sync (if online)
        if self.remote:
            self.sync_to_remote()
```

**CLI Experience:**
```bash
# Online
wmut:~$ holo books list
✓ Synced with rei (42 updates)

# Offline
wmut:~$ holo books list
⚠ Offline - cached data (synced 2h ago)

# Add offline
wmut:~$ holo books add "Neuromancer"
✓ Added to cache (will sync when online)

# Back online
wmut:~$ holo sync
✓ Uploading 3 changes...
✓ Downloading 7 updates...
✓ Sync complete
```

---

### PWA Offline (Future)

**Service Worker + IndexedDB:**
```javascript
// Cache static assets
self.addEventListener('install', (event) => {
  caches.addAll(['/', '/static/app.css', '/static/app.js']);
});

// Serve from cache, fall back to network
self.addEventListener('fetch', (event) => {
  event.respondWith(
    caches.match(event.request)
      .then(response => response || fetch(event.request))
  );
});

// Background sync
self.addEventListener('sync', (event) => {
  if (event.tag === 'sync-writes') {
    event.waitUntil(syncQueuedWrites());
  }
});
```

**Use Case: Underground Mine**
- No signal, 500m deep
- Open PWA (cached)
- Browse books (IndexedDB)
- Add notes (queued)
- Back above ground → Auto-syncs

---

## LLM Strategy (Laney-chan)

### Model Routing

```python
# holocene/llm/router.py
class LLMRouter:
    def route(self, task_type: str, privacy_sensitive: bool = False):
        """Route to appropriate model"""

        # Privacy-sensitive → finn (local)
        if privacy_sensitive and self.finn_available():
            return "ollama://finn:11434/deepseek-v3"

        # Task-specific routing via NanoGPT
        if task_type == "enrichment":
            return config.llm.primary  # DeepSeek V3
        elif task_type == "code":
            return config.llm.coding  # Qwen3-Coder
        elif task_type == "reasoning":
            return config.llm.reasoning  # DeepSeek-R1
        else:
            return config.llm.primary  # Default: Laney-chan
```

**NanoGPT Config:**
```yaml
llm:
  api_key: "<secret>"  # Move to secrets.toml
  base_url: "https://nano-gpt.com/v1"
  primary: "deepseek-ai/DeepSeek-V3.1"      # Laney-chan (690B, 64K ctx)
  primary_cheap: "deepseek-chat-cheaper"    # Quick tasks
  coding: "qwen/qwen3-coder"                # Code generation
  reasoning: "deepseek-r1"                  # Complex reasoning
  verification: "nousresearch/hermes-4-70b" # Cross-checking
```

**Budget:**
- 2,000 prompts/day (per-prompt pricing!)
- Massively underutilized
- **Batch aggressively** (64K context, use it!)

**BudgetAllocator (Future):**
- Smart batching (combine requests)
- Priority queues (urgent vs background)
- Daily limit tracking
- Fallback to finn when quota reached

---

## File Structure

```
holocene/
├── holocene/
│   ├── core/              # Core framework
│   │   ├── plugin.py      # Plugin base class
│   │   ├── channels.py    # Message bus
│   │   ├── database.py    # Database abstraction
│   │   ├── llm.py         # LLM router
│   │   └── task_queue.py  # Background tasks
│   │
│   ├── cli/               # CLI framework
│   │   ├── main.py        # Main entry point
│   │   └── commands/      # Command groups
│   │
│   ├── storage/           # Database layer
│   │   ├── models.py      # Data models
│   │   └── migrations.py  # Schema migrations
│   │
│   └── llm/               # LLM integrations
│       ├── nanogpt.py     # NanoGPT client
│       └── router.py      # Model routing
│
├── plugins/               # All plugins here
│   ├── internet_archive/
│   ├── mercadolivre/
│   ├── thermal_print/
│   ├── telegram_bot/
│   ├── calibre_sync/
│   ├── paper_fetcher/
│   └── web_interface/     # PWA + web UI
│
├── design/                # Architecture docs
│   └── architecture/
│       ├── holocene_architecture.md (this file)
│       └── database_schema.md
│
├── docs/                  # Documentation
└── tests/                 # Tests
```

---

## Implementation Phases

### Phase 1: Core + Database (Current → Week 1)
- ✅ Database schema cleanup
- ✅ Add metadata columns
- ✅ Enable foreign keys
- ✅ Add missing indexes
- ✅ Lightweight migration system

### Phase 2: Plugin Architecture (Week 2-3)
- ⏳ Plugin base class + API
- ⏳ Channel messaging system
- ⏳ Background task queue
- ⏳ Plugin loader (respects runs_on)
- ⏳ Plugin scaffolding (`holo plugin init`)

### Phase 3: rei Daemon (Week 4-5)
- ⏳ REST API (Flask)
- ⏳ Systemd service
- ⏳ Message queue persistence
- ⏳ 24/7 plugins (Telegram bot, MQTT)
- ⏳ Cloudflare Tunnel setup (optional)

### Phase 4: Offline Mode (Month 2)
- ⏳ wmut local cache + sync
- ⏳ Write queue
- ⏳ Auto-sync
- ⏳ Conflict resolution (last-write-wins)

### Phase 5: Refactor to Plugins (Month 2-3)
- ⏳ Migrate existing integrations:
  - internet_archive → plugin
  - mercadolivre → plugin
  - thermal_print → plugin
  - calibre → plugin
  - papers → plugin

### Phase 6: Web Interface + PWA (Month 3-4)
- ⏳ Web interface plugin
- ⏳ Service worker + offline
- ⏳ IndexedDB cache
- ⏳ Background sync
- ⏳ Install as PWA on eunice

### Phase 7: finn Integration (Future)
- ⏳ LLM router → finn fallback
- ⏳ Privacy-sensitive routing
- ⏳ Offline LLM support

---

## Related Documents

- `design/architecture/database_schema.md` - Database patterns
- `docs/database_current_state.md` - Current schema
- `docs/scissors_runner_evaluation.md` - SR patterns to adopt
- `docs/aedb_evaluation.md` - AEDB features (mostly deferred)
- `docs/infrastructure_naming.md` - Gibson naming schema
- `docs/ROADMAP.md` - Implementation priorities

---

**Last Updated:** 2025-11-19
**Status:** Approved in Architecture Review Session
**Next Steps:** Implement Phase 1 (Database cleanup + migrations)
