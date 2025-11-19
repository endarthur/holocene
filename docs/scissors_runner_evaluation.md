# Scissors Runner Evaluation

**Context:** Scavenging mature predecessor project for salvageable patterns and code
**Evaluated:** 2025-11-19
**Repository:** C:\Users\endar\Documents\GitHub\scissors_runner

---

## Project Overview

**Scissors Runner** is a mature PySide6 (Qt) system tray application with a plugin-based architecture. It was built before adopting Claude-assisted development workflows and represents proven patterns worth folding into Holocene.

**Core Architecture:**
- System tray application (Windows, background process)
- Plugin system with hot-reload capability
- REST API on localhost for automation
- TOML configuration with secrets management
- GitHub-based plugin marketplace
- Channel-based pub/sub messaging

**Active Plugins:**
- AVMonitor - Webcam/mic usage tracking (Windows Registry)
- Link Logger - URL and hashtag extraction from clipboard
- Telegram Bot - Bidirectional communication with enrolled users
- Quick Notes - Tray icon note-taking
- Notify.run - Push notification integration
- Countdown Timer - Simple countdown with notifications

---

## Top 10 Salvageable Components

### 1. Channel-Based Pub/Sub Messaging ⭐⭐⭐⭐⭐

**What It Is:**
```python
# From scissors_runner/plugin.py
def subscribe_to_channel(self, channel: str):
    """Subscribe to receive messages on a channel"""
    self._subscribed_channels.add(channel)
    self.plugin_manager.subscribe_plugin_to_channel(self.get_name(), channel)

def send_to_channel(self, channel: str, message: str, data: Any = None):
    """Send message to all subscribers of a channel"""
    self.plugin_manager.send_to_channel(self.get_name(), channel, message, data)

def on_channel_message(self, channel: str, sender: str, message: str, data: Any = None):
    """Override to handle channel messages"""
    pass
```

**Why Important:**
- Decouples components (plugins don't need to know about each other)
- Enables event-driven architecture
- Perfect for Holocene's integration coordination

**Holocene Use Cases:**
```python
# When a paper is added
send_to_channel("paper_added", "papers", {"doi": "10.1234/abc"})

# Paper enrichment plugin auto-subscribes
subscribe_to_channel("paper_added")

# When enrichment completes
send_to_channel("paper_enriched", "enrichment", enriched_data)

# Calibre sync plugin auto-subscribes
subscribe_to_channel("paper_enriched")
subscribe_to_channel("book_enriched")

# When link is saved
send_to_channel("link_saved", "links", {"url": url, "source": "telegram"})

# Internet Archive plugin checks if archiving needed
subscribe_to_channel("link_saved")
```

**Implementation Effort:** 4-6 hours
**Files to Study:**
- `scissors_runner/plugin.py` - Lines 150-200 (channel methods)
- `scissors_runner/plugin_manager.py` - Lines 300-400 (channel routing)

---

### 2. Background Task Execution ⭐⭐⭐⭐⭐

**What It Is:**
```python
# From scissors_runner/plugin.py
def run_in_background(self, task: Callable, on_complete: Callable = None):
    """
    Run a task in background thread without blocking UI/CLI
    Optionally call on_complete when done
    """
    self.plugin_manager.run_background_task(task, on_complete)

# From scissors_runner/plugin_manager.py
def run_background_task(self, task: Callable, callback: Callable = None):
    """Execute task in QThreadPool"""
    worker = Worker(task)
    if callback:
        worker.signals.result.connect(callback)
    self.thread_pool.start(worker)
```

**Why Critical for Holocene:**
```python
# Current problem: LLM calls block the CLI
def enrich_book(book_id):
    book = get_book(book_id)
    # This takes 5-10 seconds and blocks everything
    enriched = nanogpt_client.enrich(book)
    save_enriched_data(enriched)

# Better: Background execution
def do_enrichment():
    book = get_book(book_id)
    return nanogpt_client.enrich(book)  # Runs in background

def save_result(enriched_data):
    save_enriched_data(enriched_data)
    print("✓ Enrichment complete!")

run_in_background(do_enrichment, save_result)
print("Enrichment started in background...")
# CLI immediately returns, user can continue working
```

**Implementation Effort:** 3-4 hours
**Benefits:**
- Non-blocking LLM operations
- Better UX (no frozen CLI)
- Can batch-enrich multiple items in parallel
- Progress indicators while working

**Files to Study:**
- `scissors_runner/plugin.py` - Lines 100-130
- `scissors_runner/plugin_manager.py` - Lines 250-300 (Worker class)

---

### 3. Link Logger Plugin Logic ⭐⭐⭐⭐

**What It Is:**
```python
# From plugins/link_logger_plugin/link_logger_plugin.py
import re
from datetime import datetime

# URL extraction regex (comprehensive)
url_pattern = re.compile(
    r'https?://(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}'
    r'\b(?:[-a-zA-Z0-9()@:%_\+.~#?&/=]*)'
)

# Hashtag extraction
hashtag_pattern = re.compile(r'#(\w+)')

def extract_links_and_tags(text: str):
    """Extract URLs and hashtags from text"""
    urls = url_pattern.findall(text)
    tags = hashtag_pattern.findall(text)
    return urls, tags

# Storage format (CSV with timestamps)
# timestamp,url,tags,source
# 2025-11-19T14:30:00,https://arxiv.org/abs/1234,"#ml,#papers",clipboard
```

**Why Important:**
- Robust URL extraction (battle-tested)
- Hashtag support for quick tagging
- Clipboard monitoring pattern
- CSV storage with proper timestamps

**Direct Port to Holocene:**
```python
# Add to src/holocene/cli/links_commands.py
@links.command("add-from-clipboard")
def add_from_clipboard():
    """Monitor clipboard and auto-save links"""
    import pyperclip

    last_clipboard = ""
    while True:
        current = pyperclip.paste()
        if current != last_clipboard:
            urls, tags = extract_links_and_tags(current)
            for url in urls:
                # Add to database with extracted tags
                add_link(url, tags=tags, source="clipboard")
        last_clipboard = current
        time.sleep(1)
```

**Implementation Effort:** 2-3 hours
**Files to Study:**
- `plugins/link_logger_plugin/link_logger_plugin.py` - Complete file (~200 lines)

---

### 4. TOML Configuration with Secrets ⭐⭐⭐⭐

**What It Is:**
```python
# From scissors_runner/config.py
import tomlkit
from pathlib import Path

class Config:
    def __init__(self, config_dir: Path):
        self.config_file = config_dir / "config.toml"
        self.secrets_file = config_dir / "secrets.toml"

    def save_secret(self, key: str, value: str):
        """Save to secrets.toml with secure permissions"""
        if self.secrets_file.exists():
            with open(self.secrets_file, 'r') as f:
                secrets = tomlkit.parse(f.read())
        else:
            secrets = tomlkit.document()

        secrets[key] = value

        # Write with restricted permissions (0o600 = owner read/write only)
        with open(self.secrets_file, 'w') as f:
            f.write(tomlkit.dumps(secrets))
        self.secrets_file.chmod(0o600)

    def get_secret(self, key: str) -> str:
        """Retrieve secret from secrets.toml"""
        with open(self.secrets_file, 'r') as f:
            secrets = tomlkit.parse(f.read())
        return secrets.get(key)
```

**Why Better Than Current Holocene YAML:**
- **tomlkit preserves comments** (YAML libs often lose them)
- **Separate secrets file** (better security, easier .gitignore)
- **Secure file permissions** (0o600 = owner-only access)
- **Plugin parameter registration** (type-safe config)

**Current Holocene Config:**
```yaml
# ~/.config/holocene/config.yml
llm:
  api_key: "sk-xxxxx"  # Mixed with regular config!
  base_url: "https://nano-gpt.com/v1"
  primary: "deepseek-ai/DeepSeek-V3.1"
```

**Better Scissors Runner Pattern:**
```toml
# ~/.config/holocene/config.toml
[llm]
base_url = "https://nano-gpt.com/v1"
primary = "deepseek-ai/DeepSeek-V3.1"
# No API key here!

# ~/.config/holocene/secrets.toml (0o600 permissions)
nanogpt_api_key = "sk-xxxxx"
brightdata_password = "xxxxx"
telegram_bot_token = "xxxxx"
```

**Implementation Effort:** 3-4 hours (migration from YAML)
**Files to Study:**
- `scissors_runner/config.py` - Complete file (~400 lines)

---

### 5. REST API Architecture ⭐⭐⭐⭐

**What It Is:**
```python
# From scissors_runner/api_server.py
from flask import Flask, request, jsonify
from threading import Thread

app = Flask(__name__)

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({"status": "ok"}), 200

@app.route('/plugins', methods=['GET'])
def list_plugins():
    """List all loaded plugins"""
    plugins = [p.get_name() for p in plugin_manager.get_plugins()]
    return jsonify({"plugins": plugins}), 200

@app.route('/message', methods=['POST'])
def send_message():
    """Send message to specific plugin"""
    data = request.json
    plugin = data.get('plugin')
    message = data.get('message')
    plugin_manager.send_to_plugin(plugin, message, data.get('data'))
    return jsonify({"status": "sent"}), 200

@app.route('/broadcast', methods=['POST'])
def broadcast():
    """Broadcast to all plugins"""
    data = request.json
    plugin_manager.broadcast(data.get('message'), data.get('data'))
    return jsonify({"status": "broadcast"}), 200

# Run in background thread
def start_api_server():
    app.run(host='127.0.0.1', port=5555, debug=False)

api_thread = Thread(target=start_api_server, daemon=True)
api_thread.start()
```

**Why Important for Holocene:**
- **Browser extensions** can save links via `POST /links`
- **Mobile apps** can trigger commands remotely
- **Home Assistant** automations can call Holocene
- **Tasker (Android)** can integrate with Holocene
- **Local-only** (127.0.0.1) = secure by default

**Holocene Use Cases:**
```bash
# Browser extension saves link
curl -X POST http://localhost:5555/links \
  -H "Content-Type: application/json" \
  -d '{"url": "https://arxiv.org/abs/1234", "tags": ["ml", "papers"]}'

# Tasker automation (phone) saves note
curl -X POST http://localhost:5555/notes \
  -d '{"content": "Buy milk", "source": "phone"}'

# Home Assistant triggers morning summary print
curl -X POST http://localhost:5555/print/summary

# Check if holo daemon is running
curl http://localhost:5555/health
```

**Implementation Effort:** 4-6 hours
**Files to Study:**
- `scissors_runner/api_server.py` - Complete file (~300 lines)

---

### 6. Plugin Architecture Pattern ⭐⭐⭐⭐⭐

**What It Is:**
Full plugin lifecycle with standardized hooks:

```python
# From scissors_runner/plugin.py
class Plugin(ABC):
    """Base class for all plugins"""

    # Lifecycle hooks (called in order)
    def initialize(self):
        """Called once when plugin is loaded"""
        pass

    def startup(self):
        """Called when application starts"""
        pass

    def cleanup(self):
        """Called before plugin unload"""
        pass

    def shutdown(self):
        """Called when application exits"""
        pass

    # Messaging patterns
    def on_message(self, sender: str, message: str, data: Any):
        """Direct message to this plugin"""
        pass

    def on_broadcast(self, sender: str, message: str, data: Any):
        """Broadcast message to all plugins"""
        pass

    def on_channel_message(self, channel: str, sender: str, message: str, data: Any):
        """Channel subscription message"""
        pass

    # UI integration (optional)
    def get_tray_menu_items(self) -> List[Tuple[str, Callable]]:
        """Add items to system tray menu"""
        return []

    # CLI integration
    @cli_command("mycommand", "description")
    def my_command(self, args):
        """Exposed as CLI command"""
        pass

    # Configuration
    def get_config_parameters(self) -> Dict[str, ConfigParam]:
        """Register configuration parameters"""
        return {
            "api_key": ConfigParam(str, required=True, secret=True),
            "enabled": ConfigParam(bool, default=True)
        }
```

**Holocene Integration Refactor:**

Currently Holocene has integrations as separate modules:
```
src/holocene/integrations/
├── internet_archive.py
├── calibre.py
├── paperang/
├── bookmarks.py
└── git_scanner.py
```

Could refactor to plugin architecture:
```
src/holocene/plugins/
├── internet_archive_plugin/
│   ├── __init__.py
│   └── plugin.py  # Subscribes to book_added, paper_added
├── calibre_plugin/
│   └── plugin.py  # Subscribes to book_enriched
├── thermal_print_plugin/
│   └── plugin.py  # Subscribes to print_* commands
└── telegram_plugin/
    └── plugin.py  # Subscribes to telegram_messages
```

**Benefits:**
- Hot-reload integrations without restart
- Standardized lifecycle (initialize → startup → cleanup → shutdown)
- Declarative configuration (parameters, secrets)
- Automatic CLI command registration
- Message-based coordination (decoupled)

**Implementation Effort:** 8-12 hours (major refactor)
**Files to Study:**
- `scissors_runner/plugin.py` - Complete file (~500 lines)
- `scissors_runner/plugin_manager.py` - Complete file (~600 lines)

---

### 7. Telegram Bot Integration ⭐⭐⭐⭐

**What It Is:**
```python
# From plugins/telegram_bot_plugin/telegram_bot_plugin.py
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler

class TelegramBotPlugin(Plugin):
    def startup(self):
        """Start Telegram bot in background"""
        token = self.get_config("bot_token")
        self.app = Application.builder().token(token).build()

        # Command handlers
        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler("stop", self.cmd_stop))
        self.app.add_handler(CommandHandler("status", self.cmd_status))

        # Message handler (forward to channel)
        self.app.add_handler(MessageHandler(filters.TEXT, self.on_message))

        # Run in background
        self.run_in_background(lambda: self.app.run_polling())

    async def cmd_start(self, update: Update, context):
        """Enroll user"""
        user_id = update.effective_user.id
        self.enrolled_users.add(user_id)
        self.save_config("enrolled_users", list(self.enrolled_users))
        await update.message.reply_text("✓ Enrolled! Send me links to save.")

    async def on_message(self, update: Update, context):
        """Forward messages to telegram_messages channel"""
        text = update.message.text
        user_id = update.effective_user.id

        if user_id not in self.enrolled_users:
            await update.message.reply_text("Use /start to enroll first")
            return

        # Publish to channel for other plugins to handle
        self.send_to_channel("telegram_messages", "telegram_bot", {
            "text": text,
            "user_id": user_id
        })

        await update.message.reply_text("✓ Saved")

    def on_channel_message(self, channel, sender, message, data):
        """Send notifications to enrolled users"""
        if channel == "notifications":
            for user_id in self.enrolled_users:
                self.app.bot.send_message(user_id, data['text'])
```

**Holocene Integration:**
```python
# Holocene Telegram plugin subscribes to telegram_messages
class HoloceneTelegramHandler(Plugin):
    def initialize(self):
        self.subscribe_to_channel("telegram_messages")

    def on_channel_message(self, channel, sender, message, data):
        text = data['text']

        # Extract URLs
        urls, tags = extract_links_and_tags(text)

        for url in urls:
            # Save to database
            add_link(url, tags=tags, source="telegram")

            # Trigger archiving if needed
            self.send_to_channel("link_saved", "telegram", {"url": url})

        # Send confirmation
        self.send_to_channel("notifications", "holocene", {
            "text": f"✓ Saved {len(urls)} link(s)"
        })
```

**Use Cases:**
- Save links from phone while browsing
- Quick notes via Telegram
- Remote command execution (authorized users only)
- Status notifications (enrichment complete, print done, etc.)

**Implementation Effort:** 3-4 hours
**Files to Study:**
- `plugins/telegram_bot_plugin/telegram_bot_plugin.py` - Complete file (~400 lines)

---

### 8. Windows Registry Monitoring ⭐⭐⭐

**What It Is:**
```python
# From plugins/av_monitor_plugin/av_monitor_plugin.py
import winreg
from datetime import datetime

def _is_app_using_webcam(self, app_name: str) -> bool:
    """Check if app is currently using webcam"""
    key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\webcam"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, f"{key_path}\\{app_name}") as key:
            last_used, _ = winreg.QueryValueEx(key, "LastUsedTimeStart")
            last_stop, _ = winreg.QueryValueEx(key, "LastUsedTimeStop")
            # If last_stop == 0, app is currently using webcam
            return last_stop == 0
    except Exception:
        return False

def _is_app_using_microphone(self, app_name: str) -> bool:
    """Check if app is currently using microphone"""
    key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, f"{key_path}\\{app_name}") as key:
            last_used, _ = winreg.QueryValueEx(key, "LastUsedTimeStart")
            last_stop, _ = winreg.QueryValueEx(key, "LastUsedTimeStop")
            return last_stop == 0
    except Exception:
        return False

# Polling loop
def monitor_av_usage(self):
    """Monitor and log webcam/mic usage"""
    while self.monitoring:
        for app in self.monitored_apps:
            webcam = self._is_app_using_webcam(app)
            mic = self._is_app_using_microphone(app)

            if webcam or mic:
                # Log activity
                self.log_activity({
                    "app": app,
                    "webcam": webcam,
                    "microphone": mic,
                    "timestamp": datetime.now().isoformat()
                })

        time.sleep(5)  # Check every 5 seconds
```

**Holocene Use Cases:**
- **Meeting detection** - Auto-tag calendar events when webcam/mic used
- **Activity tracking** - Correlate webcam usage with meetings
- **Focus time tracking** - Detect when in meetings vs deep work
- **Privacy awareness** - Alert if webcam unexpectedly active

**Integration:**
```python
class MeetingDetectorPlugin(Plugin):
    def startup(self):
        self.run_in_background(self.monitor_meetings)

    def monitor_meetings(self):
        while True:
            # Check Zoom, Teams, Meet
            in_meeting = (
                self._is_app_using_webcam("Zoom.exe") or
                self._is_app_using_webcam("Teams.exe") or
                self._is_app_using_webcam("chrome.exe")  # Google Meet
            )

            if in_meeting and not self.currently_in_meeting:
                # Meeting started
                self.send_to_channel("activity", "meeting_detector", {
                    "event": "meeting_started",
                    "timestamp": datetime.now().isoformat()
                })
                self.currently_in_meeting = True

            elif not in_meeting and self.currently_in_meeting:
                # Meeting ended
                self.send_to_channel("activity", "meeting_detector", {
                    "event": "meeting_ended",
                    "timestamp": datetime.now().isoformat()
                })
                self.currently_in_meeting = False

            time.sleep(10)
```

**Implementation Effort:** 2-3 hours
**Platform:** Windows-only (Linux/Mac use different methods)
**Files to Study:**
- `plugins/av_monitor_plugin/av_monitor_plugin.py` - Lines 50-150

---

### 9. Hot-Reload Capability ⭐⭐⭐

**What It Is:**
```python
# From scissors_runner/plugin_manager.py
def reload_plugin(self, plugin_name: str):
    """Reload a plugin without restarting application"""
    # Find plugin
    plugin = self.get_plugin(plugin_name)
    if not plugin:
        raise ValueError(f"Plugin {plugin_name} not found")

    # Cleanup
    plugin.cleanup()

    # Unload module
    module_name = plugin.__module__
    if module_name in sys.modules:
        del sys.modules[module_name]

    # Reimport
    import importlib
    module = importlib.import_module(module_name)

    # Reinstantiate
    plugin_class = getattr(module, plugin.__class__.__name__)
    new_plugin = plugin_class(self, self.config)

    # Replace in registry
    self.plugins[plugin_name] = new_plugin

    # Initialize
    new_plugin.initialize()
    new_plugin.startup()

    return new_plugin
```

**Why Important:**
- **Fast iteration** - Test changes without full restart
- **Update integrations** - Fix bugs without losing state
- **Live configuration** - Update settings without downtime

**Holocene Use Case:**
```bash
# Terminal 1: Holocene daemon running
holo daemon start

# Terminal 2: Make changes to Internet Archive plugin
vim src/holocene/plugins/internet_archive_plugin/plugin.py

# Terminal 3: Reload without restart
holo daemon reload-plugin internet_archive

# Or via REST API
curl -X POST http://localhost:5555/plugins/reload \
  -d '{"plugin": "internet_archive"}'
```

**Implementation Effort:** 2-3 hours (once plugin architecture exists)
**Files to Study:**
- `scissors_runner/plugin_manager.py` - Lines 400-450

---

### 10. Plugin Marketplace (GitHub-based) ⭐⭐⭐

**What It Is:**
```python
# From scissors_runner/plugin_marketplace.py
import requests
from pathlib import Path

class PluginMarketplace:
    def __init__(self, config):
        # Default: https://github.com/endarthur/scissors-runner-plugins
        self.repositories = config.get("plugin_repositories", [
            "https://github.com/endarthur/scissors-runner-plugins"
        ])

    def list_available_plugins(self):
        """Fetch plugin list from marketplace"""
        plugins = []
        for repo_url in self.repositories:
            # Fetch plugins.json from repo
            metadata_url = f"{repo_url}/raw/main/plugins.json"
            response = requests.get(metadata_url)
            plugins.extend(response.json())
        return plugins

    def install_plugin(self, plugin_name: str):
        """Download and install plugin from marketplace"""
        plugin_info = self._find_plugin(plugin_name)
        if not plugin_info:
            raise ValueError(f"Plugin {plugin_name} not found")

        # Download plugin code
        download_url = plugin_info['download_url']
        response = requests.get(download_url)

        # Extract to plugins directory
        plugin_dir = self.plugins_dir / plugin_name
        plugin_dir.mkdir(exist_ok=True)

        # Save files
        self._extract_plugin(response.content, plugin_dir)

        # Install dependencies if needed
        if (plugin_dir / "requirements.txt").exists():
            subprocess.run(["pip", "install", "-r",
                          str(plugin_dir / "requirements.txt")])

        # Add default configuration
        if plugin_info.get('default_config'):
            self.config.add_plugin_config(plugin_name,
                                         plugin_info['default_config'])

        return plugin_dir
```

**Marketplace Metadata Format:**
```json
{
  "plugins": [
    {
      "name": "internet_archive_enhanced",
      "version": "1.0.0",
      "description": "Enhanced IA integration with OCR",
      "author": "community",
      "download_url": "https://github.com/user/repo/archive/main.zip",
      "dependencies": ["pytesseract", "pdf2image"],
      "default_config": {
        "ocr_enabled": true,
        "download_formats": ["pdf", "epub"]
      }
    }
  ]
}
```

**Holocene Use Case:**
```bash
# List available plugins
holo plugins search

# Install community plugin
holo plugins install goodreads_sync

# Update all plugins
holo plugins update-all

# Publish your own plugin
holo plugins publish my_plugin
```

**Benefits:**
- **Community contributions** - Users can extend Holocene
- **Discoverability** - Browse available integrations
- **Easy updates** - Pull latest versions
- **Sharing** - Publish your own integrations

**Implementation Effort:** 6-8 hours
**Files to Study:**
- `scissors_runner/plugin_marketplace.py` - Complete file (~300 lines)

---

## Architecture Comparison

### Scissors Runner (Current)
```
System Tray App (PySide6/Qt)
├── Plugin Manager
│   ├── AVMonitor (Registry polling)
│   ├── Link Logger (Clipboard monitoring)
│   ├── Telegram Bot (python-telegram-bot)
│   ├── Quick Notes (Tray icon)
│   └── Notify.run (Push notifications)
├── REST API Server (Flask, localhost:5555)
├── Channel-Based Messaging (pub/sub)
├── Background Task Execution (QThreadPool)
└── Configuration (TOML + secrets)
```

### Holocene (Current)
```
CLI Application (Click)
├── Command Groups
│   ├── books - Library management
│   ├── papers - Research management
│   ├── links - Link collection
│   ├── print - Thermal printing
│   └── mercadolivre - ML integration
├── Integrations (modules)
│   ├── internet_archive.py
│   ├── calibre.py
│   ├── paperang/ (Spinitex)
│   └── git_scanner.py
├── LLM Integration (NanoGPT)
├── Storage (SQLite)
└── Configuration (YAML)
```

### Holocene (With Scissors Runner Patterns)
```
CLI + Daemon Application
├── Core Application
│   ├── Plugin Manager (from SR)
│   ├── Channel Messaging (from SR)
│   ├── Background Tasks (from SR)
│   └── REST API Server (from SR)
├── Plugins (refactored integrations)
│   ├── internet_archive_plugin/
│   ├── calibre_plugin/
│   ├── thermal_print_plugin/
│   ├── telegram_plugin/ (from SR)
│   ├── link_logger_plugin/ (from SR)
│   └── meeting_detector_plugin/ (from SR)
├── LLM Integration (NanoGPT)
├── Storage (SQLite)
└── Configuration (TOML + secrets, from SR)
```

---

## Overlaps with Holocene

| Feature | Scissors Runner | Holocene | Integration Plan |
|---------|----------------|----------|------------------|
| **Link Collection** | ✅ Link Logger | ✅ holo links | Adopt regex + clipboard monitoring |
| **Telegram Bot** | ✅ Built-in plugin | ❌ Planned | Direct port |
| **Configuration** | ✅ TOML + secrets | ⚠️ YAML (no secrets) | Migrate to TOML |
| **Background Tasks** | ✅ QThreadPool | ❌ Blocking | Critical to adopt |
| **REST API** | ✅ Flask localhost | ❌ Missing | Add for automation |
| **Plugin System** | ✅ Full architecture | ❌ Modules only | Major refactor |
| **Hot-Reload** | ✅ Supported | ❌ Restart required | Adopt with plugins |
| **Channel Messaging** | ✅ Pub/sub | ❌ Direct calls | Enables decoupling |
| **Activity Tracking** | ✅ AV monitoring | ⚠️ Planned | Adapt for meetings |
| **Clipboard Monitoring** | ✅ Link Logger | ❌ Missing | Port directly |

---

## Integration Roadmap

### Phase 1: Quick Wins (Week 1)
**Goal:** Immediate improvements with minimal disruption

**Tasks:**
1. **Channel-based messaging** (4-6 hours)
   - Port `plugin.py` messaging methods
   - Create simple channel registry
   - Refactor 2-3 integrations to use channels

2. **Background task execution** (3-4 hours)
   - Port Worker class from plugin_manager
   - Add `run_in_background()` helper
   - Update LLM calls to be non-blocking

3. **TOML config + secrets** (3-4 hours)
   - Migrate config.yml → config.toml
   - Extract secrets to secrets.toml
   - Set 0o600 permissions

4. **URL extraction** (1 hour)
   - Copy regex patterns from Link Logger
   - Add to `holo links add-from-clipboard`

**Deliverables:**
- Non-blocking LLM operations
- Secure secrets management
- Better link extraction
- Event-driven integration coordination

**Estimated Total:** 11-15 hours

---

### Phase 2: Integration Features (Weeks 2-3)
**Goal:** Add missing features from Scissors Runner

**Tasks:**
1. **REST API layer** (4-6 hours)
   - Add Flask server on localhost:5555
   - Endpoints: /health, /links, /print, /books
   - Run in background thread
   - Document API for browser extensions

2. **Telegram bot plugin** (3-4 hours)
   - Port Telegram bot code
   - Subscribe to telegram_messages channel
   - Add link extraction handler
   - Support /start, /stop, /status commands

3. **CLI subcommands** (2-3 hours)
   - Add `holo daemon start/stop/status`
   - Add `holo plugins list/reload`
   - Add `holo api test`

4. **Link logger** (1-2 hours)
   - Clipboard monitoring
   - Auto-save links with extracted tags
   - Background polling loop

**Deliverables:**
- REST API for automation
- Telegram bot for mobile access
- Clipboard link monitoring
- Daemon mode for 24/7 operation

**Estimated Total:** 10-15 hours

---

### Phase 3: Architecture Refactor (Month 2)
**Goal:** Full plugin architecture adoption

**Tasks:**
1. **Plugin base class** (2-3 hours)
   - Port Plugin class from Scissors Runner
   - Add lifecycle hooks
   - Add configuration registration

2. **Plugin manager** (4-6 hours)
   - Port PluginManager class
   - Channel routing
   - Background task coordination
   - Hot-reload support

3. **Refactor integrations as plugins** (8-12 hours)
   - internet_archive_plugin
   - calibre_plugin
   - thermal_print_plugin
   - telegram_plugin
   - Each plugin: 1-2 hours refactor

4. **Plugin marketplace** (4-6 hours)
   - GitHub-based repository
   - Plugin discovery
   - Install/update commands
   - Metadata format

**Deliverables:**
- Full plugin architecture
- Hot-reload capability
- Community plugin support
- Modular, extensible design

**Estimated Total:** 18-27 hours

---

### Phase 4: Advanced Features (Month 3+)
**Goal:** Polish and advanced integrations

**Tasks:**
1. **Meeting detection** (2-3 hours)
   - Port AV monitor registry code
   - Detect Zoom/Teams/Meet usage
   - Publish to activity channel

2. **Home Assistant integration** (3-4 hours)
   - REST API sensors
   - Automation triggers
   - Service calls

3. **Browser extension** (6-8 hours)
   - Save links to REST API
   - Quick tag entry
   - Context menu integration

4. **Mobile app** (Tasker integration) (2-3 hours)
   - HTTP Request tasks
   - Quick save profiles
   - Voice command shortcuts

**Deliverables:**
- Meeting activity tracking
- Home automation integration
- Browser quick-save
- Mobile quick-save

**Estimated Total:** 13-18 hours

---

## Files to Study Closely

### Priority 1 (Must Study)
1. **scissors_runner/plugin.py** (~500 lines)
   - Plugin base class
   - Messaging patterns (direct, broadcast, channel)
   - Lifecycle hooks (initialize, startup, cleanup, shutdown)
   - Background task execution
   - Configuration integration

2. **scissors_runner/plugin_manager.py** (~600 lines)
   - Plugin orchestration
   - Channel routing logic
   - Background worker implementation (QThreadPool)
   - Plugin discovery and loading
   - Hot-reload mechanism

3. **scissors_runner/config.py** (~400 lines)
   - TOML configuration with tomlkit
   - Secrets management (separate file + permissions)
   - Plugin parameter registration
   - Config file inclusion

### Priority 2 (Highly Recommended)
4. **plugins/link_logger_plugin/link_logger_plugin.py** (~200 lines)
   - URL extraction regex
   - Hashtag extraction
   - Clipboard monitoring pattern
   - CSV storage with timestamps

5. **scissors_runner/api_server.py** (~300 lines)
   - Flask REST API
   - Thread-safe Qt integration
   - Endpoint design patterns
   - localhost-only security

6. **plugins/telegram_bot_plugin/telegram_bot_plugin.py** (~400 lines)
   - python-telegram-bot integration
   - User enrollment system
   - Command handlers
   - Message forwarding to channels

### Priority 3 (Nice to Have)
7. **plugins/av_monitor_plugin/av_monitor_plugin.py** (~300 lines)
   - Windows Registry monitoring
   - Webcam/mic usage detection
   - Activity logging patterns

8. **scissors_runner/plugin_marketplace.py** (~300 lines)
   - GitHub repository integration
   - Plugin discovery
   - Installation automation
   - Dependency management

---

## Decision Points for Architecture Review

### 1. Plugin Architecture Adoption
**Question:** Full refactor to plugin system or cherry-pick patterns?

**Option A: Full Refactor**
- ✅ Cleanest architecture
- ✅ Best long-term extensibility
- ✅ Hot-reload, marketplace, community plugins
- ❌ 18-27 hours effort
- ❌ Major breaking changes

**Option B: Cherry-Pick Patterns**
- ✅ Faster (11-15 hours Phase 1)
- ✅ Less disruptive
- ✅ Keep current CLI structure
- ❌ Miss hot-reload, marketplace
- ❌ Less extensible

**Recommendation:** Start with Phase 1 (cherry-pick), evaluate after 2-3 weeks, then decide on full refactor

---

### 2. Configuration Migration
**Question:** Migrate YAML → TOML or keep YAML + add secrets?

**Option A: Full TOML Migration**
- ✅ Better comment preservation (tomlkit)
- ✅ Separate secrets (security)
- ✅ Plugin parameter registration
- ❌ Migration effort (3-4 hours)

**Option B: Keep YAML + Add Secrets**
- ✅ Less work (1 hour)
- ✅ No breaking changes
- ❌ YAML libs lose comments
- ❌ Less elegant

**Recommendation:** Migrate to TOML (worth 3-4 hours for long-term benefits)

---

### 3. Daemon vs CLI-Only
**Question:** Add daemon mode or stay purely CLI?

**Daemon Mode:**
- ✅ REST API enabled
- ✅ Background monitoring (clipboard, meetings, etc.)
- ✅ Telegram bot 24/7
- ✅ Integration with Home Assistant
- ❌ More complex architecture

**CLI-Only:**
- ✅ Simpler
- ✅ Current model (familiar)
- ❌ No REST API
- ❌ No background tasks
- ❌ Telegram bot requires manual start

**Recommendation:** Add daemon mode (Phase 2) - enables too many useful features to skip

---

### 4. REST API Surface
**Question:** Which endpoints to expose?

**Minimal:**
```
GET  /health
POST /links
POST /print
```

**Full:**
```
GET  /health
GET  /plugins
POST /plugins/reload
POST /links
POST /books
POST /papers
POST /print
POST /message/{plugin}
POST /broadcast
```

**Recommendation:** Start minimal, expand as use cases emerge

---

### 5. Platform-Specific Features
**Question:** Port Windows Registry monitoring or skip?

**Considerations:**
- Holocene development is primarily on Windows (Framework 13)
- Beelink U59 runs Proxmox (Linux)
- Meeting detection useful for activity tracking
- Could use cross-platform alternatives (psutil for process monitoring)

**Recommendation:** Port Windows version first (2-3 hours), add Linux support later if needed

---

## Code Snippets Worth Porting

### 1. URL Extraction (Ready to Copy-Paste)
```python
import re

# From Link Logger - battle-tested regex
url_pattern = re.compile(
    r'https?://(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}'
    r'\b(?:[-a-zA-Z0-9()@:%_\+.~#?&/=]*)'
)

hashtag_pattern = re.compile(r'#(\w+)')

def extract_links_and_tags(text: str) -> tuple[list[str], list[str]]:
    """Extract URLs and hashtags from text"""
    urls = url_pattern.findall(text)
    tags = hashtag_pattern.findall(text)
    return urls, tags

# Usage
text = "Check out https://arxiv.org/abs/1234 #ml #papers"
urls, tags = extract_links_and_tags(text)
# urls = ['https://arxiv.org/abs/1234']
# tags = ['ml', 'papers']
```

### 2. Background Task Execution (Qt-based)
```python
from PySide6.QtCore import QRunnable, QThreadPool, QObject, Signal, Slot
from typing import Callable, Any

class WorkerSignals(QObject):
    """Signals for worker thread"""
    finished = Signal()
    error = Signal(tuple)
    result = Signal(object)

class Worker(QRunnable):
    """Worker thread for background tasks"""
    def __init__(self, fn: Callable, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
            self.signals.result.emit(result)
        except Exception as e:
            self.signals.error.emit((e, traceback.format_exc()))
        finally:
            self.signals.finished.emit()

# Thread pool
thread_pool = QThreadPool()

def run_in_background(task: Callable, on_complete: Callable = None):
    """Run task in background, call on_complete when done"""
    worker = Worker(task)
    if on_complete:
        worker.signals.result.connect(on_complete)
    thread_pool.start(worker)

# Usage
def slow_task():
    # Long-running operation
    return result

def handle_result(data):
    # Update UI/database
    pass

run_in_background(slow_task, handle_result)
```

### 3. Channel-Based Messaging
```python
from typing import Any, Callable, Dict, Set
from dataclasses import dataclass

@dataclass
class Message:
    channel: str
    sender: str
    message: str
    data: Any = None

class ChannelManager:
    """Simple pub/sub messaging"""
    def __init__(self):
        self.channels: Dict[str, Set[Callable]] = {}

    def subscribe(self, channel: str, callback: Callable):
        """Subscribe to channel"""
        if channel not in self.channels:
            self.channels[channel] = set()
        self.channels[channel].add(callback)

    def unsubscribe(self, channel: str, callback: Callable):
        """Unsubscribe from channel"""
        if channel in self.channels:
            self.channels[channel].discard(callback)

    def publish(self, channel: str, sender: str, message: str, data: Any = None):
        """Publish message to channel"""
        if channel not in self.channels:
            return

        msg = Message(channel, sender, message, data)
        for callback in self.channels[channel]:
            callback(msg)

# Usage
channels = ChannelManager()

def handle_paper_added(msg: Message):
    doi = msg.data['doi']
    # Auto-extract citations
    pass

channels.subscribe("paper_added", handle_paper_added)
channels.publish("paper_added", "papers_cli", "new_paper", {"doi": "10.1234/abc"})
```

### 4. Secure Secrets Management
```python
import tomlkit
from pathlib import Path

def save_secret(config_dir: Path, key: str, value: str):
    """Save secret to secrets.toml with secure permissions"""
    secrets_file = config_dir / "secrets.toml"

    if secrets_file.exists():
        with open(secrets_file, 'r') as f:
            secrets = tomlkit.parse(f.read())
    else:
        secrets = tomlkit.document()

    secrets[key] = value

    # Write with restricted permissions (owner read/write only)
    with open(secrets_file, 'w') as f:
        f.write(tomlkit.dumps(secrets))

    secrets_file.chmod(0o600)  # rw-------

def get_secret(config_dir: Path, key: str) -> str:
    """Retrieve secret from secrets.toml"""
    secrets_file = config_dir / "secrets.toml"

    if not secrets_file.exists():
        raise FileNotFoundError("secrets.toml not found")

    with open(secrets_file, 'r') as f:
        secrets = tomlkit.parse(f.read())

    return secrets.get(key)

# Usage
config_dir = Path.home() / ".config" / "holocene"
save_secret(config_dir, "nanogpt_api_key", "sk-xxxxx")
api_key = get_secret(config_dir, "nanogpt_api_key")
```

---

## Comparison Matrix

| Pattern | Scissors Runner | Holocene Current | Integration Effort | Priority |
|---------|----------------|------------------|-------------------|----------|
| **Messaging** | Channel pub/sub | Direct calls | 4-6 hours | ⭐⭐⭐⭐⭐ |
| **Background Tasks** | QThreadPool | Blocking | 3-4 hours | ⭐⭐⭐⭐⭐ |
| **Config** | TOML + secrets | YAML (no secrets) | 3-4 hours | ⭐⭐⭐⭐ |
| **URL Extraction** | Regex | Basic | 1 hour | ⭐⭐⭐⭐ |
| **REST API** | Flask localhost | None | 4-6 hours | ⭐⭐⭐⭐ |
| **Telegram Bot** | Full plugin | None | 3-4 hours | ⭐⭐⭐⭐ |
| **Plugin System** | Full architecture | Modules | 18-27 hours | ⭐⭐⭐⭐⭐ |
| **Hot-Reload** | Supported | Restart only | 2-3 hours | ⭐⭐⭐ |
| **AV Monitoring** | Windows Registry | None | 2-3 hours | ⭐⭐⭐ |
| **Marketplace** | GitHub-based | None | 6-8 hours | ⭐⭐⭐ |

---

## Risk Assessment

### Low Risk (Safe to Port Immediately)
1. **URL extraction regex** - Drop-in replacement
2. **Secrets management** - Additive (doesn't break existing config)
3. **Background task helpers** - Wrapper functions (doesn't change CLI)

### Medium Risk (Requires Testing)
4. **Channel messaging** - Need to verify with current integrations
5. **REST API** - Need to ensure localhost-only security
6. **Telegram bot** - Need to test with actual bot token

### High Risk (Major Refactor)
7. **Plugin architecture** - Breaking change, requires careful migration
8. **TOML config migration** - Breaking change for users
9. **Daemon mode** - New operational model

**Recommendation:** Start with low-risk items, build confidence, then tackle higher-risk refactors

---

## Related Documents

- `holocene_design.md` - Overall Holocene architecture
- `docs/ROADMAP.md` - Current priorities and planning
- `docs/integration_strategy_framework.md` - Paid vs self-hosted decisions
- `design/architecture/operating_modes.md` - Autonomous vs on-demand design

---

## Next Steps

1. **Review this document** in architecture review session
2. **Prioritize patterns** to adopt (Phase 1 vs Phase 2 vs Phase 3)
3. **Create implementation tasks** for chosen patterns
4. **Prototype channel messaging** (lowest effort, highest value)
5. **Test background task execution** with LLM enrichment

---

**Last Updated:** 2025-11-19
**Status:** Draft - pending architecture review
**Estimated Total Integration Effort:** 42-75 hours (phased over 2-3 months)
