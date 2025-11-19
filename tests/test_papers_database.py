"""Tests for papers database operations.

Focus on catching issues with:
- Parameter signature changes
- JSON encoding/decoding
- Alternative identifier handling
- Duplicate detection
"""

import pytest
import json
from datetime import datetime
from pathlib import Path
import tempfile

from holocene.storage.database import Database


def row_to_dict(row):
    """Convert sqlite3.Row to dict, handling JSON fields."""
    if row is None:
        return None
    d = dict(row)
    # Parse JSON fields
    if 'authors' in d:
        if d['authors'] is None or d['authors'] == '':
            d['authors'] = []
        elif isinstance(d['authors'], str):
            import json
            d['authors'] = json.loads(d['authors'])
    return d


@pytest.fixture
def temp_papers_db():
    """Create a temporary database for testing papers."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_papers.db"
        db = Database(db_path)
        yield db
        db.close()


class TestAddPaperSignature:
    """Test that add_paper has correct parameter order (title-first, not doi-first)."""

    def test_add_paper_title_first(self, temp_papers_db):
        """Test adding paper with title as first parameter."""
        paper_id = temp_papers_db.add_paper(
            title="Test Paper Title",
            authors=["John Doe", "Jane Smith"],
            publication_date="2024-01-01",
            doi="10.1234/test"
        )

        assert paper_id > 0

        # Verify stored correctly
        paper = row_to_dict(temp_papers_db.get_paper(paper_id))
        assert paper is not None
        assert paper["title"] == "Test Paper Title"
        assert paper["doi"] == "10.1234/test"

    def test_add_paper_without_doi(self, temp_papers_db):
        """Test that DOI is optional (not required)."""
        paper_id = temp_papers_db.add_paper(
            title="Old Paper Without DOI",
            authors=["Historical Author"],
            publication_date="1985-01-01"
        )

        assert paper_id > 0
        paper = row_to_dict(temp_papers_db.get_paper(paper_id))
        assert paper["title"] == "Old Paper Without DOI"
        assert paper["doi"] is None or paper["doi"] == ""


class TestJSONEncoding:
    """Test that authors and keywords are properly JSON encoded/decoded."""

    def test_authors_json_encoding(self, temp_papers_db):
        """Test that authors list is properly stored and retrieved."""
        authors = ["Alice Smith", "Bob Jones", "Carol White"]

        paper_id = temp_papers_db.add_paper(
            title="Multi-Author Paper",
            authors=authors,
            publication_date="2024-01-01"
        )

        # Retrieve and verify
        paper = row_to_dict(temp_papers_db.get_paper(paper_id))

        # Authors should be a list, not double-encoded JSON string
        assert isinstance(paper["authors"], list)
        assert paper["authors"] == authors
        assert paper["authors"][0] == "Alice Smith"

        # Should NOT be double-encoded like '[, " et al.'
        assert paper["authors"] != '[, " et al.'

    def test_empty_authors_list(self, temp_papers_db):
        """Test handling of empty authors list."""
        paper_id = temp_papers_db.add_paper(
            title="Anonymous Paper",
            authors=[],
            publication_date="2024-01-01"
        )

        paper = row_to_dict(temp_papers_db.get_paper(paper_id))
        assert isinstance(paper["authors"], list)
        assert len(paper["authors"]) == 0


class TestAlternativeIdentifiers:
    """Test alternative identifier support (arxiv, pmid, openalex, etc)."""

    def test_add_paper_with_arxiv_id(self, temp_papers_db):
        """Test adding paper with ArXiv ID instead of DOI."""
        paper_id = temp_papers_db.add_paper(
            title="ArXiv Paper",
            authors=["ArXiv Author"],
            publication_date="2024-01-01",
            arxiv_id="2401.12345"
        )

        paper = row_to_dict(temp_papers_db.get_paper(paper_id))
        assert paper["arxiv_id"] == "2401.12345"

    def test_add_paper_with_pmid(self, temp_papers_db):
        """Test adding paper with PubMed ID."""
        paper_id = temp_papers_db.add_paper(
            title="Medical Paper",
            authors=["Medical Researcher"],
            publication_date="2024-01-01",
            pmid="38123456"
        )

        paper = row_to_dict(temp_papers_db.get_paper(paper_id))
        assert paper["pmid"] == "38123456"

    def test_add_paper_with_openalex_id(self, temp_papers_db):
        """Test adding paper with OpenAlex ID."""
        paper_id = temp_papers_db.add_paper(
            title="OpenAlex Paper",
            authors=["OA Author"],
            publication_date="2024-01-01",
            openalex_id="W1234567890"
        )

        paper = row_to_dict(temp_papers_db.get_paper(paper_id))
        assert paper["openalex_id"] == "W1234567890"


class TestDuplicateDetection:
    """Test duplicate detection using hierarchical identifier matching."""

    def test_duplicate_by_doi(self, temp_papers_db):
        """Test that duplicate DOI is detected."""
        # Add first paper
        paper_id_1 = temp_papers_db.add_paper(
            title="Original Paper",
            authors=["Author One"],
            publication_date="2024-01-01",
            doi="10.1234/duplicate"
        )

        # Try to find duplicate by DOI
        duplicate = temp_papers_db.find_duplicate_paper(
            doi="10.1234/duplicate"
        )

        assert duplicate is not None
        assert duplicate["id"] == paper_id_1

    def test_duplicate_by_arxiv_id(self, temp_papers_db):
        """Test duplicate detection by ArXiv ID."""
        paper_id = temp_papers_db.add_paper(
            title="ArXiv Paper",
            authors=["Author"],
            publication_date="2024-01-01",
            arxiv_id="2401.12345"
        )

        duplicate = temp_papers_db.find_duplicate_paper(
            arxiv_id="2401.12345"
        )

        assert duplicate is not None
        assert duplicate["id"] == paper_id

    def test_duplicate_by_normalized_key(self, temp_papers_db):
        """Test duplicate detection by normalized composite key."""
        # Add paper without any IDs
        paper_id = temp_papers_db.add_paper(
            title="Unique Paper Title",
            authors=["Unique Author"],
            publication_date="2020-01-01"
        )

        # Try to find duplicate with slight variations in title/author
        duplicate = temp_papers_db.find_duplicate_paper(
            title="Unique  Paper  Title",  # Extra spaces
            first_author="Unique Author",
            year=2020
        )

        assert duplicate is not None
        assert duplicate["id"] == paper_id

    def test_no_duplicate_different_paper(self, temp_papers_db):
        """Test that different papers are not detected as duplicates."""
        temp_papers_db.add_paper(
            title="First Paper",
            authors=["Author A"],
            publication_date="2024-01-01"
        )

        duplicate = temp_papers_db.find_duplicate_paper(
            title="Different Paper",
            first_author="Author B",
            year=2024
        )

        assert duplicate is None


class TestPaperMetadata:
    """Test storing and retrieving paper metadata fields."""

    def test_full_paper_metadata(self, temp_papers_db):
        """Test storing complete paper metadata."""
        paper_id = temp_papers_db.add_paper(
            title="Complete Paper",
            authors=["Author One", "Author Two"],
            publication_date="2024-01-01",
            doi="10.1234/complete",
            journal="Journal of Testing",
            abstract="This is a test abstract.",
            is_open_access=True,
            pdf_url="https://example.com/paper.pdf"
        )

        paper = row_to_dict(temp_papers_db.get_paper(paper_id))

        assert paper["title"] == "Complete Paper"
        assert paper["authors"] == ["Author One", "Author Two"]
        assert paper["doi"] == "10.1234/complete"
        assert paper["journal"] == "Journal of Testing"
        assert paper["abstract"] == "This is a test abstract."
        assert paper["is_open_access"] == 1  # SQLite stores as 0/1

    def test_summary_fields(self, temp_papers_db):
        """Test that summary and analysis fields are stored correctly."""
        paper_id = temp_papers_db.add_paper(
            title="Analyzed Paper",
            authors=["Researcher"],
            publication_date="2024-01-01",
            summary="## Main Finding\n\nThis paper shows X.",
            analysis_pages=15,
            total_pages=20,
            full_text_analyzed=False
        )

        paper = row_to_dict(temp_papers_db.get_paper(paper_id))

        assert "## Main Finding" in paper["summary"]
        assert paper["analysis_pages"] == 15
        assert paper["total_pages"] == 20
        assert paper["full_text_analyzed"] == 0  # SQLite stores as 0/1
