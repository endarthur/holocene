"""Tests for PDF metadata extraction.

Focus on:
- DOI and ISBN regex extraction
- Text extraction parameters
- Summary extraction flags
- Metadata validation
"""

import pytest
from unittest.mock import Mock, patch
from pathlib import Path

from holocene.research.pdf_metadata_extractor import PDFMetadataExtractor


@pytest.fixture
def mock_config():
    """Create mock config for testing."""
    config = Mock()
    config.llm.api_key = "test_key"
    config.llm.base_url = "https://test.url"
    config.llm.primary = "deepseek-v3"
    return config


@pytest.fixture
def extractor(mock_config):
    """Create PDFMetadataExtractor with mock config."""
    return PDFMetadataExtractor(mock_config)


class TestDOIExtraction:
    """Test DOI pattern matching from text."""

    def test_extract_doi_standard_format(self, extractor):
        """Test extracting DOI in standard format."""
        text = "This paper has doi: 10.1234/example.paper.2024"
        doi = extractor.extract_doi_from_text(text)

        assert doi == "10.1234/example.paper.2024"

    def test_extract_doi_uppercase(self, extractor):
        """Test extracting DOI with uppercase prefix."""
        text = "DOI: 10.5678/test"
        doi = extractor.extract_doi_from_text(text)

        assert doi == "10.5678/test"

    def test_extract_doi_from_url(self, extractor):
        """Test extracting DOI from doi.org URL."""
        text = "Available at https://doi.org/10.1234/paper"
        doi = extractor.extract_doi_from_text(text)

        assert doi == "10.1234/paper"

    def test_extract_doi_from_dx_url(self, extractor):
        """Test extracting DOI from dx.doi.org URL."""
        text = "See http://dx.doi.org/10.9999/old.paper"
        doi = extractor.extract_doi_from_text(text)

        assert doi == "10.9999/old.paper"

    def test_extract_doi_with_trailing_punctuation(self, extractor):
        """Test that trailing punctuation is removed."""
        text = "doi: 10.1234/test."
        doi = extractor.extract_doi_from_text(text)

        assert doi == "10.1234/test"
        assert not doi.endswith(".")

    def test_extract_doi_not_found(self, extractor):
        """Test when no DOI is present."""
        text = "This is a paper without any identifier"
        doi = extractor.extract_doi_from_text(text)

        assert doi is None


class TestISBNExtraction:
    """Test ISBN pattern matching from text."""

    def test_extract_isbn13(self, extractor):
        """Test extracting ISBN-13."""
        text = "ISBN: 978-0-123-45678-9"
        isbn = extractor.extract_isbn_from_text(text)

        assert isbn is not None
        assert "978" in isbn
        assert "-" not in isbn  # Hyphens should be removed

    def test_extract_isbn10(self, extractor):
        """Test extracting ISBN-10."""
        text = "ISBN 0-123-45678-X"
        isbn = extractor.extract_isbn_from_text(text)

        assert isbn is not None
        assert "X" in isbn or "x" in isbn.upper()
        assert "-" not in isbn

    def test_extract_isbn_no_hyphens(self, extractor):
        """Test extracting ISBN without hyphens."""
        text = "ISBN 9780123456789"
        isbn = extractor.extract_isbn_from_text(text)

        assert isbn == "9780123456789"

    def test_extract_isbn_not_found(self, extractor):
        """Test when no ISBN is present."""
        text = "This book has no ISBN"
        isbn = extractor.extract_isbn_from_text(text)

        assert isbn is None


class TestMetadataExtraction:
    """Test full metadata extraction with mocked LLM."""

    @patch('holocene.research.pdf_metadata_extractor.pdfplumber')
    def test_extract_metadata_default_pages(self, mock_pdfplumber, extractor, mock_config):
        """Test that default extraction uses 5 pages."""
        # Mock PDF with 10 pages
        mock_pdf = Mock()
        mock_pdf.pages = [Mock()] * 10
        mock_pdfplumber.open.return_value.__enter__.return_value = mock_pdf

        # Mock LLM response
        with patch.object(extractor.llm_client, 'simple_prompt') as mock_llm:
            mock_llm.return_value = '''{
                "type": "paper",
                "title": "Test Paper",
                "authors": ["Test Author"],
                "year": 2024,
                "confidence": "high"
            }'''

            # Mock text extraction
            with patch.object(extractor, 'extract_text') as mock_extract:
                mock_extract.return_value = "Test PDF content"

                metadata = extractor.extract_metadata(Path("test.pdf"))

                # Should extract 5 pages by default (not summarizing)
                mock_extract.assert_called_once()
                call_args = mock_extract.call_args
                assert call_args[1].get('max_pages') == 5

    @patch('holocene.research.pdf_metadata_extractor.pdfplumber')
    def test_extract_metadata_with_summary_uses_more_pages(self, mock_pdfplumber, extractor):
        """Test that summary extraction uses 15 pages by default."""
        mock_pdf = Mock()
        mock_pdf.pages = [Mock()] * 20
        mock_pdfplumber.open.return_value.__enter__.return_value = mock_pdf

        with patch.object(extractor.llm_client, 'simple_prompt') as mock_llm:
            mock_llm.return_value = '''{
                "type": "paper",
                "title": "Test Paper",
                "authors": ["Author"],
                "year": 2024,
                "summary": "## Summary\\nTest summary",
                "confidence": "high"
            }'''

            with patch.object(extractor, 'extract_text') as mock_extract:
                mock_extract.return_value = "Test content"

                metadata = extractor.extract_metadata(
                    Path("test.pdf"),
                    extract_summary=True
                )

                # Should extract 15 pages when summarizing
                call_args = mock_extract.call_args
                assert call_args[1].get('max_pages') == 15

    @patch('holocene.research.pdf_metadata_extractor.pdfplumber')
    def test_extract_metadata_full_text(self, mock_pdfplumber, extractor):
        """Test that full_text flag extracts all pages."""
        mock_pdf = Mock()
        mock_pdf.pages = [Mock()] * 50
        mock_pdfplumber.open.return_value.__enter__.return_value = mock_pdf

        # Mock each page to return some text
        for page in mock_pdf.pages:
            page.extract_text.return_value = "Test page content"

        with patch.object(extractor.llm_client, 'simple_prompt') as mock_llm:
            mock_llm.return_value = '''{
                "type": "paper",
                "title": "Test",
                "authors": ["Author"],
                "year": 2024,
                "confidence": "high"
            }'''

            metadata = extractor.extract_metadata(
                Path("test.pdf"),
                full_text=True
            )

            # Should have full_text_analyzed=True
            assert metadata.get('full_text_analyzed') is True
            assert metadata.get('total_pages') == 50

    @patch('holocene.research.pdf_metadata_extractor.pdfplumber')
    def test_extract_metadata_custom_pages(self, mock_pdfplumber, extractor):
        """Test extracting custom number of pages."""
        mock_pdf = Mock()
        mock_pdf.pages = [Mock()] * 30
        mock_pdfplumber.open.return_value.__enter__.return_value = mock_pdf

        with patch.object(extractor.llm_client, 'simple_prompt') as mock_llm:
            mock_llm.return_value = '''{
                "type": "paper",
                "title": "Test",
                "authors": ["Author"],
                "year": 2024,
                "confidence": "high"
            }'''

            with patch.object(extractor, 'extract_text') as mock_extract:
                mock_extract.return_value = "Custom pages"

                metadata = extractor.extract_metadata(
                    Path("test.pdf"),
                    max_pages=10
                )

                # Should use custom page count
                call_args = mock_extract.call_args
                assert call_args[1].get('max_pages') == 10

    @patch('holocene.research.pdf_metadata_extractor.pdfplumber')
    def test_extract_metadata_tracks_pages(self, mock_pdfplumber, extractor):
        """Test that analysis_pages and total_pages are tracked."""
        # PDF with 20 pages
        mock_pdf = Mock()
        mock_pdf.pages = [Mock()] * 20
        mock_pdfplumber.open.return_value.__enter__.return_value = mock_pdf

        with patch.object(extractor.llm_client, 'simple_prompt') as mock_llm:
            mock_llm.return_value = '''{
                "type": "paper",
                "title": "Test",
                "authors": ["Author"],
                "year": 2024,
                "confidence": "high"
            }'''

            with patch.object(extractor, 'extract_text') as mock_extract:
                mock_extract.return_value = "Content"

                metadata = extractor.extract_metadata(
                    Path("test.pdf"),
                    max_pages=5
                )

                assert metadata.get('total_pages') == 20
                assert metadata.get('analysis_pages') == 5
                assert metadata.get('extraction_method') == 'deepseek_v3'


class TestLLMPromptGeneration:
    """Test that LLM prompts are correctly generated."""

    def test_extract_metadata_with_llm_basic(self, extractor):
        """Test basic metadata extraction prompt."""
        with patch.object(extractor.llm_client, 'simple_prompt') as mock_llm:
            mock_llm.return_value = '''{
                "type": "paper",
                "title": "Test Paper",
                "authors": ["Author"],
                "year": 2024,
                "confidence": "high"
            }'''

            metadata = extractor.extract_metadata_with_llm(
                text="Sample PDF text",
                extract_summary=False
            )

            # Check that LLM was called
            assert mock_llm.called
            call_args = mock_llm.call_args

            # Should NOT request summary in prompt
            prompt = call_args[1].get('prompt', '')
            assert 'summary' not in prompt.lower() or 'no summary' in prompt.lower()

    def test_extract_metadata_with_summary_prompt(self, extractor):
        """Test that summary is requested when flag is set."""
        with patch.object(extractor.llm_client, 'simple_prompt') as mock_llm:
            # Use actual newlines in the JSON response (not escaped)
            mock_llm.return_value = '''{
                "type": "paper",
                "title": "Test Paper",
                "authors": ["Author"],
                "year": 2024,
                "summary": "## Main Finding\\nTest summary",
                "confidence": "high"
            }'''

            metadata = extractor.extract_metadata_with_llm(
                text="Sample PDF text",
                extract_summary=True
            )

            # Verify summary was requested and returned
            assert 'summary' in metadata
            # The JSON parser will convert \\n to actual newline
            assert '##' in metadata['summary']
            assert 'Main Finding' in metadata['summary']
            assert 'Test summary' in metadata['summary']
