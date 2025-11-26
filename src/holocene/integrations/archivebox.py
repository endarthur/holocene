"""ArchiveBox integration for comprehensive web archiving.

ArchiveBox provides multi-format archiving with:
- SingleFile HTML with embedded assets
- WARC archives
- Screenshots
- PDF snapshots
- Media downloads
- DOM snapshots

Integrates via SSH to archivebox-rei LXC container.
"""

import subprocess
import logging
import json
from typing import Optional, Dict, Any
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class ArchiveBoxClient:
    """Client for ArchiveBox via SSH."""

    def __init__(
        self,
        ssh_host: str = "192.168.1.102",
        ssh_user: str = "holocene",
        data_dir: str = "/opt/archivebox/data",
    ):
        """
        Initialize ArchiveBox client.

        Args:
            ssh_host: ArchiveBox server hostname/IP
            ssh_user: SSH user for connection
            data_dir: ArchiveBox data directory on remote server
        """
        self.ssh_host = ssh_host
        self.ssh_user = ssh_user
        self.data_dir = data_dir

        # Check SSH connectivity
        self.available = self._check_connectivity()
        if not self.available:
            logger.warning(
                f"ArchiveBox not available at {ssh_user}@{ssh_host} - "
                "archives will be skipped"
            )

    def _check_connectivity(self) -> bool:
        """Check if we can SSH to ArchiveBox server."""
        try:
            result = subprocess.run(
                [
                    "ssh",
                    "-o", "ConnectTimeout=5",
                    "-o", "BatchMode=yes",  # Don't prompt for password
                    f"{self.ssh_user}@{self.ssh_host}",
                    "echo ok"
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0 and "ok" in result.stdout
        except Exception as e:
            logger.error(f"[ArchiveBox] Connectivity check failed: {e}")
            return False

    def _run_command(
        self,
        command: str,
        timeout: int = 120
    ) -> Dict[str, Any]:
        """
        Run ArchiveBox command via SSH.

        Args:
            command: ArchiveBox command to run
            timeout: Command timeout in seconds

        Returns:
            Dict with stdout, stderr, returncode
        """
        full_command = (
            f"cd {self.data_dir} && "
            f"sudo -u archivebox archivebox {command}"
        )

        try:
            logger.debug(f"[ArchiveBox] Running: {command}")
            result = subprocess.run(
                [
                    "ssh",
                    f"{self.ssh_user}@{self.ssh_host}",
                    full_command
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            }

        except subprocess.TimeoutExpired as e:
            logger.error(f"[ArchiveBox] Command timed out after {timeout}s")
            return {
                "stdout": "",
                "stderr": f"Command timed out after {timeout}s",
                "returncode": -1,
            }
        except Exception as e:
            logger.error(f"[ArchiveBox] Command failed: {e}")
            return {
                "stdout": "",
                "stderr": str(e),
                "returncode": -1,
            }

    def archive_url(
        self,
        url: str,
        timeout: int = 180,
        extractors: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Archive a URL using ArchiveBox.

        Args:
            url: URL to archive
            timeout: Timeout in seconds (archiving can be slow)
            extractors: Comma-separated list of extractors to use
                       (e.g., "singlefile,screenshot,pdf")
                       None = use ArchiveBox defaults (all extractors)

        Returns:
            Dict with status, archive_url, snapshot_id, and optional error
        """
        if not self.available:
            return {
                "status": "error",
                "url": url,
                "error": "ArchiveBox not available",
                "message": f"Cannot connect to {self.ssh_user}@{self.ssh_host}",
            }

        # Build command
        command = f"add '{url}'"
        if extractors:
            command += f" --extractors={extractors}"

        logger.info(f"[ArchiveBox] Archiving {url}...")

        result = self._run_command(command, timeout=timeout)

        if result["returncode"] == 0:
            # Parse output to get snapshot info
            # ArchiveBox output includes: "√ Added 1 new links to index"
            snapshot_id = self._extract_snapshot_id(result["stdout"], url)

            logger.info(f"[ArchiveBox] Success: {url} (snapshot: {snapshot_id})")

            return {
                "status": "archived",
                "url": url,
                "snapshot_id": snapshot_id,
                "archive_url": f"http://{self.ssh_host}:8000/archive/{snapshot_id}",
                "archive_date": datetime.now().isoformat(),
                "message": "Successfully archived with ArchiveBox",
            }
        else:
            error_msg = result["stderr"].strip() or result["stdout"].strip()
            logger.error(f"[ArchiveBox] Failed: {error_msg}")

            return {
                "status": "error",
                "url": url,
                "error": error_msg,
                "message": f"ArchiveBox failed: {error_msg[:200]}",
            }

    def _extract_snapshot_id(self, output: str, url: str) -> Optional[str]:
        """
        Extract snapshot ID from ArchiveBox output.

        ArchiveBox uses timestamp-based IDs like 1764018763.676681
        """
        # Try to find the snapshot directory in output
        # Format: /opt/archivebox/data/archive/1764018763.676681
        import re
        match = re.search(r'/archive/(\d+\.\d+)', output)
        if match:
            return match.group(1)

        # Fallback: get latest snapshot ID via list command
        try:
            list_result = self._run_command(f"list --json | tail -1", timeout=10)
            if list_result["returncode"] == 0:
                data = json.loads(list_result["stdout"])
                if data.get("url") == url:
                    return data.get("timestamp")
        except Exception as e:
            logger.debug(f"[ArchiveBox] Could not extract snapshot ID: {e}")

        return None

    def get_snapshot_info(self, snapshot_id: str) -> Dict[str, Any]:
        """
        Get information about an archived snapshot.

        Args:
            snapshot_id: ArchiveBox snapshot ID (timestamp)

        Returns:
            Dict with snapshot details
        """
        if not self.available:
            return {"status": "error", "error": "ArchiveBox not available"}

        # Get snapshot details via list command
        result = self._run_command(
            f"list --json --filter-type=search --filter={snapshot_id}",
            timeout=10
        )

        if result["returncode"] == 0:
            try:
                data = json.loads(result["stdout"])
                return {
                    "status": "found",
                    "snapshot_id": snapshot_id,
                    "url": data.get("url"),
                    "title": data.get("title"),
                    "timestamp": data.get("timestamp"),
                }
            except json.JSONDecodeError:
                pass

        return {
            "status": "not_found",
            "snapshot_id": snapshot_id,
        }

    def get_queue_status(self) -> Dict[str, Any]:
        """
        Get ArchiveBox queue status (pending/failed snapshots).

        Returns:
            Dict with pending_count, failed_count, and whether it's safe to add more
        """
        if not self.available:
            return {
                "available": False,
                "pending_count": 0,
                "failed_count": 0,
                "can_add_more": False,
                "error": "ArchiveBox not available",
            }

        # Get pending count
        pending_result = self._run_command(
            "list --status=pending --json 2>/dev/null | wc -l",
            timeout=15
        )
        pending_count = 0
        if pending_result["returncode"] == 0:
            try:
                pending_count = int(pending_result["stdout"].strip())
            except ValueError:
                pass

        # Get failed/incomplete count (might need re-archiving)
        failed_result = self._run_command(
            "list --status=incomplete --json 2>/dev/null | wc -l",
            timeout=15
        )
        failed_count = 0
        if failed_result["returncode"] == 0:
            try:
                failed_count = int(failed_result["stdout"].strip())
            except ValueError:
                pass

        return {
            "available": True,
            "pending_count": pending_count,
            "failed_count": failed_count,
            "can_add_more": pending_count < 20,  # Threshold
            "message": f"{pending_count} pending, {failed_count} incomplete",
        }

    def get_server_info(self) -> Dict[str, Any]:
        """Get ArchiveBox server information."""
        if not self.available:
            return {
                "available": False,
                "host": f"{self.ssh_user}@{self.ssh_host}",
                "error": "Not connected",
            }

        # Get version
        result = self._run_command("version", timeout=10)
        version = "unknown"
        if result["returncode"] == 0:
            # Parse version from output
            import re
            match = re.search(r'ArchiveBox v([\d.]+)', result["stdout"])
            if match:
                version = match.group(1)

        # Get stats
        stats_result = self._run_command("status", timeout=10)
        total_snapshots = 0
        if stats_result["returncode"] == 0:
            # Parse snapshot count from status output
            import re
            match = re.search(r'(\d+)\s+Snapshots', stats_result["stdout"])
            if match:
                total_snapshots = int(match.group(1))

        return {
            "available": True,
            "host": f"{self.ssh_user}@{self.ssh_host}",
            "version": version,
            "data_dir": self.data_dir,
            "web_ui": f"http://{self.ssh_host}:8000",
            "total_snapshots": total_snapshots,
        }
