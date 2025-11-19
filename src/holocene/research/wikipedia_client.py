"""Wikipedia API client for fetching article summaries."""

import json
import requests
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime


class WikipediaClient:
    """Client for Wikipedia REST API."""

    def __init__(self, cache_dir: Optional[Path] = None):
        """
        Initialize Wikipedia client.

        Args:
            cache_dir: Directory to cache Wikipedia responses
        """
        self.base_url = "https://en.wikipedia.org/api/rest_v1"
        self.cache_dir = cache_dir

        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_summary(self, title: str, use_cache: bool = True) -> Optional[Dict]:
        """
        Get summary for a Wikipedia article.

        Args:
            title: Article title (e.g., "Python_(programming_language)")
            use_cache: Whether to use cached results

        Returns:
            Dictionary with article summary data, or None if not found
        """
        # Check cache first
        if use_cache and self.cache_dir:
            cached = self._get_cached(title)
            if cached:
                return cached

        # Fetch from API
        try:
            # Wikipedia REST API expects titles with underscores
            title_normalized = title.replace(" ", "_")
            url = f"{self.base_url}/page/summary/{title_normalized}"

            response = requests.get(
                url,
                headers={
                    "User-Agent": "Holocene/1.0 (Personal Research Tool)"
                },
                timeout=10
            )

            if response.status_code == 404:
                return None

            response.raise_for_status()
            data = response.json()

            # Extract relevant fields
            result = {
                "title": data.get("title"),
                "extract": data.get("extract"),  # Plain text summary
                "extract_html": data.get("extract_html"),  # HTML summary
                "description": data.get("description"),  # Short description
                "url": data.get("content_urls", {}).get("desktop", {}).get("page"),
                "timestamp": data.get("timestamp"),
                "fetched_at": datetime.now().isoformat()
            }

            # Cache the result
            if self.cache_dir:
                self._cache_result(title, result)

            return result

        except requests.exceptions.RequestException as e:
            print(f"⚠️  Wikipedia API error: {e}")
            return None

    def search(self, query: str, limit: int = 5) -> list[Dict]:
        """
        Search Wikipedia for articles matching query.

        Args:
            query: Search query
            limit: Maximum number of results

        Returns:
            List of article summaries
        """
        try:
            # Use MediaWiki search API (different endpoint)
            url = "https://en.wikipedia.org/w/api.php"
            params = {
                "action": "opensearch",
                "search": query,
                "limit": limit,
                "format": "json"
            }

            response = requests.get(
                url,
                params=params,
                headers={
                    "User-Agent": "Holocene/1.0 (Personal Research Tool)"
                },
                timeout=10
            )
            response.raise_for_status()

            # OpenSearch returns: [query, [titles], [descriptions], [urls]]
            data = response.json()

            if len(data) < 4:
                return []

            titles = data[1]
            descriptions = data[2]
            urls = data[3]

            results = []
            for i in range(len(titles)):
                results.append({
                    "title": titles[i],
                    "description": descriptions[i] if i < len(descriptions) else "",
                    "url": urls[i] if i < len(urls) else ""
                })

            return results

        except requests.exceptions.RequestException as e:
            print(f"⚠️  Wikipedia search error: {e}")
            return []

    def _get_cache_path(self, title: str) -> Path:
        """Get cache file path for a title."""
        # Sanitize title for filesystem
        safe_title = "".join(c if c.isalnum() or c in "._- " else "_" for c in title)
        return self.cache_dir / f"{safe_title}.json"

    def _get_cached(self, title: str) -> Optional[Dict]:
        """Get cached Wikipedia data."""
        cache_path = self._get_cache_path(title)

        if not cache_path.exists():
            return None

        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

    def _cache_result(self, title: str, data: Dict):
        """Cache Wikipedia result."""
        cache_path = self._get_cache_path(title)

        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except IOError as e:
            print(f"⚠️  Failed to cache Wikipedia result: {e}")
