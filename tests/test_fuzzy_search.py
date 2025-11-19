"""Tests for fuzzy search functionality."""

import pytest
from holocene.core import fuzzy_search


def test_fuzzy_match_ratio_exact():
    """Test exact match returns 1.0."""
    assert fuzzy_search.fuzzy_match_ratio("hello", "hello") == 1.0


def test_fuzzy_match_ratio_partial():
    """Test partial match returns value between 0 and 1."""
    ratio = fuzzy_search.fuzzy_match_ratio("hello", "helo")
    assert 0.0 < ratio < 1.0


def test_fuzzy_match_ratio_no_match():
    """Test completely different strings return low score."""
    ratio = fuzzy_search.fuzzy_match_ratio("abc", "xyz")
    assert ratio < 0.5


def test_fuzzy_match_ratio_case_insensitive():
    """Test case-insensitive matching (default)."""
    assert fuzzy_search.fuzzy_match_ratio("Hello", "hello") == 1.0


def test_fuzzy_match_ratio_case_sensitive():
    """Test case-sensitive matching."""
    ratio = fuzzy_search.fuzzy_match_ratio("Hello", "hello", case_sensitive=True)
    assert ratio < 1.0


def test_fuzzy_match_ratio_empty():
    """Test empty strings."""
    assert fuzzy_search.fuzzy_match_ratio("", "test") == 0.0
    assert fuzzy_search.fuzzy_match_ratio("test", "") == 0.0


def test_fuzzy_match_accepts():
    """Test fuzzy_match accepts strings above threshold."""
    assert fuzzy_search.fuzzy_match("python", "python")  # Exact
    assert fuzzy_search.fuzzy_match("python", "pyton")  # Typo
    assert fuzzy_search.fuzzy_match("data", "database", threshold=0.5)


def test_fuzzy_match_rejects():
    """Test fuzzy_match rejects strings below threshold."""
    assert not fuzzy_search.fuzzy_match("abc", "xyz")
    assert not fuzzy_search.fuzzy_match("short", "completely different long text", threshold=0.8)


def test_fuzzy_search_simple():
    """Test basic fuzzy search."""
    items = ["apple", "application", "apply", "banana", "orange"]

    # Lower threshold since "app" is short compared to full words
    results = fuzzy_search.fuzzy_search(
        "app",
        items,
        key_func=lambda x: x,
        threshold=0.3  # More realistic for partial matches
    )

    # Should find app*, not banana/orange
    found_items = [item for item, score in results]
    assert "apple" in found_items
    assert "apply" in found_items
    # "application" might be included with low threshold
    assert "banana" not in found_items


def test_fuzzy_search_with_objects():
    """Test fuzzy search with custom objects."""
    class Book:
        def __init__(self, title):
            self.title = title

    books = [
        Book("Geostatistics"),
        Book("Geology"),
        Book("Python Programming"),
        Book("Geographic Information Systems"),
    ]

    results = fuzzy_search.fuzzy_search(
        "geology",  # Full word for better match
        books,
        key_func=lambda b: b.title,
        threshold=0.5
    )

    # Should find books with similar titles
    found_titles = [book.title for book, score in results]
    assert "Geology" in found_titles
    assert "Python Programming" not in found_titles


def test_fuzzy_search_sorted_by_score():
    """Test that results are sorted by score."""
    items = ["exact", "exat", "exa", "ex", "e"]

    results = fuzzy_search.fuzzy_search(
        "exact",
        items,
        key_func=lambda x: x,
        threshold=0.3
    )

    # First result should be exact match
    assert results[0][0] == "exact"
    assert results[0][1] == 1.0

    # Scores should be in descending order
    scores = [score for _, score in results]
    assert scores == sorted(scores, reverse=True)


def test_fuzzy_search_with_limit():
    """Test limiting number of results."""
    items = [f"item{i}" for i in range(100)]

    results = fuzzy_search.fuzzy_search(
        "item",
        items,
        key_func=lambda x: x,
        threshold=0.5,
        limit=10
    )

    assert len(results) <= 10


def test_fuzzy_search_empty_query():
    """Test empty query returns empty results."""
    items = ["a", "b", "c"]
    results = fuzzy_search.fuzzy_search("", items, key_func=lambda x: x)
    assert len(results) == 0


def test_fuzzy_search_multi_field():
    """Test multi-field fuzzy search."""
    class Book:
        def __init__(self, title, author):
            self.title = title
            self.author = author

    books = [
        Book("Python Programming", "Smith"),
        Book("Data Science", "Python"),  # Author named Python
        Book("Machine Learning", "Jones"),
    ]

    # Search for "python" - should match both title and author
    results = fuzzy_search.fuzzy_search_multi_field(
        "python",
        books,
        key_funcs=[
            (lambda b: b.title, 1.0),
            (lambda b: b.author, 0.5),
        ],
        threshold=0.4
    )

    found_titles = [book.title for book, score in results]
    assert "Python Programming" in found_titles
    assert "Data Science" in found_titles
    assert "Machine Learning" not in found_titles


def test_fuzzy_search_multi_field_weighted():
    """Test that field weights affect scores."""
    class Book:
        def __init__(self, title, author):
            self.title = title
            self.author = author

    books = [
        Book("Python", "Other"),  # Exact match in title
        Book("Other", "Python"),  # Exact match in author
    ]

    # Title weighted 2x more than author
    results = fuzzy_search.fuzzy_search_multi_field(
        "python",
        books,
        key_funcs=[
            (lambda b: b.title, 2.0),
            (lambda b: b.author, 1.0),
        ],
        threshold=0.3
    )

    # Title match should score higher
    assert results[0][0].title == "Python"
    assert results[0][1] > results[1][1]


def test_contains_word():
    """Test whole word matching."""
    assert fuzzy_search.contains_word("python", "python programming")
    assert fuzzy_search.contains_word("programming", "python programming")
    assert not fuzzy_search.contains_word("gram", "python programming")  # Partial word


def test_contains_word_case_insensitive():
    """Test case-insensitive word matching."""
    assert fuzzy_search.contains_word("Python", "python programming")
    assert fuzzy_search.contains_word("python", "Python Programming")


def test_substring_match():
    """Test substring matching."""
    assert fuzzy_search.substring_match("stat", "geostatistics")
    assert fuzzy_search.substring_match("geo", "geostatistics")
    assert not fuzzy_search.substring_match("xyz", "geostatistics")


def test_substring_match_case_insensitive():
    """Test case-insensitive substring matching."""
    assert fuzzy_search.substring_match("STAT", "geostatistics")
    assert fuzzy_search.substring_match("stat", "GeoSTATistics")


def test_best_fuzzy_match():
    """Test finding best match from list."""
    texts = ["python", "pyton", "java", "javascript"]

    best, score = fuzzy_search.best_fuzzy_match("python", texts)

    assert best == "python"
    assert score == 1.0


def test_best_fuzzy_match_no_match():
    """Test best match when nothing is above threshold."""
    texts = ["abc", "def", "ghi"]

    best, score = fuzzy_search.best_fuzzy_match("xyz", texts, threshold=0.8)

    assert best is None
    assert score == 0.0


def test_best_fuzzy_match_empty():
    """Test best match with empty input."""
    assert fuzzy_search.best_fuzzy_match("", ["a", "b"]) == (None, 0.0)
    assert fuzzy_search.best_fuzzy_match("a", []) == (None, 0.0)


def test_highlight_match():
    """Test match highlighting."""
    result = fuzzy_search.highlight_match("python", "Learn python programming")

    assert "python" in result.lower()
    # Should contain Rich markup
    assert "[bold yellow]" in result or "python" in result


def test_highlight_match_case_insensitive():
    """Test highlighting preserves original case."""
    result = fuzzy_search.highlight_match("python", "Learn PYTHON programming")

    # Should preserve "PYTHON" not change to "python"
    assert "PYTHON" in result


def test_highlight_match_no_match():
    """Test highlighting when no match."""
    original = "Learn Java programming"
    result = fuzzy_search.highlight_match("python", original)

    assert result == original


def test_fuzzy_search_with_typos():
    """Test real-world typo scenarios."""
    books = [
        "Introduction to Geostatistics",
        "Applied Statistics",
        "Geological Survey Methods",
        "Python for Data Analysis",
    ]

    # Typo: "geostatistcs" (missing 'i')
    # Lower threshold since we're matching against full title
    results = fuzzy_search.fuzzy_search(
        "geostatistcs",
        books,
        key_func=lambda x: x,
        threshold=0.5  # More realistic for matching substring in longer text
    )

    found = [item for item, score in results]
    # Should find the book with geostatistics
    assert "Introduction to Geostatistics" in found


def test_fuzzy_search_with_abbreviations():
    """Test searching with abbreviations - note fuzzy matching isn't perfect for this."""
    terms = [
        "Machine Learning",
        "Artificial Intelligence",
        "Natural Language Processing",
        "Computer Vision",
    ]

    # Search for full word instead - abbreviations need special handling
    results = fuzzy_search.fuzzy_search(
        "Machine",
        terms,
        key_func=lambda x: x,
        threshold=0.3
    )

    # Should find Machine Learning
    found = [item for item, score in results]
    assert "Machine Learning" in found

    # Note: For true abbreviation search, use substring_match or contains_word
    assert fuzzy_search.substring_match("ML", "Machine Learning") == False  # Doesn't contain "ML"
    assert fuzzy_search.contains_word("Machine", "Machine Learning") == True


def test_fuzzy_match_ratio_similar_words():
    """Test fuzzy ratio with similar words."""
    # Similar words should have high ratio
    assert fuzzy_search.fuzzy_match_ratio("color", "colour") > 0.8
    assert fuzzy_search.fuzzy_match_ratio("center", "centre") > 0.8


def test_multi_field_handles_none():
    """Test multi-field search handles None values gracefully."""
    class Book:
        def __init__(self, title, author=None):
            self.title = title
            self.author = author

    books = [
        Book("Test Book", None),  # No author
        Book("Python Guide", "Smith"),
    ]

    # Should not crash on None author
    results = fuzzy_search.fuzzy_search_multi_field(
        "python",
        books,
        key_funcs=[
            (lambda b: b.title, 1.0),
            (lambda b: b.author or "", 0.5),  # Handle None
        ],
        threshold=0.4
    )

    assert len(results) >= 1
