"""arXiv API client for fetching paper metadata.

arXiv API: https://arxiv.org/help/api/
"""

import re
import time
import requests
import xml.etree.ElementTree as ET
from typing import Optional, Dict, List
from datetime import datetime


class ArxivClient:
    """Client for arXiv API.

    Fetches paper metadata from arXiv using their free API.
    No authentication required.
    """

    def __init__(self):
        """Initialize arXiv client."""
        self.base_url = "http://export.arxiv.org/api/query"
        self.rate_limit_delay = 3.0  # 3 seconds between requests (arXiv requirement)
        self.last_request_time = 0

    def _rate_limit(self):
        """Enforce rate limiting (arXiv requires 3 seconds between requests)."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self.last_request_time = time.time()

    def extract_arxiv_id(self, text: str) -> Optional[str]:
        """Extract arXiv ID from text (URL or plain ID).

        Args:
            text: Text containing arXiv ID or URL

        Returns:
            arXiv ID (e.g., "2103.12345") or None

        Examples:
            "https://arxiv.org/abs/2103.12345" -> "2103.12345"
            "https://arxiv.org/pdf/2103.12345.pdf" -> "2103.12345"
            "arXiv:2103.12345" -> "2103.12345"
            "2103.12345" -> "2103.12345"
        """
        # Pattern for new arXiv IDs (YYMM.NNNNN or YYMM.NNNNNV)
        new_pattern = r'(\d{4}\.\d{4,5}(?:v\d+)?)'

        # Pattern for old arXiv IDs (archive/YYMMNNN)
        old_pattern = r'([a-z\-]+/\d{7})'

        match = re.search(new_pattern, text)
        if match:
            return match.group(1).split('v')[0]  # Remove version suffix

        match = re.search(old_pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)

        return None

    def get_paper(self, arxiv_id: str) -> Optional[Dict]:
        """Get paper metadata by arXiv ID.

        Args:
            arxiv_id: arXiv paper ID (e.g., "2103.12345")

        Returns:
            Dictionary with paper metadata or None if not found
        """
        self._rate_limit()

        params = {
            'id_list': arxiv_id,
            'max_results': 1
        }

        try:
            response = requests.get(self.base_url, params=params, timeout=10)
            response.raise_for_status()

            # Parse XML response
            root = ET.fromstring(response.content)

            # Namespace for arXiv API
            ns = {'atom': 'http://www.w3.org/2005/Atom',
                  'arxiv': 'http://arxiv.org/schemas/atom'}

            # Find entry
            entry = root.find('atom:entry', ns)
            if entry is None:
                return None

            # Extract metadata
            title = entry.find('atom:title', ns)
            title = title.text.strip().replace('\n', ' ') if title is not None else None

            summary = entry.find('atom:summary', ns)
            summary = summary.text.strip().replace('\n', ' ') if summary is not None else None

            # Authors
            authors = []
            for author in entry.findall('atom:author', ns):
                name = author.find('atom:name', ns)
                if name is not None:
                    authors.append(name.text.strip())

            # Published date
            published = entry.find('atom:published', ns)
            published_date = None
            if published is not None:
                try:
                    dt = datetime.fromisoformat(published.text.replace('Z', '+00:00'))
                    published_date = dt.strftime('%Y-%m-%d')
                except:
                    pass

            # Categories (subjects)
            categories = []
            for category in entry.findall('atom:category', ns):
                term = category.get('term')
                if term:
                    categories.append(term)

            # PDF URL
            pdf_url = None
            for link in entry.findall('atom:link', ns):
                if link.get('title') == 'pdf':
                    pdf_url = link.get('href')
                    break

            # Abstract URL
            abstract_url = None
            for link in entry.findall('atom:link', ns):
                if link.get('rel') == 'alternate':
                    abstract_url = link.get('href')
                    break

            # DOI (if available)
            doi = entry.find('arxiv:doi', ns)
            doi = doi.text.strip() if doi is not None else None

            return {
                'arxiv_id': arxiv_id,
                'title': title,
                'authors': authors,
                'abstract': summary,
                'published_date': published_date,
                'categories': categories,
                'pdf_url': pdf_url,
                'url': abstract_url,
                'doi': doi
            }

        except Exception as e:
            print(f"Error fetching arXiv paper {arxiv_id}: {e}")
            return None

    def search(self, query: str, max_results: int = 10) -> List[Dict]:
        """Search arXiv papers.

        Args:
            query: Search query
            max_results: Maximum number of results

        Returns:
            List of paper dictionaries
        """
        self._rate_limit()

        params = {
            'search_query': query,
            'max_results': max_results,
            'sortBy': 'relevance',
            'sortOrder': 'descending'
        }

        try:
            response = requests.get(self.base_url, params=params, timeout=10)
            response.raise_for_status()

            root = ET.fromstring(response.content)
            ns = {'atom': 'http://www.w3.org/2005/Atom',
                  'arxiv': 'http://arxiv.org/schemas/atom'}

            papers = []
            for entry in root.findall('atom:entry', ns):
                # Extract arXiv ID from the entry ID
                entry_id = entry.find('atom:id', ns)
                if entry_id is not None:
                    arxiv_id = self.extract_arxiv_id(entry_id.text)
                    if arxiv_id:
                        paper_data = self.get_paper(arxiv_id)
                        if paper_data:
                            papers.append(paper_data)

            return papers

        except Exception as e:
            print(f"Error searching arXiv: {e}")
            return []
