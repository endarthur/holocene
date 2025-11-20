"""Link Status Checker Plugin - Monitors link health and detects rot.

This plugin:
- Checks if links are alive (HTTP status codes)
- Fetches metadata (title, description, OpenGraph)
- Detects link rot (404s, timeouts, etc.)
- Updates link status in database
- Subscribes to links.added events for new links
- Publishes link.checked events
- Supports periodic checking of stale links
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import Dict, Optional
from urllib.parse import urlparse

from holocene.core import Plugin, Message


class LinkStatusCheckerPlugin(Plugin):
    """Automatically checks link health and detects rot."""

    def get_metadata(self):
        return {
            "name": "link_status_checker",
            "version": "1.0.0",
            "description": "Monitors link health, fetches metadata, and detects link rot",
            "runs_on": ["rei", "wmut", "both"],
            "requires": []
        }

    def on_load(self):
        """Initialize the plugin."""
        self.logger.info("LinkStatusChecker plugin loaded")

        # Stats
        self.checked_count = 0
        self.alive_count = 0
        self.dead_count = 0
        self.failed_count = 0

        # HTTP session for connection pooling
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    def on_enable(self):
        """Enable the plugin and subscribe to events."""
        self.logger.info("LinkStatusChecker plugin enabled")

        # Subscribe to link events
        self.subscribe('links.added', self._on_link_added)
        self.subscribe('link.check_requested', self._on_check_requested)
        self.subscribe('links.check_stale', self._on_check_stale)

    def _on_link_added(self, msg: Message):
        """Handle links.added event - check new links."""
        link_id = msg.data.get('link_id')
        if not link_id:
            return

        self.logger.info(f"New link added: {link_id}, checking status")

        # Get link from database
        link = self._get_link(link_id)
        if not link:
            self.logger.warning(f"Link {link_id} not found")
            return

        # Check in background
        self._check_link_async(link_id, link)

    def _on_check_requested(self, msg: Message):
        """Handle manual check requests."""
        link_id = msg.data.get('link_id')
        force = msg.data.get('force', False)

        if not link_id:
            return

        link = self._get_link(link_id)
        if not link:
            self.logger.warning(f"Link {link_id} not found")
            return

        # Check if recently checked (unless forced)
        if not force and self._was_recently_checked(link):
            self.logger.info(f"Link {link_id} was recently checked, skipping")
            return

        self.logger.info(f"Checking link {link_id} (force={force})")
        self._check_link_async(link_id, link)

    def _on_check_stale(self, msg: Message):
        """Handle periodic stale link checking."""
        max_age_days = msg.data.get('max_age_days', 7)

        self.logger.info(f"Checking for stale links (older than {max_age_days} days)")

        # Get stale links
        stale_links = self._get_stale_links(max_age_days)

        if not stale_links:
            self.logger.info("No stale links to check")
            return

        self.logger.info(f"Found {len(stale_links)} stale links to check")

        # Check each in background
        for link in stale_links:
            link_id = link.get('id')
            self._check_link_async(link_id, link)

    def _get_link(self, link_id: int) -> Optional[Dict]:
        """Get link from database."""
        try:
            cursor = self.core.db.conn.cursor()
            cursor.execute("SELECT * FROM links WHERE id = ?", (link_id,))
            row = cursor.fetchone()

            if not row:
                return None

            # Convert to dict
            return dict(row)
        except Exception as e:
            self.logger.error(f"Failed to get link {link_id}: {e}")
            return None

    def _get_stale_links(self, max_age_days: int) -> list:
        """Get links that haven't been checked recently."""
        try:
            cursor = self.core.db.conn.cursor()
            cutoff_date = (datetime.now() - timedelta(days=max_age_days)).isoformat()

            cursor.execute("""
                SELECT * FROM links
                WHERE last_checked IS NULL OR last_checked < ?
                LIMIT 100
            """, (cutoff_date,))

            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            self.logger.error(f"Failed to get stale links: {e}")
            return []

    def _was_recently_checked(self, link: Dict) -> bool:
        """Check if link was checked in last 24 hours."""
        last_checked = link.get('last_checked')
        if not last_checked:
            return False

        try:
            last_checked_dt = datetime.fromisoformat(last_checked)
            age = datetime.now() - last_checked_dt
            return age < timedelta(hours=24)
        except (ValueError, TypeError):
            return False

    def _check_link_async(self, link_id: int, link: Dict):
        """Check a link asynchronously."""
        def do_check():
            """Actually check the link (runs in background thread)."""
            try:
                result = self._check_link(link_id, link)
                return result
            except Exception as e:
                self.logger.error(f"Link check failed for {link_id}: {e}", exc_info=True)
                self.failed_count += 1
                raise

        def on_complete(result):
            """Called when check completes (runs in main thread)."""
            self.checked_count += 1

            if result['is_alive']:
                self.alive_count += 1
            else:
                self.dead_count += 1

            self.logger.info(f"Link check complete for {link_id}: {result['status_code']} (total: {self.checked_count})")

            # Note: Database update removed due to SQLite threading constraints
            # Instead, publish event with all data - consumers can handle persistence
            # TODO: Implement proper cross-thread database updates

            # Publish completion event
            self.publish('link.checked', {
                'link_id': link_id,
                'url': link.get('url'),
                'status_code': result['status_code'],
                'is_alive': result['is_alive'],
                'title': result.get('title', ''),
                'description': result.get('description', ''),
                'stats': {
                    'checked': self.checked_count,
                    'alive': self.alive_count,
                    'dead': self.dead_count,
                    'failed': self.failed_count
                }
            })

        def on_error(error):
            """Called if check fails."""
            self.logger.error(f"Background link check failed: {error}")
            self.publish('link.check_failed', {
                'link_id': link_id,
                'url': link.get('url'),
                'error': str(error)
            })

        # Run in background
        self.run_in_background(
            do_check,
            callback=on_complete,
            error_handler=on_error
        )

    def _check_link(self, link_id: int, link: Dict) -> Dict:
        """Check a link's status and fetch metadata.

        Args:
            link_id: Link ID
            link: Link dictionary

        Returns:
            Dict with status, metadata, etc.
        """
        url = link.get('url', '')

        self.logger.info(f"Checking link: {url}")

        result = {
            'link_id': link_id,
            'status_code': 0,
            'is_alive': False,
            'title': '',
            'description': '',
            'error': None
        }

        try:
            # Make request with timeout
            response = self.session.get(url, timeout=10, allow_redirects=True)
            result['status_code'] = response.status_code

            # Check if alive (2xx or 3xx status codes)
            result['is_alive'] = 200 <= response.status_code < 400

            # If successful, extract metadata
            if result['is_alive'] and response.headers.get('content-type', '').startswith('text/html'):
                metadata = self._extract_metadata(response.text, url)
                result['title'] = metadata.get('title', '')
                result['description'] = metadata.get('description', '')

        except requests.Timeout:
            result['error'] = 'timeout'
            result['is_alive'] = False
            self.logger.warning(f"Timeout checking {url}")

        except requests.ConnectionError:
            result['error'] = 'connection_error'
            result['is_alive'] = False
            self.logger.warning(f"Connection error checking {url}")

        except Exception as e:
            result['error'] = str(e)
            result['is_alive'] = False
            self.logger.error(f"Error checking {url}: {e}")

        # DON'T update database here (runs in background thread)
        # Database update happens in callback (main thread)

        return result

    def _extract_metadata(self, html: str, url: str) -> Dict:
        """Extract metadata from HTML.

        Args:
            html: HTML content
            url: URL (for logging)

        Returns:
            Dict with title, description, etc.
        """
        try:
            soup = BeautifulSoup(html, 'html.parser')

            metadata = {}

            # Try OpenGraph title first, then regular title
            og_title = soup.find('meta', property='og:title')
            if og_title and og_title.get('content'):
                metadata['title'] = og_title['content']
            else:
                title_tag = soup.find('title')
                if title_tag:
                    metadata['title'] = title_tag.string.strip() if title_tag.string else ''

            # Try OpenGraph description, then meta description
            og_desc = soup.find('meta', property='og:description')
            if og_desc and og_desc.get('content'):
                metadata['description'] = og_desc['content']
            else:
                meta_desc = soup.find('meta', attrs={'name': 'description'})
                if meta_desc and meta_desc.get('content'):
                    metadata['description'] = meta_desc['content']

            return metadata

        except Exception as e:
            self.logger.error(f"Failed to extract metadata from {url}: {e}")
            return {}

    def _update_link_status(self, link_id: int, result: Dict):
        """Update link status in database.

        Args:
            link_id: Link ID
            result: Check result dict
        """
        try:
            cursor = self.core.db.conn.cursor()
            now = datetime.now().isoformat()

            # Determine status based on result
            if result['is_alive']:
                status = 'alive'
            elif result.get('error') == 'timeout':
                status = 'timeout'
            elif result.get('error') == 'connection_error':
                status = 'connection_error'
            elif result['status_code'] == 404:
                status = 'not_found'
            elif result['status_code'] >= 500:
                status = 'server_error'
            else:
                status = 'dead'

            # Update link
            cursor.execute("""
                UPDATE links
                SET last_checked = ?,
                    status = ?,
                    status_code = ?,
                    title = COALESCE(?, title),
                    description = COALESCE(?, description)
                WHERE id = ?
            """, (
                now,
                status,
                result['status_code'],
                result.get('title') or None,
                result.get('description') or None,
                link_id
            ))

            self.core.db.conn.commit()
            self.logger.debug(f"Updated link {link_id} status: {status}")

        except Exception as e:
            self.logger.error(f"Failed to update link {link_id}: {e}")

    def on_disable(self):
        """Disable the plugin."""
        self.logger.info(
            f"LinkStatusChecker disabled - Stats: {self.checked_count} checked, "
            f"{self.alive_count} alive, {self.dead_count} dead, {self.failed_count} failed"
        )

        # Close session
        if hasattr(self, 'session'):
            self.session.close()
