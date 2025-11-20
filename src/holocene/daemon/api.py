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
    from flask import Flask, jsonify, request
    from werkzeug.serving import make_server
    FLASK_AVAILABLE = True
except ImportError:
    Flask = None
    jsonify = None
    request = None
    make_server = None
    FLASK_AVAILABLE = False

from ..core import HoloceneCore
from ..core.plugin_registry import PluginRegistry

logger = logging.getLogger(__name__)


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
        self._setup_routes()

        # Server state
        self.server = None
        self.server_thread = None
        self.running = False
        self.started_at = None

        logger.info(f"API server initialized on port {port}")

    def _setup_routes(self):
        """Setup Flask routes."""

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

    def _list_plugins(self):
        """GET /plugins - List all plugins."""
        try:
            plugins = self.registry.list_plugins()
            return jsonify({"plugins": plugins})
        except Exception as e:
            logger.error(f"Error in /plugins: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

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

    def _books(self):
        """GET /books - List books, POST /books - Add book."""
        try:
            if request.method == "GET":
                # List books
                cursor = self.core.db.conn.cursor()

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

    def _get_book(self, book_id: int):
        """GET /books/<id> - Get book details."""
        try:
            cursor = self.core.db.conn.cursor()
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

    def _links(self):
        """GET /links - List links, POST /links - Add link."""
        try:
            if request.method == "GET":
                # List links
                cursor = self.core.db.conn.cursor()

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

    def _get_link(self, link_id: int):
        """GET /links/<id> - Get link details."""
        try:
            cursor = self.core.db.conn.cursor()
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
