"""Unified archiving service coordinating local and cloud archives.

This module provides a high-level interface for archiving URLs across multiple
services (local monolith, local WARC, Internet Archive) with proper error handling,
retry logic, and database tracking.
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
import json

from holocene.integrations.local_archive import LocalArchiveClient, ArchiveFormat
from holocene.integrations.internet_archive import InternetArchiveClient
from holocene.storage.database import HoloceneDatabase

logger = logging.getLogger(__name__)


class ArchivingService:
    """Coordinates archiving across local and cloud services."""

    def __init__(
        self,
        db: HoloceneDatabase,
        local_client: Optional[LocalArchiveClient] = None,
        ia_client: Optional[InternetArchiveClient] = None,
    ):
        """
        Initialize archiving service.

        Args:
            db: Database instance
            local_client: Local archive client (will create if None)
            ia_client: Internet Archive client (optional)
        """
        self.db = db
        self.local = local_client or LocalArchiveClient()
        self.ia = ia_client

    def archive_url(
        self,
        link_id: int,
        url: str,
        local_format: Optional[ArchiveFormat] = "monolith",
        use_ia: bool = True,
        force_ia: bool = False,
    ) -> Dict[str, Any]:
        """
        Archive a URL using configured services.

        Strategy:
        1. Try local archiving first (fast, always works offline)
        2. Try Internet Archive (slower, requires internet)
        3. Record all results in archive_snapshots table

        Args:
            link_id: Link ID in database
            url: URL to archive
            local_format: Format for local archive ('monolith' or 'warc', None to skip)
            use_ia: Whether to also archive to Internet Archive
            force_ia: Force new IA snapshot even if already archived

        Returns:
            Dict with results for each service
        """
        results = {
            "url": url,
            "link_id": link_id,
            "services": {},
            "success": False,
            "errors": [],
        }

        # 1. Local archiving
        if local_format:
            logger.info(f"[Archiving] Starting local archive ({local_format}) for {url}")

            local_result = self.local.archive_url(url, format=local_format, timeout=60)

            if local_result["status"] == "archived":
                # Record success in database
                service_name = f"local_{local_format}"
                metadata = {
                    "file_size": local_result.get("file_size"),
                    "format": local_format,
                }

                snapshot_id = self.db.add_archive_snapshot(
                    link_id=link_id,
                    service=service_name,
                    snapshot_url=local_result["local_path"],
                    archive_date=local_result["archive_date"],
                    status="success",
                    metadata=json.dumps(metadata),
                )

                results["services"][service_name] = {
                    "status": "success",
                    "snapshot_id": snapshot_id,
                    "local_path": local_result["local_path"],
                    "file_size": local_result.get("file_size"),
                }
                results["success"] = True

                logger.info(f"[Archiving] Local archive successful: {local_result['local_path']}")

            else:
                # Record failure
                service_name = f"local_{local_format}"
                error_msg = local_result.get("error", "Unknown error")

                failure = self.db.record_snapshot_failure(
                    link_id=link_id,
                    service=service_name,
                    error_message=error_msg,
                )

                results["services"][service_name] = {
                    "status": "failed",
                    "error": error_msg,
                    "attempts": failure["attempts"],
                }
                results["errors"].append(f"Local archive failed: {error_msg}")

                logger.error(f"[Archiving] Local archive failed: {error_msg}")

        # 2. Internet Archive
        if use_ia and self.ia:
            logger.info(f"[Archiving] Starting Internet Archive for {url}")

            ia_result = self.ia.save_url(url, force=force_ia)

            if ia_result["status"] in ["archived", "already_archived"]:
                # Record success
                snapshot_id = self.db.add_archive_snapshot(
                    link_id=link_id,
                    service="internet_archive",
                    snapshot_url=ia_result.get("snapshot_url"),
                    archive_date=ia_result.get("archive_date"),
                    status="success",
                )

                results["services"]["internet_archive"] = {
                    "status": "success",
                    "snapshot_id": snapshot_id,
                    "snapshot_url": ia_result.get("snapshot_url"),
                    "already_archived": ia_result["status"] == "already_archived",
                }
                results["success"] = True

                logger.info(
                    f"[Archiving] IA archive successful: {ia_result.get('snapshot_url', 'N/A')[:80]}"
                )

            else:
                # Record failure
                error_msg = ia_result.get("error", "Unknown error")

                failure = self.db.record_snapshot_failure(
                    link_id=link_id,
                    service="internet_archive",
                    error_message=error_msg,
                )

                results["services"]["internet_archive"] = {
                    "status": "failed",
                    "error": error_msg,
                    "attempts": failure["attempts"],
                }
                results["errors"].append(f"IA archive failed: {error_msg}")

                logger.error(f"[Archiving] IA archive failed: {error_msg}")

        elif use_ia and not self.ia:
            logger.warning("[Archiving] IA archiving requested but no IA client configured")
            results["errors"].append("IA client not configured")

        return results

    def get_archive_status(self, link_id: int) -> Dict[str, Any]:
        """
        Get archive status for a link across all services.

        Args:
            link_id: Link ID

        Returns:
            Dict with status for each service
        """
        snapshots = self.db.get_all_snapshots(link_id)

        status = {
            "link_id": link_id,
            "services": {},
            "total_snapshots": len(snapshots),
            "has_local": False,
            "has_cloud": False,
        }

        for snapshot in snapshots:
            service = snapshot["service"]
            status["services"][service] = {
                "snapshot_url": snapshot["snapshot_url"],
                "archive_date": snapshot["archive_date"],
                "created_at": snapshot["created_at"],
            }

            if service.startswith("local_"):
                status["has_local"] = True
            if service == "internet_archive":
                status["has_cloud"] = True

        return status

    def retry_failed_archives(self, max_retries: int = 3) -> Dict[str, Any]:
        """
        Retry failed archive attempts that are eligible for retry.

        Uses exponential backoff - only retries if next_retry_after has passed.

        Args:
            max_retries: Maximum number of retry attempts

        Returns:
            Dict with retry results
        """
        # Get eligible failed snapshots
        cursor = self.db.conn.cursor()
        now = datetime.now().isoformat()

        cursor.execute(
            """
            SELECT DISTINCT link_id, service
            FROM archive_snapshots
            WHERE status = 'failed'
              AND attempts < ?
              AND (next_retry_after IS NULL OR next_retry_after <= ?)
            ORDER BY next_retry_after ASC
            LIMIT 50
        """,
            (max_retries, now),
        )

        failed_snapshots = cursor.fetchall()

        results = {
            "retried": 0,
            "succeeded": 0,
            "failed": 0,
            "details": [],
        }

        for link_id, service in failed_snapshots:
            # Get URL
            link = cursor.execute(
                "SELECT url FROM links WHERE id = ?", (link_id,)
            ).fetchone()

            if not link:
                continue

            url = link[0]
            results["retried"] += 1

            logger.info(f"[Archiving] Retrying {service} for {url}")

            # Determine archive method
            if service.startswith("local_"):
                format = service.replace("local_", "")
                result = self.archive_url(
                    link_id=link_id,
                    url=url,
                    local_format=format,
                    use_ia=False,
                )
            elif service == "internet_archive":
                result = self.archive_url(
                    link_id=link_id,
                    url=url,
                    local_format=None,
                    use_ia=True,
                    force_ia=True,
                )
            else:
                logger.warning(f"[Archiving] Unknown service: {service}")
                continue

            if result["success"]:
                results["succeeded"] += 1
            else:
                results["failed"] += 1

            results["details"].append(
                {
                    "link_id": link_id,
                    "url": url,
                    "service": service,
                    "success": result["success"],
                }
            )

        return results

    def get_tool_info(self) -> Dict[str, Any]:
        """Get information about available archiving tools."""
        info = {
            "local": self.local.get_tool_info(),
            "internet_archive": {
                "available": self.ia is not None,
                "authenticated": self.ia and (self.ia.access_key is not None),
            },
        }

        return info
