"""Brave Search API integration.

Free tier: 2,000 queries/month (~67/day)
Docs: https://api.search.brave.com/app/documentation
"""

import requests
from typing import Optional, List, Dict, Any


class BraveSearchClient:
    """Client for Brave Search API."""

    BASE_URL = "https://api.search.brave.com/res/v1"

    def __init__(self, api_key: str):
        """
        Initialize Brave Search client.

        Args:
            api_key: Brave Search API key (from https://brave.com/search/api/)
        """
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            "X-Subscription-Token": api_key,
            "Accept": "application/json",
        })

    def web_search(
        self,
        query: str,
        count: int = 10,
        country: str = "us",
        search_lang: str = "en",
        freshness: Optional[str] = None,
        safesearch: str = "moderate",
    ) -> Dict[str, Any]:
        """
        Search the web using Brave Search.

        Args:
            query: Search query
            count: Number of results (max 20)
            country: Country code for results
            search_lang: Language for results
            freshness: Filter by freshness (pd=past day, pw=past week, pm=past month, py=past year)
            safesearch: Safe search level (off, moderate, strict)

        Returns:
            Search results dict with 'web', 'query', etc.
        """
        params = {
            "q": query,
            "count": min(count, 20),  # Max 20 per request
            "country": country,
            "search_lang": search_lang,
            "safesearch": safesearch,
        }

        if freshness:
            params["freshness"] = freshness

        response = self.session.get(
            f"{self.BASE_URL}/web/search",
            params=params,
            timeout=30,
        )
        response.raise_for_status()

        return response.json()

    def search_simple(
        self,
        query: str,
        count: int = 5,
        freshness: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """
        Simple search returning just titles, URLs, and descriptions.

        Args:
            query: Search query
            count: Number of results
            freshness: Filter by freshness

        Returns:
            List of dicts with 'title', 'url', 'description'
        """
        results = self.web_search(query, count=count, freshness=freshness)

        simplified = []
        web_results = results.get("web", {}).get("results", [])

        for result in web_results[:count]:
            simplified.append({
                "title": result.get("title", ""),
                "url": result.get("url", ""),
                "description": result.get("description", ""),
            })

        return simplified

    def news_search(
        self,
        query: str,
        count: int = 10,
        freshness: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """
        Search news articles.

        Args:
            query: Search query
            count: Number of results
            freshness: Filter by freshness

        Returns:
            List of news article dicts
        """
        params = {
            "q": query,
            "count": min(count, 20),
        }

        if freshness:
            params["freshness"] = freshness

        response = self.session.get(
            f"{self.BASE_URL}/news/search",
            params=params,
            timeout=30,
        )
        response.raise_for_status()

        results = response.json()
        news_results = results.get("results", [])

        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "description": r.get("description", ""),
                "age": r.get("age", ""),
                "source": r.get("meta_url", {}).get("hostname", ""),
            }
            for r in news_results[:count]
        ]
