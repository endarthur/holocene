"""Proactive Laney Plugin - Daily digests and autonomous outreach.

This plugin:
- Sends daily digest emails to Arthur with collection updates
- Uses LLM to generate thoughtful commentary (not just data dumps)
- Surfaces forgotten items from the collection
- Spots patterns and connections
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
            "version": "1.1.0",
            "description": "Daily digests and proactive insights from Laney",
            "runs_on": ["rei"],
            "requires": []
        }

    def on_load(self):
        """Initialize the plugin."""
        self.logger.info("ProactiveLaney plugin loaded")

        # Get email config
        self.email_config = getattr(self.core.config, 'email', None)
        if not self.email_config or not self.email_config.enabled:
            self.logger.warning("Email not configured - proactive features disabled")
            self._can_run = False
            return

        self._can_run = True

        # Scheduling settings
        self.digest_hour = 8  # 8 AM local time
        self.digest_minute = 0
        self.last_digest_date = None

        # Background thread
        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None

        # Stats
        self.digests_sent = 0
        self.last_digest_sent = None

    def on_enable(self):
        """Start the proactive scheduler."""
        if not self._can_run:
            self.logger.warning("ProactiveLaney not enabled (no email config)")
            return

        self._stop_event.clear()
        self._worker_thread = threading.Thread(
            target=self._scheduler_loop,
            daemon=True,
            name="proactive-laney"
        )
        self._worker_thread.start()
        self.logger.info(f"ProactiveLaney started (digest at {self.digest_hour:02d}:{self.digest_minute:02d})")

    def on_disable(self):
        """Stop the scheduler."""
        if self._worker_thread and self._worker_thread.is_alive():
            self._stop_event.set()
            self._worker_thread.join(timeout=5)
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
