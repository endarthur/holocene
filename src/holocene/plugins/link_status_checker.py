"""Link Status Checker Plugin - Monitors link health and detects rot.

This plugin:
- Checks links in batches to avoid overwhelming servers
- Detects link rot (404s, timeouts, etc.)
- Updates link status in database
- Reports overall link health to Uptime Kuma (if configured)
- Runs on a schedule (default: every hour, 50 links per batch)
"""

import time
import sqlite3
import threading
import requests
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from urllib.parse import urlparse

from holocene.core import Plugin, Message


class LinkStatusCheckerPlugin(Plugin):
    """Monitors link health and detects link rot."""

    # Configuration
    BATCH_SIZE = 50  # Links per batch
    CHECK_INTERVAL_SECONDS = 3600  # 1 hour between batch checks
    DELAY_BETWEEN_CHECKS = 1.5  # Seconds between individual link checks
    REQUEST_TIMEOUT = 15  # Seconds
    MAX_LINK_AGE_DAYS = 21  # Re-check links older than this

    def get_metadata(self):
        return {
            "name": "link_status_checker",
            "version": "2.0.0",
            "description": "Monitors link health with batch processing and Uptime Kuma integration",
            "runs_on": ["rei"],
            "requires": []
        }

    def on_load(self):
        """Initialize the plugin."""
        self.logger.info("LinkStatusChecker plugin loaded")

        # Stats for current session
        self.session_stats = {
            "checked": 0,
            "alive": 0,
            "dead": 0,
            "errors": 0,
            "last_batch_time": None
        }

        # Background thread for scheduled checks
        self._check_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # HTTP session with connection pooling
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; HoloceneBot/1.0; +https://github.com/endarthur/holocene)'
        })

    def on_enable(self):
        """Enable the plugin and start scheduled checks."""
        self.logger.info("LinkStatusChecker plugin enabled")

        # Subscribe to events
        self.subscribe('links.check_batch', self._on_check_batch)
        self.subscribe('link.check_requested', self._on_check_requested)

        # Start background checker
        self._start_scheduled_checker()

    def on_disable(self):
        """Disable the plugin and stop background thread."""
        self._stop_scheduled_checker()

        self.logger.info(
            f"LinkStatusChecker disabled - Session stats: "
            f"{self.session_stats['checked']} checked, "
            f"{self.session_stats['alive']} alive, "
            f"{self.session_stats['dead']} dead, "
            f"{self.session_stats['errors']} errors"
        )

        if hasattr(self, 'session'):
            self.session.close()

    def _start_scheduled_checker(self):
        """Start the background scheduled checker thread."""
        self._stop_event.clear()
        self._check_thread = threading.Thread(
            target=self._scheduled_checker_worker,
            daemon=True,
            name="link_checker"
        )
        self._check_thread.start()
        self.logger.info("Scheduled link checker started")

    def _stop_scheduled_checker(self):
        """Stop the background scheduled checker thread."""
        if self._check_thread and self._check_thread.is_alive():
            self.logger.info("Stopping scheduled link checker...")
            self._stop_event.set()
            self._check_thread.join(timeout=5)
            self.logger.info("Scheduled link checker stopped")

    def _scheduled_checker_worker(self):
        """Background worker that runs batch checks on schedule."""
        self.logger.info(f"Link checker worker started (interval: {self.CHECK_INTERVAL_SECONDS}s)")

        # Initial delay to let daemon fully start
        if self._stop_event.wait(30):
            return

        while not self._stop_event.is_set():
            try:
                self._run_batch_check()
            except Exception as e:
                self.logger.error(f"Batch check failed: {e}", exc_info=True)

            # Wait for next check interval
            if self._stop_event.wait(self.CHECK_INTERVAL_SECONDS):
                break

        self.logger.info("Link checker worker stopped")

    def _on_check_batch(self, msg: Message):
        """Handle manual batch check request."""
        batch_size = msg.data.get('batch_size', self.BATCH_SIZE)
        self.logger.info(f"Manual batch check requested (size: {batch_size})")
        self._run_batch_check(batch_size=batch_size)

    def _on_check_requested(self, msg: Message):
        """Handle single link check request."""
        link_id = msg.data.get('link_id')
        if not link_id:
            return

        link = self._get_link(link_id)
        if not link:
            self.logger.warning(f"Link {link_id} not found")
            return

        self.logger.info(f"Checking single link: {link_id}")
        result = self._check_link(link)
        self._update_link_status(link_id, result)

    def _run_batch_check(self, batch_size: Optional[int] = None):
        """Run a batch check of stale links."""
        batch_size = batch_size or self.BATCH_SIZE

        # Get links to check
        links = self._get_links_to_check(batch_size)

        if not links:
            self.logger.info("No links to check")
            self._report_health_to_uptime_kuma()
            return

        self.logger.info(f"Starting batch check of {len(links)} links")
        self.session_stats['last_batch_time'] = datetime.now().isoformat()

        batch_stats = {"checked": 0, "alive": 0, "dead": 0, "errors": 0}

        for link in links:
            if self._stop_event.is_set():
                self.logger.info("Batch check interrupted by stop event")
                break

            link_id = link['id']
            url = link['url']

            try:
                result = self._check_link(link)
                self._update_link_status(link_id, result)

                batch_stats['checked'] += 1
                self.session_stats['checked'] += 1

                if result['is_alive']:
                    batch_stats['alive'] += 1
                    self.session_stats['alive'] += 1
                else:
                    batch_stats['dead'] += 1
                    self.session_stats['dead'] += 1

            except Exception as e:
                self.logger.error(f"Error checking {url}: {e}")
                batch_stats['errors'] += 1
                self.session_stats['errors'] += 1

            # Rate limiting - wait between checks
            time.sleep(self.DELAY_BETWEEN_CHECKS)

        self.logger.info(
            f"Batch check complete: {batch_stats['checked']} checked, "
            f"{batch_stats['alive']} alive, {batch_stats['dead']} dead, "
            f"{batch_stats['errors']} errors"
        )

        # Publish batch complete event
        self.publish('links.batch_checked', {
            'stats': batch_stats,
            'session_stats': self.session_stats
        })

        # Report health to Uptime Kuma
        self._report_health_to_uptime_kuma()

    def _get_links_to_check(self, limit: int) -> List[Dict]:
        """Get links that need checking, prioritized by age and importance."""
        try:
            cursor = self.core.db.conn.cursor()
            cutoff_date = (datetime.now() - timedelta(days=self.MAX_LINK_AGE_DAYS)).isoformat()

            # Prioritize:
            # 1. Never checked links
            # 2. Links with trust_tier 'pre-llm' (most valuable)
            # 3. Oldest checked links
            cursor.execute("""
                SELECT * FROM links
                WHERE last_checked IS NULL
                   OR last_checked < ?
                ORDER BY
                    CASE WHEN last_checked IS NULL THEN 0 ELSE 1 END,
                    CASE WHEN trust_tier = 'pre-llm' THEN 0
                         WHEN trust_tier = 'early-llm' THEN 1
                         ELSE 2 END,
                    last_checked ASC
                LIMIT ?
            """, (cutoff_date, limit))

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

        except Exception as e:
            self.logger.error(f"Failed to get links to check: {e}")
            return []

    def _get_link(self, link_id: int) -> Optional[Dict]:
        """Get a single link by ID."""
        try:
            cursor = self.core.db.conn.cursor()
            cursor.execute("SELECT * FROM links WHERE id = ?", (link_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        except Exception as e:
            self.logger.error(f"Failed to get link {link_id}: {e}")
            return None

    def _check_link(self, link: Dict) -> Dict:
        """Check a link's status.

        Uses HEAD request first (faster), falls back to GET if needed.
        """
        url = link.get('url', '')

        result = {
            'status_code': 0,
            'is_alive': False,
            'error': None,
            'response_time_ms': 0
        }

        start_time = time.time()

        try:
            # Try HEAD first (faster, less bandwidth)
            response = self.session.head(
                url,
                timeout=self.REQUEST_TIMEOUT,
                allow_redirects=True
            )

            # Some servers don't support HEAD, fall back to GET
            if response.status_code == 405:
                response = self.session.get(
                    url,
                    timeout=self.REQUEST_TIMEOUT,
                    allow_redirects=True,
                    stream=True  # Don't download full body
                )
                response.close()

            result['status_code'] = response.status_code
            result['is_alive'] = 200 <= response.status_code < 400
            result['response_time_ms'] = int((time.time() - start_time) * 1000)

        except requests.Timeout:
            result['error'] = 'timeout'
            result['is_alive'] = False
            self.logger.debug(f"Timeout: {url}")

        except requests.ConnectionError as e:
            result['error'] = 'connection_error'
            result['is_alive'] = False
            # Check for DNS errors specifically
            if 'Name or service not known' in str(e) or 'getaddrinfo failed' in str(e):
                result['error'] = 'dns_error'
            self.logger.debug(f"Connection error: {url}")

        except requests.TooManyRedirects:
            result['error'] = 'too_many_redirects'
            result['is_alive'] = False
            self.logger.debug(f"Too many redirects: {url}")

        except Exception as e:
            result['error'] = str(e)[:100]
            result['is_alive'] = False
            self.logger.debug(f"Error checking {url}: {e}")

        return result

    def _update_link_status(self, link_id: int, result: Dict):
        """Update link status in database."""
        try:
            cursor = self.core.db.conn.cursor()
            now = datetime.now().isoformat()

            # Determine status string
            if result['is_alive']:
                status = 'alive'
            elif result.get('error') == 'timeout':
                status = 'timeout'
            elif result.get('error') == 'connection_error':
                status = 'connection_error'
            elif result.get('error') == 'dns_error':
                status = 'dns_error'
            elif result['status_code'] == 404:
                status = 'not_found'
            elif result['status_code'] == 403:
                status = 'forbidden'
            elif result['status_code'] >= 500:
                status = 'server_error'
            else:
                status = 'dead'

            cursor.execute("""
                UPDATE links
                SET last_checked = ?,
                    status = ?,
                    status_code = ?
                WHERE id = ?
            """, (now, status, result['status_code'], link_id))

            self.core.db.conn.commit()

        except Exception as e:
            self.logger.error(f"Failed to update link {link_id}: {e}")

    def _report_health_to_uptime_kuma(self):
        """Report overall link health to Uptime Kuma push monitor."""
        try:
            # Get health stats from database
            stats = self._get_link_health_stats()

            if not stats:
                return

            # Check if Uptime Kuma link health monitor is configured
            config = self.core.config
            if not config.integrations.uptime_kuma_enabled:
                return

            # Look for a link health push token in config
            link_health_token = getattr(config.integrations, 'uptime_kuma_link_health_token', None)
            if not link_health_token:
                return

            # Calculate health percentage
            total = stats['total']
            alive = stats['alive']
            health_pct = (alive / total * 100) if total > 0 else 100

            # Determine status (up if > 90% healthy)
            status = "up" if health_pct >= 90 else "down"
            msg = f"{alive}/{total} alive ({health_pct:.1f}%)"

            # Ping Uptime Kuma
            push_url = (
                f"{config.integrations.uptime_kuma_url}/api/push/"
                f"{link_health_token}?status={status}&msg={msg}"
            )
            response = requests.get(push_url, timeout=10)

            if response.json().get('ok'):
                self.logger.debug(f"Uptime Kuma link health ping: {msg}")
            else:
                self.logger.warning(f"Uptime Kuma ping failed: {response.text}")

        except Exception as e:
            self.logger.error(f"Failed to report to Uptime Kuma: {e}")

    def _get_link_health_stats(self) -> Optional[Dict]:
        """Get overall link health statistics."""
        try:
            cursor = self.core.db.conn.cursor()

            # Total links
            cursor.execute("SELECT COUNT(*) FROM links")
            total = cursor.fetchone()[0]

            # Checked links
            cursor.execute("SELECT COUNT(*) FROM links WHERE last_checked IS NOT NULL")
            checked = cursor.fetchone()[0]

            # Alive links
            cursor.execute("SELECT COUNT(*) FROM links WHERE status = 'alive'")
            alive = cursor.fetchone()[0]

            # Dead links (various statuses)
            cursor.execute("""
                SELECT COUNT(*) FROM links
                WHERE status IN ('dead', 'not_found', 'connection_error', 'dns_error', 'timeout')
            """)
            dead = cursor.fetchone()[0]

            return {
                'total': total,
                'checked': checked,
                'alive': alive,
                'dead': dead,
                'unchecked': total - checked
            }

        except Exception as e:
            self.logger.error(f"Failed to get health stats: {e}")
            return None

    def get_health_stats(self) -> Dict:
        """Public method to get health stats (for CLI)."""
        return self._get_link_health_stats() or {}
