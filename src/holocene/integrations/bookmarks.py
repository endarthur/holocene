"""Browser bookmarks reader for Chrome/Edge/Firefox."""

import json
import sqlite3
import shutil
import tempfile
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime


class Bookmark:
    """Represents a browser bookmark."""

    def __init__(self, data: dict):
        self.name = data.get("name", "")
        self.url = data.get("url", "")
        self.date_added = data.get("date_added")
        self.date_modified = data.get("date_modified")
        self.guid = data.get("guid", "")

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "url": self.url,
            "date_added": self.date_added,
            "date_modified": self.date_modified,
        }


class BookmarksReader:
    """Reads bookmarks from Chrome/Edge."""

    def __init__(self):
        """Initialize bookmarks reader."""
        self.bookmarks_paths = self._get_bookmarks_paths()

    def _get_bookmarks_paths(self) -> List[Path]:
        """Get potential bookmarks file locations for Chrome/Edge."""
        paths = []

        # Windows paths
        if Path.home().drive:
            # Edge
            edge_path = Path.home() / "AppData/Local/Microsoft/Edge/User Data/Default/Bookmarks"
            paths.append(edge_path)

            # Chrome
            chrome_path = Path.home() / "AppData/Local/Google/Chrome/User Data/Default/Bookmarks"
            paths.append(chrome_path)

        # Linux paths
        else:
            paths.append(Path.home() / ".config/microsoft-edge/Default/Bookmarks")
            paths.append(Path.home() / ".config/google-chrome/Default/Bookmarks")

        return paths

    def _get_firefox_paths(self) -> List[Path]:
        """Get potential Firefox profile paths."""
        paths = []

        # Windows
        if Path.home().drive:
            firefox_dir = Path.home() / "AppData/Roaming/Mozilla/Firefox/Profiles"
            if firefox_dir.exists():
                # Firefox uses profile directories with random names like "xxxxxxxx.default-release"
                for profile_dir in firefox_dir.iterdir():
                    if profile_dir.is_dir():
                        places_db = profile_dir / "places.sqlite"
                        if places_db.exists():
                            paths.append(places_db)

        # Linux
        else:
            firefox_dir = Path.home() / ".mozilla/firefox"
            if firefox_dir.exists():
                for profile_dir in firefox_dir.iterdir():
                    if profile_dir.is_dir():
                        places_db = profile_dir / "places.sqlite"
                        if places_db.exists():
                            paths.append(places_db)

        return paths

    def _parse_bookmark_tree(self, node: dict, bookmarks: List[Bookmark]):
        """Recursively parse bookmark tree."""
        if node.get("type") == "url":
            # It's a bookmark
            bookmarks.append(Bookmark(node))
        elif node.get("type") == "folder":
            # It's a folder, recurse into children
            for child in node.get("children", []):
                self._parse_bookmark_tree(child, bookmarks)

    def _read_firefox_bookmarks(self, db_path: Path) -> List[Bookmark]:
        """
        Read bookmarks from Firefox places.sqlite database.

        Firefox can lock the database, so we copy it to a temp location first.
        """
        bookmarks = []

        # Copy database to temp location (Firefox may have it locked)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".sqlite") as tmp_file:
            tmp_path = Path(tmp_file.name)

        try:
            shutil.copy2(db_path, tmp_path)

            # Connect to the copy
            conn = sqlite3.connect(tmp_path)
            cursor = conn.cursor()

            # Query bookmarks from Firefox database
            # Join moz_bookmarks (bookmark metadata) with moz_places (URLs)
            query = """
                SELECT
                    b.title,
                    p.url,
                    b.dateAdded,
                    b.lastModified,
                    b.guid
                FROM moz_bookmarks b
                JOIN moz_places p ON b.fk = p.id
                WHERE b.type = 1  -- Type 1 is bookmark (not folder or separator)
                AND p.url IS NOT NULL
            """

            cursor.execute(query)
            rows = cursor.fetchall()

            for row in rows:
                title, url, date_added, date_modified, guid = row

                # Firefox stores timestamps as microseconds since epoch
                # Convert to Chrome format (microseconds since Windows epoch)
                # For simplicity, we'll just use the raw values
                bookmark_data = {
                    "name": title or "",
                    "url": url or "",
                    "date_added": date_added,
                    "date_modified": date_modified,
                    "guid": guid or "",
                }
                bookmarks.append(Bookmark(bookmark_data))

            conn.close()

        finally:
            # Clean up temp file
            if tmp_path.exists():
                tmp_path.unlink()

        return bookmarks

    def read_bookmarks(self, browser: str = "auto") -> List[Bookmark]:
        """
        Read bookmarks from browser.

        Args:
            browser: "edge", "chrome", "firefox", or "auto" (tries all)

        Returns:
            List of Bookmark objects
        """
        bookmarks = []

        # Handle Firefox separately (SQLite database)
        if browser in ["firefox", "auto"]:
            firefox_paths = self._get_firefox_paths()
            for db_path in firefox_paths:
                try:
                    firefox_bookmarks = self._read_firefox_bookmarks(db_path)
                    if firefox_bookmarks:
                        bookmarks.extend(firefox_bookmarks)
                        # If we're specifically looking for Firefox, return now
                        if browser == "firefox":
                            return bookmarks
                except Exception:
                    continue

        # Handle Chrome/Edge (JSON files)
        if browser not in ["firefox"]:
            paths_to_try = []
            if browser == "auto":
                paths_to_try = self.bookmarks_paths
            elif browser == "edge":
                paths_to_try = [p for p in self.bookmarks_paths if "Edge" in str(p)]
            elif browser == "chrome":
                paths_to_try = [p for p in self.bookmarks_paths if "Chrome" in str(p)]

            for path in paths_to_try:
                if path.exists():
                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            data = json.load(f)

                        # Parse bookmark tree
                        roots = data.get("roots", {})
                        for root_name, root_node in roots.items():
                            if root_name in ["bookmark_bar", "other", "synced"]:
                                self._parse_bookmark_tree(root_node, bookmarks)

                        # If we found bookmarks and we're not in auto mode, return them
                        if bookmarks and browser != "auto":
                            return bookmarks

                    except Exception:
                        continue

        return bookmarks

    def get_bookmark_urls(self, browser: str = "auto") -> List[str]:
        """Get just the URLs from bookmarks."""
        bookmarks = self.read_bookmarks(browser)
        return [b.url for b in bookmarks if b.url]
