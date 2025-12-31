"""Telegram Bot Plugin - Mobile interface for Holocene (eunice device).

This plugin:
- Provides Telegram interface for mobile access
- Subscribes to events and sends notifications
- Handles interactive commands
- Runs on rei (server) but provides eunice (mobile) interface
- Uses python-telegram-bot library
"""

import asyncio
import threading
import re
import os
import json
import secrets
import sqlite3
from typing import Optional, List, Dict
from datetime import datetime, timedelta
from pathlib import Path

from holocene.core import Plugin, Message
from holocene.storage.archiving import ArchivingService
from holocene.integrations.local_archive import LocalArchiveClient
from holocene.integrations.archivebox import ArchiveBoxClient
from holocene.integrations.internet_archive import InternetArchiveClient

try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    Update = None
    InlineKeyboardButton = None
    InlineKeyboardMarkup = None
    CommandHandler = None
    MessageHandler = None
    CallbackQueryHandler = None
    filters = None
    ContextTypes = None
    Application = None


class ConversationManager:
    """Manages Laney conversation history for Telegram chats.

    Stores all messages to database, but only loads last N for context.
    Each chat can have one active conversation at a time, with ability
    to view and resume past conversations.
    """

    # Max messages to include in context (with 128K tokens, can be generous)
    # At ~500 tokens/message avg, 100 messages ≈ 50K tokens, leaving room for tools
    MAX_CONTEXT_MESSAGES = 100

    def __init__(self, db_path: str):
        """Initialize conversation manager.

        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path

    def _get_conn(self) -> sqlite3.Connection:
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_or_create_conversation(self, chat_id: int) -> int:
        """Get active conversation for chat, or create new one.

        Args:
            chat_id: Telegram chat ID

        Returns:
            Conversation ID
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()

            # Look for active conversation
            cursor.execute("""
                SELECT id FROM laney_conversations
                WHERE chat_id = ? AND is_active = 1
                ORDER BY updated_at DESC
                LIMIT 1
            """, (chat_id,))
            row = cursor.fetchone()

            if row:
                return row['id']

            # Create new conversation
            now = datetime.now().isoformat()
            cursor.execute("""
                INSERT INTO laney_conversations (chat_id, created_at, updated_at, is_active)
                VALUES (?, ?, ?, 1)
            """, (chat_id, now, now))
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def start_new_conversation(self, chat_id: int) -> int:
        """Start a new conversation, deactivating any existing ones.

        Args:
            chat_id: Telegram chat ID

        Returns:
            New conversation ID
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()

            # Deactivate all existing conversations for this chat
            cursor.execute("""
                UPDATE laney_conversations
                SET is_active = 0
                WHERE chat_id = ? AND is_active = 1
            """, (chat_id,))

            # Create new conversation
            now = datetime.now().isoformat()
            cursor.execute("""
                INSERT INTO laney_conversations (chat_id, created_at, updated_at, is_active)
                VALUES (?, ?, ?, 1)
            """, (chat_id, now, now))
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def add_message(self, conversation_id: int, role: str, content: str,
                    tool_calls: Optional[str] = None, tool_results: Optional[str] = None):
        """Add a message to conversation.

        Args:
            conversation_id: Conversation ID
            role: Message role ('user', 'assistant', 'tool')
            content: Message content
            tool_calls: JSON string of tool calls (optional)
            tool_results: JSON string of tool results (optional)
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            now = datetime.now().isoformat()

            cursor.execute("""
                INSERT INTO laney_messages (conversation_id, role, content, tool_calls, tool_results, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (conversation_id, role, content, tool_calls, tool_results, now))

            # Update conversation timestamp and message count
            cursor.execute("""
                UPDATE laney_conversations
                SET updated_at = ?, message_count = message_count + 1
                WHERE id = ?
            """, (now, conversation_id))

            conn.commit()
        finally:
            conn.close()

    def get_messages(self, conversation_id: int, limit: Optional[int] = None) -> List[Dict]:
        """Get messages from conversation.

        Args:
            conversation_id: Conversation ID
            limit: Max messages to return (None = all)

        Returns:
            List of message dicts with role, content
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()

            if limit:
                # Get last N messages
                cursor.execute("""
                    SELECT role, content, tool_calls, tool_results FROM laney_messages
                    WHERE conversation_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (conversation_id, limit))
                rows = list(reversed(cursor.fetchall()))  # Reverse to get chronological order
            else:
                cursor.execute("""
                    SELECT role, content, tool_calls, tool_results FROM laney_messages
                    WHERE conversation_id = ?
                    ORDER BY created_at ASC
                """, (conversation_id,))
                rows = cursor.fetchall()

            messages = []
            for row in rows:
                msg = {"role": row['role'], "content": row['content']}
                if row['tool_calls']:
                    msg['tool_calls'] = row['tool_calls']
                messages.append(msg)

            return messages
        finally:
            conn.close()

    def get_context_messages(self, conversation_id: int) -> List[Dict]:
        """Get messages formatted for LLM context.

        Returns last N messages suitable for sending to the model.

        Args:
            conversation_id: Conversation ID

        Returns:
            List of message dicts for LLM
        """
        return self.get_messages(conversation_id, limit=self.MAX_CONTEXT_MESSAGES)

    def list_conversations(self, chat_id: int, limit: int = 10) -> List[Dict]:
        """List conversations for a chat.

        Args:
            chat_id: Telegram chat ID
            limit: Max conversations to return

        Returns:
            List of conversation summaries
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, title, created_at, updated_at, is_active, message_count
                FROM laney_conversations
                WHERE chat_id = ?
                ORDER BY updated_at DESC
                LIMIT ?
            """, (chat_id, limit))

            conversations = []
            for row in cursor.fetchall():
                # Get first user message as preview if no title
                title = row['title']
                if not title:
                    cursor.execute("""
                        SELECT content FROM laney_messages
                        WHERE conversation_id = ? AND role = 'user'
                        ORDER BY created_at ASC
                        LIMIT 1
                    """, (row['id'],))
                    first_msg = cursor.fetchone()
                    if first_msg:
                        title = first_msg['content'][:50] + ('...' if len(first_msg['content']) > 50 else '')
                    else:
                        title = "(empty conversation)"

                conversations.append({
                    'id': row['id'],
                    'title': title,
                    'created_at': row['created_at'],
                    'updated_at': row['updated_at'],
                    'is_active': bool(row['is_active']),
                    'message_count': row['message_count']
                })

            return conversations
        finally:
            conn.close()

    def resume_conversation(self, chat_id: int, conversation_id: int) -> bool:
        """Resume a past conversation.

        Args:
            chat_id: Telegram chat ID (for verification)
            conversation_id: Conversation ID to resume

        Returns:
            True if successful, False if conversation not found or unauthorized
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()

            # Verify conversation belongs to this chat
            cursor.execute("""
                SELECT id FROM laney_conversations
                WHERE id = ? AND chat_id = ?
            """, (conversation_id, chat_id))
            if not cursor.fetchone():
                return False

            # Deactivate all conversations for this chat
            cursor.execute("""
                UPDATE laney_conversations
                SET is_active = 0
                WHERE chat_id = ?
            """, (chat_id,))

            # Activate the requested conversation
            now = datetime.now().isoformat()
            cursor.execute("""
                UPDATE laney_conversations
                SET is_active = 1, updated_at = ?
                WHERE id = ?
            """, (now, conversation_id))

            conn.commit()
            return True
        finally:
            conn.close()

    def get_conversation_info(self, conversation_id: int) -> Optional[Dict]:
        """Get info about a conversation.

        Args:
            conversation_id: Conversation ID

        Returns:
            Conversation info dict or None
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, chat_id, title, created_at, updated_at, is_active, message_count
                FROM laney_conversations
                WHERE id = ?
            """, (conversation_id,))
            row = cursor.fetchone()
            if not row:
                return None

            return {
                'id': row['id'],
                'chat_id': row['chat_id'],
                'title': row['title'],
                'created_at': row['created_at'],
                'updated_at': row['updated_at'],
                'is_active': bool(row['is_active']),
                'message_count': row['message_count']
            }
        finally:
            conn.close()

    def set_title(self, conversation_id: int, title: str):
        """Set conversation title.

        Args:
            conversation_id: Conversation ID
            title: New title
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE laney_conversations
                SET title = ?
                WHERE id = ?
            """, (title, conversation_id))
            conn.commit()
        finally:
            conn.close()

    def delete_last_messages(self, conversation_id: int, count: int = 1) -> int:
        """Delete the last N messages from a conversation.

        Deletes both user and assistant messages. Useful for correcting
        mistakes or removing sensitive content from history.

        Args:
            conversation_id: Conversation ID
            count: Number of messages to delete (default 1)

        Returns:
            Number of messages actually deleted
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()

            # Get IDs of last N messages
            cursor.execute("""
                SELECT id FROM laney_messages
                WHERE conversation_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (conversation_id, count))
            rows = cursor.fetchall()

            if not rows:
                return 0

            ids_to_delete = [row['id'] for row in rows]

            # Delete the messages
            placeholders = ','.join('?' * len(ids_to_delete))
            cursor.execute(f"""
                DELETE FROM laney_messages
                WHERE id IN ({placeholders})
            """, ids_to_delete)

            deleted_count = cursor.rowcount

            # Update conversation message count
            cursor.execute("""
                UPDATE laney_conversations
                SET message_count = message_count - ?
                WHERE id = ?
            """, (deleted_count, conversation_id))

            conn.commit()
            return deleted_count
        finally:
            conn.close()


class TelegramBotPlugin(Plugin):
    """Telegram bot interface for mobile access (eunice device)."""

    def get_metadata(self):
        return {
            "name": "telegram_bot",
            "version": "1.0.0",
            "description": "Telegram interface for mobile access and notifications",
            "runs_on": ["rei", "both"],  # Server-side (provides eunice interface)
            "requires": []
        }

    def on_load(self):
        """Initialize the plugin."""
        self.logger.info("TelegramBot plugin loaded")

        # Initialize stats (always)
        self.messages_sent = 0
        self.commands_received = 0
        self.notifications_sent = 0
        self.bot_loop = None  # Event loop running the bot
        self.bot_thread = None  # Dedicated thread for bot
        self.keep_running = None  # Future that keeps bot running (so we can cancel it)

        # Track login messages for auto-expiry/updates
        # Format: {token: {'message': message_obj, 'expires_at': datetime, 'user_id': int}}
        self.login_messages = {}

        # Initialize archiving service (local + IA)
        self._init_archiving_service()

        # Initialize conversation manager for Laney memory
        self.conversation_manager = ConversationManager(self.core.config.db_path)

        if not TELEGRAM_AVAILABLE:
            self.logger.warning("python-telegram-bot not installed - bot will be disabled")
            self.logger.warning("Install with: pip install python-telegram-bot")
            self.bot_token = None
            self.application = None
            return

        # Get bot token from config
        self.bot_token = getattr(self.core.config, 'telegram_bot_token', None)
        if not self.bot_token:
            telegram_config = getattr(self.core.config, 'telegram', None)
            if telegram_config:
                self.bot_token = getattr(telegram_config, 'bot_token', None)

        if not self.bot_token:
            self.logger.warning("No Telegram bot token configured - bot will be disabled")
            self.logger.warning("Set telegram.bot_token in config.yaml")
            self.application = None
            return

        # Get chat ID (user to send notifications to)
        self.chat_id = None
        self.authorized_groups: List[int] = []  # From config
        self.pending_group_auth: Dict[int, dict] = {}  # chat_id -> {title, requested_at}
        telegram_config = getattr(self.core.config, 'telegram', None)
        if telegram_config:
            self.chat_id = getattr(telegram_config, 'chat_id', None)
            self.authorized_groups = getattr(telegram_config, 'authorized_groups', []) or []

        # Load authorized groups from database
        self._db_authorized_groups: set = self._load_db_authorized_groups()

        # Create bot application with increased timeouts for stability
        try:
            from telegram.request import HTTPXRequest
            # Configure request with longer timeouts and connection pool
            request = HTTPXRequest(
                connect_timeout=20.0,  # Connection timeout (default 5.0)
                read_timeout=30.0,     # Read timeout (default 5.0)
                write_timeout=30.0,    # Write timeout (default 5.0)
                pool_timeout=10.0,     # Pool timeout (default 1.0)
            )
            self.application = (
                Application.builder()
                .token(self.bot_token)
                .request(request)
                .get_updates_request(HTTPXRequest(
                    connect_timeout=20.0,
                    read_timeout=60.0,  # Long polling needs longer read timeout
                    write_timeout=30.0,
                    pool_timeout=10.0,
                ))
                .build()
            )
            self.logger.info("Telegram bot application created with extended timeouts")
        except Exception as e:
            self.logger.error(f"Failed to create bot application: {e}")
            self.application = None

    def on_enable(self):
        """Enable the plugin and start bot."""
        self.logger.info("TelegramBot plugin enabled")

        if not self.application:
            self.logger.warning("Bot not configured, skipping enable")
            return

        # Register command handlers
        self.application.add_handler(CommandHandler("start", self._cmd_start))
        self.application.add_handler(CommandHandler("help", self._cmd_help))
        self.application.add_handler(CommandHandler("login", self._cmd_login))
        self.application.add_handler(CommandHandler("stats", self._cmd_stats))
        self.application.add_handler(CommandHandler("plugins", self._cmd_plugins))
        self.application.add_handler(CommandHandler("status", self._cmd_status))
        self.application.add_handler(CommandHandler("recent", self._cmd_recent))
        self.application.add_handler(CommandHandler("search", self._cmd_search))
        self.application.add_handler(CommandHandler("classify", self._cmd_classify))
        self.application.add_handler(CommandHandler("spn", self._cmd_spn))
        self.application.add_handler(CommandHandler("mono", self._cmd_mono))
        self.application.add_handler(CommandHandler("box", self._cmd_box))
        self.application.add_handler(CommandHandler("ask", self._cmd_ask))
        self.application.add_handler(CommandHandler("laney", self._cmd_ask))  # Alias

        # Conversation management commands
        self.application.add_handler(CommandHandler("new", self._cmd_new_conversation))
        self.application.add_handler(CommandHandler("conversations", self._cmd_list_conversations))
        self.application.add_handler(CommandHandler("resume", self._cmd_resume_conversation))
        self.application.add_handler(CommandHandler("context", self._cmd_context))
        self.application.add_handler(CommandHandler("title", self._cmd_title))
        self.application.add_handler(CommandHandler("forget", self._cmd_forget))

        # Register message handlers for content (text, PDFs, etc.)
        self.application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            self._handle_message
        ))
        self.application.add_handler(MessageHandler(
            filters.Document.PDF | filters.Document.ALL,
            self._handle_document
        ))

        # Register callback handler for inline buttons (group authorization)
        self.application.add_handler(CallbackQueryHandler(
            self._handle_group_auth_callback,
            pattern="^auth_group:"
        ))

        # Subscribe to events for notifications
        self.subscribe('enrichment.complete', self._on_enrichment_complete)
        self.subscribe('classification.complete', self._on_classification_complete)
        self.subscribe('link.checked', self._on_link_checked)
        self.subscribe('telegram.send', self._on_telegram_send)
        self.subscribe('task.completed', self._on_task_completed)

        # Start bot in dedicated thread (not ThreadPoolExecutor - bot is long-lived)
        self.bot_thread = threading.Thread(
            target=self._start_bot,
            name="telegram-bot",
            daemon=True  # Allow holod to exit even if bot thread is running
        )
        self.bot_thread.start()
        self.logger.info("Telegram bot thread started")

    def _init_archiving_service(self):
        """Initialize the archiving service with local, IA, and ArchiveBox clients."""
        # Create local archive client
        local_client = LocalArchiveClient()

        # Create IA client if enabled
        ia_client = None
        if hasattr(self.core.config, 'integrations') and \
           getattr(self.core.config.integrations, 'internet_archive_enabled', False):
            ia_client = InternetArchiveClient(
                access_key=self.core.config.integrations.ia_access_key,
                secret_key=self.core.config.integrations.ia_secret_key,
                rate_limit=getattr(self.core.config.integrations, 'ia_rate_limit', 0.5)
            )
            self.logger.info("Archiving service initialized with local + Internet Archive")
        else:
            self.logger.info("Archiving service initialized with local only (IA disabled)")

        # Create ArchiveBox client if enabled
        archivebox_client = None
        if hasattr(self.core.config, 'integrations') and \
           getattr(self.core.config.integrations, 'archivebox_enabled', False):
            archivebox_client = ArchiveBoxClient(
                ssh_host=getattr(self.core.config.integrations, 'archivebox_host', '192.168.1.102'),
                ssh_user=getattr(self.core.config.integrations, 'archivebox_user', 'holocene'),
                data_dir=getattr(self.core.config.integrations, 'archivebox_data_dir', '/opt/archivebox/data'),
            )
            self.logger.info("ArchiveBox client initialized")

        # Create unified archiving service
        self.archiving = ArchivingService(
            db=self.core.db,
            local_client=local_client,
            ia_client=ia_client,
            archivebox_client=archivebox_client
        )

        # Log available tools
        tool_info = self.archiving.get_tool_info()
        if tool_info['local']['monolith']['available']:
            self.logger.info("Local archiving: monolith available")
        if tool_info['local']['wget']['available']:
            self.logger.info("Local archiving: wget available")
        if not tool_info['local']['monolith']['available'] and not tool_info['local']['wget']['available']:
            self.logger.warning("No local archiving tools available - install monolith or wget")
        if tool_info['archivebox']['available']:
            self.logger.info(f"ArchiveBox available: {tool_info['archivebox'].get('web_ui', 'N/A')}")

    def _start_bot(self):
        """Start the bot (runs in dedicated thread).

        This runs in its own thread, so we create a new event loop for
        the async telegram bot. We can't use run_polling() because it
        tries to set signal handlers which only work in main thread.
        """
        try:
            # Create new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self.bot_loop = loop  # Store for notifications

            async def run():
                """Start polling without signal handlers."""
                await self.application.initialize()
                await self.application.start()

                # Set bot commands for autocomplete
                from telegram import BotCommand
                commands = [
                    BotCommand("start", "Initialize and authorize bot"),
                    BotCommand("help", "Show available commands"),
                    BotCommand("ask", "Ask Laney anything about your collection"),
                    BotCommand("login", "Generate web login magic link"),
                    BotCommand("stats", "View bot statistics"),
                    BotCommand("status", "View system status"),
                    BotCommand("plugins", "List active plugins"),
                    BotCommand("recent", "Show recently added items"),
                    BotCommand("search", "Search books and papers"),
                    BotCommand("classify", "Get Dewey classification"),
                ]
                await self.application.bot.set_my_commands(commands)
                self.logger.info("Bot commands registered for autocomplete")

                # Start the updater (polling)
                await self.application.updater.start_polling(
                    allowed_updates=["message", "callback_query"],
                    drop_pending_updates=True
                )

                self.logger.info("Telegram bot polling started")

                # Keep running until stopped
                # The updater will keep polling in the background
                # We just need to keep the loop alive
                try:
                    # Create a future we can cancel later
                    self.keep_running = asyncio.Future()
                    await self.keep_running
                except asyncio.CancelledError:
                    self.logger.info("Bot polling cancelled")
                finally:
                    # Clean shutdown
                    await self.application.updater.stop()
                    await self.application.stop()
                    await self.application.shutdown()

            # Run the polling loop
            loop.run_until_complete(run())
            self.logger.info("Telegram bot polling stopped")
            return True
        except Exception as e:
            self.logger.error(f"Failed to start bot: {e}", exc_info=True)
            raise
        finally:
            # Clean up event loop
            self.bot_loop = None
            try:
                loop.close()
            except:
                pass

    def _load_db_authorized_groups(self) -> set:
        """Load authorized groups from database."""
        try:
            conn = sqlite3.connect(self.core.config.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT chat_id FROM telegram_authorized_groups
                WHERE is_active = 1
            """)
            groups = {row[0] for row in cursor.fetchall()}
            conn.close()
            if groups:
                self.logger.info(f"Loaded {len(groups)} authorized groups from DB")
            return groups
        except Exception as e:
            self.logger.debug(f"Could not load authorized groups from DB: {e}")
            return set()

    def _add_authorized_group(self, chat_id: int, chat_title: str, authorized_by: int) -> bool:
        """Add a group to authorized list in database."""
        try:
            conn = sqlite3.connect(self.core.config.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO telegram_authorized_groups
                (chat_id, chat_title, authorized_by, authorized_at, is_active)
                VALUES (?, ?, ?, ?, 1)
            """, (chat_id, chat_title, authorized_by, datetime.now().isoformat()))
            conn.commit()
            conn.close()
            self._db_authorized_groups.add(chat_id)
            self.logger.info(f"Authorized group: {chat_title} ({chat_id})")
            return True
        except Exception as e:
            self.logger.error(f"Failed to add authorized group: {e}")
            return False

    def _remove_authorized_group(self, chat_id: int) -> bool:
        """Remove a group from authorized list."""
        try:
            conn = sqlite3.connect(self.core.config.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE telegram_authorized_groups
                SET is_active = 0
                WHERE chat_id = ?
            """, (chat_id,))
            conn.commit()
            conn.close()
            self._db_authorized_groups.discard(chat_id)
            return True
        except Exception as e:
            self.logger.error(f"Failed to remove authorized group: {e}")
            return False

    async def _retry_telegram_call(self, coro_func, *args, max_retries=3, base_delay=1.0, **kwargs):
        """Retry a Telegram API call with exponential backoff.

        Args:
            coro_func: Async function to call
            max_retries: Maximum number of retries
            base_delay: Base delay in seconds (doubles each retry)
            *args, **kwargs: Arguments to pass to coro_func

        Returns:
            Result of the coroutine, or None if all retries failed
        """
        from telegram.error import TimedOut, NetworkError
        import asyncio

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                return await coro_func(*args, **kwargs)
            except (TimedOut, NetworkError) as e:
                last_error = e
                if attempt < max_retries:
                    delay = base_delay * (2 ** attempt)
                    print(f"[TELEGRAM] Retry {attempt + 1}/{max_retries} after {delay}s: {e}", flush=True)
                    await asyncio.sleep(delay)
                else:
                    print(f"[TELEGRAM] All {max_retries} retries failed: {e}", flush=True)

        return None

    def _is_authorized(self, chat_id: int, chat_type: str = "private") -> bool:
        """Check if user/group is authorized to use bot.

        Args:
            chat_id: Telegram chat ID
            chat_type: Chat type ('private', 'group', 'supergroup', 'channel')

        Returns:
            True if authorized, False otherwise
        """
        # Group chats check against both config and DB authorized groups
        if chat_type in ("group", "supergroup"):
            return chat_id in self.authorized_groups or chat_id in self._db_authorized_groups

        # Private chats: if no chat_id configured yet, first user becomes authorized
        if not self.chat_id:
            return True

        # Otherwise, only configured chat_id is authorized
        return chat_id == self.chat_id

    def _is_owner(self, user_id: int) -> bool:
        """Check if user is the bot owner (for authorizing groups)."""
        return user_id == self.chat_id

    def _is_group_chat(self, update) -> bool:
        """Check if message is from a group chat."""
        chat_type = update.effective_chat.type
        return chat_type in ("group", "supergroup")

    async def _request_group_authorization(self, chat_id: int, chat_title: str, update):
        """Send authorization request to owner via DM."""
        # Store pending request
        self.pending_group_auth[chat_id] = {
            'title': chat_title,
            'requested_at': datetime.now().isoformat()
        }

        # Create inline keyboard with Authorize/Deny buttons
        keyboard = [
            [
                InlineKeyboardButton("✅ Authorize", callback_data=f"auth_group:{chat_id}:yes"),
                InlineKeyboardButton("❌ Deny", callback_data=f"auth_group:{chat_id}:no"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Send DM to owner
        try:
            await self.application.bot.send_message(
                chat_id=self.chat_id,  # Owner's private chat
                text=f"🔔 *Group Authorization Request*\n\n"
                     f"You used `/laney` in:\n"
                     f"**{chat_title}**\n"
                     f"`{chat_id}`\n\n"
                     f"Do you want to authorize Laney for this group?",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
            self.logger.info(f"Sent group auth request for: {chat_title} ({chat_id})")
        except Exception as e:
            self.logger.error(f"Failed to send auth request: {e}")

    async def _handle_group_auth_callback(self, update, context):
        """Handle inline button callbacks for group authorization."""
        query = update.callback_query
        await query.answer()  # Acknowledge the callback

        # Parse callback data: "auth_group:<chat_id>:<yes|no>"
        data = query.data
        if not data.startswith("auth_group:"):
            return

        parts = data.split(":")
        if len(parts) != 3:
            return

        _, chat_id_str, action = parts
        try:
            group_chat_id = int(chat_id_str)
        except ValueError:
            return

        # Get pending request info
        pending = self.pending_group_auth.pop(group_chat_id, None)
        chat_title = pending['title'] if pending else f"Group {group_chat_id}"

        if action == "yes":
            # Authorize the group
            success = self._add_authorized_group(
                chat_id=group_chat_id,
                chat_title=chat_title,
                authorized_by=update.effective_user.id
            )

            if success:
                await query.edit_message_text(
                    f"✅ *Group Authorized*\n\n"
                    f"**{chat_title}**\n\n"
                    f"Laney will now respond to `/laney` commands in this group.",
                    parse_mode='Markdown'
                )

                # Also notify the group
                try:
                    await self.application.bot.send_message(
                        chat_id=group_chat_id,
                        text="👋 Hello! I'm now authorized in this group.\n\n"
                             "Use `/laney <question>` to ask me anything!\n"
                             "Type `/help` for more info.",
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    self.logger.warning(f"Could not notify group: {e}")
            else:
                await query.edit_message_text(
                    f"❌ Failed to authorize group. Check logs.",
                    parse_mode='Markdown'
                )
        else:
            # Denied
            await query.edit_message_text(
                f"🚫 *Authorization Denied*\n\n"
                f"**{chat_title}** will not receive Laney responses.",
                parse_mode='Markdown'
            )

    async def _cmd_start(self, update, context):
        """Handle /start command."""
        self.commands_received += 1

        chat_id = update.effective_chat.id

        # Check authorization
        if not self._is_authorized(chat_id):
            await update.message.reply_text(
                "❌ *Unauthorized*\n\n"
                "This bot is private and only responds to its owner.",
                parse_mode='Markdown'
            )
            self.logger.warning(f"Unauthorized access attempt from chat_id: {chat_id}")
            return

        # Save chat ID for notifications (first time only)
        if not self.chat_id:
            self.chat_id = chat_id
            self.logger.info(f"Chat ID saved: {self.chat_id}")

        welcome_msg = """🌍 *Holocene Bot*

Welcome to your personal knowledge management assistant!

I'll notify you about:
• Book enrichments
• Classifications
• Link checks

Available commands:
/help - Show this help
/stats - Show system stats
/plugins - List active plugins
/status - System status
"""
        await update.message.reply_text(welcome_msg, parse_mode='Markdown')
        self.messages_sent += 1

    async def _cmd_help(self, update, context):
        """Handle /help command."""
        self.commands_received += 1

        # Check authorization (works in groups too)
        chat_type = update.effective_chat.type
        if not self._is_authorized(update.effective_chat.id, chat_type):
            if self._is_group_chat(update):
                return  # Silently ignore in unauthorized groups
            await update.message.reply_text("❌ Unauthorized")
            return

        # Different help for groups vs private
        if self._is_group_chat(update):
            help_msg = """🌍 *Laney in Group Chat*

Use `/laney <question>` to ask me anything!

I have access to Arthur's collection of books, papers, and links. I can also search the web.

Each group has its own conversation memory.

Examples:
• `/laney What do you know about geostatistics?`
• `/laney Find papers about kriging`
• `/laney What's the latest on ESP32?`
"""
        else:
            help_msg = """📚 *Holocene Commands*

*Laney AI (with memory!):*
Just send any text to chat with Laney
/new - Start fresh conversation
/conversations - List past conversations
/resume <id> - Resume old conversation
/context - Current conversation info
/title <name> - Rename conversation
/forget [n] - Remove last n messages

*Other Commands:*
/login - Magic link for web access
/stats - View statistics
/status - System status
/recent - Show recently added items
/search <query> - Search books/papers
/classify <topic> - Get Dewey class
/spn <url> - Internet Archive snapshot
/mono <url> - Local monolith archive
/box <url> - ArchiveBox (JS render)

*Send me:*
• Text - Chat with Laney (remembers context!)
• DOIs - Fetch paper metadata
• URLs - Save and archive links
• PDFs - Saved to library
• JSON - MercadoLivre import
"""
        await update.message.reply_text(help_msg, parse_mode='Markdown')
        self.messages_sent += 1

    async def _cmd_login(self, update, context):
        """Handle /login command - generate magic link for web access."""
        self.commands_received += 1

        # Check authorization
        if not self._is_authorized(update.effective_chat.id):
            await update.message.reply_text("❌ Unauthorized")
            return

        telegram_user_id = update.effective_user.id
        telegram_username = update.effective_user.username

        try:
            # Get or create user
            db = self.core.db
            cursor = db.conn.cursor()

            # Check if user exists
            cursor.execute(
                "SELECT id FROM users WHERE telegram_user_id = ?",
                (telegram_user_id,)
            )
            user_row = cursor.fetchone()

            if user_row:
                user_id = user_row[0]
            else:
                # Create new user
                cursor.execute("""
                    INSERT INTO users (telegram_user_id, telegram_username, created_at, is_admin)
                    VALUES (?, ?, ?, 1)
                """, (telegram_user_id, telegram_username, datetime.now().isoformat()))
                user_id = cursor.lastrowid
                db.conn.commit()
                self.logger.info(f"Created new user: {user_id} (telegram: {telegram_user_id})")

            # Generate secure random token (256 bits = 32 bytes = 64 hex chars)
            token = secrets.token_urlsafe(32)  # URL-safe base64, ~43 chars

            # Calculate expiry (5 minutes from now)
            expires_at = datetime.now() + timedelta(minutes=5)

            # Store token in database
            cursor.execute("""
                INSERT INTO auth_tokens (user_id, token, created_at, expires_at)
                VALUES (?, ?, ?, ?)
            """, (user_id, token, datetime.now().isoformat(), expires_at.isoformat()))
            db.conn.commit()

            # Build magic link URL
            # TODO: Get base URL from config (for now hardcode)
            base_url = "https://holo.stdgeo.com"
            magic_link = f"{base_url}/auth/login?token={token}"

            # Send magic link to user
            # Wrap URL in backticks to prevent markdown parsing issues with token characters
            msg = f"""🔐 *Web Login Link*

Your magic link is ready! Click below to log in to the Holocene web interface.

`{magic_link}`

⏱️ *Expires in 5 minutes*
🔒 *Single-use only*

This link will grant you access to:
• Web dashboard
• Collection browser
• Research tools
"""

            sent_message = await update.message.reply_text(msg, parse_mode='Markdown', disable_web_page_preview=True)
            self.messages_sent += 1
            self.logger.info(f"Magic link generated for user {user_id} (telegram: {telegram_user_id})")

            # Track this message for auto-expiry and usage updates
            self.login_messages[token] = {
                'message': sent_message,
                'expires_at': expires_at,
                'user_id': user_id,
                'telegram_username': telegram_username
            }

            # Schedule auto-expiry (edit message after 5 minutes)
            self.run_in_background(
                lambda: self._auto_expire_login_message(token, expires_at),
                callback=lambda result: self.logger.debug(f"Login message auto-expired: {token[:8]}..."),
                error_handler=lambda e: self.logger.error(f"Failed to auto-expire login message: {e}")
            )

        except Exception as e:
            self.logger.error(f"Failed to generate login link: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Failed to generate login link: {str(e)[:100]}")

    async def _cmd_stats(self, update, context):
        """Handle /stats command."""
        self.commands_received += 1

        # Check authorization
        if not self._is_authorized(update.effective_chat.id):
            await update.message.reply_text("❌ Unauthorized")
            return

        # Gather stats from plugins
        stats_msg = f"""📊 *Holocene Stats*

*Bot:*
• Messages sent: {self.messages_sent}
• Commands received: {self.commands_received}
• Notifications: {self.notifications_sent}

*Database:*
"""

        # Get book/link counts
        try:
            cursor = self.core.db.conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM books")
            book_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM links")
            link_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM papers")
            paper_count = cursor.fetchone()[0]

            stats_msg += f"""• Books: {book_count}
• Links: {link_count}
• Papers: {paper_count}
"""
        except Exception as e:
            stats_msg += f"Error getting counts: {e}\n"

        await update.message.reply_text(stats_msg, parse_mode='Markdown')
        self.messages_sent += 1

    async def _cmd_plugins(self, update, context):
        """Handle /plugins command - show actually running plugins."""
        self.commands_received += 1

        # Check authorization
        if not self._is_authorized(update.effective_chat.id):
            await update.message.reply_text("❌ Unauthorized")
            return

        plugins_msg = "🔌 *Active Plugins*\n\n"

        # Get plugin status from registry
        # (Direct registry access is more reliable than HTTP)
        try:
            if hasattr(self.core, 'registry') and self.core.registry:
                for name, plugin in self.core.registry._plugins.items():
                    metadata = plugin.get_metadata()
                    version = metadata.get('version', '1.0.0')
                    enabled = plugin.enabled
                    status = "✅" if enabled else "⏸️"
                    plugins_msg += f"• `{name}` {status} v{version}\n"
                    if metadata.get('description'):
                        desc = metadata['description'][:60]
                        # Don't use markdown formatting for description - just plain text
                        plugins_msg += f"  {desc}\n"

                # Add debug info about API accessibility
                plugins_msg += f"\n`Registry: Direct access`"

                # Test API accessibility for diagnostics
                try:
                    import requests
                    test_response = requests.get('http://localhost:5555/health', timeout=1)
                    plugins_msg += f"\n`API: ✅ {test_response.status_code}`"
                except ImportError:
                    plugins_msg += f"\n`API: ⚠️ requests not installed`"
                except Exception as api_err:
                    plugins_msg += f"\n`API: ❌ {type(api_err).__name__}`"
                    self.logger.warning(f"REST API test failed: {api_err}")
            else:
                plugins_msg += "⚠️ Registry not available"
        except Exception as e:
            self.logger.error(f"Failed to get plugins: {e}", exc_info=True)
            plugins_msg += f"⚠️ Error: {str(e)[:50]}"

        # Send response
        try:
            self.logger.info(f"Sending plugins response ({len(plugins_msg)} chars)")
            await update.message.reply_text(plugins_msg, parse_mode='Markdown')
            self.messages_sent += 1
        except Exception as e:
            self.logger.error(f"Failed to send plugins message: {e}", exc_info=True)
            # Try sending without markdown if markdown parsing failed
            try:
                await update.message.reply_text(f"⚠️ Plugin list available but formatting failed: {str(e)[:100]}")
            except:
                pass

    async def _cmd_status(self, update, context):
        """Handle /status command."""
        self.commands_received += 1

        # Check authorization
        if not self._is_authorized(update.effective_chat.id):
            await update.message.reply_text("❌ Unauthorized")
            return

        status_msg = f"""⚡ *System Status*

*Device:* rei (server)
*Interface:* eunice (mobile)
*Status:* 🟢 Online

*Uptime:* Running
*Last update:* {datetime.now().strftime('%H:%M:%S')}
"""

        await update.message.reply_text(status_msg, parse_mode='Markdown')
        self.messages_sent += 1

    async def _cmd_recent(self, update, context):
        """Handle /recent command - show recently added items."""
        self.commands_received += 1

        # Check authorization
        if not self._is_authorized(update.effective_chat.id):
            await update.message.reply_text("❌ Unauthorized")
            return

        try:
            db = self.core.db
            recent_msg = "📚 *Recently Added*\n\n"

            # Get recent books (last 5)
            books = db.get_books(limit=5)
            if books:
                recent_msg += "*Books:*\n"
                for book in books:
                    title = book.get('title') or '(Untitled)'
                    if len(title) > 50:
                        title = title[:50] + "..."
                    # Escape markdown characters
                    title = title.replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace('`', '\\`')
                    recent_msg += f"• {title}\n"
                recent_msg += "\n"

            # Get recent papers (last 5)
            papers = db.get_papers(limit=5)
            if papers:
                recent_msg += "*Papers:*\n"
                for paper in papers:
                    title = paper.get('title') or '(Untitled)'
                    if len(title) > 50:
                        title = title[:50] + "..."
                    # Escape markdown characters
                    title = title.replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace('`', '\\`')
                    recent_msg += f"• {title}\n"
                recent_msg += "\n"

            # Get recent links (last 5)
            links = db.get_links(limit=5)
            if links:
                recent_msg += "*Links:*\n"
                for link in links:
                    title = link.get('title') or link.get('url') or '(No title)'
                    if len(title) > 50:
                        title = title[:50] + "..."
                    # Escape markdown characters
                    title = title.replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace('`', '\\`')
                    recent_msg += f"• {title}\n"

            if len(recent_msg) == len("📚 *Recently Added*\n\n"):
                recent_msg += "_No items found_"

            self.logger.info(f"Sending recent items response ({len(recent_msg)} chars)")
            await update.message.reply_text(recent_msg, parse_mode='Markdown')
            self.messages_sent += 1
        except Exception as e:
            self.logger.error(f"Failed to get recent items: {e}", exc_info=True)
            try:
                await update.message.reply_text(f"❌ Failed to get recent items: {str(e)[:100]}")
            except:
                await update.message.reply_text("❌ Failed to get recent items")

    async def _cmd_search(self, update, context):
        """Handle /search command - search books and papers."""
        self.commands_received += 1

        # Check authorization
        if not self._is_authorized(update.effective_chat.id):
            await update.message.reply_text("❌ Unauthorized")
            return

        # Get search query from command args
        query = ' '.join(context.args) if context.args else None
        if not query:
            await update.message.reply_text("Usage: /search <query>")
            return

        db = self.core.db
        results_msg = f"🔍 *Search Results for:* {query}\n\n"
        found_any = False

        # Search books
        books = db.get_books(search=query, limit=5)
        if books:
            found_any = True
            results_msg += "*Books:*\n"
            for book in books:
                title = book['title'][:50] + "..." if len(book['title']) > 50 else book['title']
                author = book.get('author', 'Unknown')[:30]
                results_msg += f"• {title} - {author}\n"
            results_msg += "\n"

        # Search papers
        papers = db.get_papers(search=query, limit=5)
        if papers:
            found_any = True
            results_msg += "*Papers:*\n"
            for paper in papers:
                title = paper['title'][:50] + "..." if len(paper['title']) > 50 else paper['title']
                results_msg += f"• {title}\n"
            results_msg += "\n"

        if not found_any:
            results_msg += "_No results found_"

        await update.message.reply_text(results_msg, parse_mode='Markdown')
        self.messages_sent += 1

    async def _cmd_classify(self, update, context):
        """Handle /classify command - get Dewey classification for a topic."""
        self.commands_received += 1

        # Check authorization
        if not self._is_authorized(update.effective_chat.id):
            await update.message.reply_text("❌ Unauthorized")
            return

        # Get topic from command args
        topic = ' '.join(context.args) if context.args else None
        if not topic:
            await update.message.reply_text("Usage: /classify <topic>")
            return

        await update.message.reply_text(f"🔍 Classifying: _{topic}_...", parse_mode='Markdown')

        # Run classification in background
        def classify():
            from ..research import DeweyClassifier
            # DeweyClassifier expects config_path (Path), not config object
            # Passing None uses default config path
            classifier = DeweyClassifier(config_path=None)
            # Use classify_book for generic topics (only method available)
            result = classifier.classify_book(title=topic)
            return result

        try:
            result = await asyncio.get_event_loop().run_in_executor(None, classify)

            # Log what we got back
            self.logger.info(f"Classification result: {result}")

            if result and result.get('dewey_number'):
                msg = f"📊 *Classification Result*\n\n"
                msg += f"*Topic:* {topic}\n"
                msg += f"*Dewey:* {result['dewey_number']}\n"
                msg += f"*Category:* {result.get('dewey_label', 'Unknown')}\n"
                msg += f"*Confidence:* {result.get('confidence', 'unknown').title()}\n"
                if result.get('alternative_numbers'):
                    alts = ', '.join(result['alternative_numbers'])
                    msg += f"*Alternatives:* {alts}\n"
            else:
                self.logger.warning(f"Classification returned no dewey number. Result: {result}")
                msg = "❌ Could not classify topic"

            await update.message.reply_text(msg, parse_mode='Markdown')
            self.messages_sent += 1
        except Exception as e:
            self.logger.error(f"Classification error: {e}", exc_info=True)
            # Send error details to user
            try:
                await update.message.reply_text(f"❌ Classification failed: {str(e)[:100]}")
            except:
                await update.message.reply_text("❌ Classification failed")

    async def _cmd_spn(self, update, context):
        """Handle /spn command - force new Internet Archive snapshot for existing link."""
        self.commands_received += 1

        # Check authorization
        if not self._is_authorized(update.effective_chat.id):
            await update.message.reply_text("❌ Unauthorized")
            return

        # Get URL from command args
        url = ' '.join(context.args) if context.args else None
        if not url:
            await update.message.reply_text(
                "Usage: `/spn <url>`\n\n"
                "Force a new Internet Archive snapshot for a URL already in your collection.\n"
                "Respects IA's rate limits (5 seconds between saves).",
                parse_mode='Markdown'
            )
            return

        # Check if URL is in database
        db = self.core.db
        link = db.conn.execute("SELECT id, url, archived FROM links WHERE url = ?", (url,)).fetchone()

        if not link:
            await update.message.reply_text(
                "❌ URL not in database.\n\n"
                "Send the URL first to add it to your collection, then use `/spn` to force re-archiving.",
                parse_mode='Markdown'
            )
            return

        link_id, actual_url, currently_archived = link

        # Send initial message
        status_msg = await update.message.reply_text(
            f"📦 *Save Page Now*\n\n"
            f"`{actual_url}`\n\n"
            f"⏳ Forcing new snapshot...\n"
            f"_(Respects 5s rate limit)_",
            parse_mode='Markdown'
        )

        # Force archive in background (local + IA)
        def force_archive():
            # Archive with unified service (local + force IA snapshot)
            result = self.archiving.archive_url(
                link_id=link[0],
                url=actual_url,
                local_format='monolith',  # Always create local archive
                use_ia=True,
                force_ia=True  # Force new IA snapshot
            )

            # Update old columns for backward compatibility
            if result.get('success') and 'internet_archive' in result.get('services', {}):
                ia_service = result['services']['internet_archive']
                if ia_service.get('status') == 'success':
                    db.update_link_archive_status(
                        url=actual_url,
                        archived=True,
                        archive_url=ia_service.get('snapshot_url'),
                        archive_date=None  # Stored in archive_snapshots now
                    )

            return result

        try:
            result = await asyncio.get_event_loop().run_in_executor(None, force_archive)

            if result.get('success'):
                # Build success message with all services
                msg = f"✅ *New Snapshot Created*\n\n`{actual_url}`\n\n"

                services = result.get('services', {})

                # Local archive
                if 'local_monolith' in services:
                    local = services['local_monolith']
                    if local.get('status') == 'success':
                        file_size = local.get('file_size', 0)
                        size_kb = file_size // 1024
                        mono_url = f"https://holo.stdgeo.com/mono/{link[0]}/latest"
                        msg += f"💾 Local: {size_kb:,} KB - [View ↗]({mono_url})\n"

                # Internet Archive
                if 'internet_archive' in services:
                    ia = services['internet_archive']
                    if ia.get('status') == 'success':
                        snapshot_url = ia.get('snapshot_url', 'N/A')
                        was_cached = ia.get('already_archived', False)
                        status_icon = "📦" if was_cached else "🌐"
                        msg += f"{status_icon} Internet Archive: [View ↗]({snapshot_url})\n"

            else:
                # Failed
                errors = result.get('errors', ['Unknown error'])
                error_text = '\n'.join(errors)
                msg = f"❌ *Archive Failed*\n\n`{actual_url}`\n\n{error_text}"

            await status_msg.edit_text(msg, parse_mode='Markdown', disable_web_page_preview=True)
            self.messages_sent += 1

        except Exception as e:
            self.logger.error(f"SPN command error: {e}", exc_info=True)
            try:
                await status_msg.edit_text(
                    f"❌ *Archive Failed*\n\n`{actual_url}`\n\n{str(e)[:200]}",
                    parse_mode='Markdown'
                )
            except:
                await update.message.reply_text("❌ Archive failed")

    async def _cmd_mono(self, update, context):
        """Handle /mono command - update local monolith snapshot only."""
        self.commands_received += 1

        # Check authorization
        if not self._is_authorized(update.effective_chat.id):
            await update.message.reply_text("❌ Unauthorized")
            return

        # Get URL from command args
        url = ' '.join(context.args) if context.args else None
        if not url:
            await update.message.reply_text(
                "Usage: `/mono <url>`\n\n"
                "Update local monolith snapshot for a URL in your collection.\n"
                "Only creates local archive (no Internet Archive).",
                parse_mode='Markdown'
            )
            return

        # Check if URL is in database
        db = self.core.db
        link = db.conn.execute("SELECT id, url FROM links WHERE url = ?", (url,)).fetchone()

        if not link:
            await update.message.reply_text(
                "❌ URL not in database.\n\n"
                "Send the URL first to add it to your collection, then use `/mono` to update local archive.",
                parse_mode='Markdown'
            )
            return

        link_id, actual_url = link

        # Send initial message
        status_msg = await update.message.reply_text(
            f"💾 *Local Archive*\n\n"
            f"`{actual_url}`\n\n"
            f"⏳ Creating monolith snapshot...",
            parse_mode='Markdown'
        )

        # Archive locally in background
        def local_archive():
            # Archive with unified service (local only, no IA)
            result = self.archiving.archive_url(
                link_id=link_id,
                url=actual_url,
                local_format='monolith',  # Create local monolith
                use_ia=False,  # Skip Internet Archive
            )
            return result

        try:
            result = await asyncio.get_event_loop().run_in_executor(None, local_archive)

            if result.get('success'):
                # Build success message
                services = result.get('services', {})

                if 'local_monolith' in services:
                    local = services['local_monolith']
                    if local.get('status') == 'success':
                        file_size = local.get('file_size', 0)
                        size_kb = file_size // 1024
                        mono_url = f"https://holo.stdgeo.com/mono/{link_id}/latest"

                        msg = (
                            f"✅ *Local Archive Updated*\n\n"
                            f"`{actual_url}`\n\n"
                            f"💾 Size: {size_kb:,} KB\n"
                            f"[View local archive ↗]({mono_url})"
                        )
                    else:
                        msg = f"❌ *Archive Failed*\n\n`{actual_url}`\n\n{local.get('error', 'Unknown error')}"
                else:
                    msg = f"❌ *Archive Failed*\n\n`{actual_url}`\n\nNo local archive created"

            else:
                # Failed
                errors = result.get('errors', ['Unknown error'])
                error_text = '\n'.join(errors)
                msg = f"❌ *Archive Failed*\n\n`{actual_url}`\n\n{error_text}"

            await status_msg.edit_text(msg, parse_mode='Markdown', disable_web_page_preview=True)
            self.messages_sent += 1

        except Exception as e:
            self.logger.error(f"Mono command error: {e}", exc_info=True)
            try:
                await status_msg.edit_text(
                    f"❌ *Archive Failed*\n\n`{actual_url}`\n\n{str(e)[:200]}",
                    parse_mode='Markdown'
                )
            except:
                await update.message.reply_text("❌ Archive failed")

    async def _cmd_box(self, update, context):
        """Handle /box command - archive with ArchiveBox (comprehensive with JS rendering)."""
        self.commands_received += 1

        # Check authorization
        if not self._is_authorized(update.effective_chat.id):
            await update.message.reply_text("❌ Unauthorized")
            return

        # Get URL from command args
        url = ' '.join(context.args) if context.args else None
        if not url:
            await update.message.reply_text(
                "Usage: `/box <url>`\n\n"
                "Archive URL with ArchiveBox (handles lazy-loaded images & JavaScript).\n"
                "Creates comprehensive archive with SingleFile, screenshots, and more.",
                parse_mode='Markdown'
            )
            return

        # Check if URL is in database
        db = self.core.db
        link = db.conn.execute("SELECT id, url FROM links WHERE url = ?", (url,)).fetchone()

        if not link:
            await update.message.reply_text(
                "❌ URL not in database.\n\n"
                "Send the URL first to add it to your collection, then use `/box` to archive.",
                parse_mode='Markdown'
            )
            return

        link_id, actual_url = link

        # Send initial message
        status_msg = await update.message.reply_text(
            f"📦 *ArchiveBox*\n\n"
            f"`{actual_url}`\n\n"
            f"⏳ Archiving with headless Chrome...\n"
            f"_(This may take 1-3 minutes)_",
            parse_mode='Markdown'
        )

        # Archive with ArchiveBox in background
        def box_archive():
            # Archive with unified service (ArchiveBox only)
            result = self.archiving.archive_url(
                link_id=link_id,
                url=actual_url,
                local_format=None,  # Skip local monolith
                use_ia=False,  # Skip Internet Archive
                use_archivebox=True  # Use ArchiveBox
            )
            return result

        try:
            result = await asyncio.get_event_loop().run_in_executor(None, box_archive)

            if result.get('success'):
                # Build success message
                services = result.get('services', {})

                if 'archivebox' in services:
                    ab = services['archivebox']
                    if ab.get('status') == 'success':
                        snapshot_id = ab.get('archivebox_snapshot_id', 'unknown')
                        # Use proxied URL through holo.stdgeo.com
                        proxied_url = f"https://holo.stdgeo.com/box/{snapshot_id}"

                        msg = (
                            f"✅ *ArchiveBox Archive Complete*\n\n"
                            f"`{actual_url}`\n\n"
                            f"📦 Snapshot ID: `{snapshot_id}`\n"
                            f"[View archive ↗]({proxied_url})\n\n"
                            f"_Includes: SingleFile, Screenshot, WARC, etc._"
                        )
                    else:
                        msg = f"❌ *Archive Failed*\n\n`{actual_url}`\n\n{ab.get('error', 'Unknown error')}"
                else:
                    msg = f"❌ *Archive Failed*\n\n`{actual_url}`\n\nNo ArchiveBox archive created"

            else:
                # Failed
                errors = result.get('errors', ['Unknown error'])
                error_text = '\n'.join(errors)
                msg = f"❌ *Archive Failed*\n\n`{actual_url}`\n\n{error_text}"

            await status_msg.edit_text(msg, parse_mode='Markdown', disable_web_page_preview=True)
            self.messages_sent += 1

        except Exception as e:
            self.logger.error(f"Box command error: {e}", exc_info=True)
            try:
                await status_msg.edit_text(
                    f"❌ *Archive Failed*\n\n`{actual_url}`\n\n{str(e)[:200]}",
                    parse_mode='Markdown'
                )
            except:
                await update.message.reply_text("❌ Archive failed")

    async def _cmd_ask(self, update, context):
        """Handle /ask and /laney commands - ask Laney a question.

        Works in both private chats and authorized group chats.
        """
        self.commands_received += 1

        # Check authorization (pass chat_type for group support)
        chat_type = update.effective_chat.type
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id

        if not self._is_authorized(chat_id, chat_type):
            if self._is_group_chat(update):
                # Check if the owner is trying to use /laney in an unauthorized group
                if self._is_owner(user_id):
                    # Owner found! Send them a DM to authorize this group
                    chat_title = update.effective_chat.title or "Unknown Group"
                    await self._request_group_authorization(chat_id, chat_title, update)
                # Silently ignore other users
                return
            await update.message.reply_text("❌ Unauthorized")
            return

        # Get query from command args
        query = ' '.join(context.args) if context.args else None
        if not query:
            # Different help text for groups vs private
            if self._is_group_chat(update):
                await update.message.reply_text(
                    "Usage: `/laney <question>`\n\n"
                    "Each group has its own conversation history.",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(
                    "Usage: `/ask <question>`\n\n"
                    "Laney remembers your conversation!\n"
                    "Just send text directly to chat.\n\n"
                    "Commands:\n"
                    "• `/new` - Start fresh conversation\n"
                    "• `/conversations` - List past chats\n"
                    "• `/context` - Current conversation info",
                    parse_mode='Markdown'
                )
            return

        # Use _ask_laney which handles conversation history
        await self._ask_laney(query, update)

    async def _cmd_new_conversation(self, update, context):
        """Handle /new command - start a fresh conversation."""
        self.commands_received += 1

        if not self._is_authorized(update.effective_chat.id):
            await update.message.reply_text("❌ Unauthorized")
            return

        chat_id = update.effective_chat.id
        conv_id = self.conversation_manager.start_new_conversation(chat_id)

        await update.message.reply_text(
            f"🆕 *New conversation started!*\n\n"
            f"Conversation ID: `{conv_id}`\n"
            f"Laney's memory has been cleared.\n"
            f"Send any message to start chatting!",
            parse_mode='Markdown'
        )
        self.messages_sent += 1

    async def _cmd_list_conversations(self, update, context):
        """Handle /conversations command - list past conversations."""
        self.commands_received += 1

        if not self._is_authorized(update.effective_chat.id):
            await update.message.reply_text("❌ Unauthorized")
            return

        chat_id = update.effective_chat.id
        conversations = self.conversation_manager.list_conversations(chat_id, limit=10)

        if not conversations:
            await update.message.reply_text(
                "📭 No conversations yet.\nJust send a message to start one!",
                parse_mode='Markdown'
            )
            return

        lines = ["📚 *Your Conversations*\n"]
        for conv in conversations:
            active = "→ " if conv['is_active'] else "  "
            # Parse date for display
            try:
                updated = datetime.fromisoformat(conv['updated_at'])
                date_str = updated.strftime("%m/%d %H:%M")
            except:
                date_str = "?"

            title = conv['title'] or "(untitled)"
            # Escape markdown in title
            title = title.replace('*', '\\*').replace('_', '\\_').replace('`', '\\`')
            lines.append(f"{active}`{conv['id']}` {title[:30]} ({conv['message_count']} msgs, {date_str})")

        lines.append("\n_Use `/resume <id>` to continue a conversation_")

        await update.message.reply_text("\n".join(lines), parse_mode='Markdown')
        self.messages_sent += 1

    async def _cmd_resume_conversation(self, update, context):
        """Handle /resume command - resume a past conversation."""
        self.commands_received += 1

        if not self._is_authorized(update.effective_chat.id):
            await update.message.reply_text("❌ Unauthorized")
            return

        # Get conversation ID from args
        if not context.args:
            await update.message.reply_text(
                "Usage: `/resume <id>`\n\n"
                "Use `/conversations` to see available IDs.",
                parse_mode='Markdown'
            )
            return

        try:
            conv_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ Invalid conversation ID")
            return

        chat_id = update.effective_chat.id
        success = self.conversation_manager.resume_conversation(chat_id, conv_id)

        if success:
            info = self.conversation_manager.get_conversation_info(conv_id)
            msg_count = info['message_count'] if info else 0
            await update.message.reply_text(
                f"▶️ *Resumed conversation {conv_id}*\n\n"
                f"Messages: {msg_count}\n"
                f"Laney remembers your previous chat!",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text("❌ Conversation not found")

        self.messages_sent += 1

    async def _cmd_context(self, update, context):
        """Handle /context command - show current conversation info with token estimates."""
        self.commands_received += 1

        if not self._is_authorized(update.effective_chat.id):
            await update.message.reply_text("❌ Unauthorized")
            return

        chat_id = update.effective_chat.id

        # Get active conversation
        conv_id = self.conversation_manager.get_or_create_conversation(chat_id)
        info = self.conversation_manager.get_conversation_info(conv_id)

        if not info:
            await update.message.reply_text("📭 No active conversation")
            return

        # Get actual messages for token estimation
        messages = self.conversation_manager.get_context_messages(conv_id)
        total_chars = sum(len(m.get('content', '')) for m in messages)
        tokens_est = total_chars // 4  # Rough estimate

        # Context health indicator
        max_tokens = 128000
        usage_pct = (tokens_est / max_tokens) * 100
        if usage_pct < 30:
            health = "🟢 Healthy"
        elif usage_pct < 60:
            health = "🟡 Moderate"
        else:
            health = "🔴 Consider /new"

        # Get some stats
        try:
            created = datetime.fromisoformat(info['created_at'])
            updated = datetime.fromisoformat(info['updated_at'])
            created_str = created.strftime("%Y-%m-%d %H:%M")
            updated_str = updated.strftime("%Y-%m-%d %H:%M")
        except:
            created_str = info['created_at']
            updated_str = info['updated_at']

        title = info['title'] or "(no title)"

        await update.message.reply_text(
            f"💬 *Current Conversation*\n\n"
            f"ID: `{info['id']}`\n"
            f"Messages: {info['message_count']} (showing last {len(messages)})\n"
            f"Started: {created_str}\n"
            f"Last activity: {updated_str}\n\n"
            f"*Context Usage:*\n"
            f"Tokens: ~{tokens_est:,} / 128K ({usage_pct:.1f}%)\n"
            f"Status: {health}\n\n"
            f"_Use `/new` to start fresh, `/title <name>` to rename_",
            parse_mode='Markdown'
        )
        self.messages_sent += 1

    async def _cmd_title(self, update, context):
        """Handle /title command - set conversation title."""
        self.commands_received += 1

        if not self._is_authorized(update.effective_chat.id):
            await update.message.reply_text("Unauthorized")
            return

        if not context.args:
            await update.message.reply_text(
                "Usage: `/title <new title>`\n\n"
                "Example: `/title Research on geostatistics`",
                parse_mode='Markdown'
            )
            return

        new_title = " ".join(context.args)
        if len(new_title) > 100:
            new_title = new_title[:100]

        chat_id = update.effective_chat.id
        conv_id = self.conversation_manager.get_or_create_conversation(chat_id)
        self.conversation_manager.set_title(conv_id, new_title)

        await update.message.reply_text(
            f"Conversation renamed to: *{new_title}*",
            parse_mode='Markdown'
        )
        self.messages_sent += 1

    async def _cmd_forget(self, update, context):
        """Handle /forget command - delete last N messages from history.

        Usage:
            /forget      - Delete last message (user + assistant pair = 2)
            /forget 3    - Delete last 3 messages
        """
        self.commands_received += 1

        if not self._is_authorized(update.effective_chat.id):
            await update.message.reply_text("Unauthorized")
            return

        # Parse count argument (default to 2 = last exchange)
        count = 2  # Default: delete last user message + assistant response
        if context.args:
            try:
                count = int(context.args[0])
                if count < 1:
                    count = 1
                elif count > 50:
                    count = 50  # Safety limit
            except ValueError:
                await update.message.reply_text(
                    "Usage: `/forget [count]`\n\n"
                    "Examples:\n"
                    "• `/forget` - Remove last exchange (2 messages)\n"
                    "• `/forget 1` - Remove last message only\n"
                    "• `/forget 5` - Remove last 5 messages",
                    parse_mode='Markdown'
                )
                return

        chat_id = update.effective_chat.id
        conv_id = self.conversation_manager.get_or_create_conversation(chat_id)
        deleted = self.conversation_manager.delete_last_messages(conv_id, count)

        if deleted == 0:
            await update.message.reply_text("No messages to forget.")
        elif deleted == 1:
            await update.message.reply_text("🗑️ Forgot 1 message.")
        else:
            await update.message.reply_text(f"🗑️ Forgot {deleted} messages.")
        self.messages_sent += 1

    # Message and document handlers

    async def _handle_message(self, update, context):
        """Handle text messages - detect DOIs, URLs, or send to Laney.

        In group chats, only /laney command works - regular messages are ignored.
        """
        # Skip group chats - they should use /laney command
        if self._is_group_chat(update):
            return

        if not self._is_authorized(update.effective_chat.id):
            return

        text = update.message.text.strip()
        self.logger.info(f"Received message: {text[:50]}...")

        # Check for DOI
        doi = self._detect_doi(text)
        if doi:
            await update.message.reply_text(f"📄 Detected DOI: `{doi}`\nProcessing...", parse_mode='Markdown')
            self.run_in_background(
                lambda: self._add_paper_from_doi(doi, update.effective_chat.id),
                callback=lambda result: self.logger.info(f"Paper added: {result}"),
                error_handler=lambda e: self.logger.error(f"Failed to add paper: {e}")
            )
            return

        # Check for arXiv ID/URL
        arxiv_id = self._detect_arxiv(text)
        if arxiv_id:
            await update.message.reply_text(f"📄 Detected arXiv paper: `{arxiv_id}`\nProcessing...", parse_mode='Markdown')
            self.run_in_background(
                lambda: self._add_paper_from_arxiv(arxiv_id, update.effective_chat.id),
                callback=lambda result: self.logger.info(f"arXiv paper added: {result}"),
                error_handler=lambda e: self.logger.error(f"Failed to add arXiv paper: {e}")
            )
            return

        # Check if message is ONLY a URL (no other text)
        url = self._detect_url(text)
        if url and self._is_only_url(text):
            # Pure URL - process as link
            processing_msg = await update.message.reply_text(
                f"🔗 Detected URL\n`{url}`\n\n⏳ Processing...",
                parse_mode='Markdown'
            )
            self.run_in_background(
                lambda: self._add_link_from_url(url, update.effective_chat.id, processing_msg),
                callback=lambda result: self.logger.info(f"Link added: {result}"),
                error_handler=lambda e: self.logger.error(f"Failed to add link: {e}")
            )
            return

        # Check for "share format": Title + URL (e.g., Google Discover shares)
        share_info = self._detect_share_format(text)
        if share_info:
            title = share_info['title']
            url = share_info['url']
            processing_msg = await update.message.reply_text(
                f"🔗 Shared link detected\n*{title[:50]}{'...' if len(title) > 50 else ''}*\n`{url}`\n\n⏳ Processing...",
                parse_mode='Markdown'
            )
            # Pass title hint to the link processor
            self.run_in_background(
                lambda: self._add_link_from_url(url, update.effective_chat.id, processing_msg, title_hint=title),
                callback=lambda result: self.logger.info(f"Shared link added: {result}"),
                error_handler=lambda e: self.logger.error(f"Failed to add shared link: {e}")
            )
            return

        # Default: Send everything else to Laney
        await self._ask_laney(text, update)

    async def _handle_document(self, update, context):
        """Handle document uploads (PDFs, JSON files, etc.)."""
        if not self._is_authorized(update.effective_chat.id):
            return

        document = update.message.document
        file_name = document.file_name
        file_size = document.file_size
        mime_type = document.mime_type

        self.logger.info(f"Received document: {file_name} ({file_size} bytes, {mime_type})")

        # Determine file type
        is_pdf = mime_type == 'application/pdf' or file_name.lower().endswith('.pdf')
        is_json = mime_type == 'application/json' or file_name.lower().endswith('.json')

        if not is_pdf and not is_json:
            await update.message.reply_text(
                "⚠️ Unsupported file type.\n\n"
                "Supported formats:\n"
                "• PDF files\n"
                "• JSON files (Mercado Livre favorites export)"
            )
            return

        # Check file size (limit to 20MB for now)
        max_size = 20 * 1024 * 1024  # 20MB
        if file_size > max_size:
            await update.message.reply_text(f"⚠️ File too large. Maximum size: {max_size // (1024*1024)}MB")
            return

        # Download the file
        try:
            file = await document.get_file()

            # Save to temp directory
            temp_dir = Path(self.core.config.data_dir) / "temp"
            temp_dir.mkdir(exist_ok=True)
            file_path = temp_dir / file_name

            await file.download_to_drive(str(file_path))

            if is_pdf:
                await update.message.reply_text(f"📄 Downloaded PDF: `{file_name}`\nProcessing...", parse_mode='Markdown')

                # Process PDF in background
                self.run_in_background(
                    lambda: self._process_pdf(str(file_path), file_name, update.effective_chat.id),
                    callback=lambda result: self.logger.info(f"PDF processed: {result}"),
                    error_handler=lambda e: self.logger.error(f"Failed to process PDF: {e}")
                )

            elif is_json:
                await update.message.reply_text(f"📋 Downloaded JSON: `{file_name}`\nProcessing...", parse_mode='Markdown')

                # Process JSON in background
                self.run_in_background(
                    lambda: self._process_mercadolivre_json(str(file_path), file_name, update.effective_chat.id),
                    callback=lambda result: self.logger.info(f"JSON processed: {result}"),
                    error_handler=lambda e: self.logger.error(f"Failed to process JSON: {e}")
                )

        except Exception as e:
            self.logger.error(f"Failed to download file: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Failed to download file: {str(e)}")

    # Helper methods

    def _detect_doi(self, text: str) -> Optional[str]:
        """Detect DOI in text.

        Args:
            text: Input text

        Returns:
            DOI if found, None otherwise
        """
        # DOI regex: 10.xxxx/yyyy
        doi_pattern = r'10\.\d{4,}/[^\s]+'
        match = re.search(doi_pattern, text)
        return match.group(0) if match else None

    def _detect_url(self, text: str) -> Optional[str]:
        """Detect URL in text.

        Args:
            text: Input text

        Returns:
            URL if found, None otherwise
        """
        # Simple URL regex
        url_pattern = r'https?://[^\s]+'
        match = re.search(url_pattern, text)
        return match.group(0) if match else None

    def _is_only_url(self, text: str) -> bool:
        """Check if text is ONLY a URL (no other content).

        Args:
            text: Input text

        Returns:
            True if text is just a URL, False if it contains other text
        """
        text = text.strip()
        url_pattern = r'^https?://[^\s]+$'
        return bool(re.match(url_pattern, text))

    def _detect_share_format(self, text: str) -> Optional[Dict[str, str]]:
        """Detect 'share format' messages: title followed by URL.

        Common formats:
        - Google Discover: "Title | Source https://share.google/..."
        - Generic share: "Title https://..."
        - With newlines: "Title\nhttps://..."

        Args:
            text: Input text

        Returns:
            Dict with 'title' and 'url' if detected, None otherwise
        """
        text = text.strip()

        # Pattern: anything + whitespace/newline + URL at end
        # The URL must be at the very end of the message
        pattern = r'^(.+?)[\s\n]+(https?://[^\s]+)$'
        match = re.match(pattern, text, re.DOTALL)

        if match:
            title = match.group(1).strip()
            url = match.group(2).strip()

            # Clean up title - remove trailing pipe and source if present
            # e.g., "Article Title | Hackaday" -> "Article Title | Hackaday" (keep it)
            # But remove common junk suffixes
            title = re.sub(r'\s*[-–—]\s*$', '', title)  # Remove trailing dashes

            # Must have some meaningful title (not just punctuation)
            if len(title) > 3 and not title.startswith('http'):
                return {'title': title, 'url': url}

        return None

    async def _ask_laney(self, query: str, update):
        """Send a query to Laney and reply with response.

        Uses conversation history for context - Laney remembers past messages.
        If Laney creates documents, sends them as file attachments.
        In group chats, attributes messages to the sender so Laney knows who said what.

        Args:
            query: The question/text to send to Laney
            update: Telegram update object
        """
        chat_id = update.effective_chat.id
        is_group = self._is_group_chat(update)

        # In group chats, attribute the message to the sender
        if is_group:
            user = update.effective_user
            # Prefer username, fall back to first_name
            sender_name = f"@{user.username}" if user.username else user.first_name
            # Format: "[sender_name]: message"
            attributed_query = f"[{sender_name}]: {query}"
        else:
            attributed_query = query

        # Get or create conversation
        conversation_id = self.conversation_manager.get_or_create_conversation(chat_id)

        # Save user message to conversation (with attribution for group chats)
        self.conversation_manager.add_message(conversation_id, "user", attributed_query)

        # Send initial "thinking" message (with retry for network issues)
        status_msg = await self._retry_telegram_call(
            update.message.reply_text,
            "🔮 *Laney is thinking...*",
            parse_mode='Markdown'
        )
        if not status_msg:
            # All retries failed - try one more time without markdown
            try:
                status_msg = await update.message.reply_text("🔮 Laney is thinking...")
            except Exception as e:
                print(f"[TELEGRAM] Failed to send thinking message: {e}", flush=True)
                return  # Can't communicate with user

        # Shared state for progress updates (thread-safe via GIL for simple ops)
        progress_state = {"tools": [], "done": False, "pending_updates": []}

        # Run Laney query in background with conversation history
        def run_laney():
            from ..llm.nanogpt import NanoGPTClient
            from ..llm.laney_tools import LANEY_TOOLS, LaneyToolHandler
            from ..cli.laney_commands import LANEY_SYSTEM_PROMPT

            config = self.core.config
            client = NanoGPTClient(config.llm.api_key, config.llm.base_url)

            # Get email config for Laney tools
            email_config = getattr(config, 'email', None)
            email_whitelist = getattr(email_config, 'allowed_senders', []) if email_config else []

            tool_handler = LaneyToolHandler(
                db_path=config.db_path,
                brave_api_key=getattr(config.integrations, 'brave_api_key', None),
                conversation_id=conversation_id,
                pending_updates=progress_state["pending_updates"],  # Shared list for async sending
                email_config=email_config,
                config_whitelist=email_whitelist,
            )

            # Load conversation history (last N messages)
            history = self.conversation_manager.get_context_messages(conversation_id)

            # Build messages with system prompt + history
            # Add group chat context if applicable
            system_prompt = LANEY_SYSTEM_PROMPT
            if is_group:
                system_prompt += """

GROUP CHAT CONTEXT:
You are in a Telegram group chat with multiple participants. Messages are prefixed with [username]: to indicate who sent them.
- Pay attention to who is asking what - different people may have different questions
- When referring to something someone said, use their username (e.g., "@alice asked about...")
- If you need to address a specific person, use their username
- The conversation history shows who said what, so you can follow multi-person discussions
- When someone asks "what did I say" or refers to themselves, look at their username in the attribution"""

            messages = [{"role": "system", "content": system_prompt}]
            messages.extend(history)

            # Estimate context usage (rough: 4 chars per token)
            context_chars = sum(len(m.get('content', '')) for m in messages)
            context_tokens_est = context_chars // 4
            context_warning = None
            if context_tokens_est > 64000:  # ~50% of 128K
                context_warning = f"⚠️ Context at ~{context_tokens_est//1000}K tokens ({context_tokens_est*100//128000}%). Consider /new if responses degrade."

            # Track tools called for verbose output (also updates shared state)
            tools_called = []
            def on_tool(name, iteration):
                tools_called.append(name)
                progress_state["tools"] = list(tools_called)  # Update shared state

            # Model fallback chain - try alternatives on timeout
            fallback_models = [
                config.llm.primary,  # deepseek-ai/DeepSeek-V3.1
                "moonshotai/Kimi-K2-Instruct",
                "nousresearch/hermes-4-70b",
            ]

            last_error = None
            used_model = None

            try:
                for model in fallback_models:
                    try:
                        import logging
                        logging.getLogger(__name__).info(f"[Laney] Trying model: {model}")
                        progress_state["current_model"] = model

                        response = client.run_with_tools(
                            messages=messages,
                            tools=LANEY_TOOLS,
                            tool_handlers=tool_handler.handlers,
                            model=model,
                            temperature=0.3,
                            max_iterations=20,
                            timeout=120,  # 2 min per model attempt (will retry with fallback)
                            on_tool_call=on_tool,
                        )
                        used_model = model
                        # Capture created documents before closing
                        created_docs = list(tool_handler.created_documents)
                        return {
                            "success": True,
                            "response": response,
                            "tools_called": tools_called,
                            "documents": created_docs,
                            "context_warning": context_warning,
                            "model_used": used_model,
                        }
                    except Exception as e:
                        error_str = str(e).lower()
                        # Only fallback on timeout errors
                        if "timeout" in error_str or "timed out" in error_str:
                            import logging
                            logging.getLogger(__name__).warning(f"[Laney] Model {model} timed out, trying next...")
                            last_error = e
                            continue
                        else:
                            # Non-timeout error - don't retry
                            return {"success": False, "error": str(e), "documents": [], "context_warning": context_warning, "tools_called": tools_called}

                # All models failed
                return {"success": False, "error": f"All models timed out. Last error: {last_error}", "documents": [], "context_warning": context_warning, "tools_called": tools_called}
            finally:
                tool_handler.close()

        # Progress updater task
        async def update_progress():
            """Periodically update status message and send interim updates."""
            import time
            from telegram.error import RetryAfter, BadRequest
            start_time = time.time()
            spinner = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
            tick = 0
            last_tools = []
            update_interval = 5  # Update every 5 seconds (avoid Telegram rate limits)
            sent_updates = 0  # Track how many we've sent

            # Emoji for update types
            update_emoji = {
                "discovery": "💡",
                "progress": "📍",
                "result": "📊",
                "question": "❓",
            }

            while not progress_state["done"]:
                await asyncio.sleep(update_interval)
                if progress_state["done"]:
                    break

                # Check for pending updates from Laney
                pending = progress_state["pending_updates"]
                while len(pending) > sent_updates:
                    upd = pending[sent_updates]
                    emoji = update_emoji.get(upd.get("type", "progress"), "📍")
                    upd_msg = f"{emoji} *Laney update*\n\n{upd['message']}"

                    try:
                        # Send as a new message (not edit)
                        await update.message.reply_text(upd_msg, parse_mode='Markdown')
                        self.messages_sent += 1
                    except BadRequest:
                        # Markdown failed - send plain
                        plain_msg = f"{emoji} Laney update\n\n{upd['message']}"
                        await update.message.reply_text(plain_msg)
                        self.messages_sent += 1
                    except RetryAfter as e:
                        await asyncio.sleep(e.retry_after + 1)
                        continue  # Retry this update
                    except Exception:
                        pass  # Skip if send fails

                    sent_updates += 1

                tick += 1
                elapsed = int(time.time() - start_time)
                spin = spinner[tick % len(spinner)]

                # Get current model (short name)
                current_model = progress_state.get("current_model", "")
                model_short = current_model.split("/")[-1][:12] if current_model else ""

                tools = progress_state["tools"]
                if tools and tools != last_tools:
                    # Show latest tool
                    latest = tools[-1].replace("_", " ")
                    msg = f"🔮 *Laney* {spin} `{latest}` ({elapsed}s)"
                    last_tools = list(tools)
                elif model_short:
                    msg = f"🔮 *Laney* {spin} [{model_short}] ({elapsed}s)"
                else:
                    msg = f"🔮 *Laney is working...* {spin} ({elapsed}s)"

                try:
                    await status_msg.edit_text(msg, parse_mode='Markdown')
                except RetryAfter as e:
                    # Respect Telegram's rate limit
                    await asyncio.sleep(e.retry_after + 1)
                except Exception:
                    pass  # Ignore other edit errors

        # Start progress updater
        progress_task = asyncio.create_task(update_progress())

        try:
            result = await asyncio.get_event_loop().run_in_executor(None, run_laney)
            progress_state["done"] = True  # Signal updater to stop
            progress_task.cancel()  # Cancel the updater

            if result.get('success'):
                response_text = result['response']

                # Save assistant response to conversation
                self.conversation_manager.add_message(conversation_id, "assistant", response_text)

                # Build tools summary if any were called
                tools_called = result.get('tools_called', [])
                tools_summary = ""
                if tools_called:
                    # Compact format: unique tools with counts
                    from collections import Counter
                    tool_counts = Counter(tools_called)
                    tool_parts = [f"{name}" if count == 1 else f"{name}×{count}"
                                  for name, count in tool_counts.items()]
                    tools_summary = f"\n\n`🔧 {' → '.join(tool_parts)}`"

                # Truncate if too long for Telegram (4096 char limit)
                max_response = 3900 - len(tools_summary)
                if len(response_text) > max_response:
                    response_text = response_text[:max_response] + "\n\n_(truncated)_"

                msg = f"🔮 *Laney*\n\n{response_text}{tools_summary}"
            else:
                tools_called = result.get('tools_called', [])
                tools_info = f" (after {len(tools_called)} tool calls)" if tools_called else ""
                msg = f"❌ *Laney Error*{tools_info}\n\n{result.get('error', 'Unknown error')[:500]}"

            # Edit with rate limit handling and markdown fallback
            from telegram.error import RetryAfter, BadRequest
            for attempt in range(3):
                try:
                    await status_msg.edit_text(msg, parse_mode='Markdown', disable_web_page_preview=True)
                    self.messages_sent += 1
                    break
                except BadRequest as e:
                    # Markdown parsing failed - fall back to plain text
                    if "parse entities" in str(e).lower() or "can't find end" in str(e).lower():
                        self.logger.warning(f"Markdown parse failed, falling back to plain text: {e}")
                        # Remove markdown formatting and try again
                        plain_msg = msg.replace('*', '').replace('_', '').replace('`', '')
                        await status_msg.edit_text(plain_msg, disable_web_page_preview=True)
                        self.messages_sent += 1
                        break
                    raise
                except RetryAfter as e:
                    await asyncio.sleep(e.retry_after + 1)

            # Send any created documents as file attachments
            docs = result.get('documents', [])
            self.logger.info(f"Documents to send: {len(docs)} - {docs}")
            for doc_path in docs:
                self.logger.info(f"Checking document: {doc_path}, exists: {doc_path.exists() if hasattr(doc_path, 'exists') else 'N/A'}")
                if hasattr(doc_path, 'exists') and doc_path.exists():
                    try:
                        await update.message.reply_document(
                            document=open(doc_path, 'rb'),
                            filename=doc_path.name,
                            caption=f"📄 {doc_path.stem.replace('-', ' ').title()}"
                        )
                        self.messages_sent += 1
                        self.logger.info(f"Sent document: {doc_path.name}")
                    except Exception as e:
                        self.logger.error(f"Failed to send document {doc_path}: {e}")

            # Send context warning if needed
            if result.get('context_warning'):
                await update.message.reply_text(result['context_warning'])

        except Exception as e:
            progress_state["done"] = True
            progress_task.cancel()
            self.logger.error(f"Laney query error: {e}", exc_info=True)

            # Try to send error message, respecting rate limits
            from telegram.error import RetryAfter, BadRequest
            error_msg = f"❌ *Error*\n\n{str(e)[:200]}"
            for attempt in range(3):
                try:
                    await status_msg.edit_text(error_msg, parse_mode='Markdown')
                    break
                except BadRequest:
                    # Markdown failed - send plain text
                    plain_msg = f"❌ Error\n\n{str(e)[:200]}"
                    await status_msg.edit_text(plain_msg)
                    break
                except RetryAfter as retry_err:
                    await asyncio.sleep(retry_err.retry_after + 1)
                except Exception:
                    try:
                        await asyncio.sleep(2)  # Brief pause before fallback
                        await update.message.reply_text("❌ Laney query failed")
                        break
                    except RetryAfter as retry_err:
                        await asyncio.sleep(retry_err.retry_after + 1)
                    except Exception:
                        break  # Give up silently

    def _detect_arxiv(self, text: str) -> Optional[str]:
        """Detect arXiv ID in text.

        Args:
            text: Input text

        Returns:
            arXiv ID if found, None otherwise
        """
        from ..research import ArxivClient

        arxiv = ArxivClient()
        return arxiv.extract_arxiv_id(text)

    def _add_paper_from_doi(self, doi: str, chat_id: int):
        """Add paper from DOI (runs in background).

        Args:
            doi: DOI string
            chat_id: Telegram chat ID for notifications
        """
        try:
            from ..research import CrossrefClient, UnpaywallClient

            db = self.core.db
            crossref = CrossrefClient()
            unpaywall = UnpaywallClient()

            # Check if already exists
            existing = db.get_paper_by_doi(doi)
            if existing:
                self._send_notification(
                    f"ℹ️ Paper already in collection:\n*{existing.get('title')}*",
                    chat_id
                )
                return "already_exists"

            # Fetch metadata
            self.logger.info(f"Fetching paper metadata for DOI: {doi}")
            paper_data = crossref.get_by_doi(doi)

            if not paper_data:
                self._send_notification(f"❌ Paper not found with DOI: `{doi}`", chat_id)
                return "not_found"

            paper = crossref.parse_paper(paper_data)

            # Check Open Access
            oa_info = {}
            try:
                oa_data = unpaywall.get_oa_status(doi)
                if oa_data:
                    oa_info = {
                        'is_oa': oa_data.get('is_oa', False),
                        'oa_status': oa_data.get('oa_status'),
                        'oa_color': oa_data.get('oa_color'),
                        'pdf_url': oa_data.get('best_oa_location', {}).get('url_for_pdf')
                    }
            except Exception as e:
                self.logger.warning(f"Failed to get OA info: {e}")

            # Add to database
            paper_id = db.add_paper(
                title=paper['title'],
                authors=paper.get('authors', []),
                doi=doi,
                publication_date=str(paper.get('year')) if paper.get('year') else None,
                journal=paper.get('journal'),
                url=paper.get('url'),
                is_open_access=oa_info.get('is_oa', False),
                pdf_url=oa_info.get('pdf_url'),
                oa_status=oa_info.get('oa_status'),
                oa_color=oa_info.get('oa_color')
            )

            # Send success notification
            authors_str = ", ".join(paper.get('authors', [])[:3])
            if len(paper.get('authors', [])) > 3:
                authors_str += " et al."

            oa_badge = "🟢 Open Access" if oa_info.get('is_oa') else "🔒 Closed Access"

            self._send_notification(
                f"✅ *Paper Added*\n\n"
                f"*{paper['title']}*\n\n"
                f"👥 {authors_str}\n"
                f"📅 {paper.get('year', 'N/A')}\n"
                f"📰 {paper.get('journal', 'N/A')}\n"
                f"{oa_badge}\n\n"
                f"Paper ID: {paper_id}",
                chat_id
            )

            return paper_id

        except Exception as e:
            self.logger.error(f"Failed to add paper: {e}", exc_info=True)
            self._send_notification(f"❌ Failed to add paper: {str(e)}", chat_id)
            raise

    def _add_paper_from_arxiv(self, arxiv_id: str, chat_id: int):
        """Add paper from arXiv (runs in background).

        Args:
            arxiv_id: arXiv ID
            chat_id: Telegram chat ID for notifications
        """
        try:
            from ..research import ArxivClient

            db = self.core.db
            arxiv = ArxivClient()

            # Check if already exists by arXiv ID
            cursor = db.conn.cursor()
            cursor.execute("SELECT id, title FROM papers WHERE arxiv_id = ?", (arxiv_id,))
            existing = cursor.fetchone()

            if existing:
                self._send_notification(
                    f"ℹ️ Paper already in collection:\n*{existing['title']}*",
                    chat_id
                )
                return "already_exists"

            # Fetch metadata from arXiv
            self.logger.info(f"Fetching arXiv paper metadata: {arxiv_id}")
            paper = arxiv.get_paper(arxiv_id)

            if not paper:
                self._send_notification(f"❌ Paper not found with arXiv ID: `{arxiv_id}`", chat_id)
                return "not_found"

            # Add to database
            paper_id = db.add_paper(
                title=paper['title'],
                authors=paper.get('authors', []),
                arxiv_id=arxiv_id,
                doi=paper.get('doi'),
                abstract=paper.get('abstract'),
                publication_date=paper.get('published_date'),
                url=paper.get('url'),
                pdf_url=paper.get('pdf_url'),
                is_open_access=True,  # arXiv papers are always open access
                oa_status='gold',
                oa_color='gold'
            )

            # Send success notification
            authors_str = ", ".join(paper.get('authors', [])[:3])
            if len(paper.get('authors', [])) > 3:
                authors_str += " et al."

            categories_str = ", ".join(paper.get('categories', [])[:3])

            self._send_notification(
                f"✅ *arXiv Paper Added*\n\n"
                f"*{paper['title']}*\n\n"
                f"👥 {authors_str}\n"
                f"📅 {paper.get('published_date', 'N/A')}\n"
                f"🏷️ {categories_str}\n"
                f"🟢 Open Access (arXiv)\n\n"
                f"Paper ID: {paper_id}",
                chat_id
            )

            return paper_id

        except Exception as e:
            self.logger.error(f"Failed to add arXiv paper: {e}", exc_info=True)
            self._send_notification(f"❌ Failed to add arXiv paper: {str(e)}", chat_id)
            raise

    def _add_link_from_url(self, url: str, chat_id: int, processing_msg=None, title_hint: str = None):
        """Add link from URL (runs in background).

        Args:
            url: URL string
            chat_id: Telegram chat ID for notifications
            processing_msg: Optional message to edit with results (instead of sending new)
            title_hint: Optional title from share format (e.g., Google Discover)
        """
        try:
            db = self.core.db

            # Check if already exists
            cursor = db.conn.cursor()
            cursor.execute("SELECT id, title FROM links WHERE url = ?", (url,))
            existing = cursor.fetchone()

            if existing:
                self._send_notification(
                    f"ℹ️ Link already in collection:\n{url}",
                    chat_id
                )
                return "already_exists"

            # Add link (unwrapping happens inside insert_link)
            # Use title_hint if provided (from share format detection)
            link_id = db.insert_link(
                url=url,
                source="telegram",
                title=title_hint,  # Use hint from share format, or None to fetch later
                notes="Added via Telegram bot"
            )

            # Check if URL was unwrapped by querying what was actually saved
            cursor.execute("SELECT url, title FROM links WHERE id = ?", (link_id,))
            saved_link = cursor.fetchone()
            actual_url = saved_link['url'] if saved_link else url

            # Immediate archiving (Phase 2: Local + Internet Archive)
            archive_result = None
            try:
                self.logger.info(f"Archiving link (local + IA): {actual_url}")

                # Archive with unified service (local + IA)
                archive_result = self.archiving.archive_url(
                    link_id=link_id,
                    url=actual_url,
                    local_format='monolith',  # Fast, browser-viewable
                    use_ia=True,
                    force_ia=False  # Don't force if already archived
                )

                # Update old columns for backward compatibility
                if archive_result.get('success') and 'internet_archive' in archive_result.get('services', {}):
                    ia_service = archive_result['services']['internet_archive']
                    if ia_service.get('status') == 'success':
                        db.update_link_archive_status(
                            url=actual_url,
                            archived=True,
                            archive_url=ia_service.get('snapshot_url'),
                            archive_date=None  # Stored in archive_snapshots now
                        )

                self.logger.info(f"Archiving complete: success={archive_result.get('success')}")

            except Exception as e:
                self.logger.error(f"Failed to archive link: {e}", exc_info=True)
                archive_result = {'success': False, 'errors': [str(e)]}

            # Build notification message
            msg = f"✅ *Link Added*\n\n"

            # Show title if we have one
            if title_hint:
                msg += f"*{title_hint}*\n\n"

            if actual_url != url:
                # URL was unwrapped
                msg += f"🔗 Original\n`{url}`\n\n"
                msg += f"📍 Unwrapped\n`{actual_url}`\n\n"
            else:
                # URL unchanged
                msg += f"`{url}`\n\n"

            msg += f"━━━━━━━━━━━━━━━━\n"
            msg += f"📋 Link ID: `{link_id}`\n"
            msg += f"📱 Source: Telegram\n"

            # Add archive status to notification
            if archive_result and archive_result.get('success'):
                services = archive_result.get('services', {})

                # Local archive
                if 'local_monolith' in services and services['local_monolith'].get('status') == 'success':
                    local = services['local_monolith']
                    file_size = local.get('file_size', 0)
                    size_kb = file_size // 1024
                    msg += f"\n━━━━━━━━━━━━━━━━\n"
                    msg += f"💾 *Local archive*: {size_kb:,} KB\n"
                    # Add link to web viewer
                    mono_url = f"https://holo.stdgeo.com/mono/{link_id}/latest"
                    msg += f"[View local ↗]({mono_url})\n"

                # Internet Archive
                if 'internet_archive' in services:
                    ia = services['internet_archive']
                    if ia.get('status') == 'success':
                        was_cached = ia.get('already_archived', False)
                        snapshot_url = ia.get('snapshot_url', '')

                        if not 'local_monolith' in services:  # Add separator if not already added
                            msg += f"\n━━━━━━━━━━━━━━━━\n"

                        if was_cached:
                            # Extract date from snapshot URL for trust tier
                            from ..storage.database import calculate_trust_tier
                            import re
                            date_match = re.search(r'/web/(\d{14})/', snapshot_url)
                            if date_match:
                                archive_date = date_match.group(1)
                                trust_tier = calculate_trust_tier(archive_date)
                                # Format date
                                try:
                                    year, month, day = archive_date[:4], archive_date[4:6], archive_date[6:8]
                                    date_str = f"{year}-{month}-{day}"
                                except:
                                    date_str = archive_date
                                msg += f"📦 *Already archived* ({trust_tier})\n"
                                msg += f"📅 Snapshot: {date_str}\n"
                            else:
                                msg += f"📦 *Already archived*\n"
                        else:
                            msg += f"🌐 *Archived to IA*\n"

                        msg += f"[View snapshot ↗]({snapshot_url})"

            elif archive_result and not archive_result.get('success'):
                msg += f"\n━━━━━━━━━━━━━━━━\n"
                msg += f"⚠️ *Archive failed*\n"
                errors = archive_result.get('errors', [])
                if errors:
                    msg += f"{errors[0][:80]}\n"
                msg += f"Will retry with exponential backoff"

            # Edit the processing message if provided, otherwise send new notification
            if processing_msg:
                self._edit_message(processing_msg, msg)
            else:
                self._send_notification(msg, chat_id)

            # Publish event for archiving
            self.publish('link.added', {'url': actual_url, 'link_id': link_id, 'archived': archive_status in ('archived', 'already_archived')})

            return link_id

        except Exception as e:
            self.logger.error(f"Failed to add link: {e}", exc_info=True)
            self._send_notification(f"❌ Failed to add link: {str(e)}", chat_id)
            raise

    def _process_pdf(self, file_path: str, file_name: str, chat_id: int):
        """Process uploaded PDF (runs in background).

        Args:
            file_path: Path to PDF file
            file_name: Original filename
            chat_id: Telegram chat ID for notifications
        """
        try:
            # TODO: Implement PDF processing
            # - Extract text
            # - Extract metadata (title, authors, etc.)
            # - Try to find DOI in PDF
            # - Add to papers or books table
            # - Optionally: LLM analysis

            self._send_notification(
                f"⚠️ PDF processing not yet implemented.\n\n"
                f"File saved: `{file_name}`\n\n"
                f"Coming soon:\n"
                f"• Text extraction\n"
                f"• Metadata detection\n"
                f"• DOI lookup\n"
                f"• LLM analysis",
                chat_id
            )

            # Clean up temp file
            try:
                os.remove(file_path)
            except Exception as e:
                self.logger.warning(f"Failed to remove temp file: {e}")

            return "pdf_processing_pending"

        except Exception as e:
            self.logger.error(f"Failed to process PDF: {e}", exc_info=True)
            self._send_notification(f"❌ Failed to process PDF: {str(e)}", chat_id)
            raise

    def _process_mercadolivre_json(self, file_path: str, file_name: str, chat_id: int):
        """Process uploaded Mercado Livre favorites JSON (runs in background).

        Args:
            file_path: Path to JSON file
            file_name: Original filename
            chat_id: Telegram chat ID for notifications
        """
        import json

        try:
            # Load JSON file
            with open(file_path, 'r', encoding='utf-8') as f:
                favorites = json.load(f)

            # Validate it's a list
            if not isinstance(favorites, list):
                self._send_notification(
                    f"❌ Invalid JSON format.\n\n"
                    f"Expected a list of Mercado Livre favorites.\n"
                    f"Got: {type(favorites).__name__}",
                    chat_id
                )
                return "invalid_json_format"

            if not favorites:
                self._send_notification(
                    f"⚠️ Empty JSON file.\n\n"
                    f"No favorites found in `{file_name}`.",
                    chat_id
                )
                return "empty_json"

            # Validate structure (check first item has expected fields)
            first_item = favorites[0]
            if 'item_id' not in first_item:
                self._send_notification(
                    f"❌ Invalid JSON structure.\n\n"
                    f"Expected Mercado Livre favorites export with 'item\\_id' field.\n"
                    f"Found keys: {', '.join(first_item.keys())[:100]}",
                    chat_id
                )
                return "invalid_json_structure"

            self.logger.info(f"Importing {len(favorites)} Mercado Livre favorites from {file_name}")

            new_count = 0
            updated_count = 0

            for item in favorites:
                # Check if exists
                existing = self.core.db.get_mercadolivre_favorite(item["item_id"])

                # Build thumbnail URL if thumbnail_id is present
                thumbnail_url = None
                if item.get("thumbnail_id"):
                    thumbnail_url = f"https://http2.mlstatic.com/D_NQ_NP_2X_{item['thumbnail_id']}-F.webp"

                # Insert/update in database
                self.core.db.insert_mercadolivre_favorite(
                    item_id=item["item_id"],
                    title=item.get("title"),
                    price=item.get("price"),
                    currency=item.get("currency"),
                    url=item.get("permalink"),
                    thumbnail_url=thumbnail_url,
                    condition=item.get("condition"),
                    bookmarked_date=item.get("collected_at"),
                    is_available=True,  # Assume available since it was in their favorites
                )

                if existing:
                    updated_count += 1
                else:
                    new_count += 1

            self._send_notification(
                f"✅ *Mercado Livre Import Complete*\n\n"
                f"📋 File: `{file_name}`\n"
                f"📦 Total: {len(favorites)} items\n"
                f"🆕 New: {new_count}\n"
                f"🔄 Updated: {updated_count}\n\n"
                f"Use `holo mercadolivre list` to view imports.\n"
                f"Use `holo mercadolivre classify --all` to classify.",
                chat_id
            )

            self.logger.info(f"Imported {len(favorites)} ML favorites: {new_count} new, {updated_count} updated")

            # Clean up temp file
            try:
                os.remove(file_path)
            except Exception as e:
                self.logger.warning(f"Failed to remove temp file: {e}")

            return f"imported_{len(favorites)}_favorites"

        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON in {file_name}: {e}")
            self._send_notification(
                f"❌ Invalid JSON file.\n\n"
                f"Could not parse `{file_name}`:\n{str(e)[:100]}",
                chat_id
            )
            return "json_parse_error"

        except Exception as e:
            self.logger.error(f"Failed to process ML JSON: {e}", exc_info=True)
            self._send_notification(f"❌ Failed to import favorites: {str(e)}", chat_id)
            raise

    # Event handlers for notifications

    def _on_enrichment_complete(self, msg: Message):
        """Handle enrichment.complete event - send notification."""
        book_id = msg.data.get('book_id')
        summary = msg.data.get('summary', '')[:100]  # First 100 chars

        notification = f"""📖 *Book Enriched*

Book ID: {book_id}
Summary: {summary}...

Enrichment complete!
"""

        self._send_notification(notification)

    def _on_classification_complete(self, msg: Message):
        """Handle classification.complete event - send notification."""
        book_id = msg.data.get('book_id')
        dewey = msg.data.get('dewey_number', '')
        label = msg.data.get('dewey_label', '')
        call_number = msg.data.get('call_number', '')

        notification = f"""🏛️ *Book Classified*

Book ID: {book_id}
Dewey: {dewey}
Label: {label}
Call #: {call_number}

Classification complete!
"""

        self._send_notification(notification)

    def _on_link_checked(self, msg: Message):
        """Handle link.checked event - send notification."""
        url = msg.data.get('url', '')
        status_code = msg.data.get('status_code', 0)
        is_alive = msg.data.get('is_alive', False)

        status_emoji = "✅" if is_alive else "❌"

        notification = f"""🔗 *Link Checked*

{status_emoji} Status: {status_code}
URL: {url[:50]}...

{'Link is alive!' if is_alive else 'Link is dead!'}
"""

        self._send_notification(notification)

    def _on_telegram_send(self, msg: Message):
        """Handle telegram.send event - send a message via Telegram."""
        chat_id = msg.data.get('chat_id')
        text = msg.data.get('text', '')
        parse_mode = msg.data.get('parse_mode', 'Markdown')

        if not chat_id or not text:
            return

        self._send_notification(text, chat_id=chat_id)

    def _on_task_completed(self, msg: Message):
        """Handle task.completed event - notify user about completed task."""
        task_id = msg.data.get('task_id')
        title = msg.data.get('title', 'Task')
        chat_id = msg.data.get('chat_id')
        items_added = msg.data.get('items_added', [])
        summary = msg.data.get('summary', '')

        if not chat_id:
            return

        # Build items message
        items_msg = ""
        if items_added:
            links = sum(1 for i in items_added if i.get('type') == 'link')
            papers = sum(1 for i in items_added if i.get('type') == 'paper')
            parts = []
            if links:
                parts.append(f"{links} link{'s' if links > 1 else ''}")
            if papers:
                parts.append(f"{papers} paper{'s' if papers > 1 else ''}")
            if parts:
                items_msg = f"\n📦 Added: {', '.join(parts)}"

        # Truncate summary
        if len(summary) > 300:
            summary = summary[:300] + "..."

        notification = f"""✅ *Task Completed*

*{title}*{items_msg}

{summary}

_Task #{task_id} - ask Laney for details_
"""

        self._send_notification(notification, chat_id=chat_id)

    def _send_notification(self, message: str, chat_id: Optional[int] = None):
        """Send a notification to the user.

        Args:
            message: Message text
            chat_id: Optional chat ID (defaults to self.chat_id)
        """
        # Use provided chat_id or fall back to self.chat_id
        target_chat_id = chat_id or self.chat_id

        if not self.application or not target_chat_id:
            self.logger.debug("Skipping notification - no chat ID or bot not configured")
            return

        if not self.bot_loop or not self.bot_loop.is_running():
            self.logger.warning("Bot loop not running, skipping notification")
            return

        self.notifications_sent += 1

        async def send():
            try:
                await self.application.bot.send_message(
                    chat_id=target_chat_id,
                    text=message,
                    parse_mode='Markdown',
                    disable_web_page_preview=True
                )
                self.messages_sent += 1
            except Exception as e:
                self.logger.error(f"Failed to send notification: {e}")

        # Schedule the send on the bot's event loop (thread-safe)
        try:
            asyncio.run_coroutine_threadsafe(send(), self.bot_loop)
        except Exception as e:
            self.logger.error(f"Failed to schedule notification: {e}")

    def _edit_message(self, message, new_text: str):
        """Edit an existing message.

        Args:
            message: Message object to edit
            new_text: New message text
        """
        if not self.bot_loop or not self.bot_loop.is_running():
            self.logger.warning("Bot loop not running, cannot edit message")
            return

        async def edit():
            try:
                await message.edit_text(
                    text=new_text,
                    parse_mode='Markdown',
                    disable_web_page_preview=True
                )
                self.logger.debug("Message edited successfully")
            except Exception as e:
                self.logger.error(f"Failed to edit message: {e}")

        # Schedule the edit on the bot's event loop (thread-safe)
        try:
            asyncio.run_coroutine_threadsafe(edit(), self.bot_loop)
        except Exception as e:
            self.logger.error(f"Failed to schedule message edit: {e}")

    def _auto_expire_login_message(self, token: str, expires_at: datetime):
        """Auto-expire a login message after timeout (runs in background).

        Args:
            token: Auth token
            expires_at: Expiry datetime
        """
        import time

        # Calculate sleep time (add 1 second buffer)
        sleep_seconds = (expires_at - datetime.now()).total_seconds() + 1

        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

        # Check if token is still tracked (might have been used)
        if token not in self.login_messages:
            self.logger.debug(f"Login token {token[:8]}... already processed")
            return

        msg_info = self.login_messages[token]
        message = msg_info['message']

        # Edit message to show it expired
        expired_msg = f"""🔐 *Web Login Link*

⏱️ *EXPIRED*

This magic link has expired (5 minute timeout).
Request a new one with /login
"""

        self._edit_message(message, expired_msg)

        # Clean up tracking
        del self.login_messages[token]
        self.logger.info(f"Login message auto-expired: {token[:8]}...")

    def mark_login_used(self, token: str, ip_address: str = None):
        """Mark a login token as used and update the Telegram message.

        Args:
            token: Auth token that was used
            ip_address: Optional IP address of user who used it
        """
        if token not in self.login_messages:
            self.logger.debug(f"Login token {token[:8]}... not tracked (already expired?)")
            return

        msg_info = self.login_messages[token]
        message = msg_info['message']
        username = msg_info['telegram_username']

        # Edit message to show it was used
        used_msg = f"""🔐 *Web Login Link*

✅ *USED SUCCESSFULLY*

Logged in as: @{username}
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

        if ip_address:
            used_msg += f"IP: {ip_address}\n"

        used_msg += """
This link is now invalid (single-use only).
"""

        self._edit_message(message, used_msg)

        # Clean up tracking
        del self.login_messages[token]
        self.logger.info(f"Login message marked as used: {token[:8]}...")

    def on_disable(self):
        """Disable the plugin and stop bot."""
        self.logger.info(
            f"TelegramBot disabled - Stats: {self.messages_sent} messages sent, "
            f"{self.commands_received} commands received, {self.notifications_sent} notifications"
        )

        if self.bot_thread and self.bot_thread.is_alive():
            try:
                self.logger.info("Telegram bot stopping...")
                # Cancel the keep_running future to trigger shutdown
                if self.bot_loop and self.keep_running and not self.keep_running.cancelled():
                    self.bot_loop.call_soon_threadsafe(self.keep_running.cancel)
                    self.logger.info("Bot shutdown signal sent")

                    # Wait for thread to finish (with timeout)
                    self.bot_thread.join(timeout=5.0)
                    if self.bot_thread.is_alive():
                        self.logger.warning("Bot thread did not stop within timeout")
                    else:
                        self.logger.info("Bot thread stopped successfully")
            except Exception as e:
                self.logger.error(f"Error stopping bot: {e}")
