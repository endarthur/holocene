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

    Checks if user is authenticated via session.
    Returns 401 Unauthorized if not authenticated.
    """
    from functools import wraps

    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if user is authenticated
        if 'user_id' not in session:
            logger.warning(f"Unauthorized access attempt to {request.path} from {request.remote_addr}")
            return jsonify({"error": "Authentication required"}), 401

        # User is authenticated, proceed
        return f(*args, **kwargs)

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

        # Auth endpoints
        self.app.route("/auth/login", methods=["GET"])(self._auth_login)
        self.app.route("/auth/logout", methods=["POST"])(self._auth_logout)
        self.app.route("/auth/status", methods=["GET"])(self._auth_status)

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
