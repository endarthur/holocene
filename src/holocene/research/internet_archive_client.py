"""Internet Archive and Open Library API client."""

import requests
from typing import Optional, List, Dict
from datetime import datetime
from pathlib import Path


class InternetArchiveClient:
    """Client for Internet Archive and Open Library APIs."""

    def __init__(self):
        """Initialize Internet Archive client."""
        self.search_url = "https://archive.org/advancedsearch.php"
        self.metadata_url = "https://archive.org/metadata"
        self.download_url = "https://archive.org/download"
        self.openlibrary_url = "https://openlibrary.org"

        self.headers = {
            "User-Agent": "Holocene/1.0 (Personal Research Tool)"
        }

    def search_books(
        self,
        query: str,
        from_year: Optional[int] = None,
        until_year: Optional[int] = None,
        subject: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict]:
        """
        Search Internet Archive for public domain books.

        Args:
            query: Search query
            from_year: Minimum publication year
            until_year: Maximum publication year
            subject: Subject/topic filter
            limit: Maximum results

        Returns:
            List of book metadata
        """
        # Build query
        query_parts = [f"({query})"]

        # Only get texts (books)
        query_parts.append("mediatype:texts")

        # Add subject filter
        if subject:
            query_parts.append(f"subject:{subject}")

        # Add date range
        if from_year or until_year:
            from_y = from_year or 1000
            until_y = until_year or 2030
            query_parts.append(f"date:[{from_y} TO {until_y}]")

        full_query = " AND ".join(query_parts)

        params = {
            "q": full_query,
            "fl[]": ["identifier", "title", "creator", "date", "subject", "description", "downloads"],
            "rows": limit,
            "page": 1,
            "output": "json",
            "sort[]": "downloads desc"  # Sort by popularity
        }

        try:
            response = requests.get(
                self.search_url,
                params=params,
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

            docs = data.get("response", {}).get("docs", [])
            return [self._parse_search_result(doc) for doc in docs]

        except requests.exceptions.RequestException as e:
            print(f"⚠️  Internet Archive search error: {e}")
            return []

    def get_metadata(self, identifier: str) -> Optional[Dict]:
        """
        Get detailed metadata for an IA item.

        Args:
            identifier: Internet Archive identifier

        Returns:
            Item metadata or None
        """
        try:
            url = f"{self.metadata_url}/{identifier}"
            response = requests.get(
                url,
                headers=self.headers,
                timeout=30
            )

            if response.status_code == 404:
                return None

            response.raise_for_status()
            data = response.json()
            return data.get("metadata", {})

        except requests.exceptions.RequestException as e:
            print(f"⚠️  Internet Archive metadata error: {e}")
            return None

    def get_pdf_url(self, identifier: str) -> Optional[str]:
        """
        Get PDF download URL for an IA item.

        Args:
            identifier: Internet Archive identifier

        Returns:
            PDF URL or None
        """
        metadata = self.get_metadata(identifier)
        if not metadata:
            return None

        # Try to find a PDF file
        files_url = f"https://archive.org/metadata/{identifier}/files"
        try:
            response = requests.get(files_url, headers=self.headers, timeout=30)
            response.raise_for_status()
            data = response.json()

            # Look for PDF file
            for file_info in data.get("result", []):
                filename = file_info.get("name", "")
                if filename.lower().endswith(".pdf"):
                    return f"{self.download_url}/{identifier}/{filename}"

            return None

        except requests.exceptions.RequestException:
            return None

    def download_pdf(self, identifier: str, output_path: Path) -> bool:
        """
        Download PDF for an IA item.

        Args:
            identifier: Internet Archive identifier
            output_path: Where to save the PDF

        Returns:
            True if successful
        """
        pdf_url = self.get_pdf_url(identifier)
        if not pdf_url:
            print(f"⚠️  No PDF found for {identifier}")
            return False

        try:
            print(f"📥 Downloading PDF from {pdf_url}...")
            response = requests.get(pdf_url, headers=self.headers, stream=True, timeout=120)
            response.raise_for_status()

            # Ensure output directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Download with progress
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0

            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            percent = (downloaded / total_size) * 100
                            print(f"\r   Progress: {percent:.1f}%", end="", flush=True)

            print("\n✓ Download complete!")
            return True

        except requests.exceptions.RequestException as e:
            print(f"\n⚠️  Download error: {e}")
            return False

    def search_pre_llm_books(
        self,
        query: str,
        subject: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict]:
        """
        Search for pre-LLM era books (before 2022).

        Args:
            query: Search query
            subject: Subject filter
            limit: Maximum results

        Returns:
            List of book metadata
        """
        # Focus on older books (1900-2022)
        return self.search_books(
            query=query,
            from_year=1900,
            until_year=2022,
            subject=subject,
            limit=limit
        )

    def get_openlibrary_info(self, isbn: Optional[str] = None, oclc: Optional[str] = None) -> Optional[Dict]:
        """
        Get book info from Open Library API.

        Args:
            isbn: Book ISBN
            oclc: OCLC number

        Returns:
            Book metadata or None
        """
        if not isbn and not oclc:
            return None

        try:
            if isbn:
                url = f"{self.openlibrary_url}/isbn/{isbn}.json"
            else:
                url = f"{self.openlibrary_url}/books/OCLC/{oclc}.json"

            response = requests.get(url, headers=self.headers, timeout=30)

            if response.status_code == 404:
                return None

            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException:
            return None

    def _parse_search_result(self, doc: Dict) -> Dict:
        """
        Parse Internet Archive search result.

        Args:
            doc: Raw search result

        Returns:
            Parsed book metadata
        """
        # Parse creators/authors
        creators = doc.get("creator", [])
        if isinstance(creators, str):
            creators = [creators]

        # Parse subjects
        subjects = doc.get("subject", [])
        if isinstance(subjects, str):
            subjects = [subjects]

        # Parse date
        date = doc.get("date")
        if isinstance(date, list) and date:
            date = date[0]

        return {
            "identifier": doc.get("identifier"),
            "title": doc.get("title"),
            "authors": creators,
            "publication_year": date,
            "subjects": subjects,
            "description": doc.get("description"),
            "downloads": doc.get("downloads", 0),
            "url": f"https://archive.org/details/{doc.get('identifier')}"
        }
