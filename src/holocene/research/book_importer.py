"""LibraryCat/LibraryThing book import functionality."""

from pathlib import Path
from typing import List, Dict
import csv
import json


class LibraryCatImporter:
    """Imports books from LibraryCat CSV and LibraryThing JSON exports."""

    def parse_csv(self, csv_path: Path) -> List[Dict]:
        """
        Parse LibraryCat CSV export.

        Expected CSV format:
        Title, Author, ISBN, ISBN13, Year, Publisher, Tags/Subjects, etc.

        Args:
            csv_path: Path to CSV file

        Returns:
            List of book dictionaries
        """
        books = []

        with open(csv_path, 'r', encoding='utf-8') as f:
            # Try to detect delimiter
            sample = f.read(1024)
            f.seek(0)

            sniffer = csv.Sniffer()
            try:
                dialect = sniffer.sniff(sample)
            except csv.Error:
                dialect = csv.excel  # Fallback

            reader = csv.DictReader(f, dialect=dialect)

            for row in reader:
                book = self._parse_row(row)
                if book:
                    books.append(book)

        return books

    def _parse_row(self, row: Dict[str, str]) -> Dict:
        """
        Parse a single CSV row into book dictionary.

        Handles various possible column names from LibraryCat/LibraryThing.

        Args:
            row: CSV row as dictionary

        Returns:
            Standardized book dictionary
        """
        # Map various possible column names
        title = (
            row.get('Title') or
            row.get('TITLE') or
            row.get('title') or
            ""
        )

        if not title:
            return None  # Skip rows without title

        author = (
            row.get('Author') or
            row.get('AUTHOR') or
            row.get('author') or
            row.get('Primary Author') or
            None
        )

        subtitle = (
            row.get('Subtitle') or
            row.get('SUBTITLE') or
            None
        )

        isbn = (
            row.get('ISBN') or
            row.get('isbn') or
            None
        )

        isbn13 = (
            row.get('ISBN13') or
            row.get('isbn13') or
            row.get('ISBN-13') or
            None
        )

        year_str = (
            row.get('Year') or
            row.get('Date') or
            row.get('Publication Year') or
            row.get('YEAR') or
            None
        )

        try:
            publication_year = int(year_str) if year_str else None
        except ValueError:
            publication_year = None

        publisher = (
            row.get('Publisher') or
            row.get('PUBLISHER') or
            None
        )

        # Parse subjects/tags
        subjects_str = (
            row.get('Tags') or
            row.get('tags') or
            row.get('Subjects') or
            row.get('Subject') or
            row.get('subjects') or
            ""
        )

        # Split subjects by comma or semicolon
        if subjects_str:
            subjects = [s.strip() for s in subjects_str.replace(';', ',').split(',') if s.strip()]
        else:
            subjects = []

        notes = (
            row.get('Notes') or
            row.get('NOTES') or
            row.get('Comment') or
            None
        )

        lc_classification = (
            row.get('LC Classification') or
            row.get('LCC') or
            None
        )

        dewey = (
            row.get('Dewey Decimal') or
            row.get('DDC') or
            None
        )

        return {
            'title': title.strip(),
            'author': author.strip() if author else None,
            'subtitle': subtitle.strip() if subtitle else None,
            'isbn': isbn.strip() if isbn else None,
            'isbn13': isbn13.strip() if isbn13 else None,
            'publication_year': publication_year,
            'publisher': publisher.strip() if publisher else None,
            'subjects': subjects,
            'lc_classification': lc_classification,
            'dewey_decimal': dewey,
            'notes': notes.strip() if notes else None,
        }

    def parse_json(self, json_path: Path) -> List[Dict]:
        """
        Parse LibraryThing JSON export.

        Expected JSON format:
        {
            "book_id": {
                "title": "...",
                "primaryauthor": "...",
                "isbn": [...],
                "date": "...",
                ...
            }
        }

        Args:
            json_path: Path to JSON file

        Returns:
            List of book dictionaries
        """
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        books = []
        for book_id, book_data in data.items():
            book = self._parse_json_book(book_data)
            if book:
                books.append(book)

        return books

    def _parse_json_book(self, book_data: Dict) -> Dict:
        """
        Parse a single LibraryThing book entry.

        Args:
            book_data: Book data dictionary from JSON

        Returns:
            Standardized book dictionary
        """
        title = book_data.get('title', '').strip()
        if not title:
            return None  # Skip entries without title

        # Parse author
        author = book_data.get('primaryauthor')
        if author and ',' in author:
            # Convert "Last, First" to "First Last"
            parts = author.split(',', 1)
            author = f"{parts[1].strip()} {parts[0].strip()}"

        # Parse ISBN - can be array or object
        isbn = None
        isbn13 = None
        isbn_data = book_data.get('isbn', [])

        if isinstance(isbn_data, list):
            for isbn_value in isbn_data:
                isbn_str = str(isbn_value).strip()
                if len(isbn_str) == 13:
                    isbn13 = isbn_str
                elif len(isbn_str) == 10:
                    isbn = isbn_str
        elif isinstance(isbn_data, dict):
            for key, value in isbn_data.items():
                isbn_str = str(value).strip()
                if len(isbn_str) == 13:
                    isbn13 = isbn_str
                elif len(isbn_str) == 10:
                    isbn = isbn_str

        # If no ISBN but we have originalisbn
        if not isbn and not isbn13:
            orig_isbn = book_data.get('originalisbn', '').strip()
            if orig_isbn:
                if len(orig_isbn) == 13:
                    isbn13 = orig_isbn
                elif len(orig_isbn) == 10:
                    isbn = orig_isbn

        # Parse publication year
        year_str = book_data.get('date')
        try:
            publication_year = int(year_str) if year_str else None
        except (ValueError, TypeError):
            publication_year = None

        # Extract publisher from publication field
        # Format: "Publisher Name (Year), Edition: X, Y pages"
        publisher = None
        publication = book_data.get('publication', '')
        if publication and '(' in publication:
            publisher = publication.split('(')[0].strip()

        # Parse genres as subjects
        subjects = book_data.get('genre', [])
        if not isinstance(subjects, list):
            subjects = []

        # Get Dewey and LC classifications
        ddc_data = book_data.get('ddc', {})
        if isinstance(ddc_data, dict) and 'code' in ddc_data:
            dewey_codes = ddc_data['code']
            dewey = dewey_codes[0] if isinstance(dewey_codes, list) and dewey_codes else None
        else:
            dewey = None

        lcc_data = book_data.get('lcc', {})
        if isinstance(lcc_data, dict):
            lc_classification = lcc_data.get('code')
        elif isinstance(lcc_data, list) and lcc_data:
            lc_classification = lcc_data[0]
        else:
            lc_classification = None

        return {
            'title': title,
            'author': author.strip() if author else None,
            'subtitle': None,  # LibraryThing doesn't separate subtitle
            'isbn': isbn,
            'isbn13': isbn13,
            'publication_year': publication_year,
            'publisher': publisher,
            'subjects': subjects,
            'lc_classification': lc_classification,
            'dewey_decimal': dewey,
            'notes': book_data.get('summary'),
        }

    def import_to_database(self, file_path: Path, db) -> int:
        """
        Import books from CSV or JSON file into database.

        Args:
            file_path: Path to CSV or JSON file
            db: Database instance

        Returns:
            Number of books imported
        """
        # Determine file type and parse accordingly
        if file_path.suffix.lower() == '.json':
            books = self.parse_json(file_path)
        elif file_path.suffix.lower() == '.csv':
            books = self.parse_csv(file_path)
        else:
            raise ValueError(f"Unsupported file format: {file_path.suffix}. Use .csv or .json")

        count = 0
        for book in books:
            try:
                db.insert_book(
                    title=book['title'],
                    author=book.get('author'),
                    subtitle=book.get('subtitle'),
                    isbn=book.get('isbn'),
                    isbn13=book.get('isbn13'),
                    publication_year=book.get('publication_year'),
                    publisher=book.get('publisher'),
                    subjects=book.get('subjects'),
                    notes=book.get('notes')
                )
                count += 1
            except Exception as e:
                print(f"Failed to import '{book['title']}': {e}")

        return count
