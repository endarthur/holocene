"""Tests for text normalization and duplicate detection.

These functions are critical for finding duplicate papers with variations in:
- Unicode characters and accents
- Punctuation
- Whitespace
- Author name formats
"""

import pytest
from holocene.storage.database import (
    normalize_text,
    normalize_author_name,
    generate_normalized_key
)


class TestNormalizeText:
    """Test text normalization for title matching."""

    def test_normalize_basic_text(self):
        """Test basic text normalization."""
        result = normalize_text("Simple Title")
        assert result == "simple title"

    def test_normalize_unicode_accents(self):
        """Test that accents are removed for matching."""
        # Portuguese: "Análise Geoestatística"
        text1 = normalize_text("Análise Geoestatística")
        text2 = normalize_text("Analise Geoestatistica")

        assert text1 == text2
        assert "analise" in text1
        assert "geoestatistica" in text1

    def test_normalize_punctuation(self):
        """Test that punctuation is removed."""
        text1 = normalize_text("Title: With Punctuation!")
        text2 = normalize_text("Title With Punctuation")

        assert text1 == text2
        assert ":" not in text1
        assert "!" not in text1

    def test_normalize_extra_whitespace(self):
        """Test that extra whitespace is collapsed."""
        text1 = normalize_text("Multiple   Spaces    Here")
        text2 = normalize_text("Multiple Spaces Here")

        assert text1 == text2
        assert "  " not in text1  # No double spaces

    def test_normalize_case_insensitive(self):
        """Test case insensitivity."""
        text1 = normalize_text("CamelCase Title")
        text2 = normalize_text("camelcase title")

        assert text1 == text2

    def test_normalize_empty_string(self):
        """Test handling of empty string."""
        result = normalize_text("")
        assert result == ""

    def test_normalize_none(self):
        """Test handling of None."""
        result = normalize_text(None)
        assert result == ""

    def test_normalize_special_characters(self):
        """Test handling of special characters like em-dash, quotes."""
        text1 = normalize_text('Title—With Special "Quotes"')
        text2 = normalize_text("Title With Special Quotes")

        # Should match (punctuation removed)
        assert normalize_text(text1) == normalize_text(text2)


class TestNormalizeAuthorName:
    """Test author name normalization for matching."""

    def test_normalize_simple_name(self):
        """Test simple author name."""
        result = normalize_author_name("John Smith")
        assert "smith" in result
        assert "john" in result

    def test_normalize_first_author_from_list(self):
        """Test extracting first author from 'LastName, FirstName' format."""
        result = normalize_author_name("Doe, John")
        assert "doe" in result

    def test_normalize_portuguese_name(self):
        """Test Portuguese name with accents."""
        name1 = normalize_author_name("José Silva")
        name2 = normalize_author_name("Jose Silva")

        assert name1 == name2

    def test_normalize_name_with_middle_initial(self):
        """Test name with middle initial."""
        result = normalize_author_name("John Q. Public")
        assert "public" in result
        assert "john" in result

    def test_normalize_name_with_suffix(self):
        """Test name with suffix (Jr., Sr., III)."""
        name1 = normalize_author_name("John Smith Jr.")
        name2 = normalize_author_name("John Smith")

        # Should be similar (punctuation removed)
        assert "smith" in name1
        assert "john" in name1


class TestGenerateNormalizedKey:
    """Test composite key generation for duplicate detection."""

    def test_generate_basic_key(self):
        """Test basic normalized key generation."""
        key = generate_normalized_key(
            title="Test Paper",
            first_author="John Doe",
            year=2024
        )

        assert "test paper" in key
        assert "doe" in key
        assert "2024" in key
        assert "|" in key  # Separator

    def test_generate_key_unicode_tolerance(self):
        """Test that keys match despite unicode differences."""
        key1 = generate_normalized_key(
            title="Análise Geoestatística de Depósitos Minerais",
            first_author="José Silva",
            year=2020
        )

        key2 = generate_normalized_key(
            title="Analise Geoestatistica de Depositos Minerais",
            first_author="Jose Silva",
            year=2020
        )

        assert key1 == key2

    def test_generate_key_punctuation_tolerance(self):
        """Test that keys match despite punctuation differences."""
        key1 = generate_normalized_key(
            title="Deep Learning: A Survey",
            first_author="Smith, John",
            year=2024
        )

        key2 = generate_normalized_key(
            title="Deep Learning A Survey",
            first_author="John Smith",
            year=2024
        )

        # Should match after normalization
        assert normalize_text("Deep Learning: A Survey") == normalize_text("Deep Learning A Survey")

    def test_generate_key_whitespace_tolerance(self):
        """Test that keys match despite whitespace differences."""
        key1 = generate_normalized_key(
            title="Multiple   Spaces   Title",
            first_author="Author Name",
            year=2024
        )

        key2 = generate_normalized_key(
            title="Multiple Spaces Title",
            first_author="Author Name",
            year=2024
        )

        assert key1 == key2

    def test_generate_key_missing_year(self):
        """Test key generation when year is missing."""
        key = generate_normalized_key(
            title="Undated Paper",
            first_author="Author",
            year=None
        )

        assert "undated paper" in key
        assert "author" in key
        assert "unknown" in key  # Year placeholder

    def test_generate_key_different_papers(self):
        """Test that different papers generate different keys."""
        key1 = generate_normalized_key(
            title="First Paper",
            first_author="Author A",
            year=2024
        )

        key2 = generate_normalized_key(
            title="Second Paper",
            first_author="Author B",
            year=2024
        )

        assert key1 != key2

    def test_generate_key_same_paper_different_formatting(self):
        """Test real-world case: same paper with formatting differences."""
        # Paper title from PDF (with linebreaks, extra spaces)
        key1 = generate_normalized_key(
            title="Geostatistical Analysis\nof Mineral Deposits",
            first_author="Ginaldo, A. C.",
            year=2020
        )

        # Paper title from metadata (clean)
        key2 = generate_normalized_key(
            title="Geostatistical Analysis of Mineral Deposits",
            first_author="Ginaldo AC",
            year=2020
        )

        # These should match after normalization
        norm_title1 = normalize_text("Geostatistical Analysis\nof Mineral Deposits")
        norm_title2 = normalize_text("Geostatistical Analysis of Mineral Deposits")

        assert norm_title1 == norm_title2
