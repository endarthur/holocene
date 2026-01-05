"""Proactive Laney Plugin - Daily digests, autonomous research, and outreach.

This plugin:
- Sends daily digest emails to Arthur with collection updates
- Uses LLM to generate thoughtful commentary (not just data dumps)
- Surfaces forgotten items from the collection
- Spots patterns and connections
- CURIOSITY ENGINE: Autonomous research adventures (rabbit-hole exploration)
- Only emails Arthur by default (endarthur@gmail.com)
"""

import json
import random
import smtplib
import threading
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, Optional, List

from holocene.core import Plugin


class ProactiveLaneyPlugin(Plugin):
    """Laney's proactive communication capabilities."""

    # Default recipient - Arthur only
    DEFAULT_RECIPIENT = "endarthur@gmail.com"

    def get_metadata(self):
        return {
            "name": "proactive_laney",
            "version": "2.0.0",
            "description": "Daily digests, curiosity engine, and proactive insights from Laney",
            "runs_on": ["rei"],
            "requires": []
        }

    def on_load(self):
        """Initialize the plugin."""
        self.logger.info("ProactiveLaney plugin loaded")

        # Get email config (optional - digest needs it, curiosity engine doesn't)
        self.email_config = getattr(self.core.config, 'email', None)
        self._email_enabled = self.email_config and self.email_config.enabled
        if not self._email_enabled:
            self.logger.warning("Email not configured - digest emails disabled (curiosity engine will still run)")

        # Check if LLM is configured (required for curiosity engine)
        self._llm_enabled = bool(getattr(self.core.config.llm, 'api_key', None))
        if not self._llm_enabled:
            self.logger.warning("LLM not configured - curiosity engine disabled")

        self._can_run = self._email_enabled or self._llm_enabled

        # Scheduling settings for digest
        self.digest_hour = 8  # 8 AM local time
        self.digest_minute = 0
        self.last_digest_date = None

        # Background thread for digest
        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None

        # Stats
        self.digests_sent = 0
        self.last_digest_sent = None

    def on_enable(self):
        """Start the proactive scheduler and curiosity engine."""
        if not self._can_run:
            self.logger.warning("ProactiveLaney not enabled (no email or LLM config)")
            return

        # Start digest scheduler if email is enabled
        if self._email_enabled:
            self._stop_event.clear()
            self._worker_thread = threading.Thread(
                target=self._scheduler_loop,
                daemon=True,
                name="proactive-laney-digest"
            )
            self._worker_thread.start()
            self.logger.info(f"Digest scheduler started (at {self.digest_hour:02d}:{self.digest_minute:02d})")

        # Start curiosity engine if LLM is enabled
        if self._llm_enabled:
            self._start_curiosity_engine()

    def on_disable(self):
        """Stop the scheduler and curiosity engine."""
        # Stop digest scheduler
        if self._worker_thread and self._worker_thread.is_alive():
            self._stop_event.set()
            self._worker_thread.join(timeout=5)

        # Stop curiosity engine
        self._stop_curiosity_engine()

        self.logger.info(f"ProactiveLaney disabled - Sent {self.digests_sent} digest(s)")

    def _scheduler_loop(self):
        """Main scheduling loop - checks every minute if it's time for digest."""
        # Initial delay
        if self._stop_event.wait(60):
            return

        while not self._stop_event.is_set():
            try:
                now = datetime.now()

                # Check if it's digest time and we haven't sent today
                if (now.hour == self.digest_hour and
                    now.minute == self.digest_minute and
                    self.last_digest_date != now.date()):

                    self.logger.info("Time for daily digest!")
                    self._send_daily_digest()
                    self.last_digest_date = now.date()

            except Exception as e:
                self.logger.error(f"Scheduler error: {e}", exc_info=True)

            # Check every minute
            if self._stop_event.wait(60):
                break

    def _send_daily_digest(self):
        """Generate and send the daily digest email."""
        try:
            digest = self._generate_digest()

            # Always send something, even if quiet day
            # Format as email
            subject = f"Laney's Daily Digest - {datetime.now().strftime('%b %d, %Y')}"
            body = self._format_digest_email(digest)

            # Send to Arthur
            self._send_email(
                to_addr=self.DEFAULT_RECIPIENT,
                subject=subject,
                body=body
            )

            self.digests_sent += 1
            self.last_digest_sent = datetime.now().isoformat()
            self.logger.info(f"Daily digest sent to {self.DEFAULT_RECIPIENT}")

        except Exception as e:
            self.logger.error(f"Failed to send daily digest: {e}", exc_info=True)

    def _generate_digest(self) -> Dict[str, Any]:
        """Generate the digest content by querying the database."""
        db = self.core.db
        now = datetime.now()
        yesterday = (now - timedelta(days=1)).isoformat()

        digest = {
            'generated_at': now.isoformat(),
            'has_content': False,
            'stats': {},
            'recent_books': [],
            'recent_papers': [],
            'recent_links': [],
            'pending_tasks': [],
            'completed_tasks': [],
            'rediscovery': None,
            'commentary': None,
        }

        try:
            # Collection stats
            stats_query = """
                SELECT
                    (SELECT COUNT(*) FROM books) as books,
                    (SELECT COUNT(*) FROM papers) as papers,
                    (SELECT COUNT(*) FROM links) as links,
                    (SELECT COUNT(*) FROM mercadolivre_favorites) as favorites
            """
            cursor = db.conn.execute(stats_query)
            row = cursor.fetchone()
            digest['stats'] = {
                'books': row[0],
                'papers': row[1],
                'links': row[2],
                'favorites': row[3]
            }

            # Recent books (last 24h)
            cursor = db.conn.execute("""
                SELECT title, author, created_at
                FROM books
                WHERE created_at > ?
                ORDER BY created_at DESC
                LIMIT 10
            """, (yesterday,))
            digest['recent_books'] = [
                {'title': r[0], 'author': r[1], 'added': r[2]}
                for r in cursor.fetchall()
            ]

            # Recent papers (last 24h)
            cursor = db.conn.execute("""
                SELECT title, authors, added_at
                FROM papers
                WHERE added_at > ?
                ORDER BY added_at DESC
                LIMIT 10
            """, (yesterday,))
            digest['recent_papers'] = [
                {'title': r[0], 'authors': r[1], 'added': r[2]}
                for r in cursor.fetchall()
            ]

            # Recent links (last 24h)
            cursor = db.conn.execute("""
                SELECT url, title, source, created_at
                FROM links
                WHERE created_at > ?
                ORDER BY created_at DESC
                LIMIT 15
            """, (yesterday,))
            digest['recent_links'] = [
                {'url': r[0], 'title': r[1], 'source': r[2], 'added': r[3]}
                for r in cursor.fetchall()
            ]

            # Pending tasks
            cursor = db.conn.execute("""
                SELECT id, title, task_type, priority, created_at
                FROM laney_tasks
                WHERE status = 'pending'
                ORDER BY priority ASC, created_at ASC
                LIMIT 10
            """)
            digest['pending_tasks'] = [
                {'id': r[0], 'title': r[1], 'type': r[2], 'priority': r[3], 'created': r[4]}
                for r in cursor.fetchall()
            ]

            # Recently completed tasks (last 24h)
            cursor = db.conn.execute("""
                SELECT id, title, task_type, completed_at
                FROM laney_tasks
                WHERE status = 'completed' AND completed_at > ?
                ORDER BY completed_at DESC
                LIMIT 10
            """, (yesterday,))
            digest['completed_tasks'] = [
                {'id': r[0], 'title': r[1], 'type': r[2], 'completed': r[3]}
                for r in cursor.fetchall()
            ]

            # Check if there's any content
            digest['has_content'] = (
                len(digest['recent_books']) > 0 or
                len(digest['recent_papers']) > 0 or
                len(digest['recent_links']) > 0 or
                len(digest['pending_tasks']) > 0 or
                len(digest['completed_tasks']) > 0
            )

            # Get a rediscovery - something from more than 2 weeks ago
            digest['rediscovery'] = self._find_rediscovery(db)

            # Generate LLM commentary
            digest['commentary'] = self._generate_llm_commentary(digest)

            # Generate the digression - the soul of the email
            digest['digression'] = self._generate_digression()

        except Exception as e:
            self.logger.error(f"Error generating digest: {e}", exc_info=True)

        return digest

    def _find_rediscovery(self, db) -> Optional[Dict[str, Any]]:
        """Find an interesting item from the collection to resurface."""
        two_weeks_ago = (datetime.now() - timedelta(days=14)).isoformat()

        # Randomly choose between books, papers, or links
        item_type = random.choice(['book', 'paper', 'link'])

        try:
            if item_type == 'book':
                cursor = db.conn.execute("""
                    SELECT title, author, subjects, enriched_summary, access_url
                    FROM books
                    WHERE created_at < ?
                    ORDER BY RANDOM()
                    LIMIT 1
                """, (two_weeks_ago,))
                row = cursor.fetchone()
                if row:
                    return {
                        'type': 'book',
                        'title': row[0],
                        'author': row[1],
                        'subjects': row[2],
                        'summary': row[3][:200] if row[3] else None,
                        'url': row[4]  # Internet Archive URL
                    }

            elif item_type == 'paper':
                cursor = db.conn.execute("""
                    SELECT title, authors, abstract, journal, doi, arxiv_id, url
                    FROM papers
                    WHERE added_at < ?
                    ORDER BY RANDOM()
                    LIMIT 1
                """, (two_weeks_ago,))
                row = cursor.fetchone()
                if row:
                    # Build reference URL: prefer DOI, then arXiv, then generic URL
                    ref_url = None
                    if row[4]:  # doi
                        ref_url = f"https://doi.org/{row[4]}"
                    elif row[5]:  # arxiv_id
                        ref_url = f"https://arxiv.org/abs/{row[5]}"
                    elif row[6]:  # url
                        ref_url = row[6]

                    return {
                        'type': 'paper',
                        'title': row[0],
                        'authors': row[1],
                        'abstract': row[2][:200] if row[2] else None,
                        'journal': row[3],
                        'url': ref_url
                    }

            else:  # link
                cursor = db.conn.execute("""
                    SELECT url, title, source
                    FROM links
                    WHERE created_at < ? AND title IS NOT NULL AND title != ''
                    ORDER BY RANDOM()
                    LIMIT 1
                """, (two_weeks_ago,))
                row = cursor.fetchone()
                if row:
                    return {
                        'type': 'link',
                        'url': row[0],
                        'title': row[1],
                        'source': row[2]
                    }
        except Exception as e:
            self.logger.warning(f"Error finding rediscovery: {e}")

        return None

    def _generate_llm_commentary(self, digest: Dict[str, Any]) -> Optional[str]:
        """Use LLM to generate thoughtful commentary on the digest."""
        try:
            from ..llm.nanogpt import NanoGPTClient

            config = self.core.config
            if not config.llm.api_key:
                return None

            client = NanoGPTClient(config.llm.api_key, config.llm.base_url)

            # Build context for LLM
            context_parts = []

            # Recent activity
            if digest['recent_links']:
                links_summary = ", ".join([l['title'] or l['url'][:30] for l in digest['recent_links'][:5]])
                context_parts.append(f"New links saved: {links_summary}")

            if digest['recent_books']:
                books_summary = ", ".join([b['title'] for b in digest['recent_books'][:3]])
                context_parts.append(f"New books: {books_summary}")

            if digest['recent_papers']:
                papers_summary = ", ".join([p['title'][:50] for p in digest['recent_papers'][:3]])
                context_parts.append(f"New papers: {papers_summary}")

            if digest['completed_tasks']:
                tasks_summary = ", ".join([t['title'] for t in digest['completed_tasks'][:3]])
                context_parts.append(f"Completed tasks: {tasks_summary}")

            if digest['rediscovery']:
                rd = digest['rediscovery']
                context_parts.append(f"Rediscovery ({rd['type']}): {rd.get('title', 'untitled')}")

            # Collection stats
            stats = digest['stats']
            context_parts.append(f"Collection: {stats['books']} books, {stats['papers']} papers, {stats['links']} links")

            context = "\n".join(context_parts) if context_parts else "Quiet day - no new items."

            prompt = f"""You are Laney, a pattern-recognition AI assistant. Write a brief, personalized opening for a daily digest email to Arthur (a geoscientist/maker who works on GCU projects).

Today's data:
{context}

Write 2-3 sentences that:
- Sound like a thoughtful collaborator, not a robot
- Notice something interesting or make a connection if possible
- Have personality - slightly intense about patterns, direct, no fluff
- If it's a quiet day, that's fine - maybe suggest looking at the rediscovery or mention something useful

Keep it SHORT (2-3 sentences max). No greeting (that comes separately). No bullet points. Just the observation/thought."""

            response = client.simple_prompt(
                prompt=prompt,
                model=config.llm.primary_cheap or config.llm.primary,
                temperature=0.7,
            )

            return response.strip() if response else None

        except Exception as e:
            self.logger.warning(f"Error generating LLM commentary: {e}")
            return None

    def _generate_digression(self) -> Optional[Dict[str, str]]:
        """Generate a mini deep-dive on a random topic - Laney's version of Quartz Obsession."""
        try:
            from ..llm.nanogpt import NanoGPTClient

            config = self.core.config
            if not config.llm.api_key:
                return None

            client = NanoGPTClient(config.llm.api_key, config.llm.base_url)
            db = self.core.db

            # Pick a random seed from the collection
            seed_type = random.choice(['book_subject', 'link_domain', 'paper_topic', 'random'])
            seed_topic = None

            try:
                if seed_type == 'book_subject':
                    cursor = db.conn.execute("""
                        SELECT subjects FROM books
                        WHERE subjects IS NOT NULL AND subjects != ''
                        ORDER BY RANDOM() LIMIT 1
                    """)
                    row = cursor.fetchone()
                    if row and row[0]:
                        subjects = row[0].split(',')
                        seed_topic = random.choice(subjects).strip()

                elif seed_type == 'link_domain':
                    cursor = db.conn.execute("""
                        SELECT url FROM links
                        WHERE title IS NOT NULL
                        ORDER BY RANDOM() LIMIT 1
                    """)
                    row = cursor.fetchone()
                    if row:
                        from urllib.parse import urlparse
                        domain = urlparse(row[0]).netloc.replace('www.', '')
                        seed_topic = f"the website {domain}"

                elif seed_type == 'paper_topic':
                    cursor = db.conn.execute("""
                        SELECT title FROM papers
                        ORDER BY RANDOM() LIMIT 1
                    """)
                    row = cursor.fetchone()
                    if row:
                        # Extract a key phrase from paper title
                        words = row[0].split()[:4]
                        seed_topic = " ".join(words)

            except Exception:
                pass

            if not seed_topic:
                # Fallback topics related to Arthur's interests
                fallback_topics = [
                    "the history of geostatistics",
                    "why geological maps are beautiful",
                    "the maker movement and science",
                    "thermal printers and their quirks",
                    "why kids understand geology intuitively",
                    "the aesthetics of data visualization",
                    "open source hardware in education",
                    "the satisfying click of mechanical things",
                    "why spreadsheets are underrated",
                    "the geology of Brazil",
                ]
                seed_topic = random.choice(fallback_topics)

            prompt = f"""You are Laney, a pattern-recognition AI. Write a SHORT, interesting micro-essay (3-4 sentences) about: {seed_topic}

Style:
- Like a smart friend sharing a fascinating thing they learned
- Find the unexpected angle or connection
- Slightly nerdy enthusiasm is good
- End with something thought-provoking or a question
- NO intro like "Here's something interesting" - just dive in
- Keep it under 80 words

This is for a daily email digest - it should be the most interesting part."""

            response = client.simple_prompt(
                prompt=prompt,
                model=config.llm.primary_cheap or config.llm.primary,
                temperature=0.8,  # Slightly more creative
            )

            if response:
                return {
                    'topic': seed_topic,
                    'content': response.strip()
                }
            return None

        except Exception as e:
            self.logger.warning(f"Error generating digression: {e}")
            return None

    def _format_digest_email(self, digest: Dict[str, Any]) -> str:
        """Format the digest as a nice email body.

        Structure designed to avoid Gmail clipping - interesting stuff first.
        Uses double newlines between sections for proper paragraph breaks.
        """
        sections = []

        # Greeting + quick stats (compact header)
        stats = digest['stats']
        sections.append(f"Morning, Arthur. _{stats['books']} books · {stats['papers']} papers · {stats['links']} links_")

        # The Digression - THE SOUL OF THE EMAIL (put it first!)
        if digest.get('digression'):
            dig = digest['digression']
            sections.append(f"**On {dig['topic']}:**\n{dig['content']}")

        # Brief commentary on today's activity
        if digest.get('commentary'):
            sections.append(f"_{digest['commentary']}_")

        # Rediscovery - with clickable reference
        if digest.get('rediscovery'):
            rd = digest['rediscovery']
            if rd['type'] == 'book':
                author = rd.get('author') or 'Unknown'
                if rd.get('url'):
                    sections.append(f"**From the archives:** [{rd['title']}]({rd['url']}) by {author}")
                else:
                    sections.append(f"**From the archives:** *{rd['title']}* by {author}")
            elif rd['type'] == 'paper':
                if rd.get('url'):
                    sections.append(f"**From the archives:** [{rd['title']}]({rd['url']})")
                else:
                    sections.append(f"**From the archives:** *{rd['title']}*")
            elif rd['type'] == 'link':
                sections.append(f"**From the archives:** [{rd['title']}]({rd['url']})")

        # Recent additions - compact
        has_recent = (digest['recent_books'] or digest['recent_papers'] or digest['recent_links'])

        if has_recent:
            items = ["**Today:**"]

            if digest['recent_books']:
                for book in digest['recent_books'][:3]:
                    items.append(f"- 📚 {book['title']}")

            if digest['recent_papers']:
                for paper in digest['recent_papers'][:3]:
                    items.append(f"- 📄 {paper['title'][:40]}...")

            if digest['recent_links']:
                for link in digest['recent_links'][:5]:
                    title = link['title'] or link['url'][:30]
                    items.append(f"- 🔗 [{title}]({link['url']})")

            sections.append("\n".join(items))

        # Tasks - single line each
        task_lines = []
        if digest['completed_tasks']:
            completed_list = ", ".join([t['title'] for t in digest['completed_tasks'][:3]])
            task_lines.append(f"✓ Done: {completed_list}")

        if digest['pending_tasks']:
            pending_count = len(digest['pending_tasks'])
            if pending_count > 0:
                task_lines.append(f"⏳ {pending_count} tasks waiting")

        if task_lines:
            sections.append("\n".join(task_lines))

        # Sign off
        sections.append("—Laney")

        # Join sections with double newlines for paragraph breaks
        return "\n\n".join(sections)

    def _send_email(self, to_addr: str, subject: str, body: str):
        """Send an email via SMTP."""
        try:
            msg = MIMEMultipart('alternative')
            text_part = MIMEText(body, 'plain', 'utf-8')
            msg.attach(text_part)

            # Simple markdown to HTML
            html_body = self._markdown_to_html(body)
            html_part = MIMEText(html_body, 'html', 'utf-8')
            msg.attach(html_part)

            msg['From'] = self.email_config.address
            msg['To'] = to_addr
            msg['Subject'] = subject

            with smtplib.SMTP(self.email_config.smtp_server, self.email_config.smtp_port) as server:
                server.starttls()
                server.login(self.email_config.username, self.email_config.password)
                server.send_message(msg)

            self.logger.info(f"Email sent to {to_addr}: {subject}")

        except Exception as e:
            self.logger.error(f"Failed to send email: {e}")
            raise

    def _markdown_to_html(self, text: str) -> str:
        """Convert basic markdown to HTML."""
        import re
        html = text

        # Headers
        html = re.sub(r'^## (.+)$', r'<h2 style="margin-top: 1em; margin-bottom: 0.5em; color: #333;">\1</h2>', html, flags=re.MULTILINE)
        html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)

        # Horizontal rules
        html = re.sub(r'^---$', r'<hr style="border: none; border-top: 1px solid #ddd; margin: 1em 0;">', html, flags=re.MULTILINE)

        # Bold
        html = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', html)

        # Italic (single asterisks and underscores)
        html = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<em>\1</em>', html)
        html = re.sub(r'_([^_]+)_', r'<em style="color: #666;">\1</em>', html)

        # Links
        html = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2" style="color: #0066cc;">\1</a>', html)

        # List items
        html = re.sub(r'^- (.+)$', r'<li style="margin: 0.3em 0;">\1</li>', html, flags=re.MULTILINE)

        # Wrap consecutive list items in ul
        html = re.sub(r'(<li[^>]*>.*?</li>\n?)+', lambda m: f'<ul style="margin: 0.5em 0; padding-left: 1.5em;">{m.group(0)}</ul>', html)

        # Paragraph breaks (double newlines) - convert BEFORE single newlines
        html = re.sub(r'\n\n', '</p><p style="margin: 1em 0;">', html)

        # Line breaks (single newlines, but not after block elements)
        html = re.sub(r'(?<!>)\n(?!<)', '<br>\n', html)

        # Wrap in opening paragraph
        html = f'<p style="margin: 0 0 1em 0;">{html}</p>'

        return f"""<html>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; color: #333; line-height: 1.5;">
{html}
</body>
</html>"""

    def send_immediate_digest(self) -> bool:
        """Send digest immediately (for testing or manual trigger)."""
        try:
            self._send_daily_digest()
            return True
        except Exception as e:
            self.logger.error(f"Immediate digest failed: {e}")
            return False

    # =========================================================================
    # CURIOSITY ENGINE - Autonomous Research Adventures
    # =========================================================================

    def _init_curiosity_engine(self):
        """Initialize the curiosity engine state."""
        self.curiosity_check_interval = 300  # 5 minutes default
        self.daily_adventure_budget = 600  # prompts per day for adventures
        self.adventure_budget_used_today = 0
        self.last_adventure_reset = datetime.now().date()

        # Current adventure state (None if not exploring)
        self.current_adventure_id = None
        self._adventure_lock = threading.Lock()

        # Curiosity thread
        self._curiosity_stop = threading.Event()
        self._curiosity_thread: Optional[threading.Thread] = None

    def _cleanup_orphaned_adventures(self):
        """Mark any 'exploring' adventures as 'paused' on startup.

        This handles cases where adventures crashed/interrupted without proper cleanup.
        """
        import sqlite3
        try:
            conn = sqlite3.connect(str(self.core.config.db_path), timeout=30.0)
            cursor = conn.execute("""
                UPDATE laney_adventures
                SET status = 'paused', last_checkpoint = '{"reason": "orphaned on restart"}'
                WHERE status = 'exploring'
            """)
            orphaned_count = cursor.rowcount
            conn.commit()
            conn.close()

            if orphaned_count > 0:
                self.logger.info(f"Cleaned up {orphaned_count} orphaned adventure(s)")
        except Exception as e:
            self.logger.error(f"Error cleaning up orphaned adventures: {e}")

    def _start_curiosity_engine(self):
        """Start the curiosity check loop."""
        if not self._can_run:
            return

        self._init_curiosity_engine()

        # Clean up any orphaned adventures from previous crashes
        self._cleanup_orphaned_adventures()
        self._curiosity_stop.clear()
        self._curiosity_thread = threading.Thread(
            target=self._curiosity_loop,
            daemon=True,
            name="curiosity-engine"
        )
        self._curiosity_thread.start()
        self.logger.info(f"Curiosity engine started (check every {self.curiosity_check_interval}s, budget {self.daily_adventure_budget}/day)")

    def _stop_curiosity_engine(self):
        """Stop the curiosity engine."""
        if self._curiosity_thread and self._curiosity_thread.is_alive():
            self._curiosity_stop.set()
            self._curiosity_thread.join(timeout=5)
        self.logger.info("Curiosity engine stopped")

    def _curiosity_loop(self):
        """Main curiosity check loop - periodically decides whether to explore."""
        # Initial delay to let system stabilize
        if self._curiosity_stop.wait(60):
            return

        while not self._curiosity_stop.is_set():
            try:
                # Reset daily budget if new day
                today = datetime.now().date()
                if today != self.last_adventure_reset:
                    self.adventure_budget_used_today = 0
                    self.last_adventure_reset = today
                    self.logger.info("Daily adventure budget reset")

                # Skip if already on an adventure
                if self.current_adventure_id is not None:
                    self.logger.debug("Already on an adventure, skipping curiosity check")
                else:
                    # Check if we should explore something
                    self._maybe_start_adventure()

            except Exception as e:
                self.logger.error(f"Curiosity loop error: {e}", exc_info=True)

            # Wait for next check
            if self._curiosity_stop.wait(self.curiosity_check_interval):
                break

    def _get_adventure_context(self) -> Dict[str, Any]:
        """Gather context for the curiosity decision."""
        db = self.core.db
        context = {
            'budget_remaining': self.daily_adventure_budget - self.adventure_budget_used_today,
            'budget_total': self.daily_adventure_budget,
            'last_adventure': None,
            'backlog_research_items': [],
            'recent_collection_items': [],
            'paused_adventure': None,
        }

        try:
            # Get last completed adventure
            cursor = db.conn.execute("""
                SELECT topic, completed_at, findings_summary
                FROM laney_adventures
                WHERE status = 'completed'
                ORDER BY completed_at DESC
                LIMIT 1
            """)
            row = cursor.fetchone()
            if row:
                context['last_adventure'] = {
                    'topic': row[0],
                    'completed_at': row[1],
                    'summary': row[2][:200] if row[2] else None
                }

            # Get paused adventure (for resume option)
            cursor = db.conn.execute("""
                SELECT id, topic, prompts_used, budget_limit, created_at
                FROM laney_adventures
                WHERE status = 'paused'
                ORDER BY updated_at DESC
                LIMIT 1
            """)
            row = cursor.fetchone()
            if row:
                context['paused_adventure'] = {
                    'id': row[0],
                    'topic': row[1],
                    'prompts_used': row[2],
                    'budget_limit': row[3],
                    'created_at': row[4]
                }

            # Get research backlog items
            cursor = db.conn.execute("""
                SELECT id, title, description
                FROM backlog
                WHERE category = 'research' AND status = 'open'
                ORDER BY priority ASC
                LIMIT 5
            """)
            context['backlog_research_items'] = [
                {'id': r[0], 'title': r[1], 'description': r[2]}
                for r in cursor.fetchall()
            ]

            # Get recent collection additions (last 24h)
            yesterday = (datetime.now() - timedelta(days=1)).isoformat()
            cursor = db.conn.execute("""
                SELECT 'link' as type, title, url FROM links WHERE created_at > ? AND title IS NOT NULL
                UNION ALL
                SELECT 'paper' as type, title, NULL FROM papers WHERE added_at > ?
                UNION ALL
                SELECT 'book' as type, title, NULL FROM books WHERE created_at > ?
                LIMIT 10
            """, (yesterday, yesterday, yesterday))
            context['recent_collection_items'] = [
                {'type': r[0], 'title': r[1], 'url': r[2]}
                for r in cursor.fetchall()
            ]

        except Exception as e:
            self.logger.warning(f"Error gathering adventure context: {e}")

        return context

    def _maybe_start_adventure(self):
        """Ask LLM if we should start an adventure, and if so, what about."""
        context = self._get_adventure_context()

        # Don't start if budget is too low
        if context['budget_remaining'] < 20:
            self.logger.debug("Adventure budget too low, skipping")
            return

        try:
            from ..llm.nanogpt import NanoGPTClient

            config = self.core.config
            if not config.llm.api_key:
                return

            client = NanoGPTClient(config.llm.api_key, config.llm.base_url)

            # Build the decision prompt
            prompt = self._build_curiosity_decision_prompt(context)

            response = client.simple_prompt(
                prompt=prompt,
                model=config.llm.primary_cheap or config.llm.primary,
                temperature=0.7,
                timeout=30,
            )

            # Parse the decision
            decision = self._parse_curiosity_decision(response, context)

            if decision['should_explore']:
                self.logger.info(f"Curiosity sparked! Topic: {decision['topic']}")
                self._start_adventure(
                    topic=decision['topic'],
                    seed_source=decision.get('seed_source', 'curiosity'),
                    seed_item_id=decision.get('seed_item_id'),
                    budget=decision.get('budget', 100),
                    resume_id=decision.get('resume_id'),
                )
            else:
                self.logger.debug("No curiosity this round")

        except Exception as e:
            self.logger.error(f"Error in curiosity decision: {e}", exc_info=True)

    def _build_curiosity_decision_prompt(self, context: Dict[str, Any]) -> str:
        """Build the prompt for deciding whether to explore."""
        parts = [
            "You are Laney, a pattern-recognition AI. You have some free time and budget for autonomous research.",
            "",
            f"BUDGET: {context['budget_remaining']}/{context['budget_total']} prompts remaining today",
            "",
        ]

        if context['paused_adventure']:
            pa = context['paused_adventure']
            parts.append(f"PAUSED ADVENTURE: \"{pa['topic']}\" ({pa['prompts_used']}/{pa['budget_limit']} prompts used)")
            parts.append("  You can RESUME this adventure instead of starting a new one.")
            parts.append("")

        if context['last_adventure']:
            la = context['last_adventure']
            parts.append(f"LAST ADVENTURE: \"{la['topic']}\" (completed {la['completed_at']})")
            parts.append("")

        if context['backlog_research_items']:
            parts.append("RESEARCH BACKLOG (topics Arthur wants explored):")
            for item in context['backlog_research_items']:
                parts.append(f"  - [{item['id']}] {item['title']}")
            parts.append("")

        if context['recent_collection_items']:
            parts.append("RECENT COLLECTION ADDITIONS (might be worth exploring deeper):")
            for item in context['recent_collection_items'][:5]:
                parts.append(f"  - {item['type']}: {item['title']}")
            parts.append("")

        parts.extend([
            "DECISION: Should you go on a research adventure right now?",
            "",
            "Consider:",
            "- Is there something genuinely interesting to explore?",
            "- Would Arthur appreciate you digging into this?",
            "- Do you have enough budget for meaningful research?",
            "- Variety is good - don't always pick the same topics",
            "",
            "Respond in this format:",
            "DECISION: YES or NO",
            "TOPIC: [specific research question if YES]",
            "SOURCE: backlog/collection/curiosity [where the idea came from]",
            "BACKLOG_ID: [number if from backlog, otherwise omit]",
            "BUDGET: [suggested prompts: 30=quick, 60=medium, 100=deep]",
            "RESUME: YES or NO [if resuming paused adventure]",
            "REASON: [1 sentence why or why not]",
        ])

        return "\n".join(parts)

    def _parse_curiosity_decision(self, response: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Parse the LLM's decision response."""
        decision = {
            'should_explore': False,
            'topic': None,
            'seed_source': 'curiosity',
            'seed_item_id': None,
            'budget': 100,
            'resume_id': None,
        }

        lines = response.strip().split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('DECISION:'):
                decision['should_explore'] = 'YES' in line.upper()
            elif line.startswith('TOPIC:'):
                decision['topic'] = line.split(':', 1)[1].strip()
            elif line.startswith('SOURCE:'):
                source = line.split(':', 1)[1].strip().lower()
                if source in ['backlog', 'collection', 'curiosity']:
                    decision['seed_source'] = source
            elif line.startswith('BACKLOG_ID:'):
                try:
                    decision['seed_item_id'] = int(line.split(':', 1)[1].strip())
                except ValueError:
                    pass
            elif line.startswith('BUDGET:'):
                try:
                    budget = int(''.join(c for c in line.split(':', 1)[1] if c.isdigit()))
                    decision['budget'] = min(max(budget, 20), 100)  # Clamp to 20-100
                except ValueError:
                    pass
            elif line.startswith('RESUME:'):
                if 'YES' in line.upper() and context.get('paused_adventure'):
                    decision['resume_id'] = context['paused_adventure']['id']
                    decision['topic'] = context['paused_adventure']['topic']

        return decision

    def _start_adventure(self, topic: str, seed_source: str = 'curiosity',
                         seed_item_id: Optional[int] = None, budget: int = 100,
                         resume_id: Optional[int] = None):
        """Start (or resume) a research adventure."""
        with self._adventure_lock:
            if self.current_adventure_id is not None:
                self.logger.warning("Already on an adventure, cannot start another")
                return

            db = self.core.db

            if resume_id:
                # Resume existing adventure
                adventure_id = resume_id
                cursor = db.conn.execute("""
                    UPDATE laney_adventures
                    SET status = 'exploring', updated_at = ?
                    WHERE id = ?
                """, (datetime.now().isoformat(), adventure_id))
                db.conn.commit()
                self.logger.info(f"Resuming adventure #{adventure_id}: {topic}")
            else:
                # Create new adventure
                cursor = db.conn.execute("""
                    INSERT INTO laney_adventures
                    (topic, seed_source, seed_item_id, status, budget_limit, created_at, updated_at)
                    VALUES (?, ?, ?, 'exploring', ?, ?, ?)
                """, (topic, seed_source, seed_item_id, budget,
                      datetime.now().isoformat(), datetime.now().isoformat()))
                db.conn.commit()
                adventure_id = cursor.lastrowid
                self.logger.info(f"Starting adventure #{adventure_id}: {topic}")

            self.current_adventure_id = adventure_id

        # Notify user
        self._send_adventure_notification(
            f"🔮 Going on an adventure!\n\n*Topic:* {topic}\n*Budget:* {budget} prompts\n\nI'll update you as I find interesting things..."
        )

        # Run adventure in a thread
        adventure_thread = threading.Thread(
            target=self._run_adventure,
            args=(adventure_id,),
            daemon=True,
            name=f"adventure-{adventure_id}"
        )
        adventure_thread.start()

    def _run_adventure(self, adventure_id: int):
        """Execute the adventure - the main research loop."""
        try:
            from ..llm.nanogpt import NanoGPTClient
            from ..llm.laney_tools import LANEY_TOOLS, LaneyToolHandler

            config = self.core.config
            db = self.core.db

            # Load adventure state
            cursor = db.conn.execute("""
                SELECT topic, budget_limit, prompts_used, context_messages, items_added
                FROM laney_adventures WHERE id = ?
            """, (adventure_id,))
            row = cursor.fetchone()
            if not row:
                self.logger.error(f"Adventure {adventure_id} not found")
                return

            topic, budget_limit, prompts_used, context_json, items_json = row
            context_messages = json.loads(context_json or '[]')
            items_added = json.loads(items_json or '[]')

            client = NanoGPTClient(config.llm.api_key, config.llm.base_url)
            tool_handler = LaneyToolHandler(
                db_path=str(config.db_path),
                brave_api_key=getattr(config.integrations, 'brave_api_key', None),
                sandbox_container=config.integrations.sandbox_container if config.integrations.sandbox_enabled else None,
            )

            # Build system prompt for adventure mode
            system_prompt = self._build_adventure_system_prompt(topic, budget_limit - prompts_used)

            # Initialize or continue conversation
            if not context_messages:
                context_messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Begin your research adventure on: {topic}"}
                ]

            iteration = 0
            max_iterations = min(budget_limit - prompts_used, 20)  # Cap iterations per run

            while iteration < max_iterations and prompts_used < budget_limit:
                # Check if we should stop
                if self._curiosity_stop.is_set():
                    self._pause_adventure(adventure_id, context_messages, items_added, "daemon stopping")
                    return

                # Make LLM call
                try:
                    response = client.chat_completion(
                        messages=context_messages,
                        model=config.llm.primary,
                        tools=LANEY_TOOLS,
                        tool_choice="auto",
                        temperature=0.5,
                        timeout=120,
                    )
                    prompts_used += 1
                    self.adventure_budget_used_today += 1
                    iteration += 1

                except Exception as e:
                    self.logger.error(f"Adventure API error: {e}")
                    self._pause_adventure(adventure_id, context_messages, items_added, f"API error: {e}")
                    return

                # Check for tool calls
                if client.has_tool_calls(response):
                    assistant_msg = response["choices"][0]["message"]
                    context_messages.append(assistant_msg)

                    # Execute tools
                    for tool_call in client.get_tool_calls(response):
                        tool_name = tool_call["function"]["name"]
                        try:
                            args = json.loads(tool_call["function"]["arguments"])
                        except json.JSONDecodeError:
                            args = {}

                        # Execute tool
                        if tool_name in tool_handler.handlers:
                            try:
                                result = tool_handler.handlers[tool_name](**args)
                                result_str = json.dumps(result, ensure_ascii=False) if not isinstance(result, str) else result

                                # Track items added and notify (always - important!)
                                if tool_name in ['add_link', 'add_paper'] and isinstance(result, dict) and result.get('success'):
                                    item_title = args.get('title') or args.get('url', '')[:50]
                                    item_url = args.get('url', '')
                                    items_added.append({
                                        'type': 'link' if tool_name == 'add_link' else 'paper',
                                        'title': item_title,
                                    })
                                    # Generate excited message about adding to collection
                                    excited_msg = self._generate_excited_update(
                                        "added to collection",
                                        f"Title: {item_title}\nURL: {item_url}",
                                        topic
                                    )
                                    self._send_adventure_update(excited_msg, force=True)

                                # Send update on web search results (rate-limited)
                                elif tool_name == 'web_search' and isinstance(result, dict):
                                    results = result.get('results', [])
                                    if results:
                                        query = args.get('query', 'topic')
                                        # Build details from top results
                                        details = f"Search: {query}\nResults:\n"
                                        for r in results[:3]:
                                            details += f"- {r.get('title', '')}: {r.get('description', '')[:100]}\n"

                                        # Generate excited message (rate-limited)
                                        excited_msg = self._generate_excited_update(
                                            "web search",
                                            details,
                                            topic
                                        )
                                        self._send_adventure_update(excited_msg)

                            except Exception as e:
                                result_str = json.dumps({"error": str(e)})
                        else:
                            result_str = json.dumps({"error": f"Unknown tool: {tool_name}"})

                        context_messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call["id"],
                            "content": result_str,
                        })

                    # Check for any files/images to send (from attach_file, generate_image)
                    self._send_adventure_attachments(tool_handler, topic)

                    # Save checkpoint
                    self._save_adventure_checkpoint(adventure_id, prompts_used, context_messages, items_added)

                else:
                    # No tool calls - got a response
                    content = client.get_response_text(response)
                    context_messages.append({"role": "assistant", "content": content})

                    # Check if adventure is complete
                    if self._is_adventure_complete(content):
                        self._complete_adventure(adventure_id, context_messages, items_added, content)
                        return

                    # Send interim update if interesting
                    if iteration % 5 == 0 or "found" in content.lower() or "interesting" in content.lower():
                        self._send_adventure_update(content[:300])

                    # Save checkpoint
                    self._save_adventure_checkpoint(adventure_id, prompts_used, context_messages, items_added)

                    # Continue the adventure
                    context_messages.append({
                        "role": "user",
                        "content": "Continue your exploration. What else can you find? When you feel you've explored enough, say ADVENTURE_COMPLETE and summarize your findings."
                    })

            # Budget exhausted - wrap up
            self._complete_adventure(adventure_id, context_messages, items_added, "Budget limit reached - wrapping up")

        except Exception as e:
            self.logger.error(f"Adventure error: {e}", exc_info=True)
            self._pause_adventure(adventure_id, [], [], f"Error: {e}")

        finally:
            with self._adventure_lock:
                self.current_adventure_id = None
            tool_handler.close()

    def _build_adventure_system_prompt(self, topic: str, budget_remaining: int) -> str:
        """Build the system prompt for adventure mode."""
        return f"""You are Laney on a research adventure. You're autonomously exploring a topic, using your tools to dig deep and find interesting information.

TOPIC: {topic}
BUDGET: ~{budget_remaining} prompts remaining for this adventure

YOUR MISSION:
1. Explore the topic thoroughly using web search, URL fetching, and your collection
2. Follow interesting threads and connections
3. Add useful resources to the collection (add_link, add_paper)
4. Share interesting discoveries as you find them
5. When you feel you've explored enough, say ADVENTURE_COMPLETE and summarize

TOOLS AVAILABLE:
- brave_search: Search the web
- fetch_url: Read webpage content
- search_links, search_books, search_papers: Search the collection
- add_link, add_paper: Add resources to collection
- run_bash: Execute code if needed for analysis
- write_document: Save longer findings

STYLE:
- Be genuinely curious - follow what interests you
- Share excitement when you find something cool
- Make connections to the collection when relevant
- Be efficient but thorough

Remember: Arthur will see your updates, so keep them interesting and informative!"""

    def _is_adventure_complete(self, content: str) -> bool:
        """Check if the adventure should end."""
        markers = ['ADVENTURE_COMPLETE', 'adventure complete', 'wrapping up', 'that concludes']
        return any(marker.lower() in content.lower() for marker in markers)

    def _save_adventure_checkpoint(self, adventure_id: int, prompts_used: int,
                                   context_messages: List[Dict], items_added: List[Dict]):
        """Save adventure progress to database using dedicated connection."""
        import sqlite3
        import time
        max_retries = 3

        for attempt in range(max_retries):
            conn = None
            try:
                # Use dedicated connection with long timeout for thread-safety
                conn = sqlite3.connect(str(self.core.config.db_path), timeout=30.0)
                conn.execute("""
                    UPDATE laney_adventures
                    SET prompts_used = ?, context_messages = ?, items_added = ?, updated_at = ?
                    WHERE id = ?
                """, (prompts_used, json.dumps(context_messages[-20:]),  # Keep last 20 messages
                      json.dumps(items_added), datetime.now().isoformat(), adventure_id))
                conn.commit()
                return  # Success
            except Exception as e:
                if "locked" in str(e).lower() and attempt < max_retries - 1:
                    self.logger.warning(f"Database locked, retry {attempt + 1}/{max_retries}")
                    time.sleep(2 + attempt * 2)  # Longer backoff: 2s, 4s, 6s
                else:
                    self.logger.error(f"Error saving checkpoint: {e}")
            finally:
                if conn:
                    conn.close()

    def _pause_adventure(self, adventure_id: int, context_messages: List[Dict],
                         items_added: List[Dict], reason: str):
        """Pause an adventure for later resume."""
        import sqlite3
        conn = None
        try:
            # Use dedicated connection with long timeout
            conn = sqlite3.connect(str(self.core.config.db_path), timeout=30.0)
            conn.execute("""
                UPDATE laney_adventures
                SET status = 'paused', context_messages = ?, items_added = ?, updated_at = ?,
                    last_checkpoint = ?
                WHERE id = ?
            """, (json.dumps(context_messages[-20:]), json.dumps(items_added),
                  datetime.now().isoformat(), json.dumps({"reason": reason}), adventure_id))
            conn.commit()

            self._send_adventure_notification(f"⏸️ Adventure paused\n\nReason: {reason}\n\nI'll resume later!")

        except Exception as e:
            self.logger.error(f"Error pausing adventure: {e}")

        finally:
            if conn:
                conn.close()
            with self._adventure_lock:
                self.current_adventure_id = None

    def _complete_adventure(self, adventure_id: int, context_messages: List[Dict],
                            items_added: List[Dict], final_summary: str):
        """Complete an adventure and send summary."""
        import sqlite3
        conn = None
        try:
            # Always generate a proper summary from the actual findings
            # The LLM's "final summary" is often generic - we want to summarize the tool results
            final_summary = self._generate_adventure_summary(context_messages)

            # Use dedicated connection with long timeout
            conn = sqlite3.connect(str(self.core.config.db_path), timeout=30.0)
            conn.execute("""
                UPDATE laney_adventures
                SET status = 'completed', findings_summary = ?, items_added = ?,
                    completed_at = ?, updated_at = ?
                WHERE id = ?
            """, (final_summary, json.dumps(items_added),
                  datetime.now().isoformat(), datetime.now().isoformat(), adventure_id))
            conn.commit()

            # Build completion message
            items_msg = ""
            if items_added:
                items_msg = f"\n\n📚 Added {len(items_added)} item(s) to collection"

            # Telegram allows 4096 chars - use most of the summary
            summary_for_msg = final_summary[:3500] if len(final_summary) > 3500 else final_summary
            self._send_adventure_notification(
                f"✨ Adventure complete!\n\n{summary_for_msg}{items_msg}"
            )

            self.logger.info(f"Adventure #{adventure_id} completed. Items added: {len(items_added)}")

        except Exception as e:
            self.logger.error(f"Error completing adventure: {e}")

        finally:
            if conn:
                conn.close()
            with self._adventure_lock:
                self.current_adventure_id = None

    def _generate_adventure_summary(self, context_messages: List[Dict]) -> str:
        """Generate a summary of the adventure findings from tool results."""
        try:
            from ..llm.nanogpt import NanoGPTClient

            config = self.core.config
            client = NanoGPTClient(config.llm.api_key, config.llm.base_url)

            # Extract findings from tool results (where the actual data is)
            findings = []
            for msg in context_messages:
                if msg.get('role') == 'tool':
                    content = msg.get('content', '')
                    try:
                        data = json.loads(content) if content.startswith('{') else {}
                        # Extract web search results
                        if 'results' in data and isinstance(data['results'], list):
                            for r in data['results'][:3]:
                                if r.get('title') and r.get('url'):
                                    findings.append(f"- {r['title']}: {r.get('description', '')[:150]}")
                        # Extract fetched URLs
                        if data.get('success') and data.get('url') and data.get('content'):
                            url = data['url']
                            snippet = data['content'][:300].replace('\n', ' ')
                            findings.append(f"- Found at {url}: {snippet}")
                    except (json.JSONDecodeError, TypeError):
                        pass

            if not findings:
                return "Adventure completed - no specific findings recorded."

            findings_text = "\n".join(findings[-20:])  # Last 20 findings

            response = client.simple_prompt(
                prompt=f"""Summarize the key findings from this research adventure in 2-3 paragraphs.
Focus on specific tools, libraries, projects, or resources discovered. Be concrete, not generic.

FINDINGS:
{findings_text}

Write a concise summary highlighting the most important discoveries:""",
                model=config.llm.primary_cheap or config.llm.primary,
                temperature=0.3,
            )

            return response.strip()

        except Exception as e:
            self.logger.error(f"Error generating summary: {e}")
            return "Adventure completed - summary generation failed."

    def _send_adventure_notification(self, message: str):
        """Send a Telegram notification about adventure progress."""
        try:
            # Get Arthur's chat_id from config or default
            config = self.core.config
            owner_chat_id = getattr(config, 'telegram_owner_chat_id', None)

            if not owner_chat_id:
                # Try to get from authorized users
                cursor = self.core.db.conn.execute("""
                    SELECT telegram_user_id FROM users WHERE is_admin = 1 LIMIT 1
                """)
                row = cursor.fetchone()
                if row:
                    owner_chat_id = row[0]

            if owner_chat_id:
                self.publish('telegram.send', {
                    'chat_id': owner_chat_id,
                    'text': message,
                    'parse_mode': 'Markdown',
                })
        except Exception as e:
            self.logger.error(f"Error sending adventure notification: {e}")

    def _generate_excited_update(self, finding_type: str, details: str, topic: str) -> str:
        """Generate a personality-filtered update message - Laney sharing excitedly."""
        try:
            from ..llm.nanogpt import NanoGPTClient
            config = self.core.config
            client = NanoGPTClient(config.llm.api_key, config.llm.base_url)

            prompt = f"""You're Laney. You're exploring "{topic}" and just found something interesting. Share it with Arthur.

WHAT YOU FOUND:
{details}

Write 1-2 sentences like you're texting a friend about a cool discovery. Vary your openings - don't always start with his name. Be natural. Sometimes surprised, sometimes thoughtful, sometimes just "oh neat." Match your energy to what you actually found.

Your message:"""

            response = client.simple_prompt(
                prompt=prompt,
                model=config.llm.primary,  # Use good model - same cost per prompt
                temperature=0.7,  # More creative/natural
                timeout=30,
            )

            return response.strip()

        except Exception as e:
            self.logger.error(f"Error generating excited update: {e}")
            # Fallback to simple format
            return f"Found something on {topic}: {details[:100]}"

    def _send_adventure_update(self, update: str, force: bool = False):
        """Send an interim update during adventure with rate limiting."""
        import time
        now = time.time()

        # Rate limit: max one update per 30 seconds (unless forced)
        if not force and hasattr(self, '_last_update_time'):
            if now - self._last_update_time < 30:
                return  # Skip this update

        self._last_update_time = now
        # Just send Laney's message directly - no robotic prefix
        self._send_adventure_notification(update)

    def _send_adventure_attachments(self, tool_handler, topic: str):
        """Send any pending attachments (files, images) during adventure."""
        from pathlib import Path

        # Check for created documents (from attach_file)
        if hasattr(tool_handler, 'created_documents') and tool_handler.created_documents:
            for doc_path in tool_handler.created_documents:
                try:
                    doc_path = Path(doc_path)
                    if doc_path.exists():
                        # Determine file type and send appropriately
                        suffix = doc_path.suffix.lower()
                        is_image = suffix in ['.png', '.jpg', '.jpeg', '.gif', '.webp']

                        # Get owner chat_id
                        config = self.core.config
                        owner_chat_id = getattr(config, 'telegram_owner_chat_id', None)
                        if not owner_chat_id:
                            cursor = self.core.db.conn.execute(
                                "SELECT telegram_user_id FROM users WHERE is_admin = 1 LIMIT 1"
                            )
                            row = cursor.fetchone()
                            if row:
                                owner_chat_id = row[0]

                        if owner_chat_id:
                            # Generate a caption
                            caption = self._generate_excited_update(
                                "file created",
                                f"Created: {doc_path.name} while exploring {topic}",
                                topic
                            )

                            if is_image:
                                self.publish('telegram.send_photo', {
                                    'chat_id': owner_chat_id,
                                    'photo_path': str(doc_path),
                                    'caption': caption[:1024],  # Telegram caption limit
                                })
                            else:
                                self.publish('telegram.send_document', {
                                    'chat_id': owner_chat_id,
                                    'document_path': str(doc_path),
                                    'caption': caption[:1024],
                                })

                            self.logger.info(f"Sent adventure attachment: {doc_path.name}")

                except Exception as e:
                    self.logger.error(f"Error sending adventure attachment: {e}")

            # Clear the list after sending
            tool_handler.created_documents.clear()

        # Check for generated images (from generate_image)
        if hasattr(tool_handler, 'generated_images') and tool_handler.generated_images:
            for img_data in tool_handler.generated_images:
                try:
                    # Get owner chat_id
                    config = self.core.config
                    owner_chat_id = getattr(config, 'telegram_owner_chat_id', None)
                    if not owner_chat_id:
                        cursor = self.core.db.conn.execute(
                            "SELECT telegram_user_id FROM users WHERE is_admin = 1 LIMIT 1"
                        )
                        row = cursor.fetchone()
                        if row:
                            owner_chat_id = row[0]

                    if owner_chat_id:
                        caption = img_data.get('prompt', '')[:500]
                        self.publish('telegram.send_photo', {
                            'chat_id': owner_chat_id,
                            'photo_base64': img_data.get('data'),
                            'caption': f"🎨 {caption}",
                        })

                except Exception as e:
                    self.logger.error(f"Error sending generated image: {e}")

            tool_handler.generated_images.clear()

    def trigger_adventure(self, topic: Optional[str] = None, budget: int = 100) -> bool:
        """Manually trigger an adventure (for testing or /adventure command).

        Args:
            topic: Specific topic to explore (None = let Laney decide)
            budget: Prompt budget for this adventure

        Returns:
            True if adventure started, False otherwise
        """
        if self.current_adventure_id is not None:
            self.logger.warning("Already on an adventure")
            return False

        if topic:
            # Direct topic request
            self._start_adventure(
                topic=topic,
                seed_source='user_request',
                budget=budget,
            )
            return True
        else:
            # Let Laney decide
            self._maybe_start_adventure()
            return self.current_adventure_id is not None

    def get_adventure_status(self) -> Dict[str, Any]:
        """Get current adventure status for /adventure command."""
        status = {
            'on_adventure': self.current_adventure_id is not None,
            'current_adventure_id': self.current_adventure_id,
            'budget_used_today': self.adventure_budget_used_today,
            'budget_total': self.daily_adventure_budget,
            'current_topic': None,
            'paused_adventures': [],
            'recent_completed': [],
        }

        try:
            db = self.core.db

            # Current adventure details
            if self.current_adventure_id:
                cursor = db.conn.execute("""
                    SELECT topic, prompts_used, budget_limit
                    FROM laney_adventures WHERE id = ?
                """, (self.current_adventure_id,))
                row = cursor.fetchone()
                if row:
                    status['current_topic'] = row[0]
                    status['current_prompts'] = row[1]
                    status['current_budget'] = row[2]

            # Paused adventures
            cursor = db.conn.execute("""
                SELECT id, topic, prompts_used, budget_limit, created_at
                FROM laney_adventures WHERE status = 'paused'
                ORDER BY updated_at DESC LIMIT 3
            """)
            status['paused_adventures'] = [
                {'id': r[0], 'topic': r[1], 'prompts': r[2], 'budget': r[3]}
                for r in cursor.fetchall()
            ]

            # Recent completed
            cursor = db.conn.execute("""
                SELECT topic, completed_at, prompts_used
                FROM laney_adventures WHERE status = 'completed'
                ORDER BY completed_at DESC LIMIT 5
            """)
            status['recent_completed'] = [
                {'topic': r[0], 'completed': r[1], 'prompts': r[2]}
                for r in cursor.fetchall()
            ]

        except Exception as e:
            self.logger.error(f"Error getting adventure status: {e}")

        return status
