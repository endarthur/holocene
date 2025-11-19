"""Calibre library integration using calibredb CLI."""

import subprocess
from pathlib import Path
from typing import Optional, List


class CalibreIntegration:
    """Integrate with Calibre library using calibredb CLI."""

    def __init__(
        self,
        library_path: Optional[Path] = None,
        content_server_port: int = 8080,
        username: Optional[str] = None,
        password: Optional[str] = None
    ):
        """
        Initialize Calibre integration.

        Args:
            library_path: Path to Calibre library (uses default if None)
            content_server_port: Port for Calibre Content server (default 8080)
            username: Username for Content server authentication (optional)
            password: Password for Content server authentication (optional)
        """
        self.library_path = library_path
        self.content_server_port = content_server_port
        self.username = username
        self.password = password

    def _is_calibre_running(self) -> bool:
        """
        Check if Calibre GUI is currently running.

        Returns:
            True if Calibre is running
        """
        try:
            # Try a simple list command with --library-path
            # If Calibre is running, this will fail with a specific error
            result = subprocess.run(
                ["calibredb", "list", "--limit", "1", "--library-path", str(self.library_path)],
                capture_output=True,
                text=True,
                timeout=5
            )
            # Check if error message indicates Calibre is running
            if "Another calibre program" in result.stderr:
                return True
            return False
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _get_library_args(self) -> List[str]:
        """
        Get the appropriate library arguments based on whether Calibre is running.

        Returns:
            List of command-line arguments for library specification
        """
        if not self.library_path:
            return []

        # Check if Calibre GUI is running
        if self._is_calibre_running():
            # Use --with-library to connect to running Calibre via Content server
            # Just use base URL - Content server knows its own library
            library_url = f"http://localhost:{self.content_server_port}"

            args = ["--with-library", library_url]

            # Add authentication if configured
            if self.username:
                args.extend(["--username", self.username])
            if self.password:
                args.extend(["--password", self.password])

            return args
        else:
            # Use --library-path for direct access
            return ["--library-path", str(self.library_path)]

    def add_book(
        self,
        pdf_path: Path,
        title: str,
        authors: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        isbn: Optional[str] = None,
        publisher: Optional[str] = None,
        pubdate: Optional[str] = None,
        comments: Optional[str] = None
    ) -> bool:
        """
        Add a book to Calibre library.

        Args:
            pdf_path: Path to PDF file
            title: Book title
            authors: List of author names
            tags: List of tags
            isbn: ISBN
            publisher: Publisher name
            pubdate: Publication date
            comments: Comments/description

        Returns:
            True if successful
        """
        if not pdf_path.exists():
            print(f"⚠️  PDF not found: {pdf_path}")
            return False

        # Build calibredb command - must add file first, then set metadata
        cmd = ["calibredb", "add", str(pdf_path)]

        # Add library arguments (auto-detects if Calibre is running)
        cmd.extend(self._get_library_args())

        # Add basic metadata during import (supported by 'add' command)
        if title:
            cmd.extend(["-t", title])

        if authors:
            cmd.extend(["-a", " & ".join(authors)])

        if tags:
            cmd.extend(["-T", ", ".join(tags)])

        if isbn:
            cmd.extend(["-i", isbn])

        # Execute add command
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode != 0:
                print(f"⚠️  Calibre error: {result.stderr}")
                return False

            # Extract book ID from output
            # Output format: "Added book ids: 123"
            book_id = None
            for line in result.stdout.split('\n'):
                if 'Added book ids:' in line:
                    book_id = line.split(':')[1].strip()
                    break

            # Set additional metadata if book was added successfully
            if book_id and (comments or pubdate or publisher):
                self._set_metadata(book_id, comments=comments, pubdate=pubdate, publisher=publisher)

            print(f"✓ Added to Calibre: {title}")
            return True

        except subprocess.TimeoutExpired:
            print("⚠️  Calibre add timed out")
            return False
        except FileNotFoundError:
            print("⚠️  calibredb not found. Is Calibre installed?")
            return False
        except Exception as e:
            print(f"⚠️  Error adding to Calibre: {e}")
            return False

    def _set_metadata(
        self,
        book_id: str,
        comments: Optional[str] = None,
        pubdate: Optional[str] = None,
        publisher: Optional[str] = None
    ):
        """
        Set additional metadata on a book after adding.

        Args:
            book_id: Calibre book ID
            comments: Book comments/description
            pubdate: Publication date
            publisher: Publisher name
        """
        cmd = ["calibredb", "set_metadata", book_id]

        # Add library arguments (auto-detects if Calibre is running)
        cmd.extend(self._get_library_args())

        # Build field arguments
        fields = []
        if comments:
            fields.extend(["--field", f"comments:{comments}"])
        if pubdate:
            fields.extend(["--field", f"pubdate:{pubdate}"])
        if publisher:
            fields.extend(["--field", f"publisher:{publisher}"])

        if fields:
            cmd.extend(fields)
            try:
                subprocess.run(cmd, capture_output=True, timeout=30)
            except (subprocess.TimeoutExpired, Exception):
                pass  # Non-critical, don't fail if metadata setting fails

    def is_available(self) -> bool:
        """
        Check if calibredb is available.

        Returns:
            True if calibredb can be executed
        """
        try:
            result = subprocess.run(
                ["calibredb", "--version"],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def list_books(self, limit: int = 10) -> List[dict]:
        """
        List books in Calibre library.

        Args:
            limit: Maximum number of books to return

        Returns:
            List of book dicts
        """
        cmd = ["calibredb", "list", "--for-machine", "--limit", str(limit)]

        # Add library arguments (auto-detects if Calibre is running)
        cmd.extend(self._get_library_args())

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                import json
                return json.loads(result.stdout)
            else:
                return []

        except Exception:
            return []
