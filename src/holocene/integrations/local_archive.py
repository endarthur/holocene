"""Local archiving integration for saving web pages locally.

Supports multiple archiving formats:
- monolith: Single HTML file with embedded assets (fast, browser-viewable)
- wget WARC: ISO standard web archive format (preservation-grade)
"""

import subprocess
import shutil
import logging
from pathlib import Path
from typing import Optional, Dict, Any, Literal
from datetime import datetime
from urllib.parse import urlparse
import hashlib

logger = logging.getLogger(__name__)

ArchiveFormat = Literal["monolith", "warc"]


class LocalArchiveClient:
    """Client for local web page archiving."""

    def __init__(self, archive_dir: Optional[Path] = None):
        """
        Initialize local archive client.

        Args:
            archive_dir: Directory to store archives (default: ~/.holocene/archives/)
        """
        if archive_dir is None:
            archive_dir = Path.home() / ".holocene" / "archives"

        self.archive_dir = Path(archive_dir)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

        # Check available tools
        self.has_monolith = self._check_tool("monolith")
        self.has_wget = self._check_tool("wget")

        if not self.has_monolith and not self.has_wget:
            logger.warning("No local archiving tools found. Install monolith or wget.")

    def _check_tool(self, tool: str) -> bool:
        """Check if a tool is available in PATH."""
        return shutil.which(tool) is not None

    def _url_to_filename(self, url: str, format: ArchiveFormat) -> str:
        """
        Generate a safe filename from URL.

        Uses hash of URL to avoid filesystem issues with special characters.
        Format: {domain}_{hash}_{timestamp}.{ext}

        Args:
            url: URL to archive
            format: Archive format (determines extension)

        Returns:
            Safe filename
        """
        parsed = urlparse(url)
        domain = parsed.netloc.replace(":", "_")

        # Use first 8 chars of URL hash for uniqueness
        url_hash = hashlib.sha256(url.encode()).hexdigest()[:8]

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        ext = "html" if format == "monolith" else "warc.gz"

        return f"{domain}_{url_hash}_{timestamp}.{ext}"

    def _get_archive_path(self, url: str, format: ArchiveFormat) -> Path:
        """Get full path for archive file."""
        filename = self._url_to_filename(url, format)

        # Organize by format subdirectory
        format_dir = self.archive_dir / format
        format_dir.mkdir(parents=True, exist_ok=True)

        return format_dir / filename

    def archive_with_monolith(self, url: str, timeout: int = 60) -> Dict[str, Any]:
        """
        Archive URL using monolith (single HTML file).

        Args:
            url: URL to archive
            timeout: Timeout in seconds

        Returns:
            Dict with status, local_path, and optional error
        """
        if not self.has_monolith:
            return {
                "status": "error",
                "url": url,
                "error": "monolith not installed",
                "message": "Install monolith: cargo install monolith",
            }

        output_path = self._get_archive_path(url, "monolith")

        try:
            logger.info(f"[LocalArchive] Archiving {url} with monolith...")

            # Run monolith with options:
            # -j: Include JavaScript
            # -i: Include images
            # -I: Isolate document (prevent external requests)
            result = subprocess.run(
                ["monolith", "-j", "-i", "-I", url, "-o", str(output_path)],
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            if result.returncode == 0:
                file_size = output_path.stat().st_size
                logger.info(f"[LocalArchive] Success: {output_path} ({file_size:,} bytes)")

                return {
                    "status": "archived",
                    "url": url,
                    "local_path": str(output_path),
                    "file_size": file_size,
                    "archive_date": datetime.now().isoformat(),
                    "message": "Successfully archived with monolith",
                }
            else:
                error_msg = result.stderr.strip() or result.stdout.strip()
                logger.error(f"[LocalArchive] Monolith failed: {error_msg}")

                return {
                    "status": "error",
                    "url": url,
                    "error": error_msg,
                    "message": f"Monolith failed: {error_msg}",
                }

        except subprocess.TimeoutExpired:
            logger.error(f"[LocalArchive] Monolith timed out after {timeout}s")
            return {
                "status": "error",
                "url": url,
                "error": f"Timeout after {timeout}s",
                "message": f"Archiving timed out after {timeout}s",
            }
        except Exception as e:
            logger.error(f"[LocalArchive] Exception: {e}")
            return {
                "status": "error",
                "url": url,
                "error": str(e),
                "message": f"Failed to archive: {e}",
            }

    def archive_with_warc(self, url: str, timeout: int = 120) -> Dict[str, Any]:
        """
        Archive URL using wget WARC format.

        Args:
            url: URL to archive
            timeout: Timeout in seconds

        Returns:
            Dict with status, local_path, and optional error
        """
        if not self.has_wget:
            return {
                "status": "error",
                "url": url,
                "error": "wget not installed",
                "message": "wget not available on system",
            }

        output_path = self._get_archive_path(url, "warc")
        warc_base = output_path.stem.replace(".warc", "")  # Remove .warc from stem

        try:
            logger.info(f"[LocalArchive] Archiving {url} with wget WARC...")

            # Run wget with WARC options:
            # --warc-file: Output WARC file
            # --warc-cdx: Generate CDX index
            # --page-requisites: Download assets
            # --adjust-extension: Add .html to HTML files
            # --convert-links: Convert links for offline browsing
            # --no-directories: Flat structure
            # --timeout: Connection timeout
            result = subprocess.run(
                [
                    "wget",
                    "--warc-file", str(output_path.parent / warc_base),
                    "--warc-cdx",
                    "--page-requisites",
                    "--adjust-extension",
                    "--convert-links",
                    "--no-directories",
                    "--timeout", "30",
                    url,
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(output_path.parent),
            )

            # Check if WARC file was created
            if output_path.exists():
                file_size = output_path.stat().st_size
                logger.info(f"[LocalArchive] Success: {output_path} ({file_size:,} bytes)")

                return {
                    "status": "archived",
                    "url": url,
                    "local_path": str(output_path),
                    "file_size": file_size,
                    "archive_date": datetime.now().isoformat(),
                    "message": "Successfully archived with wget WARC",
                }
            else:
                error_msg = result.stderr.strip() or "WARC file not created"
                logger.error(f"[LocalArchive] Wget failed: {error_msg}")

                return {
                    "status": "error",
                    "url": url,
                    "error": error_msg,
                    "message": f"Wget failed: {error_msg}",
                }

        except subprocess.TimeoutExpired:
            logger.error(f"[LocalArchive] Wget timed out after {timeout}s")
            return {
                "status": "error",
                "url": url,
                "error": f"Timeout after {timeout}s",
                "message": f"Archiving timed out after {timeout}s",
            }
        except Exception as e:
            logger.error(f"[LocalArchive] Exception: {e}")
            return {
                "status": "error",
                "url": url,
                "error": str(e),
                "message": f"Failed to archive: {e}",
            }

    def archive_url(
        self,
        url: str,
        format: ArchiveFormat = "monolith",
        timeout: int = 60,
    ) -> Dict[str, Any]:
        """
        Archive a URL in the specified format.

        Args:
            url: URL to archive
            format: Archive format ('monolith' or 'warc')
            timeout: Timeout in seconds

        Returns:
            Dict with archiving result
        """
        if format == "monolith":
            return self.archive_with_monolith(url, timeout)
        elif format == "warc":
            return self.archive_with_warc(url, timeout)
        else:
            return {
                "status": "error",
                "url": url,
                "error": f"Unknown format: {format}",
                "message": f"Format must be 'monolith' or 'warc', got '{format}'",
            }

    def get_available_formats(self) -> list[ArchiveFormat]:
        """Get list of available archive formats based on installed tools."""
        formats = []
        if self.has_monolith:
            formats.append("monolith")
        if self.has_wget:
            formats.append("warc")
        return formats

    def get_tool_info(self) -> Dict[str, Any]:
        """Get information about available archiving tools."""
        return {
            "monolith": {
                "available": self.has_monolith,
                "description": "Single HTML file with embedded assets (fast, browser-viewable)",
                "install": "cargo install monolith",
            },
            "wget": {
                "available": self.has_wget,
                "description": "ISO standard WARC format (preservation-grade)",
                "install": "System package manager (apt, brew, etc.)",
            },
            "archive_dir": str(self.archive_dir),
        }
