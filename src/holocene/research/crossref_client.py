"""Crossref API client for academic paper discovery."""

import requests
from typing import Optional, List, Dict
from datetime import datetime


class CrossrefClient:
    """Client for Crossref REST API - 165M academic works."""

    def __init__(self):
        """Initialize Crossref client."""
        self.base_url = "https://api.crossref.org/works"
        # Be polite - identify ourselves
        self.headers = {
            "User-Agent": "Holocene/1.0 (Personal Research Tool; mailto:research@example.com)"
        }

    def search(
        self,
        query: str,
        from_date: Optional[str] = None,
        until_date: Optional[str] = None,
        limit: int = 20,
        offset: int = 0
    ) -> Dict:
        """
        Search Crossref for academic papers.

        Args:
            query: Search query
            from_date: Start date (YYYY or YYYY-MM-DD)
            until_date: End date (YYYY or YYYY-MM-DD)
            limit: Number of results (max 1000)
            offset: Pagination offset

        Returns:
            Dictionary with search results
        """
        params = {
            "query": query,
            "rows": min(limit, 1000),  # Crossref max
            "offset": offset,
            "select": "DOI,title,author,abstract,published,container-title,URL,reference,is-referenced-by-count"
        }

        # Add date filters if specified
        filters = []
        if from_date:
            filters.append(f"from-pub-date:{from_date}")
        if until_date:
            filters.append(f"until-pub-date:{until_date}")

        if filters:
            params["filter"] = ",".join(filters)

        try:
            response = requests.get(
                self.base_url,
                params=params,
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            print(f"⚠️  Crossref API error: {e}")
            return {"status": "error", "message": str(e)}

    def get_by_doi(self, doi: str) -> Optional[Dict]:
        """
        Get full metadata for a paper by DOI.

        Args:
            doi: Paper DOI (e.g., "10.1234/example")

        Returns:
            Paper metadata or None
        """
        try:
            url = f"{self.base_url}/{doi}"
            response = requests.get(
                url,
                headers=self.headers,
                timeout=30
            )

            if response.status_code == 404:
                return None

            response.raise_for_status()
            data = response.json()
            return data.get("message")

        except requests.exceptions.RequestException as e:
            print(f"⚠️  Crossref API error: {e}")
            return None

    def parse_paper(self, item: Dict) -> Dict:
        """
        Parse Crossref item into simplified paper metadata.

        Args:
            item: Raw Crossref item

        Returns:
            Simplified paper dict
        """
        # Extract authors
        authors = []
        for author in item.get("author", []):
            given = author.get("given", "")
            family = author.get("family", "")
            if given and family:
                authors.append(f"{given} {family}")
            elif family:
                authors.append(family)

        # Extract publication date
        pub_date = None
        if "published" in item:
            date_parts = item["published"].get("date-parts", [[]])[0]
            if date_parts:
                if len(date_parts) >= 3:
                    pub_date = f"{date_parts[0]:04d}-{date_parts[1]:02d}-{date_parts[2]:02d}"
                elif len(date_parts) >= 2:
                    pub_date = f"{date_parts[0]:04d}-{date_parts[1]:02d}"
                elif len(date_parts) >= 1:
                    pub_date = f"{date_parts[0]:04d}"

        # Extract journal/container
        journal = None
        if "container-title" in item:
            container = item["container-title"]
            if isinstance(container, list) and container:
                journal = container[0]
            elif isinstance(container, str):
                journal = container

        # Extract title
        title = None
        if "title" in item:
            title_list = item["title"]
            if isinstance(title_list, list) and title_list:
                title = title_list[0]
            elif isinstance(title_list, str):
                title = title_list

        return {
            "doi": item.get("DOI"),
            "title": title,
            "authors": authors,
            "abstract": item.get("abstract"),
            "publication_date": pub_date,
            "journal": journal,
            "url": item.get("URL"),
            "cited_by_count": item.get("is-referenced-by-count", 0),
            "references": [ref.get("DOI") for ref in item.get("reference", []) if ref.get("DOI")]
        }

    def search_pre_llm(
        self,
        query: str,
        limit: int = 20,
        offset: int = 0
    ) -> List[Dict]:
        """
        Search for pre-LLM papers (before November 2022).

        Args:
            query: Search query
            limit: Number of results
            offset: Pagination offset

        Returns:
            List of parsed papers
        """
        result = self.search(
            query=query,
            from_date="1990",
            until_date="2022-11",
            limit=limit,
            offset=offset
        )

        if result.get("status") == "error":
            return []

        items = result.get("message", {}).get("items", [])
        return [self.parse_paper(item) for item in items]
