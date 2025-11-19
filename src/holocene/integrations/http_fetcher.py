"""Generic HTTP fetcher with optional proxy support.

Provides a clean abstraction for making HTTP requests with:
- Optional proxy routing (Bright Data, etc.)
- HTML caching to avoid re-fetch costs
- Automatic SSL handling
- Browser-like headers
"""

import requests
import urllib3
from typing import Optional, Dict, Tuple
from pathlib import Path
from bs4 import BeautifulSoup

# Disable SSL warnings when using proxies
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class HTTPFetcher:
    """HTTP fetcher with optional proxy and caching."""

    def __init__(
        self,
        config,
        use_proxy: bool = False,
        cache_dir: Optional[Path] = None,
        cache_enabled: bool = False
    ):
        """
        Initialize HTTP fetcher.

        Args:
            config: Holocene config object
            use_proxy: Whether to use proxy for requests
            cache_dir: Directory for caching HTML (if cache_enabled)
            cache_enabled: Whether to cache fetched HTML
        """
        self.config = config
        self.use_proxy = use_proxy
        self.cache_enabled = cache_enabled
        self.cache_dir = cache_dir

        if self.cache_enabled and cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_proxy_dict(self) -> Optional[Dict[str, str]]:
        """Get proxy configuration for requests library."""
        if not self.use_proxy:
            return None

        # Bright Data proxy
        bd_user = self.config.integrations.brightdata_username
        bd_pass = self.config.integrations.brightdata_password
        bd_host = self.config.integrations.brightdata_host
        bd_port = self.config.integrations.brightdata_port

        if bd_user and bd_pass:
            proxy_url = f"http://{bd_user}:{bd_pass}@{bd_host}:{bd_port}"
            return {
                'http': proxy_url,
                'https': proxy_url
            }

        return None

    def _get_browser_headers(self) -> Dict[str, str]:
        """Get realistic browser headers."""
        return {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
        }

    def fetch(
        self,
        url: str,
        cache_key: Optional[str] = None,
        timeout: int = 30,
        custom_headers: Optional[Dict[str, str]] = None
    ) -> Tuple[str, Optional[str]]:
        """
        Fetch URL and optionally cache HTML.

        Args:
            url: URL to fetch
            cache_key: Unique key for caching (e.g., item_id)
            timeout: Request timeout in seconds
            custom_headers: Custom headers to merge with browser headers

        Returns:
            Tuple of (html_content, cached_path_relative)
            cached_path_relative is None if caching disabled

        Raises:
            requests.exceptions.RequestException: On fetch failure
        """
        # Prepare headers
        headers = self._get_browser_headers()
        if custom_headers:
            headers.update(custom_headers)

        # Get proxy if enabled
        proxies = self._get_proxy_dict()

        # Make request
        response = requests.get(
            url,
            proxies=proxies,
            timeout=timeout,
            headers=headers,
            verify=False  # Disable SSL verification for proxies
        )
        response.raise_for_status()

        html_content = response.text
        cached_path = None

        # Cache if enabled
        if self.cache_enabled and self.cache_dir and cache_key:
            html_file = self.cache_dir / f"{cache_key}.html"
            html_file.write_text(html_content, encoding='utf-8')
            # Return path relative to data_dir for portability
            try:
                cached_path = str(html_file.relative_to(self.config.data_dir))
            except ValueError:
                # If not relative to data_dir, use absolute path
                cached_path = str(html_file)

        return html_content, cached_path

    def fetch_and_parse(
        self,
        url: str,
        cache_key: Optional[str] = None,
        timeout: int = 30
    ) -> Tuple[BeautifulSoup, Optional[str]]:
        """
        Fetch URL and return parsed BeautifulSoup object.

        Args:
            url: URL to fetch
            cache_key: Unique key for caching
            timeout: Request timeout in seconds

        Returns:
            Tuple of (BeautifulSoup object, cached_path_relative)
        """
        html_content, cached_path = self.fetch(url, cache_key, timeout)
        soup = BeautifulSoup(html_content, 'html.parser')
        return soup, cached_path

    @classmethod
    def from_config(
        cls,
        config,
        use_proxy: bool = False,
        integration_name: Optional[str] = None
    ) -> 'HTTPFetcher':
        """
        Create fetcher from config with automatic cache setup.

        Args:
            config: Holocene config
            use_proxy: Whether to use proxy
            integration_name: Name for cache subdirectory (e.g., 'mercadolivre')

        Returns:
            Configured HTTPFetcher instance
        """
        cache_enabled = False
        cache_dir = None

        # Check if specific integration has caching enabled
        if integration_name == 'mercadolivre':
            cache_enabled = config.mercadolivre.cache_html
            if cache_enabled:
                cache_dir = config.data_dir / "cache" / "mercadolivre" / "html"

        return cls(
            config=config,
            use_proxy=use_proxy,
            cache_dir=cache_dir,
            cache_enabled=cache_enabled
        )
