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
from typing import Optional
from datetime import datetime

try:
    from flask import Flask, jsonify, request, session, redirect
    from werkzeug.serving import make_server
    FLASK_AVAILABLE = True
except ImportError:
    Flask = None
    jsonify = None
    request = None
    session = None
    redirect = None
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
        self.app = Flask("holod-api")

        # Configure secret key for sessions
        # TODO: Load from config or generate persistent key
        import secrets
        self.app.secret_key = secrets.token_hex(32)  # Generate 256-bit key

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
        // Import xterm-kit utilities from koma repo
        import { parse as parseArgs, hasHelp, showHelp } from 'https://cdn.jsdelivr.net/gh/endarthur/koma@main/src/lib/xterm-kit/argparse.js';
        import { showError, showSuccess, showInfo, formatSize, formatDate } from 'https://cdn.jsdelivr.net/gh/endarthur/koma@main/src/lib/xterm-kit/output.js';
        import { Table, renderTable } from 'https://cdn.jsdelivr.net/gh/endarthur/koma@main/src/lib/xterm-kit/table.js';
        import { Spinner } from 'https://cdn.jsdelivr.net/gh/endarthur/koma@main/src/lib/xterm-kit/progress.js';
        import { Autocomplete, createTabHandler } from 'https://cdn.jsdelivr.net/gh/endarthur/koma@main/src/lib/xterm-kit/autocomplete.js';

        // Terminal setup
        const term = new Terminal({
            cursorBlink: true,
            fontSize: 14,
            fontFamily: 'Fira Code, JetBrains Mono, Consolas, monospace',
            theme: {
                background: '#1e1e1e',
                foreground: '#cccccc',
                cursor: '#4ec9b0',
                black: '#1e1e1e',
                red: '#f48771',
                green: '#4ec9b0',
                yellow: '#dcdcaa',
                blue: '#569cd6',
                magenta: '#c586c0',
                cyan: '#4ec9b0',
                white: '#d4d4d4',
                brightBlack: '#6a6a6a',
                brightRed: '#f48771',
                brightGreen: '#4ec9b0',
                brightYellow: '#dcdcaa',
                brightBlue: '#569cd6',
                brightMagenta: '#c586c0',
                brightCyan: '#4ec9b0',
                brightWhite: '#ffffff'
            }
        });

        const fitAddon = new FitAddon.FitAddon();
        term.loadAddon(fitAddon);
        term.open(document.getElementById('terminal'));
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

        // Tab completion using xterm-kit
        const completer = new Autocomplete({
            commands: ['help', 'auth', 'books', 'links', 'ask', 'status', 'clear', 'token', 'whoami'],
            subcommands: {
                'auth': ['status'],
                'books': ['list'],
                'links': ['list']
            }
        });

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
                        showHelp();
                        break;

                    case 'auth':
                        if (args[0] === 'status') {
                            await authStatus();
                        } else {
                            writeln('Usage: auth status', colors.red);
                        }
                        break;

                    case 'books':
                        if (args[0] === 'list' || !args[0]) {
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
                        if (args.length === 0) {
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
        function showHelp() {
            writeln('');
            writeln(colors.bright + 'Available Commands:' + colors.reset, '');
            writeln('');
            writeln('  ' + colors.cyan + 'whoami' + colors.reset + '                    Show current user', '');
            writeln('  ' + colors.cyan + 'token <token>' + colors.reset + '            Set API token (starts with hlc_)', '');
            writeln('  ' + colors.cyan + 'auth status' + colors.reset + '               Check authentication status', '');
            writeln('  ' + colors.cyan + 'books list [N|all]' + colors.reset + '        List books (default: 20, or N items, or all)', '');
            writeln('  ' + colors.cyan + 'links list [N|all]' + colors.reset + '        List links (default: 20, or N items, or all)', '');
            writeln('  ' + colors.cyan + 'ask <query>' + colors.reset + '               Ask the AI Librarian', '');
            writeln('  ' + colors.cyan + 'status' + colors.reset + '                    Get daemon status', '');
            writeln('  ' + colors.cyan + 'clear' + colors.reset + '                     Clear terminal', '');
            writeln('  ' + colors.cyan + 'help' + colors.reset + '                      Show this help', '');
            writeln('');
            writeln(colors.dim + 'Examples:', '');
            writeln(colors.dim + '  books list         ' + colors.reset + '  # Show first 20 books', '');
            writeln(colors.dim + '  books list 50      ' + colors.reset + '  # Show first 50 books', '');
            writeln(colors.dim + '  books list all     ' + colors.reset + '  # Show all books', '');
            writeln('');
            writeln(colors.dim + 'Generate a token: ' + colors.cyan + 'holo auth token create --name "Web Terminal"' + colors.reset, '');
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
