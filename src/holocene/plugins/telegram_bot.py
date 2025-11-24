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
import secrets
from typing import Optional
from datetime import datetime, timedelta
from pathlib import Path

from holocene.core import Plugin, Message

try:
    from telegram import Update
    from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    Update = None
    CommandHandler = None
    MessageHandler = None
    filters = None
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
        self.bot_thread = None  # Dedicated thread for bot
        self.keep_running = None  # Future that keeps bot running (so we can cancel it)

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
        self.application.add_handler(CommandHandler("login", self._cmd_login))
        self.application.add_handler(CommandHandler("stats", self._cmd_stats))
        self.application.add_handler(CommandHandler("plugins", self._cmd_plugins))
        self.application.add_handler(CommandHandler("status", self._cmd_status))
        self.application.add_handler(CommandHandler("recent", self._cmd_recent))
        self.application.add_handler(CommandHandler("search", self._cmd_search))
        self.application.add_handler(CommandHandler("classify", self._cmd_classify))

        # Register message handlers for content (text, PDFs, etc.)
        self.application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            self._handle_message
        ))
        self.application.add_handler(MessageHandler(
            filters.Document.PDF | filters.Document.ALL,
            self._handle_document
        ))

        # Subscribe to events for notifications
        self.subscribe('enrichment.complete', self._on_enrichment_complete)
        self.subscribe('classification.complete', self._on_classification_complete)
        self.subscribe('link.checked', self._on_link_checked)

        # Start bot in dedicated thread (not ThreadPoolExecutor - bot is long-lived)
        self.bot_thread = threading.Thread(
            target=self._start_bot,
            name="telegram-bot",
            daemon=True  # Allow holod to exit even if bot thread is running
        )
        self.bot_thread.start()
        self.logger.info("Telegram bot thread started")

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

    def _is_authorized(self, chat_id: int) -> bool:
        """Check if user is authorized to use bot.

        Args:
            chat_id: Telegram chat ID

        Returns:
            True if authorized, False otherwise
        """
        # If no chat_id configured yet, first user becomes authorized
        if not self.chat_id:
            return True

        # Otherwise, only configured chat_id is authorized
        return chat_id == self.chat_id

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

        # Check authorization
        if not self._is_authorized(update.effective_chat.id):
            await update.message.reply_text("❌ Unauthorized")
            return

        help_msg = """📚 *Holocene Commands*

/start - Initialize bot
/help - Show this help
/login - Get magic link for web access
/stats - View statistics
/status - System status
/plugins - List active plugins
/recent - Show recently added items
/search <query> - Search books and papers
/classify <topic> - Get Dewey classification

*Send me:*
• DOIs - I'll fetch paper metadata
• URLs - I'll save and archive links
• arXiv papers - Auto-detected
• PDFs - Saved to your library

*Notifications:*
You'll receive updates when:
• Books are enriched with AI summaries
• Books are classified (Dewey)
• Links are checked for health
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
            msg = f"""🔐 *Web Login Link*

Your magic link is ready! Click below to log in to the Holocene web interface.

{magic_link}

⏱️ *Expires in 5 minutes*
🔒 *Single-use only*

This link will grant you access to:
• Web dashboard
• Collection browser
• Research tools
"""

            await update.message.reply_text(msg, parse_mode='Markdown')
            self.messages_sent += 1
            self.logger.info(f"Magic link generated for user {user_id} (telegram: {telegram_user_id})")

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

    # Message and document handlers

    async def _handle_message(self, update, context):
        """Handle text messages - detect DOIs and URLs."""
        if not self._is_authorized(update.effective_chat.id):
            return

        text = update.message.text
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

        # Check for arXiv ID/URL (before generic URL check)
        arxiv_id = self._detect_arxiv(text)
        if arxiv_id:
            await update.message.reply_text(f"📄 Detected arXiv paper: `{arxiv_id}`\nProcessing...", parse_mode='Markdown')
            self.run_in_background(
                lambda: self._add_paper_from_arxiv(arxiv_id, update.effective_chat.id),
                callback=lambda result: self.logger.info(f"arXiv paper added: {result}"),
                error_handler=lambda e: self.logger.error(f"Failed to add arXiv paper: {e}")
            )
            return

        # Check for URL (generic links)
        url = self._detect_url(text)
        if url:
            await update.message.reply_text(f"🔗 Detected URL: `{url}`\nProcessing...", parse_mode='Markdown')
            self.run_in_background(
                lambda: self._add_link_from_url(url, update.effective_chat.id),
                callback=lambda result: self.logger.info(f"Link added: {result}"),
                error_handler=lambda e: self.logger.error(f"Failed to add link: {e}")
            )
            return

        # No DOI, arXiv, or URL found
        await update.message.reply_text(
            "ℹ️ I can process:\n"
            "• DOIs (e.g., 10.1234/example)\n"
            "• arXiv papers (e.g., 2103.12345 or arxiv.org/abs/...)\n"
            "• URLs (http/https links)\n"
            "• PDFs (send as document)\n\n"
            "Use /help for available commands."
        )

    async def _handle_document(self, update, context):
        """Handle document uploads (PDFs, etc.)."""
        if not self._is_authorized(update.effective_chat.id):
            return

        document = update.message.document
        file_name = document.file_name
        file_size = document.file_size
        mime_type = document.mime_type

        self.logger.info(f"Received document: {file_name} ({file_size} bytes, {mime_type})")

        # Check if it's a PDF
        if mime_type != 'application/pdf' and not file_name.lower().endswith('.pdf'):
            await update.message.reply_text("⚠️ Only PDF files are supported for now.")
            return

        # Check file size (limit to 20MB for now)
        max_size = 20 * 1024 * 1024  # 20MB
        if file_size > max_size:
            await update.message.reply_text(f"⚠️ File too large. Maximum size: {max_size // (1024*1024)}MB")
            return

        await update.message.reply_text(f"📄 Downloading PDF: `{file_name}`...", parse_mode='Markdown')

        # Download the file
        try:
            file = await document.get_file()

            # Save to temp directory
            temp_dir = Path(self.core.config.data_dir) / "temp"
            temp_dir.mkdir(exist_ok=True)
            file_path = temp_dir / file_name

            await file.download_to_drive(str(file_path))

            await update.message.reply_text(f"✅ Downloaded! Processing PDF...")

            # Process in background
            self.run_in_background(
                lambda: self._process_pdf(str(file_path), file_name, update.effective_chat.id),
                callback=lambda result: self.logger.info(f"PDF processed: {result}"),
                error_handler=lambda e: self.logger.error(f"Failed to process PDF: {e}")
            )

        except Exception as e:
            self.logger.error(f"Failed to download PDF: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Failed to download PDF: {str(e)}")

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

    def _add_link_from_url(self, url: str, chat_id: int):
        """Add link from URL (runs in background).

        Args:
            url: URL string
            chat_id: Telegram chat ID for notifications
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
            link_id = db.insert_link(
                url=url,
                source="telegram",
                title=None,  # Will be fetched later
                notes="Added via Telegram bot"
            )

            # Check if URL was unwrapped by querying what was actually saved
            cursor.execute("SELECT url, title FROM links WHERE id = ?", (link_id,))
            saved_link = cursor.fetchone()
            actual_url = saved_link['url'] if saved_link else url

            # Immediate archiving to Internet Archive (Phase 1: Full Gwern)
            archive_status = None
            archive_result = None
            if hasattr(self.core.config, 'integrations') and \
               getattr(self.core.config.integrations, 'internet_archive_enabled', False):
                try:
                    from ..integrations import InternetArchiveClient

                    ia = InternetArchiveClient(
                        access_key=self.core.config.integrations.ia_access_key,
                        secret_key=self.core.config.integrations.ia_secret_key,
                        rate_limit_seconds=self.core.config.integrations.ia_rate_limit_seconds
                    )

                    self.logger.info(f"Archiving link to Internet Archive: {actual_url}")
                    archive_result = ia.save_url(actual_url, force=False)
                    archive_status = archive_result.get('status')

                    # Update database with archive info
                    if archive_status in ('archived', 'already_archived'):
                        db.update_link_archive_status(
                            url=actual_url,
                            archived=True,
                            archive_url=archive_result.get('snapshot_url'),
                            archive_date=archive_result.get('archive_date')
                        )
                        self.logger.info(f"Link archived: {archive_status}")
                    else:
                        # Record failure
                        error_msg = archive_result.get('error') or archive_result.get('message') or 'Unknown error'
                        db.record_archive_failure(actual_url, error_msg)
                        self.logger.warning(f"Archive failed: {error_msg}")

                except Exception as e:
                    self.logger.error(f"Failed to archive link: {e}", exc_info=True)
                    archive_status = 'error'
            else:
                self.logger.debug("Internet Archive integration not enabled, skipping immediate archiving")

            # Build notification message
            msg = f"✅ *Link Added*\n\n"

            if actual_url != url:
                # URL was unwrapped
                msg += f"🔗 Original: {url}\n"
                msg += f"📍 Unwrapped: {actual_url}\n\n"
            else:
                # URL unchanged
                msg += f"{url}\n\n"

            msg += f"Link ID: {link_id}\n"
            msg += f"Source: Telegram\n"

            # Add archive status to notification
            if archive_status == 'archived':
                msg += f"\n📦 *Archived to IA*\n"
                msg += f"Snapshot: {archive_result.get('snapshot_url', '')[:50]}"
            elif archive_status == 'already_archived':
                from ..storage.database import calculate_trust_tier
                archive_date = archive_result.get('archive_date')
                if archive_date:
                    trust_tier = calculate_trust_tier(archive_date)
                    msg += f"\n📦 *Already archived* ({trust_tier})\n"
                    msg += f"Snapshot: {archive_result.get('snapshot_url', '')[:50]}"
                else:
                    msg += f"\n📦 *Already archived*"
            elif archive_status == 'error' or (archive_result and archive_status not in ('archived', 'already_archived')):
                msg += f"\n⚠️ *Archive failed* (will retry later)"

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
