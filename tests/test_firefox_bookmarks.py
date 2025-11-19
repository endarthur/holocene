"""Tests for Firefox bookmark import functionality."""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from holocene.integrations.bookmarks import BookmarksReader, Bookmark


@pytest.fixture
def firefox_places_db():
    """Create a temporary Firefox places.sqlite database with test bookmarks."""
    # Create a temporary database
    with tempfile.NamedTemporaryFile(delete=False, suffix=".sqlite") as tmp_file:
        db_path = Path(tmp_file.name)

    # Create Firefox schema and add test data
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create moz_places table (simplified)
    cursor.execute("""
        CREATE TABLE moz_places (
            id INTEGER PRIMARY KEY,
            url TEXT,
            title TEXT
        )
    """)

    # Create moz_bookmarks table (simplified)
    cursor.execute("""
        CREATE TABLE moz_bookmarks (
            id INTEGER PRIMARY KEY,
            type INTEGER,
            fk INTEGER,
            title TEXT,
            dateAdded INTEGER,
            lastModified INTEGER,
            guid TEXT
        )
    """)

    # Insert test URLs
    test_urls = [
        (1, "https://python.org", "Python"),
        (2, "https://github.com", "GitHub"),
        (3, "https://stackoverflow.com", "Stack Overflow"),
    ]

    for url_id, url, title in test_urls:
        cursor.execute(
            "INSERT INTO moz_places (id, url, title) VALUES (?, ?, ?)",
            (url_id, url, title),
        )

    # Insert test bookmarks
    test_bookmarks = [
        (1, 1, 1, "Python Homepage", 1700000000000000, 1700000000000000, "bookmark1"),
        (2, 1, 2, "GitHub", 1700000000000000, 1700000000000000, "bookmark2"),
        (3, 1, 3, "Stack Overflow", 1700000000000000, 1700000000000000, "bookmark3"),
        # Add a folder (type 2) - should be ignored
        (4, 2, None, "My Folder", 1700000000000000, 1700000000000000, "folder1"),
        # Add a separator (type 3) - should be ignored
        (5, 3, None, None, 1700000000000000, 1700000000000000, "separator1"),
    ]

    for bm_id, bm_type, fk, title, date_added, date_modified, guid in test_bookmarks:
        cursor.execute(
            "INSERT INTO moz_bookmarks (id, type, fk, title, dateAdded, lastModified, guid) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (bm_id, bm_type, fk, title, date_added, date_modified, guid),
        )

    conn.commit()
    conn.close()

    yield db_path

    # Cleanup
    db_path.unlink()


def test_read_firefox_bookmarks(firefox_places_db):
    """Test reading bookmarks from Firefox places.sqlite database."""
    reader = BookmarksReader()
    bookmarks = reader._read_firefox_bookmarks(firefox_places_db)

    # Should have 3 bookmarks (folders and separators ignored)
    assert len(bookmarks) == 3

    # Check first bookmark
    assert bookmarks[0].name == "Python Homepage"
    assert bookmarks[0].url == "https://python.org"
    assert bookmarks[0].guid == "bookmark1"

    # Check URLs
    urls = [b.url for b in bookmarks]
    assert "https://python.org" in urls
    assert "https://github.com" in urls
    assert "https://stackoverflow.com" in urls


def test_firefox_bookmarks_with_missing_data(firefox_places_db):
    """Test handling of bookmarks with missing data."""
    # Add a bookmark with NULL title
    conn = sqlite3.connect(firefox_places_db)
    cursor = conn.cursor()

    cursor.execute("INSERT INTO moz_places (id, url, title) VALUES (?, ?, ?)", (4, "https://example.com", None))
    cursor.execute(
        "INSERT INTO moz_bookmarks (id, type, fk, title, dateAdded, lastModified, guid) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (6, 1, 4, None, 1700000000000000, 1700000000000000, "bookmark4"),
    )

    conn.commit()
    conn.close()

    reader = BookmarksReader()
    bookmarks = reader._read_firefox_bookmarks(firefox_places_db)

    # Should still read the bookmark
    assert len(bookmarks) == 4

    # Find the bookmark with no title
    bookmark = next((b for b in bookmarks if b.url == "https://example.com"), None)
    assert bookmark is not None
    assert bookmark.name == ""  # Should default to empty string


def test_read_bookmarks_firefox_option():
    """Test read_bookmarks with browser='firefox' option."""
    reader = BookmarksReader()

    # This will attempt to read from actual Firefox profile
    # In a real test environment, this should be mocked or we should
    # set up a proper test profile. For now, just verify it doesn't crash.
    bookmarks = reader.read_bookmarks(browser="firefox")

    # Result can be empty if Firefox isn't installed or has no bookmarks
    assert isinstance(bookmarks, list)


def test_bookmark_to_dict():
    """Test Bookmark.to_dict() method."""
    bookmark_data = {
        "name": "Test Bookmark",
        "url": "https://example.com",
        "date_added": 1700000000000000,
        "date_modified": 1700000000000000,
        "guid": "test123",
    }

    bookmark = Bookmark(bookmark_data)
    result = bookmark.to_dict()

    assert result["name"] == "Test Bookmark"
    assert result["url"] == "https://example.com"
    assert result["date_added"] == 1700000000000000
    assert result["date_modified"] == 1700000000000000
    assert "guid" not in result  # guid is not included in to_dict()


def test_firefox_locked_database(firefox_places_db):
    """Test reading from a locked Firefox database (should copy to temp file)."""
    # This test verifies the copy-to-temp strategy works
    # Open a connection to "lock" the database
    conn = sqlite3.connect(firefox_places_db)

    try:
        reader = BookmarksReader()
        # Should still work because we copy to temp file
        bookmarks = reader._read_firefox_bookmarks(firefox_places_db)

        assert len(bookmarks) == 3

    finally:
        conn.close()
