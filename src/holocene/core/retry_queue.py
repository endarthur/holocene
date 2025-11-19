"""
Retry queue for failed operations with exponential backoff.

Provides persistent queue for retrying failed API calls, downloads, and other operations.
"""

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("holocene.retry_queue")


class RetryQueue:
    """
    SQLite-backed retry queue with exponential backoff.

    Tracks failed operations and manages retry scheduling with
    configurable backoff strategies.
    """

    def __init__(
        self,
        db_path: Path | str,
        max_attempts: int = 5,
        base_backoff_seconds: int = 60,
        max_backoff_seconds: int = 86400,  # 24 hours
    ):
        """
        Initialize retry queue.

        Args:
            db_path: Path to SQLite database
            max_attempts: Maximum retry attempts before giving up
            base_backoff_seconds: Base delay for exponential backoff (default 60s)
            max_backoff_seconds: Maximum backoff delay (default 24 hours)
        """
        self.db_path = Path(db_path)
        self.max_attempts = max_attempts
        self.base_backoff_seconds = base_backoff_seconds
        self.max_backoff_seconds = max_backoff_seconds

        # Ensure database directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize database and create table
        self._init_db()

        logger.debug(
            f"Initialized retry queue: {db_path} "
            f"(max_attempts={max_attempts}, base_backoff={base_backoff_seconds}s)"
        )

    def _init_db(self):
        """Create retry_queue table if it doesn't exist."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS retry_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                operation_type TEXT NOT NULL,
                operation_key TEXT NOT NULL,
                operation_data TEXT NOT NULL,
                error_message TEXT,
                attempt_count INTEGER DEFAULT 0,
                max_attempts INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                last_attempt_at TEXT,
                next_retry_at TEXT,
                status TEXT DEFAULT 'pending',
                completed_at TEXT,
                UNIQUE(operation_type, operation_key)
            )
            """
        )

        # Index for efficient querying
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_retry_status
            ON retry_queue(status, next_retry_at)
            """
        )

        conn.commit()
        conn.close()

    def _calculate_backoff(self, attempt_count: int) -> int:
        """
        Calculate exponential backoff delay in seconds.

        Formula: min(base * 2^attempt, max_backoff)

        Args:
            attempt_count: Number of attempts made

        Returns:
            Delay in seconds
        """
        delay = self.base_backoff_seconds * (2**attempt_count)
        return min(delay, self.max_backoff_seconds)

    def add(
        self,
        operation_type: str,
        operation_key: str,
        operation_data: Dict[str, Any],
        error_message: str,
        max_attempts: Optional[int] = None,
    ) -> int:
        """
        Add or update failed operation in retry queue.

        Args:
            operation_type: Type of operation (e.g., 'crossref_fetch', 'ia_download')
            operation_key: Unique key for this operation (e.g., URL, DOI)
            operation_data: JSON-serializable data needed to retry
            error_message: Error message from failure
            max_attempts: Override default max_attempts for this operation

        Returns:
            Row ID of the queued operation
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        now = datetime.now(timezone.utc).isoformat()

        # Check if operation already exists
        cursor.execute(
            """
            SELECT id, attempt_count, max_attempts FROM retry_queue
            WHERE operation_type = ? AND operation_key = ?
            """,
            (operation_type, operation_key),
        )

        existing = cursor.fetchone()

        if existing:
            # Update existing entry
            row_id, attempt_count, existing_max_attempts = existing
            attempt_count += 1

            # Use provided max_attempts or keep existing value
            max_attempts_to_use = max_attempts if max_attempts is not None else existing_max_attempts

            # Calculate next retry time
            backoff_seconds = self._calculate_backoff(attempt_count)
            next_retry = (
                datetime.now(timezone.utc) + timedelta(seconds=backoff_seconds)
            ).isoformat()

            # Check if max attempts exceeded
            if attempt_count >= max_attempts_to_use:
                status = "failed"
                next_retry = None
                logger.warning(
                    f"Operation {operation_type}:{operation_key} exceeded max attempts ({max_attempts_to_use})"
                )
            else:
                status = "pending"
                logger.info(
                    f"Retry scheduled for {operation_type}:{operation_key} "
                    f"(attempt {attempt_count}/{max_attempts_to_use}, backoff {backoff_seconds}s)"
                )

            cursor.execute(
                """
                UPDATE retry_queue
                SET operation_data = ?,
                    error_message = ?,
                    attempt_count = ?,
                    max_attempts = ?,
                    last_attempt_at = ?,
                    next_retry_at = ?,
                    status = ?
                WHERE id = ?
                """,
                (
                    json.dumps(operation_data),
                    error_message,
                    attempt_count,
                    max_attempts_to_use,
                    now,
                    next_retry,
                    status,
                    row_id,
                ),
            )

        else:
            # Insert new entry
            max_attempts_to_use = max_attempts if max_attempts is not None else self.max_attempts
            backoff_seconds = self._calculate_backoff(0)
            next_retry = (
                datetime.now(timezone.utc) + timedelta(seconds=backoff_seconds)
            ).isoformat()

            cursor.execute(
                """
                INSERT INTO retry_queue (
                    operation_type, operation_key, operation_data,
                    error_message, attempt_count, max_attempts,
                    created_at, last_attempt_at, next_retry_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    operation_type,
                    operation_key,
                    json.dumps(operation_data),
                    error_message,
                    0,
                    max_attempts_to_use,
                    now,
                    now,
                    next_retry,
                    "pending",
                ),
            )

            row_id = cursor.lastrowid
            logger.info(
                f"Added {operation_type}:{operation_key} to retry queue "
                f"(backoff {backoff_seconds}s)"
            )

        conn.commit()
        conn.close()

        return row_id

    def get_ready_items(
        self, operation_type: Optional[str] = None, limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get operations ready for retry.

        Args:
            operation_type: Filter by operation type (optional)
            limit: Maximum number of items to return

        Returns:
            List of operations ready to retry
        """
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        now = datetime.now(timezone.utc).isoformat()

        query = """
            SELECT * FROM retry_queue
            WHERE status = 'pending'
            AND next_retry_at <= ?
        """
        params = [now]

        if operation_type:
            query += " AND operation_type = ?"
            params.append(operation_type)

        query += " ORDER BY next_retry_at"

        if limit:
            query += f" LIMIT {limit}"

        cursor.execute(query, params)
        rows = cursor.fetchall()

        conn.close()

        items = []
        for row in rows:
            items.append(
                {
                    "id": row["id"],
                    "operation_type": row["operation_type"],
                    "operation_key": row["operation_key"],
                    "operation_data": json.loads(row["operation_data"]),
                    "error_message": row["error_message"],
                    "attempt_count": row["attempt_count"],
                    "max_attempts": row["max_attempts"],
                    "created_at": row["created_at"],
                    "last_attempt_at": row["last_attempt_at"],
                    "next_retry_at": row["next_retry_at"],
                }
            )

        return items

    def mark_completed(self, operation_id: int) -> None:
        """
        Mark operation as successfully completed.

        Args:
            operation_id: Database row ID
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        now = datetime.now(timezone.utc).isoformat()

        cursor.execute(
            """
            UPDATE retry_queue
            SET status = 'completed', completed_at = ?
            WHERE id = ?
            """,
            (now, operation_id),
        )

        conn.commit()
        conn.close()

        logger.debug(f"Marked operation {operation_id} as completed")

    def mark_failed(self, operation_id: int, error_message: str) -> None:
        """
        Mark operation as failed (exceeded max attempts).

        Args:
            operation_id: Database row ID
            error_message: Final error message
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE retry_queue
            SET status = 'failed', error_message = ?
            WHERE id = ?
            """,
            (error_message, operation_id),
        )

        conn.commit()
        conn.close()

        logger.warning(f"Marked operation {operation_id} as permanently failed")

    def remove(self, operation_id: int) -> bool:
        """
        Remove operation from queue.

        Args:
            operation_id: Database row ID

        Returns:
            True if removed, False if not found
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        cursor.execute("DELETE FROM retry_queue WHERE id = ?", (operation_id,))

        removed = cursor.rowcount > 0
        conn.commit()
        conn.close()

        if removed:
            logger.debug(f"Removed operation {operation_id} from queue")

        return removed

    def get_stats(self) -> Dict[str, Any]:
        """
        Get retry queue statistics.

        Returns:
            Dict with counts by status
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT status, COUNT(*) as count
            FROM retry_queue
            GROUP BY status
            """
        )

        stats = {"total": 0}
        for row in cursor.fetchall():
            status, count = row
            stats[status] = count
            stats["total"] += count

        # Get oldest pending
        cursor.execute(
            """
            SELECT MIN(created_at) as oldest
            FROM retry_queue
            WHERE status = 'pending'
            """
        )

        oldest_row = cursor.fetchone()
        if oldest_row and oldest_row[0]:
            stats["oldest_pending"] = oldest_row[0]

        conn.close()

        return stats

    def clear_completed(self, older_than_days: Optional[int] = None) -> int:
        """
        Clear completed operations from queue.

        Args:
            older_than_days: Only remove completed items older than N days

        Returns:
            Number of items removed
        """
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        if older_than_days:
            cutoff = (
                datetime.now(timezone.utc) - timedelta(days=older_than_days)
            ).isoformat()
            cursor.execute(
                """
                DELETE FROM retry_queue
                WHERE status = 'completed' AND completed_at < ?
                """,
                (cutoff,),
            )
        else:
            cursor.execute("DELETE FROM retry_queue WHERE status = 'completed'")

        removed = cursor.rowcount
        conn.commit()
        conn.close()

        if removed > 0:
            logger.info(f"Cleared {removed} completed operations from retry queue")

        return removed
