"""Tests for ErrorHandler."""

import pytest

from holocene.core import error_handler


def test_error_handler_initialization():
    """Test error handler initialization."""
    handler = error_handler.ErrorHandler()
    assert handler.max_errors is None
    assert handler.max_warnings is None
    assert handler.error_count() == 0
    assert handler.warning_count() == 0


def test_error_handler_with_limits():
    """Test error handler with configured limits."""
    handler = error_handler.ErrorHandler(max_errors=10, max_warnings=5)
    assert handler.max_errors == 10
    assert handler.max_warnings == 5


def test_add_error():
    """Test adding errors."""
    handler = error_handler.ErrorHandler()

    handler.add_error("test_context", "Test error message")

    assert handler.error_count() == 1
    assert handler.has_errors()


def test_add_warning():
    """Test adding warnings."""
    handler = error_handler.ErrorHandler()

    handler.add_warning("test_context", "Test warning message")

    assert handler.warning_count() == 1
    assert handler.has_warnings()


def test_add_error_with_exception():
    """Test adding error with exception object."""
    handler = error_handler.ErrorHandler()

    try:
        raise ValueError("Test exception")
    except ValueError as e:
        handler.add_error("test_context", "Operation failed", exception=e)

    errors = handler.get_errors()
    assert len(errors) == 1
    assert errors[0]["exception_type"] == "ValueError"
    assert errors[0]["exception_message"] == "Test exception"


def test_add_error_with_item_id():
    """Test adding error with item identifier."""
    handler = error_handler.ErrorHandler()

    handler.add_error("book_enrichment", "Failed to enrich", item_id=42)

    errors = handler.get_errors()
    assert errors[0]["item_id"] == 42


def test_add_error_with_metadata():
    """Test adding error with custom metadata."""
    handler = error_handler.ErrorHandler()

    handler.add_error(
        "test_context",
        "Error",
        url="https://example.com",
        status_code=500,
        retry_count=3,
    )

    errors = handler.get_errors()
    assert errors[0]["metadata"]["url"] == "https://example.com"
    assert errors[0]["metadata"]["status_code"] == 500
    assert errors[0]["metadata"]["retry_count"] == 3


def test_max_errors_raises_exception():
    """Test that max errors raises exception when limit exceeded."""
    handler = error_handler.ErrorHandler(max_errors=3)

    handler.add_error("test", "Error 1")
    handler.add_error("test", "Error 2")

    # Third error should raise
    with pytest.raises(error_handler.TooManyErrorsException):
        handler.add_error("test", "Error 3")


def test_max_errors_no_exception_when_disabled():
    """Test that max errors doesn't raise when stop_on_error_limit=False."""
    handler = error_handler.ErrorHandler(max_errors=3, stop_on_error_limit=False)

    # Should not raise
    for i in range(5):
        handler.add_error("test", f"Error {i}")

    assert handler.error_count() == 5


def test_max_warnings_raises_exception():
    """Test that max warnings raises exception when configured."""
    handler = error_handler.ErrorHandler(max_warnings=3, stop_on_warning_limit=True)

    handler.add_warning("test", "Warning 1")
    handler.add_warning("test", "Warning 2")

    # Third warning should raise
    with pytest.raises(error_handler.TooManyWarningsException):
        handler.add_warning("test", "Warning 3")


def test_max_warnings_no_exception_by_default():
    """Test that max warnings doesn't raise by default."""
    handler = error_handler.ErrorHandler(max_warnings=3)

    # Should not raise (stop_on_warning_limit defaults to False)
    for i in range(5):
        handler.add_warning("test", f"Warning {i}")

    assert handler.warning_count() == 5


def test_get_errors_filter_by_context():
    """Test filtering errors by context."""
    handler = error_handler.ErrorHandler()

    handler.add_error("context_a", "Error A1")
    handler.add_error("context_b", "Error B1")
    handler.add_error("context_a", "Error A2")

    context_a_errors = handler.get_errors(context="context_a")
    assert len(context_a_errors) == 2

    context_b_errors = handler.get_errors(context="context_b")
    assert len(context_b_errors) == 1


def test_get_errors_with_limit():
    """Test limiting number of errors returned."""
    handler = error_handler.ErrorHandler()

    for i in range(10):
        handler.add_error("test", f"Error {i}")

    limited_errors = handler.get_errors(limit=5)
    assert len(limited_errors) == 5


def test_get_warnings_filter_by_context():
    """Test filtering warnings by context."""
    handler = error_handler.ErrorHandler()

    handler.add_warning("context_a", "Warning A1")
    handler.add_warning("context_b", "Warning B1")
    handler.add_warning("context_a", "Warning A2")

    context_a_warnings = handler.get_warnings(context="context_a")
    assert len(context_a_warnings) == 2


def test_get_summary():
    """Test summary generation."""
    handler = error_handler.ErrorHandler(max_errors=10)

    handler.add_error("context_a", "Error A1")
    handler.add_error("context_a", "Error A2")
    handler.add_error("context_b", "Error B1")
    handler.add_warning("context_a", "Warning A1")

    summary = handler.get_summary()

    assert summary["total_errors"] == 3
    assert summary["total_warnings"] == 1
    assert summary["error_contexts"]["context_a"] == 2
    assert summary["error_contexts"]["context_b"] == 1
    assert summary["warning_contexts"]["context_a"] == 1
    assert summary["max_errors"] == 10
    assert summary["error_limit_exceeded"] is False


def test_summary_limit_exceeded():
    """Test that summary shows when limits are exceeded."""
    handler = error_handler.ErrorHandler(
        max_errors=2, max_warnings=2, stop_on_error_limit=False
    )

    for i in range(3):
        handler.add_error("test", f"Error {i}")
        handler.add_warning("test", f"Warning {i}")

    summary = handler.get_summary()
    assert summary["error_limit_exceeded"] is True
    assert summary["warning_limit_exceeded"] is True


def test_format_report_basic():
    """Test basic report formatting."""
    handler = error_handler.ErrorHandler()

    handler.add_error("test", "Error 1")
    handler.add_warning("test", "Warning 1")

    report = handler.format_report()

    assert "ERROR HANDLER SUMMARY" in report
    assert "Errors: 1" in report
    assert "Warnings: 1" in report


def test_format_report_with_details():
    """Test report formatting with details."""
    handler = error_handler.ErrorHandler()

    handler.add_error("test", "Test error", item_id=42)
    handler.add_warning("test", "Test warning", item_id=99)

    report = handler.format_report(show_details=True)

    assert "ERROR DETAILS" in report
    assert "WARNING DETAILS" in report
    assert "Test error" in report
    assert "Test warning" in report
    assert "item: 42" in report
    assert "item: 99" in report


def test_format_report_shows_exception_details():
    """Test that report shows exception details."""
    handler = error_handler.ErrorHandler()

    try:
        raise RuntimeError("Something went wrong")
    except RuntimeError as e:
        handler.add_error("test", "Operation failed", exception=e)

    report = handler.format_report(show_details=True)

    assert "RuntimeError" in report
    assert "Something went wrong" in report


def test_reset():
    """Test resetting error handler."""
    handler = error_handler.ErrorHandler()

    handler.add_error("test", "Error")
    handler.add_warning("test", "Warning")

    assert handler.error_count() == 1
    assert handler.warning_count() == 1

    handler.reset()

    assert handler.error_count() == 0
    assert handler.warning_count() == 0
    assert not handler.has_errors()
    assert not handler.has_warnings()


def test_has_errors():
    """Test has_errors checker."""
    handler = error_handler.ErrorHandler()

    assert not handler.has_errors()

    handler.add_error("test", "Error")
    assert handler.has_errors()


def test_has_warnings():
    """Test has_warnings checker."""
    handler = error_handler.ErrorHandler()

    assert not handler.has_warnings()

    handler.add_warning("test", "Warning")
    assert handler.has_warnings()


def test_error_timestamps_recorded():
    """Test that timestamps are recorded for errors."""
    from datetime import datetime, timezone

    handler = error_handler.ErrorHandler()

    before = datetime.now(timezone.utc)
    handler.add_error("test", "Error")
    after = datetime.now(timezone.utc)

    errors = handler.get_errors()
    timestamp = datetime.fromisoformat(errors[0]["timestamp"])

    assert before <= timestamp <= after


def test_warning_timestamps_recorded():
    """Test that timestamps are recorded for warnings."""
    from datetime import datetime, timezone

    handler = error_handler.ErrorHandler()

    before = datetime.now(timezone.utc)
    handler.add_warning("test", "Warning")
    after = datetime.now(timezone.utc)

    warnings = handler.get_warnings()
    timestamp = datetime.fromisoformat(warnings[0]["timestamp"])

    assert before <= timestamp <= after


def test_multiple_contexts():
    """Test handling multiple different contexts."""
    handler = error_handler.ErrorHandler()

    handler.add_error("book_enrichment", "Enrichment failed")
    handler.add_error("crossref_fetch", "API timeout")
    handler.add_error("ia_download", "Download failed")
    handler.add_warning("book_enrichment", "Missing metadata")

    summary = handler.get_summary()

    assert len(summary["error_contexts"]) == 3
    assert summary["error_contexts"]["book_enrichment"] == 1
    assert summary["error_contexts"]["crossref_fetch"] == 1
    assert summary["error_contexts"]["ia_download"] == 1


def test_error_data_structure():
    """Test that error data structure is complete."""
    handler = error_handler.ErrorHandler()

    handler.add_error("test", "Test message", item_id=123, custom_field="value")

    errors = handler.get_errors()
    error = errors[0]

    assert "timestamp" in error
    assert "context" in error
    assert "message" in error
    assert "exception_type" in error
    assert "exception_message" in error
    assert "item_id" in error
    assert "metadata" in error

    assert error["context"] == "test"
    assert error["message"] == "Test message"
    assert error["item_id"] == 123
    assert error["metadata"]["custom_field"] == "value"
