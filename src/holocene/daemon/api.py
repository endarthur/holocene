"""REST API Server for holod daemon.

Provides HTTP API for wmut CLI to communicate with holod running on rei.

Endpoints:
    GET  /status                       - Daemon status
    GET  /plugins                      - List all plugins
    GET  /plugins/<name>               - Get plugin details
    POST /plugins/<name>/enable        - Enable plugin
    POST /plugins/<name>/disable       - Disable plugin
    POST /channels/<channel>/publish   - Publish to channel
    GET  /channels/<channel>/history   - Get channel history
    GET  /books                        - List books
    GET  /books/<id>                   - Get book details
    POST /books                        - Add book
    GET  /links                        - List links
    GET  /links/<id>                   - Get link details
    POST /links                        - Add link
"""

import logging
import threading
import requests
from typing import Optional
from datetime import datetime

try:
    from flask import Flask, jsonify, request, session, redirect, render_template, send_file, abort
    from werkzeug.serving import make_server
    FLASK_AVAILABLE = True
except ImportError:
    Flask = None
    jsonify = None
    request = None
    session = None
    redirect = None
    render_template = None
    make_server = None
    FLASK_AVAILABLE = False

from ..core import HoloceneCore
from ..core.plugin_registry import PluginRegistry

logger = logging.getLogger(__name__)


def require_auth(f):
    """Decorator to require authentication for endpoints.

    Checks if user is authenticated via:
    1. Session cookie (from magic link login)
    2. API token (Authorization: Bearer hlc_...)

    Returns 401 Unauthorized if not authenticated.
    """
    from functools import wraps

    @wraps(f)
    def decorated_function(self, *args, **kwargs):
        # Method 1: Check session authentication (from magic link login)
        if 'user_id' in session:
            # User authenticated via session, proceed
            return f(self, *args, **kwargs)

        # Method 2: Check API token authentication
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]  # Remove 'Bearer ' prefix

            # Validate token
            cursor = self.core.db.conn.cursor()
            cursor.execute("""
                SELECT
                    api_tokens.id,
                    api_tokens.user_id,
                    api_tokens.revoked_at,
                    users.telegram_username
                FROM api_tokens
                JOIN users ON api_tokens.user_id = users.id
                WHERE api_tokens.token = ?
            """, (token,))

            token_row = cursor.fetchone()

            if token_row:
                token_id, user_id, revoked_at, username = token_row

                # Check if token is revoked
                if revoked_at:
                    logger.warning(f"Revoked API token used: {token_id} by user {user_id}")
                    return jsonify({"error": "Token has been revoked"}), 401

                # Token is valid! Update last_used_at
                from datetime import datetime
                cursor.execute("""
                    UPDATE api_tokens
                    SET last_used_at = ?
                    WHERE id = ?
                """, (datetime.now().isoformat(), token_id))
                self.core.db.conn.commit()

                logger.debug(f"API token authenticated: user {user_id} ({username})")

                # Store user info in request context for endpoint to access if needed
                request.user_id = user_id
                request.username = username

                # Proceed with the request
                return f(self, *args, **kwargs)

        # No valid authentication found
        logger.warning(f"Unauthorized access attempt to {request.path} from {request.remote_addr}")
        return jsonify({"error": "Authentication required"}), 401

    return decorated_function


class APIServer:
    """REST API server for holod daemon.

    Runs Flask server in background thread on port 5555.
    Provides API for wmut CLI to communicate with holod.
    """

    def __init__(self, core: HoloceneCore, registry: PluginRegistry, port: int = 5555):
        """Initialize API server.

        Args:
            core: HoloceneCore instance
            registry: PluginRegistry instance
            port: Port to listen on (default: 5555)
        """
        if not FLASK_AVAILABLE:
            raise ImportError("Flask is required for REST API. Install with: pip install flask")

        self.core = core
        self.registry = registry
        self.port = port

        # Flask app
        # Use __name__ so Flask can find templates/ directory relative to this module
        self.app = Flask(__name__)

        # Configure secret key for sessions (persistent across restarts)
        self.app.secret_key = self._get_or_create_secret_key()

        # Configure session lifetime (7 days)
        from datetime import timedelta
        self.app.permanent_session_lifetime = timedelta(days=7)

        self._setup_routes()

        # Server state
        self.server = None
        self.server_thread = None
        self.running = False
        self.started_at = None

        logger.info(f"API server initialized on port {port}")

    def _get_or_create_secret_key(self):
        """Get or create persistent Flask secret key.

        Stores the secret key in database so sessions survive daemon restarts.
        """
        import secrets

        cursor = self.core.db.conn.cursor()

        # Create settings table if it doesn't exist
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daemon_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        # Try to load existing secret key
        cursor.execute("SELECT value FROM daemon_settings WHERE key = 'flask_secret_key'")
        row = cursor.fetchone()

        if row:
            logger.debug("Loaded persistent Flask secret key from database")
            return row[0]

        # Generate new secret key
        secret_key = secrets.token_hex(32)  # 256-bit key
        now = datetime.now().isoformat()

        cursor.execute("""
            INSERT INTO daemon_settings (key, value, created_at, updated_at)
            VALUES (?, ?, ?, ?)
        """, ('flask_secret_key', secret_key, now, now))

        self.core.db.conn.commit()
        logger.info("Generated new persistent Flask secret key")

        return secret_key

    def _setup_routes(self):
        """Setup Flask routes."""

        # Root endpoint
        self.app.route("/", methods=["GET"])(self._root)

        # Auth endpoints
        self.app.route("/auth/login", methods=["GET"])(self._auth_login)
        self.app.route("/auth/logout", methods=["POST"])(self._auth_logout)
        self.app.route("/auth/status", methods=["GET"])(self._auth_status)

        # Web terminal
        self.app.route("/term", methods=["GET"])(self._term)

        # Status endpoints
        self.app.route("/status", methods=["GET"])(self._status)
        self.app.route("/health", methods=["GET"])(self._health)

        # Plugin endpoints
        self.app.route("/plugins", methods=["GET"])(self._list_plugins)
        self.app.route("/plugins/<name>", methods=["GET"])(self._get_plugin)
        self.app.route("/plugins/<name>/enable", methods=["POST"])(self._enable_plugin)
        self.app.route("/plugins/<name>/disable", methods=["POST"])(self._disable_plugin)

        # Channel endpoints
        self.app.route("/channels/<channel>/publish", methods=["POST"])(self._publish_to_channel)
        self.app.route("/channels/<channel>/history", methods=["GET"])(self._channel_history)
        self.app.route("/channels", methods=["GET"])(self._list_channels)

        # Book endpoints
        self.app.route("/books", methods=["GET", "POST"])(self._books)
        self.app.route("/books/<int:book_id>", methods=["GET"])(self._get_book)

        # Link endpoints
        self.app.route("/links", methods=["GET", "POST"])(self._links)
        self.app.route("/links/<int:link_id>", methods=["GET"])(self._get_link)

        # Archive viewer endpoints (local monolith archives)
        self.app.route("/mono/<int:link_id>", methods=["GET"])(self._mono_latest)
        self.app.route("/mono/<int:link_id>/latest", methods=["GET"])(self._mono_latest)
        self.app.route("/mono/<int:link_id>/first", methods=["GET"])(self._mono_first)
        self.app.route("/mono/<int:link_id>/<int:index>", methods=["GET"])(self._mono_index)
        self.app.route("/snapshot/<int:snapshot_id>", methods=["GET"])(self._snapshot_by_id)

        # ArchiveBox proxy endpoints
        self.app.route("/box/<snapshot_id>", methods=["GET"])(self._box_snapshot)

        # Telegram Mini App endpoints
        self.app.route("/webapp", methods=["GET"])(self._webapp_index)
        self.app.route("/webapp/", methods=["GET"])(self._webapp_index)
        self.app.route("/webapp/stats", methods=["GET"])(self._webapp_stats)
        self.app.route("/webapp/conversations", methods=["GET"])(self._webapp_conversations)
        self.app.route("/webapp/papers", methods=["GET"])(self._webapp_papers)
        self.app.route("/webapp/books", methods=["GET"])(self._webapp_books)
        self.app.route("/webapp/links", methods=["GET"])(self._webapp_links)

        # Error handlers
        self.app.errorhandler(404)(self._not_found)
        self.app.errorhandler(500)(self._internal_error)

    # Root endpoint

    def _root(self):
        """GET / - Root endpoint with API info."""
        return """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Holocene API</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            max-width: 800px;
            margin: 50px auto;
            padding: 20px;
            background: #f5f5f5;
        }
        .card {
            background: white;
            border-radius: 8px;
            padding: 30px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        h1 {
            color: #2c3e50;
            margin-top: 0;
        }
        .badge {
            display: inline-block;
            padding: 4px 8px;
            background: #27ae60;
            color: white;
            border-radius: 4px;
            font-size: 12px;
            margin-left: 10px;
        }
        .links {
            list-style: none;
            padding: 0;
        }
        .links li {
            margin: 10px 0;
        }
        .links a {
            color: #3498db;
            text-decoration: none;
            padding: 8px 12px;
            background: #ecf0f1;
            border-radius: 4px;
            display: inline-block;
        }
        .links a:hover {
            background: #3498db;
            color: white;
        }
        .note {
            color: #7f8c8d;
            font-size: 14px;
            margin-top: 20px;
            padding-top: 20px;
            border-top: 1px solid #ecf0f1;
        }
    </style>
</head>
<body>
    <div class="card">
        <h1>Holocene API <span class="badge">ONLINE</span></h1>
        <p>Personal knowledge management and productivity tracking system.</p>

        <h3>Quick Links:</h3>
        <ul class="links">
            <li><a href="/webapp">🔮 Laney Mini App</a></li>
            <li><a href="/term">Web Terminal</a></li>
            <li><a href="/health">Health Check</a></li>
            <li><a href="/status">API Status</a></li>
            <li><a href="/auth/status">Auth Status</a></li>
        </ul>

        <div class="note">
            <strong>Authentication Required:</strong> Most endpoints require authentication.
            Use <code>/login</code> command in Telegram to get a magic link.
        </div>
    </div>
</body>
</html>
"""

    # Auth endpoints

    def _auth_login(self):
        """GET /auth/login?token=<token> - Magic link login endpoint.

        Validates token and creates session.
        """
        try:
            # Get token from query params
            token = request.args.get('token')
            if not token:
                return jsonify({"error": "Missing token parameter"}), 400

            # Ignore link preview bots (Telegram, Discord, Slack, etc.)
            # These prefetch links to generate previews, consuming single-use tokens
            user_agent = request.headers.get('User-Agent', '').lower()
            bot_indicators = ['telegrambot', 'discordbot', 'slackbot', 'facebookexternalhit',
                            'twitterbot', 'whatsapp', 'bot', 'preview', 'crawler']
            if any(indicator in user_agent for indicator in bot_indicators):
                logger.debug(f"Ignoring preview bot request: {user_agent}")
                # Return a simple page that doesn't consume the token
                return """
<!DOCTYPE html>
<html>
<head><title>Login - Holocene</title></head>
<body>
    <h1>🔐 Holocene Login</h1>
    <p>Click the link to log in.</p>
</body>
</html>
"""

            cursor = self.core.db.conn.cursor()

            # Find token in database
            cursor.execute("""
                SELECT
                    auth_tokens.id,
                    auth_tokens.user_id,
                    auth_tokens.expires_at,
                    auth_tokens.used_at,
                    users.telegram_username,
                    users.telegram_user_id
                FROM auth_tokens
                JOIN users ON auth_tokens.user_id = users.id
                WHERE auth_tokens.token = ?
            """, (token,))

            token_row = cursor.fetchone()

            if not token_row:
                logger.warning(f"Invalid login attempt with unknown token: {token[:10]}...")
                return jsonify({"error": "Invalid or expired token"}), 401

            token_id, user_id, expires_at, used_at, username, tg_id = token_row

            # Check if already used
            if used_at:
                logger.warning(f"Login attempt with already-used token {token_id} by user {user_id}")
                return jsonify({"error": "Token already used"}), 401

            # Check if expired
            from datetime import datetime
            expires_dt = datetime.fromisoformat(expires_at)
            if datetime.now() > expires_dt:
                logger.warning(f"Login attempt with expired token {token_id} by user {user_id}")
                return jsonify({"error": "Token expired"}), 401

            # Mark token as used
            cursor.execute("""
                UPDATE auth_tokens
                SET used_at = ?, ip_address = ?, user_agent = ?
                WHERE id = ?
            """, (
                datetime.now().isoformat(),
                request.remote_addr,
                request.headers.get('User-Agent', ''),
                token_id
            ))
            self.core.db.conn.commit()

            # Notify Telegram bot that token was used (for message editing)
            try:
                telegram_plugin = self.registry.get_plugin('telegram_bot')
                if telegram_plugin and hasattr(telegram_plugin, 'mark_login_used'):
                    telegram_plugin.mark_login_used(token, request.remote_addr)
            except Exception as e:
                logger.warning(f"Failed to notify Telegram bot of login: {e}")

            # Create session
            session.permanent = True  # Use configured lifetime (7 days)
            session['user_id'] = user_id
            session['telegram_user_id'] = tg_id
            session['telegram_username'] = username
            session['logged_in_at'] = datetime.now().isoformat()

            # Update last_login_at
            cursor.execute("""
                UPDATE users
                SET last_login_at = ?
                WHERE id = ?
            """, (datetime.now().isoformat(), user_id))
            self.core.db.conn.commit()

            logger.info(f"User {user_id} (telegram: {tg_id}) logged in successfully")

            # Redirect to dashboard (or return JSON for API clients)
            if request.headers.get('Accept') == 'application/json':
                return jsonify({
                    "status": "logged_in",
                    "user_id": user_id,
                    "username": username
                })
            else:
                # Show success page
                return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Logged In - Holocene</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            max-width: 800px;
            margin: 50px auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .card {{
            background: white;
            border-radius: 8px;
            padding: 30px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #2c3e50;
            margin-top: 0;
        }}
        .success {{
            color: #27ae60;
            font-size: 48px;
            margin-bottom: 10px;
        }}
        .info {{
            background: #ecf0f1;
            padding: 15px;
            border-radius: 4px;
            margin: 20px 0;
        }}
        .info dt {{
            font-weight: bold;
            color: #7f8c8d;
            font-size: 12px;
            text-transform: uppercase;
            margin-bottom: 5px;
        }}
        .info dd {{
            margin: 0 0 15px 0;
            color: #2c3e50;
        }}
        .links {{
            list-style: none;
            padding: 0;
        }}
        .links li {{
            margin: 10px 0;
        }}
        .links a {{
            color: #3498db;
            text-decoration: none;
            padding: 8px 12px;
            background: #ecf0f1;
            border-radius: 4px;
            display: inline-block;
        }}
        .links a:hover {{
            background: #3498db;
            color: white;
        }}
        .note {{
            color: #7f8c8d;
            font-size: 14px;
            margin-top: 20px;
            padding-top: 20px;
            border-top: 1px solid #ecf0f1;
        }}
    </style>
</head>
<body>
    <div class="card">
        <div class="success">✅</div>
        <h1>Successfully Logged In</h1>
        <p>Welcome to the Holocene API. Your session is now active.</p>

        <div class="info">
            <dl>
                <dt>User</dt>
                <dd>{username or '(no username)'}</dd>

                <dt>Telegram ID</dt>
                <dd>{tg_id}</dd>

                <dt>Session Expires</dt>
                <dd>7 days from now</dd>
            </dl>
        </div>

        <h3>Test API Endpoints:</h3>
        <ul class="links">
            <li><a href="/auth/status">🔐 Check Auth Status</a></li>
            <li><a href="/status">📊 API Status</a></li>
            <li><a href="/plugins">🔌 List Plugins</a></li>
            <li><a href="/books?limit=10">📚 List Books</a></li>
            <li><a href="/links?limit=10">🔗 List Links</a></li>
            <li><a href="/channels">📡 List Channels</a></li>
        </ul>

        <div class="note">
            <strong>Note:</strong> holod is currently API-only. All endpoints return JSON.
            A web dashboard is planned for future development.
        </div>
    </div>
</body>
</html>
"""

        except Exception as e:
            logger.error(f"Error in /auth/login: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    def _auth_logout(self):
        """POST /auth/logout - Logout endpoint."""
        try:
            # Clear session
            session.clear()

            return jsonify({"status": "logged_out"})

        except Exception as e:
            logger.error(f"Error in /auth/logout: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    def _auth_status(self):
        """GET /auth/status - Check authentication status."""
        try:
            if 'user_id' in session:
                return jsonify({
                    "authenticated": True,
                    "user_id": session['user_id'],
                    "username": session.get('telegram_username'),
                    "logged_in_at": session.get('logged_in_at')
                })
            else:
                return jsonify({
                    "authenticated": False
                })

        except Exception as e:
            logger.error(f"Error in /auth/status: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    def _term(self):
        """GET /term - Web-based terminal interface."""
        return render_template('terminal.html')

    def _term_old(self):
        """OLD: GET /term - Web-based terminal interface (embedded HTML version)."""
        return """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Holocene Terminal</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/xterm@5.3.0/css/xterm.css" />
    <style>
        body {
            margin: 0;
            padding: 0;
            background: #1e1e1e;
            font-family: 'Fira Code', 'JetBrains Mono', 'Consolas', monospace;
            overflow: hidden;
        }
        #container {
            width: 100vw;
            height: 100vh;
            display: flex;
            flex-direction: column;
        }
        #header {
            background: #2d2d2d;
            color: #cccccc;
            padding: 8px 16px;
            font-size: 14px;
            border-bottom: 1px solid #3e3e3e;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        #header .title {
            font-weight: bold;
        }
        #header .status {
            font-size: 12px;
            color: #4ec9b0;
        }
        #terminal {
            flex: 1;
            padding: 10px;
        }
        .xterm {
            height: 100%;
        }
        .xterm-viewport {
            background-color: #1e1e1e !important;
        }
        /* Scrollbar theming */
        ::-webkit-scrollbar {
            width: 10px;
            height: 10px;
        }
        ::-webkit-scrollbar-track {
            background: #1e1e1e;
        }
        ::-webkit-scrollbar-thumb {
            background: #3e3e3e;
            border-radius: 5px;
        }
        ::-webkit-scrollbar-thumb:hover {
            background: #4e4e4e;
        }
        /* Firefox scrollbar */
        * {
            scrollbar-width: thin;
            scrollbar-color: #3e3e3e #1e1e1e;
        }
    </style>
</head>
<body>
    <div id="container">
        <div id="header">
            <span class="title">Holocene Terminal</span>
            <span class="status" id="status">Connecting...</span>
        </div>
        <div id="terminal"></div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/xterm@5.3.0/lib/xterm.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/xterm-addon-fit@0.8.0/lib/xterm-addon-fit.js"></script>
    <script type="module">
        // Import xterm-kit utilities from koma repo (v1.1.2)
        import { parse as parseArgs, hasHelp, showHelp } from 'https://cdn.jsdelivr.net/gh/endarthur/koma@v1.1.2/src/lib/xterm-kit/argparse.js';
        import { showError, showSuccess, showInfo, formatSize, formatDate } from 'https://cdn.jsdelivr.net/gh/endarthur/koma@v1.1.2/src/lib/xterm-kit/output.js';
        import { Table, renderTable } from 'https://cdn.jsdelivr.net/gh/endarthur/koma@v1.1.2/src/lib/xterm-kit/table.js';
        import { Spinner } from 'https://cdn.jsdelivr.net/gh/endarthur/koma@v1.1.2/src/lib/xterm-kit/progress.js';
        import { Autocomplete, createTabHandler } from 'https://cdn.jsdelivr.net/gh/endarthur/koma@v1.1.2/src/lib/xterm-kit/autocomplete.js';
        import { CommandRegistry } from 'https://cdn.jsdelivr.net/gh/endarthur/koma@v1.1.2/src/lib/xterm-kit/command-registry.js';
        import { Pager } from 'https://cdn.jsdelivr.net/gh/endarthur/koma@v1.1.2/src/lib/xterm-kit/pager.js';
        import { Box, renderBox } from 'https://cdn.jsdelivr.net/gh/endarthur/koma@v1.1.2/src/lib/xterm-kit/box.js';
        import { setTheme, olivineTheme } from 'https://cdn.jsdelivr.net/gh/endarthur/koma@v1.1.2/src/lib/xterm-kit/themes.js';

        // Terminal setup with xterm-kit theme
        const term = new Terminal({
            cursorBlink: true,
            fontSize: 14,
            fontFamily: 'Fira Code, JetBrains Mono, Consolas, monospace'
        });

        const fitAddon = new FitAddon.FitAddon();
        term.loadAddon(fitAddon);
        term.open(document.getElementById('terminal'));

        // Apply xterm-kit olivine theme (phosphor green terminal aesthetic)
        setTheme(olivineTheme);
        term.options.theme = olivineTheme;

        fitAddon.fit();
        term.focus(); // Auto-focus terminal on load

        // Resize handler
        window.addEventListener('resize', () => {
            fitAddon.fit();
        });

        // Terminal state
        let currentLine = '';
        let cursorPos = 0; // Cursor position in current line
        let commandHistory = [];
        let historyIndex = -1;
        let apiToken = sessionStorage.getItem('holocene_api_token');

        // Command registry with full metadata
        const registry = new CommandRegistry();

        // Register all commands
        registry.register('help', {
            description: 'Show all available commands',
            category: 'general'
        });

        registry.register('whoami', {
            description: 'Show current user',
            category: 'auth'
        });

        registry.register('token', {
            description: 'Set API token',
            category: 'auth'
        });

        registry.register('auth', {
            description: 'Authentication management',
            category: 'auth',
            subcommands: {
                'status': 'Check authentication status'
            }
        });

        registry.register('books', {
            description: 'Book library management',
            category: 'library',
            subcommands: {
                'list': 'List books'
            },
            schema: {
                description: 'Manage your book library',
                flags: {
                    help: { short: 'h', description: 'Show help' }
                }
            }
        });

        registry.register('links', {
            description: 'Link management',
            category: 'library',
            subcommands: {
                'list': 'List links'
            }
        });

        registry.register('ask', {
            description: 'Ask the AI Librarian',
            category: 'ai',
            schema: {
                description: 'Query your library using natural language',
                positional: { description: '<query>' },
                flags: {
                    verbose: { short: 'v', description: 'Verbose output' }
                }
            }
        });

        registry.register('status', {
            description: 'Get daemon status',
            category: 'system'
        });

        registry.register('clear', {
            description: 'Clear terminal',
            category: 'general'
        });

        // Tab completion using registry (v1.1.2+ auto-extracts subcommands!)
        const completer = new Autocomplete({ registry });

        // ANSI color codes
        const colors = {
            reset: '\\x1b[0m',
            bright: '\\x1b[1m',
            dim: '\\x1b[2m',
            red: '\\x1b[31m',
            green: '\\x1b[32m',
            yellow: '\\x1b[33m',
            blue: '\\x1b[34m',
            magenta: '\\x1b[35m',
            cyan: '\\x1b[36m',
            white: '\\x1b[37m'
        };

        // Write with color support
        function write(text, color = '') {
            if (color) {
                term.write(color + text + colors.reset);
            } else {
                term.write(text);
            }
        }

        function writeln(text, color = '') {
            write(text + '\\r\\n', color);
        }

        // ASCII art banner
        function showBanner() {
            writeln('');
            writeln(' ██╗  ██╗ ██████╗ ██╗      ██████╗  ██████╗███████╗███╗   ██╗███████╗', colors.cyan);
            writeln(' ██║  ██║██╔═══██╗██║     ██╔═══██╗██╔════╝██╔════╝████╗  ██║██╔════╝', colors.cyan);
            writeln(' ███████║██║   ██║██║     ██║   ██║██║     █████╗  ██╔██╗ ██║█████╗  ', colors.cyan);
            writeln(' ██╔══██║██║   ██║██║     ██║   ██║██║     ██╔══╝  ██║╚██╗██║██╔══╝  ', colors.cyan);
            writeln(' ██║  ██║╚██████╔╝███████╗╚██████╔╝╚██████╗███████╗██║ ╚████║███████╗', colors.cyan);
            writeln(' ╚═╝  ╚═╝ ╚═════╝ ╚══════╝ ╚═════╝  ╚═════╝╚══════╝╚═╝  ╚═══╝╚══════╝', colors.cyan);
            writeln('');
            writeln(' Your personal geological record of the present', colors.dim);
            writeln('');
            writeln(' Type ' + colors.yellow + 'help' + colors.reset + ' for available commands', colors.dim);
            writeln('');
        }

        // API call helper
        async function apiCall(endpoint, options = {}) {
            const headers = {
                'Content-Type': 'application/json',
                ...(options.headers || {})
            };

            if (apiToken) {
                headers['Authorization'] = `Bearer ${apiToken}`;
            }

            try {
                const response = await fetch(endpoint, {
                    ...options,
                    headers
                });

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.error || `HTTP ${response.status}`);
                }

                return data;
            } catch (error) {
                throw error;
            }
        }

        // Command parser
        async function executeCommand(cmd) {
            const parts = cmd.trim().split(/\\s+/);
            const command = parts[0].toLowerCase();
            const args = parts.slice(1);

            try {
                switch (command) {
                    case 'help':
                        showAllCommands();
                        break;

                    case 'auth':
                        if (args[0] === 'status') {
                            await authStatus();
                        } else {
                            writeln('Usage: auth status', colors.red);
                        }
                        break;

                    case 'books':
                        // Check for --help flag
                        if (hasHelp(args)) {
                            const schema = registry.getSchema('books');
                            showHelp('books', args, schema, term);
                        } else if (args[0] === 'list' || !args[0]) {
                            await listBooks(args.slice(1));  // Pass args after 'list'
                        } else {
                            writeln('Usage: books list [limit|all]', colors.red);
                        }
                        break;

                    case 'links':
                        if (args[0] === 'list' || !args[0]) {
                            await listLinks(args.slice(1));  // Pass args after 'list'
                        } else {
                            writeln('Usage: links list [limit|all]', colors.red);
                        }
                        break;

                    case 'ask':
                        // Check for --help flag
                        if (hasHelp(args)) {
                            const schema = registry.getSchema('ask');
                            showHelp('ask', args, schema, term);
                        } else if (args.length === 0) {
                            writeln('Usage: ask <your question>', colors.red);
                        } else {
                            await ask(args.join(' '));
                        }
                        break;

                    case 'status':
                        await getStatus();
                        break;

                    case 'clear':
                        term.clear();
                        break;

                    case 'whoami':
                        await whoami();
                        break;

                    case 'token':
                        if (args[0]) {
                            setToken(args[0]);
                        } else {
                            writeln('Usage: token <your-api-token>', colors.red);
                        }
                        break;

                    case '':
                        // Empty command, just show new prompt
                        break;

                    default:
                        writeln(`Unknown command: ${command}`, colors.red);
                        writeln('Type ' + colors.bright + 'help' + colors.reset + ' for available commands', colors.dim);
                }
            } catch (error) {
                writeln(`Error: ${error.message}`, colors.red);
            }

            showPrompt();
        }

        // Utility: Clickable URL
        function clickableUrl(url, text) {
            // OSC 8 hyperlink support in xterm.js
            return '\\x1b]8;;' + url + '\\x1b\\\\' + (text || url) + '\\x1b]8;;\\x1b\\\\';
        }

        // Command implementations
        function showAllCommands() {
            // Build help content
            let content = 'Available Commands:\n\n';

            // Get commands grouped by category from registry
            const byCategory = registry.getByCategory();
            const categoryOrder = ['general', 'auth', 'library', 'ai', 'system'];

            categoryOrder.forEach(category => {
                const commands = byCategory[category];
                if (!commands || commands.length === 0) return;

                // Category header
                const categoryName = category.charAt(0).toUpperCase() + category.slice(1);
                content += `${categoryName}:\n`;

                commands.forEach(cmd => {
                    const subcommands = registry.getSubcommands(cmd.name);
                    let cmdLine = `  ${cmd.name}`;

                    // Add subcommand hints
                    if (subcommands) {
                        const subNames = Object.keys(subcommands);
                        cmdLine += ' <' + subNames.join('|') + '>';
                    }

                    // Pad and add description
                    const padding = ' '.repeat(Math.max(1, 28 - cmdLine.length));
                    content += `${cmdLine}${padding}${cmd.description}\n`;
                });

                content += '\n';
            });

            content += 'Examples:\n';
            content += '  books list         # Show first 20 books\n';
            content += '  books list 50      # Show first 50 books\n';
            content += '  books list all     # Show all books\n\n';
            content += 'Generate a token: holo auth token create --name "Web Terminal"';

            // Render in a box for prettier output
            writeln('');
            renderBox(term, {
                title: 'Holocene Terminal Help',
                content: content,
                style: 'rounded',
                padding: 1
            });
            writeln('');
        }

        async function whoami() {
            if (!apiToken) {
                writeln('');
                writeln('[!] Not authenticated', colors.red);
                writeln('');
                return;
            }

            try {
                const data = await apiCall('/auth/status');
                writeln('');
                if (data.username) {
                    writeln(colors.green + data.username + colors.reset, '');
                } else {
                    writeln(colors.dim + 'authenticated (no username)' + colors.reset, '');
                }
                writeln('');
            } catch (error) {
                writeln('');
                writeln('[ERROR] ' + error.message, colors.red);
                writeln('');
            }
        }

        async function authStatus() {
            if (!apiToken) {
                writeln('Not authenticated. Use: token <your-token>', colors.red);
                return;
            }

            const data = await apiCall('/auth/status');
            writeln('');
            writeln(colors.green + '[OK] Authenticated' + colors.reset, '');
            if (data.username) {
                writeln(`  User: ${data.username}`, colors.dim);
            }
            writeln('');
        }

        async function listBooks(args = []) {
            try {
                // Parse limit argument
                let limit = 20;  // Default
                if (args.length > 0) {
                    if (args[0] === 'all') {
                        limit = Infinity;
                    } else {
                        const parsed = parseInt(args[0]);
                        if (!isNaN(parsed) && parsed > 0) {
                            limit = parsed;
                        }
                    }
                }

                const spinner = new Spinner(term);
                spinner.start('Fetching books...');
                const data = await apiCall('/books');
                spinner.stop();

                if (data.books && data.books.length > 0) {
                    const booksToShow = limit === Infinity ? data.books : data.books.slice(0, limit);

                    // Use Pager for large lists (>30 books)
                    if (booksToShow.length > 30) {
                        // Build content for pager
                        let content = `Books (${booksToShow.length} of ${data.books.length}):\n\n`;

                        booksToShow.forEach((book, idx) => {
                            const num = String(idx + 1).padStart(4, ' ');
                            const title = (book.title || 'Untitled').padEnd(50, ' ').slice(0, 50);
                            const author = (book.author || '(no author)').slice(0, 30);
                            content += `${num}  ${title}  ${author}\n`;
                        });

                        content += `\nUse arrow keys to navigate, q to quit`;

                        const pager = new Pager(term);
                        await pager.show(content);
                    } else {
                        // Normal table output for small lists
                        writeln('');
                        writeln(colors.bright + `Books (showing ${booksToShow.length} of ${data.books.length}):` + colors.reset, '');
                        writeln('');

                        const table = new Table({
                            columns: ['#', 'Title', 'Author'],
                            align: ['right', 'left', 'left']
                        });

                        booksToShow.forEach((book, idx) => {
                            table.addRow([
                                String(idx + 1),
                                book.title || 'Untitled',
                                book.author || '(no author)'
                            ]);
                        });

                        table.render(term);

                        if (limit !== Infinity && data.books.length > limit) {
                            writeln('');
                            writeln(`  ${colors.dim}... and ${data.books.length - limit} more. Use 'books list all' to see all.${colors.reset}`, '');
                        }
                        writeln('');
                    }
                } else {
                    writeln('');
                    showInfo(term, 'No books found.');
                    writeln('');
                }
            } catch (error) {
                writeln('');
                showError(term, 'books', error.message);
                writeln('');
            }
        }

        async function listLinks(args = []) {
            try {
                // Parse limit argument
                let limit = 20;  // Default
                if (args.length > 0) {
                    if (args[0] === 'all') {
                        limit = Infinity;
                    } else {
                        const parsed = parseInt(args[0]);
                        if (!isNaN(parsed) && parsed > 0) {
                            limit = parsed;
                        }
                    }
                }

                const spinner = new Spinner(term);
                spinner.start('Fetching links...');
                const data = await apiCall('/links');
                spinner.stop();

                if (data.links && data.links.length > 0) {
                    const linksToShow = limit === Infinity ? data.links : data.links.slice(0, limit);

                    writeln('');
                    writeln(colors.bright + `Links (showing ${linksToShow.length} of ${data.links.length}):` + colors.reset, '');
                    writeln('');

                    const table = new Table({
                        columns: ['#', 'Title', 'URL'],
                        align: ['right', 'left', 'left']
                    });

                    linksToShow.forEach((link, idx) => {
                        const url = link.url || '';
                        const clickableURL = url ? clickableUrl(url, url.slice(0, 60) + (url.length > 60 ? '...' : '')) : '';

                        table.addRow([
                            String(idx + 1),
                            link.title || 'Untitled',
                            clickableURL
                        ]);
                    });

                    table.render(term);

                    if (limit !== Infinity && data.links.length > limit) {
                        writeln('');
                        writeln(`  ${colors.dim}... and ${data.links.length - limit} more. Use 'links list all' to see all.${colors.reset}`, '');
                    }
                    writeln('');
                } else {
                    writeln('');
                    showInfo(term, 'No links found.');
                    writeln('');
                }
            } catch (error) {
                writeln('');
                showError(term, 'links', error.message);
                writeln('');
            }
        }

        async function ask(query) {
            writeln('');
            writeln(`Asking AI Librarian: "${query}"...`, colors.dim);
            writeln('');
            writeln('[This feature will be implemented when /ask API endpoint is available]', colors.yellow);
            writeln('');
        }

        async function getStatus() {
            try {
                const spinner = new Spinner(term);
                spinner.start('Fetching status...');
                const data = await apiCall('/status');
                spinner.stop();

                writeln('');
                writeln(colors.bright + 'Holod Status:' + colors.reset, '');
                writeln('');
                writeln(`  Daemon: ${colors.green}Running${colors.reset}`, '');
                writeln(`  Plugins: ${data.plugins?.length || 0} loaded`, colors.dim);
                writeln('');
            } catch (error) {
                writeln('');
                showError(term, 'status', error.message);
                writeln('');
            }
        }

        function setToken(token) {
            apiToken = token;
            sessionStorage.setItem('holocene_api_token', token);
            document.getElementById('status').textContent = 'Authenticated';
            document.getElementById('status').style.color = '#4ec9b0';
            writeln('');
            writeln(colors.green + '[OK] API token saved' + colors.reset, '');
            writeln('');
        }

        // Prompt
        function showPrompt() {
            write('\\r\\n' + colors.green + 'holo' + colors.reset + colors.dim + '@' + colors.reset + colors.cyan + 'web' + colors.reset + ' $ ');
        }

        // Tab completion
        // Tab completion handler using xterm-kit
        const state = { currentLine: '', cursorPos: 0 };
        const handleTab = createTabHandler(term, completer, state, (line) => {
            // Redraw prompt + line
            term.write('\\r\\x1b[K\\x1b[32mholo\\x1b[0m\\x1b[2m@\\x1b[0m\\x1b[36mweb\\x1b[0m $ ' + line);
        });

        // Input handling
        term.onData(data => {
            const code = data.charCodeAt(0);

            // Handle special keys
            if (code === 13) { // Enter
                term.write('\\r\\n');
                if (currentLine.trim()) {
                    commandHistory.push(currentLine);
                    historyIndex = commandHistory.length;
                    executeCommand(currentLine);
                } else {
                    showPrompt();
                }
                currentLine = '';
                cursorPos = 0;
            } else if (code === 127) { // Backspace
                if (cursorPos > 0) {
                    // Delete character before cursor
                    currentLine = currentLine.slice(0, cursorPos - 1) + currentLine.slice(cursorPos);
                    cursorPos--;

                    // Redraw line from cursor position
                    term.write('\\b' + currentLine.slice(cursorPos) + ' ');
                    // Move cursor back to position
                    for (let i = 0; i < currentLine.length - cursorPos + 1; i++) {
                        term.write('\\b');
                    }
                }
            } else if (code === 9) { // Tab
                // Sync state before calling handleTab
                state.currentLine = currentLine;
                state.cursorPos = cursorPos;
                handleTab();
                // Sync state back after handleTab
                currentLine = state.currentLine;
                cursorPos = state.cursorPos;
            } else if (code === 27) { // Escape sequences (arrows)
                if (data === '\\x1b[A') { // Up arrow - history
                    if (historyIndex > 0) {
                        // Clear current line
                        term.write('\\r\\x1b[K');
                        showPrompt();
                        historyIndex--;
                        currentLine = commandHistory[historyIndex];
                        cursorPos = currentLine.length;
                        term.write(currentLine);
                    }
                } else if (data === '\\x1b[B') { // Down arrow - history
                    if (historyIndex < commandHistory.length - 1) {
                        // Clear current line
                        term.write('\\r\\x1b[K');
                        showPrompt();
                        historyIndex++;
                        currentLine = commandHistory[historyIndex];
                        cursorPos = currentLine.length;
                        term.write(currentLine);
                    } else if (historyIndex === commandHistory.length - 1) {
                        // Clear current line
                        term.write('\\r\\x1b[K');
                        showPrompt();
                        historyIndex = commandHistory.length;
                        currentLine = '';
                        cursorPos = 0;
                    }
                } else if (data === '\\x1b[C') { // Right arrow - move cursor right
                    if (cursorPos < currentLine.length) {
                        cursorPos++;
                        term.write('\\x1b[C'); // Move cursor right
                    }
                } else if (data === '\\x1b[D') { // Left arrow - move cursor left
                    if (cursorPos > 0) {
                        cursorPos--;
                        term.write('\\x1b[D'); // Move cursor left
                    }
                } else if (data === '\\x1b[H') { // Home - move to start
                    while (cursorPos > 0) {
                        cursorPos--;
                        term.write('\\x1b[D');
                    }
                } else if (data === '\\x1b[F') { // End - move to end
                    while (cursorPos < currentLine.length) {
                        cursorPos++;
                        term.write('\\x1b[C');
                    }
                }
            } else if (code === 3) { // Ctrl+C
                // Cancel current line
                term.write('^C\\r\\n');
                currentLine = '';
                cursorPos = 0;
                showPrompt();
            } else if (code < 32) { // Other control characters
                // Ignore
            } else { // Regular character
                // Insert character at cursor position
                currentLine = currentLine.slice(0, cursorPos) + data + currentLine.slice(cursorPos);
                cursorPos++;

                // Redraw from cursor position
                term.write(currentLine.slice(cursorPos - 1));
                // Move cursor back to correct position
                for (let i = 0; i < currentLine.length - cursorPos; i++) {
                    term.write('\\b');
                }
            }
        });

        // Initialize
        showBanner();

        if (apiToken) {
            document.getElementById('status').textContent = 'Authenticated';
            document.getElementById('status').style.color = '#4ec9b0';
            writeln(colors.green + '[OK] API token loaded from session' + colors.reset, '');
            writeln('');
        } else {
            document.getElementById('status').textContent = 'Not authenticated';
            document.getElementById('status').style.color = '#f48771';
            writeln(colors.yellow + '[!] Not authenticated' + colors.reset, '');
            writeln('  Generate a token: ' + colors.cyan + 'holo auth token create --name "Web Terminal"' + colors.reset, colors.dim);
            writeln('  Then use: ' + colors.cyan + 'token <your-token>' + colors.reset, colors.dim);
            writeln('');
        }

        showPrompt();
    </script>
</body>
</html>
"""

    # Status endpoints

    def _status(self):
        """GET /status - Daemon status."""
        try:
            plugins = self.registry.list_plugins()

            return jsonify({
                "status": "running",
                "started_at": self.started_at.isoformat() if self.started_at else None,
                "uptime_seconds": (datetime.now() - self.started_at).total_seconds() if self.started_at else 0,
                "plugins": {
                    "total": len(plugins),
                    "enabled": len([p for p in plugins if p.get('enabled', False)]),
                    "disabled": len([p for p in plugins if not p.get('enabled', False)])
                },
                "api": {
                    "version": "1.0.0",
                    "port": self.port
                }
            })
        except Exception as e:
            logger.error(f"Error in /status: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    def _health(self):
        """GET /health - Health check."""
        return jsonify({"status": "ok"})

    # Plugin endpoints

    @require_auth
    def _list_plugins(self):
        """GET /plugins - List all plugins."""
        try:
            plugins = self.registry.list_plugins()
            return jsonify({"plugins": plugins})
        except Exception as e:
            logger.error(f"Error in /plugins: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @require_auth
    def _get_plugin(self, name: str):
        """GET /plugins/<name> - Get plugin details."""
        try:
            plugin = self.registry.get_plugin(name)
            if not plugin:
                return jsonify({"error": f"Plugin '{name}' not found"}), 404

            metadata = plugin.get_metadata()
            return jsonify({
                "name": metadata['name'],
                "version": metadata['version'],
                "description": metadata['description'],
                "runs_on": metadata['runs_on'],
                "requires": metadata['requires'],
                "enabled": plugin.enabled,
                "loaded": True
            })
        except Exception as e:
            logger.error(f"Error in /plugins/{name}: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @require_auth
    def _enable_plugin(self, name: str):
        """POST /plugins/<name>/enable - Enable plugin."""
        try:
            if not self.registry.get_plugin(name):
                return jsonify({"error": f"Plugin '{name}' not found"}), 404

            success = self.registry.enable_plugin(name)
            if success:
                return jsonify({"status": "enabled", "plugin": name})
            else:
                return jsonify({"error": f"Failed to enable plugin '{name}'"}), 500
        except Exception as e:
            logger.error(f"Error enabling plugin {name}: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @require_auth
    def _disable_plugin(self, name: str):
        """POST /plugins/<name>/disable - Disable plugin."""
        try:
            if not self.registry.get_plugin(name):
                return jsonify({"error": f"Plugin '{name}' not found"}), 404

            success = self.registry.disable_plugin(name)
            if success:
                return jsonify({"status": "disabled", "plugin": name})
            else:
                return jsonify({"error": f"Failed to disable plugin '{name}'"}), 500
        except Exception as e:
            logger.error(f"Error disabling plugin {name}: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    # Channel endpoints

    @require_auth
    def _publish_to_channel(self, channel: str):
        """POST /channels/<channel>/publish - Publish to channel."""
        try:
            data = request.get_json()
            if not data:
                return jsonify({"error": "No data provided"}), 400

            sender = data.get('sender', 'api')
            payload = data.get('data', {})

            self.core.channels.publish(channel, payload, sender=sender)

            return jsonify({
                "status": "published",
                "channel": channel,
                "sender": sender
            })
        except Exception as e:
            logger.error(f"Error publishing to channel {channel}: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @require_auth
    def _channel_history(self, channel: str):
        """GET /channels/<channel>/history - Get channel history."""
        try:
            limit = request.args.get('limit', 100, type=int)

            history = self.core.channels.get_history(channel, limit=limit)

            # Convert messages to JSON-serializable format
            messages = [
                {
                    "channel": msg.channel,
                    "data": msg.data,
                    "timestamp": msg.timestamp.isoformat(),
                    "sender": msg.sender
                }
                for msg in history
            ]

            return jsonify({
                "channel": channel,
                "messages": messages,
                "count": len(messages)
            })
        except Exception as e:
            logger.error(f"Error getting channel history {channel}: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @require_auth
    def _list_channels(self):
        """GET /channels - List all channels."""
        try:
            channels = self.core.channels.list_channels()

            # Get subscriber counts
            channel_info = []
            for channel in channels:
                channel_info.append({
                    "name": channel,
                    "subscribers": self.core.channels.subscriber_count(channel),
                    "message_count": len(self.core.channels.get_history(channel, limit=1000))
                })

            return jsonify({
                "channels": channel_info,
                "count": len(channel_info)
            })
        except Exception as e:
            logger.error(f"Error listing channels: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    # Book endpoints

    @require_auth
    def _books(self):
        """GET /books - List books, POST /books - Add book."""
        try:
            if request.method == "GET":
                # List books
                cursor = self.core.db.cursor()

                limit = request.args.get('limit', 100, type=int)
                offset = request.args.get('offset', 0, type=int)

                cursor.execute("""
                    SELECT id, title, author, publication_year, isbn, source, date_added
                    FROM books
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                """, (limit, offset))

                rows = cursor.fetchall()
                books = [dict(row) for row in rows]

                return jsonify({
                    "books": books,
                    "count": len(books),
                    "limit": limit,
                    "offset": offset
                })

            elif request.method == "POST":
                # Add book
                data = request.get_json()
                if not data:
                    return jsonify({"error": "No data provided"}), 400

                # Add book to database
                book_id = self.core.db.add_book(
                    title=data.get('title'),
                    author=data.get('author'),
                    year=data.get('year'),
                    isbn=data.get('isbn'),
                    source=data.get('source', 'api')
                )

                # Publish books.added event
                self.core.channels.publish('books.added', {
                    'book_id': book_id,
                    'title': data.get('title'),
                    'author': data.get('author')
                }, sender='api')

                return jsonify({
                    "status": "created",
                    "book_id": book_id
                }), 201

        except Exception as e:
            logger.error(f"Error in /books: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @require_auth
    def _get_book(self, book_id: int):
        """GET /books/<id> - Get book details."""
        try:
            cursor = self.core.db.cursor()
            cursor.execute("SELECT * FROM books WHERE id = ?", (book_id,))
            row = cursor.fetchone()

            if not row:
                return jsonify({"error": f"Book {book_id} not found"}), 404

            book = dict(row)
            return jsonify(book)

        except Exception as e:
            logger.error(f"Error getting book {book_id}: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    # Link endpoints

    @require_auth
    def _links(self):
        """GET /links - List links, POST /links - Add link."""
        try:
            if request.method == "GET":
                # List links
                cursor = self.core.db.cursor()

                limit = request.args.get('limit', 100, type=int)
                offset = request.args.get('offset', 0, type=int)

                cursor.execute("""
                    SELECT id, url, title, source, archived, first_seen, last_checked, trust_tier
                    FROM links
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                """, (limit, offset))

                rows = cursor.fetchall()
                links = [dict(row) for row in rows]

                return jsonify({
                    "links": links,
                    "count": len(links),
                    "limit": limit,
                    "offset": offset
                })

            elif request.method == "POST":
                # Add link
                data = request.get_json()
                if not data:
                    return jsonify({"error": "No data provided"}), 400

                # Add link to database
                link_id = self.core.db.add_link(
                    url=data.get('url'),
                    title=data.get('title'),
                    source=data.get('source', 'api')
                )

                # Publish links.added event
                self.core.channels.publish('links.added', {
                    'link_id': link_id,
                    'url': data.get('url'),
                    'title': data.get('title')
                }, sender='api')

                return jsonify({
                    "status": "created",
                    "link_id": link_id
                }), 201

        except Exception as e:
            logger.error(f"Error in /links: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @require_auth
    def _get_link(self, link_id: int):
        """GET /links/<id> - Get link details."""
        try:
            cursor = self.core.db.cursor()
            cursor.execute("SELECT * FROM links WHERE id = ?", (link_id,))
            row = cursor.fetchone()

            if not row:
                return jsonify({"error": f"Link {link_id} not found"}), 404

            link = dict(row)
            return jsonify(link)

        except Exception as e:
            logger.error(f"Error getting link {link_id}: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    # Archive viewer endpoints

    @require_auth
    def _mono_latest(self, link_id: int):
        """GET /mono/<link_id> or /mono/<link_id>/latest - Serve latest local monolith archive."""
        return self._serve_monolith(link_id, version='latest')

    @require_auth
    def _mono_first(self, link_id: int):
        """GET /mono/<link_id>/first - Serve first local monolith archive."""
        return self._serve_monolith(link_id, version='first')

    @require_auth
    def _mono_index(self, link_id: int, index: int):
        """GET /mono/<link_id>/<index> - Serve nth local monolith archive (0=latest, 1=previous, etc)."""
        return self._serve_monolith(link_id, version=index)

    @require_auth
    def _snapshot_by_id(self, snapshot_id: int):
        """GET /snapshot/<snapshot_id> - Serve archive snapshot by ID."""
        try:
            cursor = self.core.db.cursor()
            cursor.execute("""
                SELECT snapshot_url, service
                FROM archive_snapshots
                WHERE id = ?
            """, (snapshot_id,))

            row = cursor.fetchone()
            if not row:
                return abort(404, description=f"Snapshot {snapshot_id} not found")

            snapshot_url = row[0]
            service = row[1]

            # Only serve local archives
            if not service.startswith('local_'):
                return abort(400, description="Only local archives can be served directly")

            # Serve the file
            return self._serve_archive_file(snapshot_url, service)

        except Exception as e:
            logger.error(f"Error serving snapshot {snapshot_id}: {e}", exc_info=True)
            return abort(500, description=str(e))

    @require_auth
    def _box_snapshot(self, snapshot_id: str):
        """GET /box/<snapshot_id> - Proxy ArchiveBox snapshot from archivebox-rei.

        Args:
            snapshot_id: ArchiveBox snapshot ID (timestamp like 1764022942.528686)

        Serves singlefile.html by default (comprehensive single-file archive with all assets embedded).
        Injects an archive banner at the top showing metadata and link to live site.
        """
        try:
            # Get ArchiveBox config
            archivebox_host = getattr(self.core.config.integrations, 'archivebox_host', '192.168.1.102')
            archivebox_port = 8000

            # ArchiveBox URL - serve singlefile.html (comprehensive single-file archive)
            archivebox_url = f"http://{archivebox_host}:{archivebox_port}/archive/{snapshot_id}/singlefile.html"

            logger.info(f"Proxying ArchiveBox snapshot: {archivebox_url}")

            # Get archive metadata from database
            cursor = self.core.db.conn.cursor()
            cursor.execute("""
                SELECT l.url, a.archive_date, a.created_at, a.metadata
                FROM archive_snapshots a
                JOIN links l ON a.link_id = l.id
                WHERE a.service = 'archivebox' AND a.metadata LIKE ?
                LIMIT 1
            """, (f'%{snapshot_id}%',))

            metadata = cursor.fetchone()
            original_url = metadata[0] if metadata else "Unknown"
            archive_date = metadata[1] if metadata else "Unknown"
            created_at = metadata[2] if metadata else "Unknown"

            # Make request to ArchiveBox
            response = requests.get(archivebox_url, timeout=30)

            if response.status_code == 404:
                return abort(404, description=f"ArchiveBox snapshot {snapshot_id} not found")
            elif response.status_code != 200:
                return abort(response.status_code, description=f"ArchiveBox returned status {response.status_code}")

            # Get HTML content - decode as UTF-8 explicitly to preserve special characters
            # Using response.content.decode() instead of response.text to avoid encoding issues
            try:
                html_content = response.content.decode('utf-8')
            except UnicodeDecodeError:
                # Fallback to latin-1 if UTF-8 fails
                html_content = response.content.decode('latin-1')

            # Create archive banner with holographic effect
            banner_html = f"""
            <style>
                @keyframes holo-shimmer {{
                    0% {{ background-position: -200% center; }}
                    100% {{ background-position: 200% center; }}
                }}
                #holocene-archive-banner {{
                    position: fixed !important;
                    top: 0;
                    left: 0;
                    right: 0;
                    width: 100%;
                    z-index: 2147483647;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 10px 20px;
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    font-size: 14px;
                    box-shadow: 0 2px 12px rgba(0,0,0,0.2);
                    border-bottom: 2px solid rgba(255,255,255,0.2);
                    box-sizing: border-box;
                    transition: transform 0.3s ease;
                }}
                #holocene-archive-banner.hidden {{
                    transform: translateY(-100%);
                }}
                #holocene-archive-banner::before {{
                    content: '';
                    position: absolute;
                    top: 0;
                    left: 0;
                    right: 0;
                    bottom: 0;
                    background: linear-gradient(
                        90deg,
                        transparent 0%,
                        rgba(255,255,255,0.15) 25%,
                        rgba(255,255,255,0.3) 50%,
                        rgba(255,255,255,0.15) 75%,
                        transparent 100%
                    );
                    background-size: 200% 100%;
                    animation: holo-shimmer 12s linear infinite;
                    pointer-events: none;
                }}
                #holocene-banner-spacer {{
                    height: 60px;
                    display: block;
                    transition: height 0.3s ease;
                }}
                #holocene-banner-spacer.hidden {{
                    height: 0;
                }}
                #holocene-banner-toggle {{
                    position: fixed;
                    top: 65px;
                    right: 20px;
                    z-index: 2147483646;
                    background: rgba(102, 126, 234, 0.9);
                    color: white;
                    border: 1px solid rgba(255,255,255,0.3);
                    padding: 6px 10px;
                    border-radius: 4px;
                    cursor: pointer;
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    font-size: 12px;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.2);
                    transition: all 0.3s ease;
                }}
                #holocene-banner-toggle:hover {{
                    background: rgba(118, 75, 162, 0.9);
                }}
                #holocene-banner-toggle.banner-hidden {{
                    top: 10px;
                }}
            </style>
            <div id="holocene-archive-banner">
                <div style="max-width: 1400px; margin: 0 auto; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px; position: relative; z-index: 1;">
                    <div style="display: flex; align-items: center; gap: 10px;">
                        <span style="font-size: 18px;">📦</span>
                        <div>
                            <div style="font-weight: 600; font-size: 13px; margin-bottom: 1px;">
                                Holocene Archive
                            </div>
                            <div style="font-size: 11px; opacity: 0.85;">
                                Archived on {archive_date[:10] if archive_date != "Unknown" else "Unknown date"}
                            </div>
                        </div>
                    </div>
                    <div style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap;">
                        <a href="{original_url}" target="_blank" rel="noopener noreferrer" style="
                            color: white;
                            text-decoration: none;
                            padding: 5px 14px;
                            background: rgba(255,255,255,0.2);
                            border-radius: 4px;
                            font-weight: 500;
                            font-size: 13px;
                            transition: background 0.2s;
                            border: 1px solid rgba(255,255,255,0.3);
                            white-space: nowrap;
                        " onmouseover="this.style.background='rgba(255,255,255,0.35)'" onmouseout="this.style.background='rgba(255,255,255,0.2)'">
                            🔗 Visit Live Site
                        </a>
                        <div style="font-size: 11px; opacity: 0.75; max-width: 350px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="{original_url}">
                            {original_url}
                        </div>
                    </div>
                </div>
            </div>
            <button id="holocene-banner-toggle" onclick="
                var banner = document.getElementById('holocene-archive-banner');
                var spacer = document.getElementById('holocene-banner-spacer');
                var toggle = document.getElementById('holocene-banner-toggle');
                var isHidden = banner.classList.toggle('hidden');
                spacer.classList.toggle('hidden');
                toggle.classList.toggle('banner-hidden');
                toggle.innerHTML = isHidden ? '▼ Show Archive Banner' : '▲ Hide Banner';
            ">▲ Hide Banner</button>
            <div id="holocene-banner-spacer"></div>
            """

            # Inject banner after <body> tag
            if '<body' in html_content.lower():
                # Find the end of the <body> tag (handles attributes)
                import re
                body_match = re.search(r'<body[^>]*>', html_content, re.IGNORECASE)
                if body_match:
                    insert_pos = body_match.end()
                    html_content = html_content[:insert_pos] + banner_html + html_content[insert_pos:]
            else:
                # Fallback: prepend to content
                html_content = banner_html + html_content

            # Proxy the response
            from flask import Response

            return Response(
                html_content,
                status=200,
                content_type='text/html; charset=utf-8',
                headers={
                    'X-Proxied-From': archivebox_url,
                    'X-Original-URL': original_url,
                }
            )

        except requests.Timeout:
            logger.error(f"Timeout proxying ArchiveBox snapshot {snapshot_id}")
            return abort(504, description="ArchiveBox request timed out")
        except requests.ConnectionError:
            logger.error(f"Connection error proxying ArchiveBox snapshot {snapshot_id}")
            return abort(502, description="Cannot connect to ArchiveBox")
        except Exception as e:
            logger.error(f"Error proxying ArchiveBox snapshot {snapshot_id}: {e}", exc_info=True)
            return abort(500, description=str(e))

    def _serve_monolith(self, link_id: int, version='latest'):
        """Helper to serve a monolith archive for a link.

        Args:
            link_id: Link ID
            version: 'latest', 'first', or integer index (0=latest, 1=previous, etc)
        """
        try:
            cursor = self.core.db.cursor()

            # Get snapshots for this link (monolith only)
            cursor.execute("""
                SELECT id, snapshot_url, created_at
                FROM archive_snapshots
                WHERE link_id = ? AND service = 'local_monolith' AND status = 'success'
                ORDER BY created_at DESC
            """, (link_id,))

            snapshots = cursor.fetchall()

            if not snapshots:
                return abort(404, description=f"No local monolith archives found for link {link_id}")

            # Select snapshot based on version
            if version == 'latest':
                snapshot = snapshots[0]  # First in DESC order
            elif version == 'first':
                snapshot = snapshots[-1]  # Last in DESC order
            elif isinstance(version, int):
                if version < 0 or version >= len(snapshots):
                    return abort(404, description=f"Snapshot index {version} out of range (0-{len(snapshots)-1})")
                snapshot = snapshots[version]
            else:
                return abort(400, description=f"Invalid version: {version}")

            snapshot_url = snapshot[1]

            # Serve the file
            return self._serve_archive_file(snapshot_url, 'local_monolith')

        except Exception as e:
            logger.error(f"Error serving monolith for link {link_id}: {e}", exc_info=True)
            return abort(500, description=str(e))

    def _serve_archive_file(self, file_path: str, service: str):
        """Helper to serve an archive file from disk.

        Args:
            file_path: Path to archive file
            service: Service type (for validation)
        """
        from pathlib import Path
        import os

        try:
            # Security: Validate file path
            archive_path = Path(file_path)

            # Must be absolute path
            if not archive_path.is_absolute():
                return abort(400, description="Invalid file path")

            # Must exist
            if not archive_path.exists():
                return abort(404, description="Archive file not found")

            # Must be under ~/.holocene/archives/
            holocene_archives = Path.home() / ".holocene" / "archives"
            try:
                archive_path.resolve().relative_to(holocene_archives.resolve())
            except ValueError:
                # Path is not under archives directory
                return abort(403, description="Access denied")

            # Determine MIME type based on service
            if service == 'local_monolith':
                mimetype = 'text/html'
            elif service == 'local_warc':
                mimetype = 'application/warc'
            else:
                mimetype = 'application/octet-stream'

            # For monolith files, strip embedded CSP meta tag that blocks Cloudflare
            if service == 'local_monolith':
                # Read and modify HTML to remove strict CSP
                with open(archive_path, 'r', encoding='utf-8') as f:
                    html_content = f.read()

                # Remove the CSP meta tag that monolith embeds
                import re
                html_content = re.sub(
                    r'<meta\s+http-equiv=["\']Content-Security-Policy["\'][^>]*>',
                    '',
                    html_content,
                    flags=re.IGNORECASE
                )

                # Return modified HTML
                from flask import Response
                return Response(
                    html_content,
                    mimetype='text/html',
                    headers={
                        'Content-Security-Policy': (
                            "default-src 'self'; "
                            "script-src 'self' 'unsafe-inline' https://static.cloudflareinsights.com; "
                            "style-src 'self' 'unsafe-inline' data:; "
                            "img-src 'self' data:; "
                            "font-src 'self' data:; "
                            "connect-src 'self' https://cloudflareinsights.com"
                        )
                    }
                )

            # For other file types, serve directly
            return send_file(
                archive_path,
                mimetype=mimetype,
                as_attachment=False,
                download_name=archive_path.name
            )

        except Exception as e:
            logger.error(f"Error serving archive file {file_path}: {e}", exc_info=True)
            return abort(500, description=str(e))

    # Telegram Mini App endpoints

    def _validate_telegram_init_data(self) -> Optional[dict]:
        """Validate Telegram WebApp init data.

        Returns user data dict if valid, None otherwise.
        For now, we trust the init data since it's signed by Telegram.
        In production, should verify the hash using bot token.
        """
        init_data = request.headers.get('X-Telegram-Init-Data', '')
        if not init_data:
            return None

        # Parse init data (URL-encoded)
        from urllib.parse import parse_qs
        try:
            params = parse_qs(init_data)

            # Extract user data
            user_data = params.get('user', [None])[0]
            if user_data:
                import json
                return json.loads(user_data)
        except Exception as e:
            logger.warning(f"Failed to parse Telegram init data: {e}")

        return None

    def _webapp_index(self):
        """GET /webapp - Serve the Mini App HTML."""
        from pathlib import Path

        # Serve index.html from webapp directory
        webapp_dir = Path(__file__).parent / 'webapp'
        index_path = webapp_dir / 'index.html'

        if not index_path.exists():
            return jsonify({"error": "WebApp not found"}), 404

        return send_file(index_path, mimetype='text/html')

    def _webapp_stats(self):
        """GET /webapp/stats - Dashboard stats for Mini App."""
        try:
            # Validate Telegram auth (optional for now, can be enforced later)
            tg_user = self._validate_telegram_init_data()

            cursor = self.core.db.cursor()

            # Get collection counts
            cursor.execute("SELECT COUNT(*) FROM books")
            books_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM papers")
            papers_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM links")
            links_count = cursor.fetchone()[0]

            # Get conversation count (if table exists)
            conversations_count = 0
            try:
                cursor.execute("SELECT COUNT(*) FROM laney_conversations")
                conversations_count = cursor.fetchone()[0]
            except Exception:
                pass

            # Get active conversation for this user
            active_conversation = None
            if tg_user:
                try:
                    cursor.execute("""
                        SELECT id, title, message_count, updated_at
                        FROM laney_conversations
                        WHERE chat_id = ? AND is_active = 1
                        ORDER BY updated_at DESC
                        LIMIT 1
                    """, (tg_user.get('id'),))
                    row = cursor.fetchone()
                    if row:
                        active_conversation = {
                            'id': row[0],
                            'title': row[1],
                            'message_count': row[2],
                            'updated_at': row[3]
                        }
                except Exception:
                    pass

            # Context usage estimate (simplified)
            # In reality, would need to track actual token usage
            context_estimate = {
                'used': 0,
                'max': 128000
            }
            if active_conversation:
                # Rough estimate: 50 tokens per message
                context_estimate['used'] = active_conversation['message_count'] * 50 + 3500  # Base overhead

            # Recent activity (last 5 items added)
            recent_activity = []
            try:
                cursor.execute("""
                    SELECT 'book' as type, title, created_at FROM books
                    UNION ALL
                    SELECT 'link' as type, title, created_at FROM links
                    ORDER BY created_at DESC
                    LIMIT 5
                """)
                for row in cursor.fetchall():
                    item_type, title, created_at = row
                    icon = '📚' if item_type == 'book' else '🔗'
                    recent_activity.append({
                        'icon': icon,
                        'text': title[:40] + ('...' if len(title) > 40 else '') if title else 'Untitled',
                        'time': self._format_relative_time(created_at)
                    })
            except Exception as e:
                logger.warning(f"Failed to get recent activity: {e}")

            # Get NanoGPT subscription usage
            api_usage = {'used': 0, 'limit': 2000}
            try:
                from ..llm.nanogpt import NanoGPTClient
                config = self.core.config
                if hasattr(config, 'llm') and config.llm.api_key:
                    client = NanoGPTClient(config.llm.api_key)
                    usage_data = client.get_subscription_usage()
                    if 'error' not in usage_data:
                        # Extract daily usage from NanoGPT response
                        daily = usage_data.get('daily', {})
                        limits = usage_data.get('limits', {})
                        api_usage = {
                            'used': daily.get('used', 0),
                            'limit': limits.get('daily', 2000),
                            'remaining': daily.get('remaining', 0),
                            'percent': daily.get('percentUsed', 0) * 100,
                        }
            except Exception as e:
                logger.warning(f"Failed to get NanoGPT usage: {e}")

            return jsonify({
                'books': books_count,
                'papers': papers_count,
                'links': links_count,
                'conversations': conversations_count,
                'context': context_estimate,
                'active_conversation': active_conversation,
                'recent_activity': recent_activity,
                'api_usage': api_usage
            })

        except Exception as e:
            logger.error(f"Error in /webapp/stats: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    def _webapp_conversations(self):
        """GET /webapp/conversations - List Laney conversations."""
        try:
            tg_user = self._validate_telegram_init_data()
            chat_id = tg_user.get('id') if tg_user else None

            cursor = self.core.db.cursor()

            # Build query based on whether we have a chat_id
            if chat_id:
                cursor.execute("""
                    SELECT id, title, message_count, created_at, updated_at, is_active
                    FROM laney_conversations
                    WHERE chat_id = ?
                    ORDER BY updated_at DESC
                    LIMIT 50
                """, (chat_id,))
            else:
                cursor.execute("""
                    SELECT id, title, message_count, created_at, updated_at, is_active
                    FROM laney_conversations
                    ORDER BY updated_at DESC
                    LIMIT 50
                """)

            conversations = []
            for row in cursor.fetchall():
                conversations.append({
                    'id': row[0],
                    'title': row[1],
                    'message_count': row[2],
                    'created_at': row[3],
                    'updated_at': row[4],
                    'is_active': bool(row[5])
                })

            return jsonify({'conversations': conversations})

        except Exception as e:
            logger.error(f"Error in /webapp/conversations: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    def _webapp_papers(self):
        """GET /webapp/papers - List papers."""
        try:
            cursor = self.core.db.cursor()

            limit = request.args.get('limit', 50, type=int)
            offset = request.args.get('offset', 0, type=int)

            cursor.execute("""
                SELECT id, title, authors, year, doi, arxiv_id, url, created_at
                FROM papers
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            """, (limit, offset))

            papers = []
            for row in cursor.fetchall():
                papers.append({
                    'id': row[0],
                    'title': row[1],
                    'authors': row[2].split(', ') if row[2] else [],
                    'year': row[3],
                    'doi': row[4],
                    'arxiv_id': row[5],
                    'url': row[6],
                    'created_at': row[7]
                })

            return jsonify({
                'papers': papers,
                'count': len(papers),
                'limit': limit,
                'offset': offset
            })

        except Exception as e:
            logger.error(f"Error in /webapp/papers: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    def _webapp_books(self):
        """GET /webapp/books - List books for Mini App."""
        try:
            cursor = self.core.db.cursor()

            limit = request.args.get('limit', 50, type=int)
            offset = request.args.get('offset', 0, type=int)

            cursor.execute("""
                SELECT id, title, author, publication_year, isbn, source, created_at
                FROM books
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            """, (limit, offset))

            books = []
            for row in cursor.fetchall():
                books.append({
                    'id': row[0],
                    'title': row[1],
                    'author': row[2],
                    'year': row[3],
                    'isbn': row[4],
                    'source': row[5],
                    'created_at': row[6]
                })

            return jsonify({
                'books': books,
                'count': len(books),
                'limit': limit,
                'offset': offset
            })

        except Exception as e:
            logger.error(f"Error in /webapp/books: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    def _webapp_links(self):
        """GET /webapp/links - List links for Mini App."""
        try:
            cursor = self.core.db.cursor()

            limit = request.args.get('limit', 50, type=int)
            offset = request.args.get('offset', 0, type=int)

            cursor.execute("""
                SELECT id, url, title, source, archived, first_seen, trust_tier, created_at
                FROM links
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            """, (limit, offset))

            links = []
            for row in cursor.fetchall():
                links.append({
                    'id': row[0],
                    'url': row[1],
                    'title': row[2],
                    'source': row[3],
                    'archived': bool(row[4]),
                    'first_seen': row[5],
                    'trust_tier': row[6],
                    'created_at': row[7]
                })

            return jsonify({
                'links': links,
                'count': len(links),
                'limit': limit,
                'offset': offset
            })

        except Exception as e:
            logger.error(f"Error in /webapp/links: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    def _format_relative_time(self, datetime_str: str) -> str:
        """Format datetime string as relative time (e.g., '2h ago')."""
        if not datetime_str:
            return ''

        try:
            from datetime import datetime
            dt = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
            now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
            diff = now - dt

            seconds = diff.total_seconds()
            if seconds < 60:
                return 'Just now'
            elif seconds < 3600:
                return f'{int(seconds // 60)}m ago'
            elif seconds < 86400:
                return f'{int(seconds // 3600)}h ago'
            elif seconds < 604800:
                return f'{int(seconds // 86400)}d ago'
            else:
                return dt.strftime('%b %d')
        except Exception:
            return ''

    # Error handlers

    def _not_found(self, error):
        """Handle 404 errors."""
        return jsonify({"error": "Not found"}), 404

    def _internal_error(self, error):
        """Handle 500 errors."""
        logger.error(f"Internal server error: {error}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500

    # Server lifecycle

    def start(self):
        """Start the API server in background thread."""
        if self.running:
            logger.warning("API server already running")
            return

        logger.info(f"Starting API server on port {self.port}...")

        # Create server
        self.server = make_server('0.0.0.0', self.port, self.app, threaded=True)
        self.server_thread = threading.Thread(target=self._run_server, daemon=True)

        self.running = True
        self.started_at = datetime.now()

        # Start server thread
        self.server_thread.start()

        logger.info(f"API server started on http://0.0.0.0:{self.port}")

    def _run_server(self):
        """Run the Flask server (runs in background thread)."""
        try:
            self.server.serve_forever()
        except Exception as e:
            logger.error(f"API server error: {e}", exc_info=True)
            self.running = False

    def stop(self):
        """Stop the API server."""
        if not self.running:
            logger.warning("API server not running")
            return

        logger.info("Stopping API server...")

        self.running = False

        # Shutdown server
        if self.server:
            self.server.shutdown()

        # Wait for thread to finish
        if self.server_thread:
            self.server_thread.join(timeout=5)

        logger.info("API server stopped")
