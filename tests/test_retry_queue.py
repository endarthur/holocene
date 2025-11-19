"""Tests for RetryQueue."""

import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from holocene.core import retry_queue


@pytest.fixture
def temp_db(tmp_path):
    """Create temporary database for testing."""
    return tmp_path / "test_retry.db"


def test_retry_queue_initialization(temp_db):
    """Test retry queue initialization creates table."""
    queue = retry_queue.RetryQueue(temp_db)
    assert temp_db.exists()
    assert queue.max_attempts == 5
    assert queue.base_backoff_seconds == 60


def test_retry_queue_custom_config(temp_db):
    """Test retry queue with custom configuration."""
    queue = retry_queue.RetryQueue(
        temp_db, max_attempts=3, base_backoff_seconds=30, max_backoff_seconds=3600
    )
    assert queue.max_attempts == 3
    assert queue.base_backoff_seconds == 30
    assert queue.max_backoff_seconds == 3600


def test_add_operation(temp_db):
    """Test adding operation to queue."""
    queue = retry_queue.RetryQueue(temp_db)

    row_id = queue.add(
        operation_type="test_op",
        operation_key="key1",
        operation_data={"url": "https://example.com"},
        error_message="Connection timeout",
    )

    assert row_id > 0


def test_add_duplicate_operation(temp_db):
    """Test that adding duplicate operation updates existing entry."""
    queue = retry_queue.RetryQueue(temp_db)

    # Add first time
    row_id1 = queue.add(
        operation_type="test_op",
        operation_key="key1",
        operation_data={"url": "https://example.com"},
        error_message="Error 1",
    )

    # Add again with same key
    row_id2 = queue.add(
        operation_type="test_op",
        operation_key="key1",
        operation_data={"url": "https://example.com"},
        error_message="Error 2",
    )

    # Should update same row
    assert row_id1 == row_id2


def test_exponential_backoff_calculation(temp_db):
    """Test exponential backoff calculation."""
    queue = retry_queue.RetryQueue(temp_db, base_backoff_seconds=60)

    # Attempt 0: 60 * 2^0 = 60s
    assert queue._calculate_backoff(0) == 60

    # Attempt 1: 60 * 2^1 = 120s
    assert queue._calculate_backoff(1) == 120

    # Attempt 2: 60 * 2^2 = 240s
    assert queue._calculate_backoff(2) == 240

    # Attempt 3: 60 * 2^3 = 480s
    assert queue._calculate_backoff(3) == 480


def test_backoff_respects_maximum(temp_db):
    """Test that backoff respects maximum delay."""
    queue = retry_queue.RetryQueue(
        temp_db, base_backoff_seconds=60, max_backoff_seconds=300
    )

    # Very high attempt count
    backoff = queue._calculate_backoff(10)  # Would be 60 * 2^10 = 61440s

    # Should be capped at max
    assert backoff == 300


def test_get_ready_items_respects_time(temp_db):
    """Test that get_ready_items only returns items ready to retry."""
    queue = retry_queue.RetryQueue(temp_db, base_backoff_seconds=1)

    # Add operation (will have next_retry_at in ~1 second)
    queue.add(
        operation_type="test_op",
        operation_key="key1",
        operation_data={"url": "https://example.com"},
        error_message="Error",
    )

    # Immediately check - should be empty (not ready yet)
    ready = queue.get_ready_items()
    assert len(ready) == 0

    # Wait for backoff period
    time.sleep(1.5)

    # Now should be ready
    ready = queue.get_ready_items()
    assert len(ready) == 1
    assert ready[0]["operation_key"] == "key1"


def test_get_ready_items_filter_by_type(temp_db):
    """Test filtering ready items by operation type."""
    queue = retry_queue.RetryQueue(temp_db, base_backoff_seconds=0)

    queue.add("type_a", "key1", {"data": 1}, "Error")
    queue.add("type_b", "key2", {"data": 2}, "Error")
    queue.add("type_a", "key3", {"data": 3}, "Error")

    # Wait briefly
    time.sleep(0.1)

    # Get all
    all_ready = queue.get_ready_items()
    assert len(all_ready) == 3

    # Get only type_a
    type_a_ready = queue.get_ready_items(operation_type="type_a")
    assert len(type_a_ready) == 2


def test_get_ready_items_limit(temp_db):
    """Test limiting number of ready items returned."""
    queue = retry_queue.RetryQueue(temp_db, base_backoff_seconds=0)

    queue.add("test_op", "key1", {"data": 1}, "Error")
    queue.add("test_op", "key2", {"data": 2}, "Error")
    queue.add("test_op", "key3", {"data": 3}, "Error")

    time.sleep(0.1)

    # Get only 2
    ready = queue.get_ready_items(limit=2)
    assert len(ready) == 2


def test_mark_completed(temp_db):
    """Test marking operation as completed."""
    queue = retry_queue.RetryQueue(temp_db, base_backoff_seconds=0)

    row_id = queue.add("test_op", "key1", {"data": 1}, "Error")

    time.sleep(0.1)

    # Should be ready
    ready = queue.get_ready_items()
    assert len(ready) == 1

    # Mark completed
    queue.mark_completed(row_id)

    # Should no longer be ready
    ready = queue.get_ready_items()
    assert len(ready) == 0


def test_mark_failed(temp_db):
    """Test marking operation as permanently failed."""
    queue = retry_queue.RetryQueue(temp_db)

    row_id = queue.add("test_op", "key1", {"data": 1}, "Error")

    queue.mark_failed(row_id, "Final error message")

    # Should not appear in ready items
    ready = queue.get_ready_items()
    assert len(ready) == 0


def test_remove_operation(temp_db):
    """Test removing operation from queue."""
    queue = retry_queue.RetryQueue(temp_db)

    row_id = queue.add("test_op", "key1", {"data": 1}, "Error")

    # Remove
    removed = queue.remove(row_id)
    assert removed is True

    # Try to remove again
    removed_again = queue.remove(row_id)
    assert removed_again is False


def test_attempt_count_increments(temp_db):
    """Test that attempt count increments on repeated failures."""
    queue = retry_queue.RetryQueue(temp_db, base_backoff_seconds=0)

    # Add operation
    queue.add("test_op", "key1", {"data": 1}, "Error 1")

    time.sleep(0.1)

    ready = queue.get_ready_items()
    assert ready[0]["attempt_count"] == 0

    # Add again (simulating retry failure)
    queue.add("test_op", "key1", {"data": 1}, "Error 2")

    time.sleep(0.1)

    ready = queue.get_ready_items()
    assert ready[0]["attempt_count"] == 1


def test_max_attempts_exceeded(temp_db):
    """Test that operation is marked failed after max attempts."""
    queue = retry_queue.RetryQueue(temp_db, max_attempts=3, base_backoff_seconds=0)

    # Add operation 4 times (0, 1, 2, 3 attempts)
    for i in range(4):
        queue.add("test_op", "key1", {"data": 1}, f"Error {i}")
        time.sleep(0.1)

    # After 3 attempts, should be marked as failed
    ready = queue.get_ready_items()
    assert len(ready) == 0  # Not in pending state anymore


def test_get_stats(temp_db):
    """Test getting queue statistics."""
    queue = retry_queue.RetryQueue(temp_db, base_backoff_seconds=0)

    # Empty queue
    stats = queue.get_stats()
    assert stats["total"] == 0

    # Add operations
    id1 = queue.add("test_op", "key1", {"data": 1}, "Error")
    id2 = queue.add("test_op", "key2", {"data": 2}, "Error")
    id3 = queue.add("test_op", "key3", {"data": 3}, "Error")

    stats = queue.get_stats()
    assert stats["total"] == 3
    assert stats.get("pending", 0) > 0

    # Mark one completed
    queue.mark_completed(id1)

    stats = queue.get_stats()
    assert stats["total"] == 3
    assert stats.get("completed", 0) == 1


def test_clear_completed(temp_db):
    """Test clearing completed operations."""
    queue = retry_queue.RetryQueue(temp_db)

    id1 = queue.add("test_op", "key1", {"data": 1}, "Error")
    id2 = queue.add("test_op", "key2", {"data": 2}, "Error")
    id3 = queue.add("test_op", "key3", {"data": 3}, "Error")

    # Mark some completed
    queue.mark_completed(id1)
    queue.mark_completed(id2)

    # Clear completed
    removed = queue.clear_completed()
    assert removed == 2

    # Total should be 1 now
    stats = queue.get_stats()
    assert stats["total"] == 1


def test_operation_data_preserved(temp_db):
    """Test that operation data is preserved correctly."""
    queue = retry_queue.RetryQueue(temp_db, base_backoff_seconds=0)

    operation_data = {
        "url": "https://api.example.com/resource",
        "method": "GET",
        "params": {"id": 123},
        "nested": {"key": "value"},
    }

    queue.add("test_op", "key1", operation_data, "Error")

    time.sleep(0.1)

    ready = queue.get_ready_items()
    assert len(ready) == 1
    assert ready[0]["operation_data"] == operation_data


def test_different_operation_types_independent(temp_db):
    """Test that different operation types are tracked independently."""
    queue = retry_queue.RetryQueue(temp_db, base_backoff_seconds=0)

    # Same key, different types
    queue.add("type_a", "key1", {"data": 1}, "Error")
    queue.add("type_b", "key1", {"data": 2}, "Error")

    time.sleep(0.1)

    # Should have 2 different operations
    ready = queue.get_ready_items()
    assert len(ready) == 2

    # Different keys, different data
    types = {item["operation_type"] for item in ready}
    assert types == {"type_a", "type_b"}


def test_custom_max_attempts_per_operation(temp_db):
    """Test that max_attempts can be overridden per operation."""
    queue = retry_queue.RetryQueue(temp_db, max_attempts=5, base_backoff_seconds=0)

    # Add with custom max_attempts=2
    queue.add("test_op", "key1", {"data": 1}, "Error", max_attempts=2)

    # Fail 3 times
    for i in range(3):
        queue.add("test_op", "key1", {"data": 1}, f"Error {i}")
        time.sleep(0.1)

    # Should be marked failed after 2 attempts (not 5)
    ready = queue.get_ready_items()
    assert len(ready) == 0


def test_timestamps_recorded(temp_db):
    """Test that timestamps are recorded correctly."""
    from datetime import timezone

    queue = retry_queue.RetryQueue(temp_db, base_backoff_seconds=0)

    before = datetime.now(timezone.utc)
    queue.add("test_op", "key1", {"data": 1}, "Error")
    after = datetime.now(timezone.utc)

    time.sleep(0.1)

    ready = queue.get_ready_items()
    item = ready[0]

    # Check timestamps are in expected range
    created_at = datetime.fromisoformat(item["created_at"])
    assert before <= created_at <= after

    assert item["last_attempt_at"] is not None
    assert item["next_retry_at"] is not None
