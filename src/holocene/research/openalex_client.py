"""OpenAlex API client for academic paper discovery."""

import requests
from typing import Optional, List, Dict
from datetime import datetime


class OpenAlexClient:
    """Client for OpenAlex REST API - 250M+ academic works."""

    def __init__(self, email: Optional[str] = None):
        """
        Initialize OpenAlex client.

        Args:
            email: Optional email for polite pool (10 req/sec vs 1 req/sec)
        """
        self.base_url = "https://api.openalex.org/works"
        self.headers = {
            "User-Agent": "Holocene/1.0 (Personal Research Tool)"
        }
        if email:
            self.headers["User-Agent"] += f"; mailto:{email}"

    def search(
        self,
        query: str,
        from_year: Optional[int] = None,
        to_year: Optional[int] = None,
        limit: int = 20,
        offset: int = 0
    ) -> Dict:
        """
        Search OpenAlex for academic papers.

        Args:
            query: Search query (title, abstract, fulltext)
            from_year: Start year filter
            to_year: End year filter
            limit: Number of results (max 200 per page)
            offset: Pagination offset

        Returns:
            Dictionary with search results
        """
        params = {
            "search": query,
            "per-page": min(limit, 200),
            "page": (offset // limit) + 1 if limit > 0 else 1
        }

        # Add year filters
        filters = []
        if from_year:
            filters.append(f"publication_year:>{from_year-1}")
        if to_year:
            filters.append(f"publication_year:<{to_year+1}")

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
            print(f"⚠️  OpenAlex API error: {e}")
            return {"meta": {"count": 0}, "results": []}

    def search_by_title_author(
        self,
        title: str,
        author: Optional[str] = None,
        year: Optional[int] = None
    ) -> List[Dict]:
        """
        Search for paper by title and optionally author/year.

        Args:
            title: Paper title
            author: First author name (optional)
            year: Publication year (optional)

        Returns:
            List of matching papers
        """
        # Build search query
        query_parts = [title]
        if author:
            query_parts.append(author)

        query = " ".join(query_parts)

        # Use year as filter if provided
        params = {
            "search": query,
            "per-page": 10
        }

        if year:
            params["filter"] = f"publication_year:{year}"

        try:
            response = requests.get(
                self.base_url,
                params=params,
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            return data.get("results", [])

        except requests.exceptions.RequestException as e:
            print(f"⚠️  OpenAlex API error: {e}")
            return []

    def get_by_doi(self, doi: str) -> Optional[Dict]:
        """
        Get full metadata for a paper by DOI.

        Args:
            doi: Paper DOI (e.g., "10.1234/example")

        Returns:
            Paper metadata or None
        """
        try:
            # OpenAlex allows filtering by external IDs
            params = {
                "filter": f"doi:{doi}"
            }

            response = requests.get(
                self.base_url,
                params=params,
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

            results = data.get("results", [])
            if results:
                return results[0]
            return None

        except requests.exceptions.RequestException as e:
            print(f"⚠️  OpenAlex API error: {e}")
            return None

    def get_by_openalex_id(self, openalex_id: str) -> Optional[Dict]:
        """
        Get full metadata by OpenAlex ID.

        Args:
            openalex_id: OpenAlex ID (e.g., "W2741809807" or full URL)

        Returns:
            Paper metadata or None
        """
        try:
            # Handle both short IDs and full URLs
            if openalex_id.startswith("http"):
                url = openalex_id
            elif openalex_id.startswith("W"):
                url = f"https://api.openalex.org/works/{openalex_id}"
            else:
                url = f"https://api.openalex.org/works/W{openalex_id}"

            response = requests.get(
                url,
                headers=self.headers,
                timeout=30
            )

            if response.status_code == 404:
                return None

            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            print(f"⚠️  OpenAlex API error: {e}")
            return None

    def parse_paper(self, work: Dict) -> Dict:
        """
        Parse OpenAlex work data into standardized format.

        Args:
            work: OpenAlex work object

        Returns:
            Standardized paper dictionary
        """
        # Extract DOI (remove https://doi.org/ prefix if present)
        doi = work.get("doi", "")
        if doi:
            doi = doi.replace("https://doi.org/", "")

        # Extract authors
        authors = []
        for authorship in work.get("authorships", []):
            author = authorship.get("author", {})
            display_name = author.get("display_name")
            if display_name:
                authors.append(display_name)

        # Extract publication date
        pub_date = work.get("publication_date", "")

        # Extract journal/venue
        primary_location = work.get("primary_location", {})
        source = primary_location.get("source", {})
        journal = source.get("display_name", "")

        # Extract abstract (inverted index format)
        abstract = ""
        abstract_inverted = work.get("abstract_inverted_index")
        if abstract_inverted:
            # Reconstruct abstract from inverted index
            word_positions = []
            for word, positions in abstract_inverted.items():
                for pos in positions:
                    word_positions.append((pos, word))
            word_positions.sort()
            abstract = " ".join(word for _, word in word_positions)

        # Extract identifiers
        openalex_id = work.get("id", "").replace("https://openalex.org/", "")
        pmid = work.get("ids", {}).get("pmid")
        if pmid:
            pmid = pmid.replace("https://pubmed.ncbi.nlm.nih.gov/", "")

        # Extract year
        year = work.get("publication_year")

        # Extract citation count
        cited_by_count = work.get("cited_by_count", 0)

        # Extract OA info
        open_access = work.get("open_access", {})
        is_oa = open_access.get("is_oa", False)
        oa_status = open_access.get("oa_status", "")
        oa_url = open_access.get("oa_url")

        return {
            "doi": doi,
            "openalex_id": openalex_id,
            "pmid": pmid,
            "title": work.get("title", ""),
            "authors": authors,
            "abstract": abstract,
            "publication_date": pub_date,
            "year": year,
            "journal": journal,
            "url": work.get("id", ""),  # OpenAlex work URL
            "cited_by_count": cited_by_count,
            "is_open_access": is_oa,
            "oa_status": oa_status,
            "pdf_url": oa_url if oa_url and oa_url.endswith(".pdf") else None,
            "references": [],  # Would need separate API call
        }
