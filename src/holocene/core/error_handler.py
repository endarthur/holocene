"""
Error handling for batch operations with configurable limits.

Provides centralized error tracking and reporting for long-running operations.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("holocene.error_handler")


class TooManyErrorsException(Exception):
    """Raised when error limit is exceeded during batch operations."""

    pass


class TooManyWarningsException(Exception):
    """Raised when warning limit is exceeded during batch operations."""

    pass


class ErrorHandler:
    """
    Error handler for batch operations.

    Tracks errors and warnings during long-running operations,
    enforces configurable limits, and provides summary reporting.
    """

    def __init__(
        self,
        max_errors: Optional[int] = None,
        max_warnings: Optional[int] = None,
        stop_on_error_limit: bool = True,
        stop_on_warning_limit: bool = False,
    ):
        """
        Initialize error handler.

        Args:
            max_errors: Maximum errors before stopping (None = unlimited)
            max_warnings: Maximum warnings before stopping (None = unlimited)
            stop_on_error_limit: Whether to raise exception when error limit exceeded
            stop_on_warning_limit: Whether to raise exception when warning limit exceeded
        """
        self.max_errors = max_errors
        self.max_warnings = max_warnings
        self.stop_on_error_limit = stop_on_error_limit
        self.stop_on_warning_limit = stop_on_warning_limit

        self.errors: List[Dict[str, Any]] = []
        self.warnings: List[Dict[str, Any]] = []

        logger.debug(
            f"Initialized error handler (max_errors={max_errors}, max_warnings={max_warnings})"
        )

    def add_error(
        self,
        context: str,
        message: str,
        exception: Optional[Exception] = None,
        item_id: Optional[Any] = None,
        **metadata,
    ) -> None:
        """
        Record an error.

        Args:
            context: Context where error occurred (e.g., 'book_enrichment', 'crossref_fetch')
            message: Error message
            exception: Optional exception object
            item_id: Optional identifier for the item that failed
            **metadata: Additional context data
        """
        error_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "context": context,
            "message": message,
            "exception_type": type(exception).__name__ if exception else None,
            "exception_message": str(exception) if exception else None,
            "item_id": item_id,
            "metadata": metadata,
        }

        self.errors.append(error_entry)

        logger.error(
            f"[{context}] Error #{len(self.errors)}: {message}"
            + (f" (item: {item_id})" if item_id else "")
        )

        # Check if limit exceeded
        if self.max_errors and len(self.errors) >= self.max_errors:
            if self.stop_on_error_limit:
                raise TooManyErrorsException(
                    f"Error limit exceeded: {len(self.errors)}/{self.max_errors}"
                )
            else:
                logger.warning(
                    f"Error limit reached ({self.max_errors}), continuing anyway"
                )

    def add_warning(
        self, context: str, message: str, item_id: Optional[Any] = None, **metadata
    ) -> None:
        """
        Record a warning.

        Args:
            context: Context where warning occurred
            message: Warning message
            item_id: Optional identifier for the item
            **metadata: Additional context data
        """
        warning_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "context": context,
            "message": message,
            "item_id": item_id,
            "metadata": metadata,
        }

        self.warnings.append(warning_entry)

        logger.warning(
            f"[{context}] Warning #{len(self.warnings)}: {message}"
            + (f" (item: {item_id})" if item_id else "")
        )

        # Check if limit exceeded
        if self.max_warnings and len(self.warnings) >= self.max_warnings:
            if self.stop_on_warning_limit:
                raise TooManyWarningsException(
                    f"Warning limit exceeded: {len(self.warnings)}/{self.max_warnings}"
                )
            else:
                logger.warning(
                    f"Warning limit reached ({self.max_warnings}), continuing anyway"
                )

    def has_errors(self) -> bool:
        """Check if any errors were recorded."""
        return len(self.errors) > 0

    def has_warnings(self) -> bool:
        """Check if any warnings were recorded."""
        return len(self.warnings) > 0

    def error_count(self) -> int:
        """Get number of errors recorded."""
        return len(self.errors)

    def warning_count(self) -> int:
        """Get number of warnings recorded."""
        return len(self.warnings)

    def get_errors(
        self, context: Optional[str] = None, limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get recorded errors.

        Args:
            context: Filter by context (optional)
            limit: Maximum number of errors to return

        Returns:
            List of error dictionaries
        """
        errors = self.errors

        if context:
            errors = [e for e in errors if e["context"] == context]

        if limit:
            errors = errors[:limit]

        return errors

    def get_warnings(
        self, context: Optional[str] = None, limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get recorded warnings.

        Args:
            context: Filter by context (optional)
            limit: Maximum number of warnings to return

        Returns:
            List of warning dictionaries
        """
        warnings = self.warnings

        if context:
            warnings = [w for w in warnings if w["context"] == context]

        if limit:
            warnings = warnings[:limit]

        return warnings

    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary of errors and warnings.

        Returns:
            Dict with counts and statistics
        """
        # Count by context
        error_contexts: Dict[str, int] = {}
        for error in self.errors:
            ctx = error["context"]
            error_contexts[ctx] = error_contexts.get(ctx, 0) + 1

        warning_contexts: Dict[str, int] = {}
        for warning in self.warnings:
            ctx = warning["context"]
            warning_contexts[ctx] = warning_contexts.get(ctx, 0) + 1

        summary = {
            "total_errors": len(self.errors),
            "total_warnings": len(self.warnings),
            "error_contexts": error_contexts,
            "warning_contexts": warning_contexts,
            "max_errors": self.max_errors,
            "max_warnings": self.max_warnings,
            "error_limit_exceeded": (
                self.max_errors is not None and len(self.errors) >= self.max_errors
            ),
            "warning_limit_exceeded": (
                self.max_warnings is not None
                and len(self.warnings) >= self.max_warnings
            ),
        }

        return summary

    def format_report(self, show_details: bool = False) -> str:
        """
        Format a human-readable report.

        Args:
            show_details: Whether to include detailed error/warning messages

        Returns:
            Formatted report string
        """
        summary = self.get_summary()

        lines = []
        lines.append("=" * 60)
        lines.append("ERROR HANDLER SUMMARY")
        lines.append("=" * 60)

        # Overall stats
        lines.append(
            f"Errors: {summary['total_errors']}"
            + (
                f" (limit: {self.max_errors})"
                if self.max_errors
                else " (no limit)"
            )
        )
        lines.append(
            f"Warnings: {summary['total_warnings']}"
            + (
                f" (limit: {self.max_warnings})"
                if self.max_warnings
                else " (no limit)"
            )
        )

        # By context
        if summary["error_contexts"]:
            lines.append("\nErrors by context:")
            for ctx, count in sorted(summary["error_contexts"].items()):
                lines.append(f"  {ctx}: {count}")

        if summary["warning_contexts"]:
            lines.append("\nWarnings by context:")
            for ctx, count in sorted(summary["warning_contexts"].items()):
                lines.append(f"  {ctx}: {count}")

        # Details
        if show_details:
            if self.errors:
                lines.append("\n" + "-" * 60)
                lines.append("ERROR DETAILS:")
                lines.append("-" * 60)
                for i, error in enumerate(self.errors, 1):
                    lines.append(
                        f"{i}. [{error['context']}] {error['message']}"
                        + (
                            f" (item: {error['item_id']})"
                            if error["item_id"]
                            else ""
                        )
                    )
                    if error["exception_type"]:
                        lines.append(
                            f"   Exception: {error['exception_type']}: {error['exception_message']}"
                        )

            if self.warnings:
                lines.append("\n" + "-" * 60)
                lines.append("WARNING DETAILS:")
                lines.append("-" * 60)
                for i, warning in enumerate(self.warnings, 1):
                    lines.append(
                        f"{i}. [{warning['context']}] {warning['message']}"
                        + (
                            f" (item: {warning['item_id']})"
                            if warning["item_id"]
                            else ""
                        )
                    )

        lines.append("=" * 60)

        return "\n".join(lines)

    def reset(self) -> None:
        """Clear all recorded errors and warnings."""
        self.errors.clear()
        self.warnings.clear()
        logger.debug("Error handler reset")
