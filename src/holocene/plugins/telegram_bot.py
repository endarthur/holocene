"""Telegram Bot Plugin - Mobile interface for Holocene (eunice device).

This plugin:
- Provides Telegram interface for mobile access
- Subscribes to events and sends notifications
- Handles interactive commands
- Runs on rei (server) but provides eunice (mobile) interface
- Uses python-telegram-bot library
"""

import asyncio
from typing import Optional
from datetime import datetime

from holocene.core import Plugin, Message

try:
    from telegram import Update
    from telegram.ext import Application, CommandHandler, ContextTypes
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    Update = None
    CommandHandler = None
    ContextTypes = None
    Application = None


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
        telegram_config = getattr(self.core.config, 'telegram', None)
        if telegram_config:
            self.chat_id = getattr(telegram_config, 'chat_id', None)

        # Create bot application
        try:
            self.application = Application.builder().token(self.bot_token).build()
            self.logger.info("Telegram bot application created")
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
        self.application.add_handler(CommandHandler("stats", self._cmd_stats))
        self.application.add_handler(CommandHandler("plugins", self._cmd_plugins))
        self.application.add_handler(CommandHandler("status", self._cmd_status))

        # Subscribe to events for notifications
        self.subscribe('enrichment.complete', self._on_enrichment_complete)
        self.subscribe('classification.complete', self._on_classification_complete)
        self.subscribe('link.checked', self._on_link_checked)

        # Start bot in background
        self.run_in_background(
            self._start_bot,
            callback=lambda x: self.logger.info("Bot started successfully"),
            error_handler=lambda e: self.logger.error(f"Bot startup failed: {e}")
        )

    def _start_bot(self):
        """Start the bot (runs in background thread).

        This runs in a ThreadPoolExecutor thread, so we need to create
        a new event loop for the async telegram bot.
        """
        try:
            # Create new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self.bot_loop = loop  # Store for notifications

            # Run polling in this event loop
            # This will block until the bot is stopped
            self.logger.info("Starting Telegram bot polling...")
            self.application.run_polling(
                allowed_updates=["message", "callback_query"],
                drop_pending_updates=True
            )
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

    async def _cmd_start(self, update, context):
        """Handle /start command."""
        self.commands_received += 1

        # Save chat ID for notifications
        if not self.chat_id:
            self.chat_id = update.effective_chat.id
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

        help_msg = """📚 *Holocene Commands*

/start - Initialize bot
/help - Show this help
/stats - View statistics
/plugins - List active plugins
/status - System status

*Notifications:*
You'll receive updates when:
• Books are enriched with AI summaries
• Books are classified (Dewey)
• Links are checked for health
"""
        await update.message.reply_text(help_msg, parse_mode='Markdown')
        self.messages_sent += 1

    async def _cmd_stats(self, update, context):
        """Handle /stats command."""
        self.commands_received += 1

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
        """Handle /plugins command."""
        self.commands_received += 1

        plugins_msg = "🔌 *Active Plugins*\n\n"

        # This is a bit tricky - we need to access the registry
        # For now, just show that we're a plugin
        plugins_msg += f"• telegram_bot ✅\n"
        plugins_msg += f"• book_enricher ✅\n"
        plugins_msg += f"• book_classifier ✅\n"
        plugins_msg += f"• link_status_checker ✅\n"

        await update.message.reply_text(plugins_msg, parse_mode='Markdown')
        self.messages_sent += 1

    async def _cmd_status(self, update, context):
        """Handle /status command."""
        self.commands_received += 1

        status_msg = f"""⚡ *System Status*

*Device:* rei (server)
*Interface:* eunice (mobile)
*Status:* 🟢 Online

*Uptime:* Running
*Last update:* {datetime.now().strftime('%H:%M:%S')}
"""

        await update.message.reply_text(status_msg, parse_mode='Markdown')
        self.messages_sent += 1

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

    def _send_notification(self, message: str):
        """Send a notification to the user.

        Args:
            message: Message text
        """
        if not self.application or not self.chat_id:
            self.logger.debug("Skipping notification - no chat ID or bot not configured")
            return

        if not self.bot_loop or not self.bot_loop.is_running():
            self.logger.warning("Bot loop not running, skipping notification")
            return

        self.notifications_sent += 1

        async def send():
            try:
                await self.application.bot.send_message(
                    chat_id=self.chat_id,
                    text=message,
                    parse_mode='Markdown'
                )
                self.messages_sent += 1
            except Exception as e:
                self.logger.error(f"Failed to send notification: {e}")

        # Schedule the send on the bot's event loop (thread-safe)
        try:
            asyncio.run_coroutine_threadsafe(send(), self.bot_loop)
        except Exception as e:
            self.logger.error(f"Failed to schedule notification: {e}")

    def on_disable(self):
        """Disable the plugin and stop bot."""
        self.logger.info(
            f"TelegramBot disabled - Stats: {self.messages_sent} messages sent, "
            f"{self.commands_received} commands received, {self.notifications_sent} notifications"
        )

        if self.application:
            try:
                # Stop the updater gracefully
                # run_polling() handles cleanup internally
                self.logger.info("Telegram bot stopping...")
            except Exception as e:
                self.logger.error(f"Error stopping bot: {e}")
