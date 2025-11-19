"""BibTeX file importer for building paper collections from bibliographies."""

import bibtexparser
from typing import List, Dict, Optional
from pathlib import Path


class BibTeXImporter:
    """Import papers from BibTeX files (e.g., thesis bibliographies)."""

    def __init__(self):
        """Initialize BibTeX importer."""
        pass

    def parse_file(self, bib_path: Path) -> List[Dict]:
        """
        Parse a BibTeX file and extract paper information.

        Args:
            bib_path: Path to .bib file

        Returns:
            List of parsed entries with metadata
        """
        with open(bib_path, 'r', encoding='utf-8') as f:
            bib_database = bibtexparser.load(f)

        entries = []
        for entry in bib_database.entries:
            parsed = self._parse_entry(entry)
            if parsed:
                entries.append(parsed)

        return entries

    def _parse_entry(self, entry: Dict) -> Optional[Dict]:
        """
        Parse a single BibTeX entry.

        Args:
            entry: Raw BibTeX entry dict

        Returns:
            Standardized paper metadata or None if not a paper
        """
        entry_type = entry.get('ENTRYTYPE', '').lower()

        # Only process articles, conference papers, books, theses
        valid_types = ['article', 'inproceedings', 'book', 'phdthesis',
                       'mastersthesis', 'incollection', 'inbook']

        if entry_type not in valid_types:
            return None

        # Extract key fields
        title = entry.get('title', '').strip('{}')
        authors = self._parse_authors(entry.get('author', ''))
        year = entry.get('year', '')
        doi = entry.get('doi', '').strip()

        # Try to get journal/publisher
        journal = entry.get('journal') or entry.get('booktitle') or entry.get('publisher')

        # Build search query for Crossref (if no DOI)
        search_query = None
        if not doi and title:
            # Use title + first author for searching
            if authors:
                search_query = f"{title} {authors[0]}"
            else:
                search_query = title

        return {
            'bibtex_key': entry.get('ID', ''),
            'entry_type': entry_type,
            'title': title,
            'authors': authors,
            'year': year,
            'doi': doi,
            'journal': journal,
            'abstract': entry.get('abstract', ''),
            'search_query': search_query,
            'raw_entry': entry
        }

    def _parse_authors(self, author_string: str) -> List[str]:
        """
        Parse BibTeX author string into list of names.

        Args:
            author_string: BibTeX author field (e.g., "Smith, John and Doe, Jane")

        Returns:
            List of author names
        """
        if not author_string:
            return []

        # Split on 'and' (BibTeX author separator)
        authors = []
        for author in author_string.split(' and '):
            author = author.strip()
            # Remove curly braces
            author = author.strip('{}')

            # Handle "Last, First" format
            if ',' in author:
                parts = author.split(',', 1)
                if len(parts) == 2:
                    last, first = parts
                    author = f"{first.strip()} {last.strip()}"

            authors.append(author)

        return authors

    def categorize_entries(self, entries: List[Dict]) -> Dict[str, List[Dict]]:
        """
        Categorize parsed entries by whether they have DOIs.

        Args:
            entries: List of parsed BibTeX entries

        Returns:
            Dictionary with 'with_doi' and 'without_doi' lists
        """
        with_doi = []
        without_doi = []

        for entry in entries:
            if entry.get('doi'):
                with_doi.append(entry)
            else:
                without_doi.append(entry)

        return {
            'with_doi': with_doi,
            'without_doi': without_doi,
            'total': len(entries)
        }
