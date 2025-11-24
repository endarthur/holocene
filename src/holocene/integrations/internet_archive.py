"""Internet Archive integration for archiving URLs."""

import requests
from typing import Optional, Dict, Any
from datetime import datetime

from holocene.core.api_client import BaseAPIClient


class InternetArchiveClient(BaseAPIClient):
    """Client for Internet Archive Wayback Machine API."""

    def __init__(
        self,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        rate_limit: float = 0.5,  # 0.5 req/s = 2 seconds between requests
        use_global_limiter: bool = True,
    ):
        """
        Initialize Internet Archive client.

        Args:
            access_key: IA S3 access key (optional)
            secret_key: IA S3 secret key (optional)
            rate_limit: Requests per second (default 0.5 = 2 seconds between requests)
            use_global_limiter: Whether to use global rate limiter
        """
        # Initialize base client with IA base URL and rate limiting
        super().__init__(
            base_url="https://archive.org",
            rate_limit=rate_limit,
            use_global_limiter=use_global_limiter,
        )

        # Configure rate limits per IA's API documentation:
        # - Availability API (archive.org): Can be faster for read-only checks
        # - Save API (web.archive.org): Max 12 captures/minute for authenticated users
        #   = 0.2 req/s = 5 seconds between saves
        if self.rate_limiter:
            self.rate_limiter.domain_rates["archive.org"] = rate_limit  # Availability checks
            self.rate_limiter.domain_rates["web.archive.org"] = 0.2  # Save API: 12/min limit

        self.access_key = access_key
        self.secret_key = secret_key

    def check_availability(self, url: str) -> Dict[str, Any]:
        """
        Check if a URL is archived in the Wayback Machine.

        Args:
            url: URL to check

        Returns:
            Dict with 'available' (bool), 'url' (str), and optional 'timestamp' and 'snapshot_url'
        """
        # Normalize URL for IA's availability API - strip trailing slash from domain-only URLs
        # IA treats "example.com/" and "example.com" as different, but we want to check both
        from urllib.parse import urlparse
        parsed = urlparse(url)
        check_url = url
        if parsed.path in ('/', '') and not parsed.query and not parsed.fragment:
            # Domain-only URL with trailing slash - remove it
            check_url = url.rstrip('/')

        api_url = f"/wayback/available?url={check_url}"

        try:
            import logging
            logger = logging.getLogger(__name__)

            response = self.get(api_url, timeout=10)
            response.raise_for_status()
            data = response.json()

            logger.warning(f"[IA] Availability check response: {data}")

            if "archived_snapshots" in data and "closest" in data["archived_snapshots"]:
                snapshot = data["archived_snapshots"]["closest"]
                timestamp = snapshot.get("timestamp")  # Format: YYYYMMDDhhmmss
                result = {
                    "available": snapshot.get("available", False),
                    "url": url,
                    "timestamp": timestamp,
                    "archive_date": timestamp,  # Keep IA timestamp format for trust tier calc
                    "snapshot_url": snapshot.get("url"),
                }
                logger.warning(f"[IA] Availability: {result['available']}, snapshot: {result.get('snapshot_url', 'N/A')[:80]}")
                return result

            logger.warning(f"[IA] No archived snapshots found for {url}")
            return {
                "available": False,
                "url": url,
            }

        except Exception as e:
            return {
                "available": False,
                "url": url,
                "error": str(e),
            }

    def save_url(self, url: str, force: bool = False) -> Dict[str, Any]:
        """
        Submit a URL to be archived.

        Args:
            url: URL to archive
            force: Force re-archiving even if already archived

        Returns:
            Dict with result information
        """
        # Check if already archived (unless forcing)
        if not force:
            availability = self.check_availability(url)
            if availability.get("available"):
                return {
                    "status": "already_archived",
                    "url": url,
                    "snapshot_url": availability.get("snapshot_url"),
                    "archive_date": availability.get("archive_date"),
                    "message": "URL already archived, skipping",
                }

        # Submit for archiving - use full URL since this is on web.archive.org
        save_endpoint = f"https://web.archive.org/save/{url}"

        try:
            # Add S3 authentication if available
            headers = {}
            if self.access_key and self.secret_key:
                headers["Authorization"] = f"LOW {self.access_key}:{self.secret_key}"

            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"[IA] Starting save_url for: {url}")
            logger.warning(f"[IA] Save endpoint: {save_endpoint}")
            logger.warning(f"[IA] Headers: {bool(headers)}")

            import time
            start_time = time.time()
            logger.warning(f"[IA] About to call POST to save endpoint at {start_time}")

            # Use POST per IA's Save Page Now 2 API documentation
            # Don't follow redirects - IA sends 302 to snapshot, we just need the Location header
            import requests as direct_requests
            response = direct_requests.post(save_endpoint, headers=headers, timeout=90, allow_redirects=False)

            elapsed = time.time() - start_time
            logger.warning(f"[IA] POST request completed after {elapsed:.2f}s")
            logger.warning(f"[IA] Response status: {response.status_code}")

            # IA returns various status codes
            if response.status_code in [200, 301, 302]:
                # Try to extract snapshot URL from headers or response
                # With allow_redirects=False, the snapshot URL is in Location header (302 redirect)
                snapshot_url = response.headers.get("Location") or response.headers.get("Content-Location")
                timestamp = None

                if snapshot_url:
                    # Extract timestamp from snapshot URL
                    # Format: https://web.archive.org/web/YYYYMMDDhhmmss/url
                    import re
                    match = re.search(r'/web/(\d{14})/', snapshot_url)
                    if match:
                        timestamp = match.group(1)

                if not snapshot_url or not timestamp:
                    # Fallback: construct snapshot URL with current timestamp
                    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                    snapshot_url = f"https://web.archive.org/web/{timestamp}/{url}"

                return {
                    "status": "archived",
                    "url": url,
                    "snapshot_url": snapshot_url,
                    "archive_date": timestamp,
                    "message": "Successfully submitted for archiving",
                }
            else:
                return {
                    "status": "error",
                    "url": url,
                    "status_code": response.status_code,
                    "message": f"Archive request returned status {response.status_code}",
                }

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"[IA] Exception after {elapsed:.2f}s: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"[IA] Traceback:\n{traceback.format_exc()}")

            return {
                "status": "error",
                "url": url,
                "error": str(e),
                "message": f"Failed to archive: {e}",
            }

    def archive_urls_batch(self, urls: list[str], check_first: bool = True) -> list[Dict[str, Any]]:
        """
        Archive multiple URLs with rate limiting.

        Args:
            urls: List of URLs to archive
            check_first: Check if already archived before submitting

        Returns:
            List of result dicts
        """
        results = []

        for url in urls:
            result = self.save_url(url, force=not check_first)
            results.append(result)

        return results
