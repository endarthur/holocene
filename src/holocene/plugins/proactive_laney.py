"""Proactive Laney Plugin - Daily digests and autonomous outreach.

This plugin:
- Sends daily digest emails to Arthur with collection updates
- Tracks interesting patterns and connections
- Provides proactive insights without being asked
- Only emails Arthur by default (endarthur@gmail.com)
"""

import json
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
            "version": "1.0.0",
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

            if not digest['has_content']:
                self.logger.info("No content for digest - skipping")
                return

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
            'insights': []
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

            # Recent papers (last 24h) - note: papers uses added_at, not created_at
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

            # Check if there's any content worth sending
            digest['has_content'] = (
                len(digest['recent_books']) > 0 or
                len(digest['recent_papers']) > 0 or
                len(digest['recent_links']) > 0 or
                len(digest['pending_tasks']) > 0 or
                len(digest['completed_tasks']) > 0
            )

            # Add some insights if we have data
            if digest['has_content']:
                insights = self._generate_insights(digest)
                digest['insights'] = insights

        except Exception as e:
            self.logger.error(f"Error generating digest: {e}", exc_info=True)

        return digest

    def _generate_insights(self, digest: Dict[str, Any]) -> List[str]:
        """Generate simple insights from the digest data."""
        insights = []

        # Link sources breakdown
        sources = {}
        for link in digest['recent_links']:
            source = link.get('source', 'unknown')
            sources[source] = sources.get(source, 0) + 1

        if sources:
            top_source = max(sources.items(), key=lambda x: x[1])
            if top_source[1] > 1:
                insights.append(f"Most active link source today: {top_source[0]} ({top_source[1]} links)")

        # Task progress
        pending = len(digest['pending_tasks'])
        completed = len(digest['completed_tasks'])
        if completed > 0:
            insights.append(f"Completed {completed} task(s) in the last 24 hours")
        if pending > 5:
            insights.append(f"You have {pending} pending tasks in the queue")

        return insights

    def _format_digest_email(self, digest: Dict[str, Any]) -> str:
        """Format the digest as a nice email body."""
        lines = []
        lines.append("Good morning, Arthur!\n")
        lines.append("Here's your daily collection update:\n")

        # Stats summary
        stats = digest['stats']
        lines.append(f"**Collection:** {stats['books']} books, {stats['papers']} papers, "
                    f"{stats['links']} links, {stats['favorites']} ML favorites\n")

        # Recent additions
        if digest['recent_books']:
            lines.append("\n## New Books")
            for book in digest['recent_books']:
                author = book['author'] or 'Unknown'
                lines.append(f"- **{book['title']}** by {author}")

        if digest['recent_papers']:
            lines.append("\n## New Papers")
            for paper in digest['recent_papers']:
                authors = paper['authors'] or 'Unknown'
                if len(authors) > 50:
                    authors = authors[:47] + "..."
                lines.append(f"- **{paper['title']}** ({authors})")

        if digest['recent_links']:
            lines.append("\n## New Links")
            for link in digest['recent_links'][:10]:  # Limit to 10
                title = link['title'] or link['url'][:50]
                source = link['source'] or 'unknown'
                lines.append(f"- [{title}]({link['url']}) (via {source})")

        # Tasks
        if digest['completed_tasks']:
            lines.append("\n## Completed Tasks")
            for task in digest['completed_tasks']:
                lines.append(f"- {task['title']} ({task['type']})")

        if digest['pending_tasks']:
            lines.append("\n## Pending Tasks")
            for task in digest['pending_tasks'][:5]:
                priority = "!" * (6 - task['priority']) if task['priority'] <= 5 else ""
                lines.append(f"- {priority} {task['title']} ({task['type']})")

        # Insights
        if digest['insights']:
            lines.append("\n## Insights")
            for insight in digest['insights']:
                lines.append(f"- {insight}")

        lines.append("\n---")
        lines.append("*Laney - your pattern-recognition collaborator*")
        lines.append("*laney@gentropic.org*")

        return "\n".join(lines)

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
        html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
        html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)

        # Bold
        html = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', html)

        # Links
        html = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', html)

        # List items
        html = re.sub(r'^- (.+)$', r'<li>\1</li>', html, flags=re.MULTILINE)

        # Line breaks
        html = html.replace('\n', '<br>\n')

        return f"<html><body style='font-family: sans-serif;'>{html}</body></html>"

    def send_immediate_digest(self) -> bool:
        """Send digest immediately (for testing or manual trigger)."""
        try:
            self._send_daily_digest()
            return True
        except Exception as e:
            self.logger.error(f"Immediate digest failed: {e}")
            return False
