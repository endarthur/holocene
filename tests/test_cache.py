"""Tests for APICache."""

import json
import time
from pathlib import Path

import pytest

from holocene.core import cache


@pytest.fixture
def temp_cache_dir(tmp_path):
    """Create temporary cache directory."""
    return tmp_path / "test_cache"


def test_cache_initialization(temp_cache_dir):
    """Test cache initialization creates directory."""
    cache_instance = cache.APICache(temp_cache_dir)
    assert temp_cache_dir.exists()
    assert cache_instance.ttl_seconds is None


def test_cache_with_ttl(temp_cache_dir):
    """Test cache initialization with TTL."""
    cache_instance = cache.APICache(temp_cache_dir, ttl_seconds=3600)
    assert cache_instance.ttl_seconds == 3600


def test_cache_with_namespace(temp_cache_dir):
    """Test cache with namespace."""
    cache_instance = cache.APICache(temp_cache_dir, namespace="test")
    assert cache_instance.namespace == "test"


def test_basic_get_set(temp_cache_dir):
    """Test basic cache get/set operations."""
    cache_instance = cache.APICache(temp_cache_dir)

    # Set value
    cache_instance.set("key1", {"data": "value1"})

    # Get value
    result = cache_instance.get("key1")
    assert result == {"data": "value1"}


def test_cache_miss(temp_cache_dir):
    """Test cache miss returns None."""
    cache_instance = cache.APICache(temp_cache_dir)
    result = cache_instance.get("nonexistent")
    assert result is None


def test_cache_different_types(temp_cache_dir):
    """Test caching different data types."""
    cache_instance = cache.APICache(temp_cache_dir)

    # String
    cache_instance.set("string", "hello")
    assert cache_instance.get("string") == "hello"

    # Number
    cache_instance.set("number", 42)
    assert cache_instance.get("number") == 42

    # List
    cache_instance.set("list", [1, 2, 3])
    assert cache_instance.get("list") == [1, 2, 3]

    # Dict
    cache_instance.set("dict", {"a": 1, "b": 2})
    assert cache_instance.get("dict") == {"a": 1, "b": 2}

    # Nested structure
    cache_instance.set("nested", {"items": [1, 2], "meta": {"count": 2}})
    assert cache_instance.get("nested") == {"items": [1, 2], "meta": {"count": 2}}


def test_ttl_not_expired(temp_cache_dir):
    """Test that cache returns value when TTL not expired."""
    cache_instance = cache.APICache(temp_cache_dir, ttl_seconds=10)

    cache_instance.set("key1", "value1")

    # Immediately fetch - should succeed
    result = cache_instance.get("key1")
    assert result == "value1"


def test_ttl_expired(temp_cache_dir):
    """Test that cache returns None when TTL expired."""
    cache_instance = cache.APICache(temp_cache_dir, ttl_seconds=0.1)  # 100ms

    cache_instance.set("key1", "value1")

    # Wait for expiration
    time.sleep(0.2)

    # Should return None
    result = cache_instance.get("key1")
    assert result is None

    # Cache file should be deleted
    cache_files = list(temp_cache_dir.glob("*.json"))
    assert len(cache_files) == 0


def test_ttl_none_never_expires(temp_cache_dir):
    """Test that TTL=None means cache never expires."""
    cache_instance = cache.APICache(temp_cache_dir, ttl_seconds=None)

    cache_instance.set("key1", "value1")

    # Even after waiting, should still be cached
    time.sleep(0.1)
    result = cache_instance.get("key1")
    assert result == "value1"


def test_key_hashing(temp_cache_dir):
    """Test that keys are hashed for safe filenames."""
    cache_instance = cache.APICache(temp_cache_dir)

    # Use problematic characters in key
    key = "https://example.com/path?param=value&other=123"
    cache_instance.set(key, "data")

    # Should create a hashed filename
    cache_files = list(temp_cache_dir.glob("*.json"))
    assert len(cache_files) == 1

    # Filename should be hex (SHA256)
    filename = cache_files[0].stem
    assert len(filename) == 64  # SHA256 hex length
    assert all(c in "0123456789abcdef" for c in filename)


def test_namespace_isolation(temp_cache_dir):
    """Test that different namespaces are isolated."""
    cache1 = cache.APICache(temp_cache_dir, namespace="ns1")
    cache2 = cache.APICache(temp_cache_dir, namespace="ns2")

    cache1.set("key1", "value_ns1")
    cache2.set("key1", "value_ns2")

    # Different namespaces should have different values
    assert cache1.get("key1") == "value_ns1"
    assert cache2.get("key1") == "value_ns2"


def test_delete(temp_cache_dir):
    """Test cache deletion."""
    cache_instance = cache.APICache(temp_cache_dir)

    cache_instance.set("key1", "value1")
    assert cache_instance.get("key1") == "value1"

    # Delete
    result = cache_instance.delete("key1")
    assert result is True

    # Should be gone
    assert cache_instance.get("key1") is None

    # Delete non-existent
    result = cache_instance.delete("nonexistent")
    assert result is False


def test_clear(temp_cache_dir):
    """Test clearing all cache entries."""
    cache_instance = cache.APICache(temp_cache_dir)

    # Add multiple entries
    cache_instance.set("key1", "value1")
    cache_instance.set("key2", "value2")
    cache_instance.set("key3", "value3")

    # Clear
    count = cache_instance.clear()
    assert count == 3

    # All should be gone
    assert cache_instance.get("key1") is None
    assert cache_instance.get("key2") is None
    assert cache_instance.get("key3") is None


def test_clear_respects_namespace(temp_cache_dir):
    """Test that clear only removes entries from same namespace."""
    cache1 = cache.APICache(temp_cache_dir, namespace="ns1")
    cache2 = cache.APICache(temp_cache_dir, namespace="ns2")

    cache1.set("key1", "value1")
    cache2.set("key2", "value2")

    # Clear ns1
    cache1.clear()

    # ns1 should be gone, ns2 should remain
    assert cache1.get("key1") is None
    assert cache2.get("key2") == "value2"


def test_cache_stats(temp_cache_dir):
    """Test cache statistics."""
    cache_instance = cache.APICache(temp_cache_dir, ttl_seconds=3600)

    # Empty cache
    stats = cache_instance.get_stats()
    assert stats["file_count"] == 0
    assert stats["total_size_bytes"] == 0
    assert stats["ttl_seconds"] == 3600

    # Add some entries
    cache_instance.set("key1", "value1")
    cache_instance.set("key2", {"data": "value2"})

    stats = cache_instance.get_stats()
    assert stats["file_count"] == 2
    assert stats["total_size_bytes"] > 0
    assert stats["total_size_mb"] > 0
    assert "oldest_entry" in stats
    assert "newest_entry" in stats


def test_prune_expired(temp_cache_dir):
    """Test pruning expired cache entries."""
    cache_instance = cache.APICache(temp_cache_dir, ttl_seconds=0.1)

    # Add entries
    cache_instance.set("key1", "value1")
    cache_instance.set("key2", "value2")

    # Wait for expiration
    time.sleep(0.2)

    # Add new entry (not expired)
    cache_instance.set("key3", "value3")

    # Prune
    count = cache_instance.prune_expired()
    assert count == 2  # key1 and key2 expired

    # Only key3 should remain
    assert cache_instance.get("key1") is None
    assert cache_instance.get("key2") is None
    assert cache_instance.get("key3") == "value3"


def test_prune_with_no_ttl(temp_cache_dir):
    """Test that prune does nothing when TTL is None."""
    cache_instance = cache.APICache(temp_cache_dir, ttl_seconds=None)

    cache_instance.set("key1", "value1")

    count = cache_instance.prune_expired()
    assert count == 0

    # Entry should still be there
    assert cache_instance.get("key1") == "value1"


def test_corrupted_cache_file(temp_cache_dir):
    """Test handling of corrupted cache files."""
    cache_instance = cache.APICache(temp_cache_dir)

    # Create corrupted cache file
    cache_path = cache_instance._get_cache_path("corrupted")
    cache_path.write_text("not valid json {{{")

    # Should return None gracefully
    result = cache_instance.get("corrupted")
    assert result is None


def test_get_cache_for_api(tmp_path, monkeypatch):
    """Test convenience function for getting API-specific cache."""
    # Mock Path.home() to return tmp_path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    # Get cache for an API
    ia_cache = cache.get_cache_for_api("ia", ttl_seconds=None)

    assert ia_cache.namespace == "ia"
    assert ia_cache.ttl_seconds is None

    expected_dir = tmp_path / ".holocene" / "cache" / "ia"
    assert ia_cache.cache_dir == expected_dir
    assert expected_dir.exists()


def test_overwrite_existing_key(temp_cache_dir):
    """Test that setting an existing key overwrites the value."""
    cache_instance = cache.APICache(temp_cache_dir)

    cache_instance.set("key1", "original")
    assert cache_instance.get("key1") == "original"

    # Overwrite
    cache_instance.set("key1", "updated")
    assert cache_instance.get("key1") == "updated"


def test_cache_timestamp_recorded(temp_cache_dir):
    """Test that timestamp is recorded in cache file."""
    cache_instance = cache.APICache(temp_cache_dir)

    before = time.time()
    cache_instance.set("key1", "value1")
    after = time.time()

    # Read cache file directly
    cache_path = cache_instance._get_cache_path("key1")
    with open(cache_path, "r") as f:
        data = json.load(f)

    assert "timestamp" in data
    assert before <= data["timestamp"] <= after


def test_multiple_caches_same_directory(temp_cache_dir):
    """Test multiple cache instances in same directory with namespaces."""
    cache_ia = cache.APICache(temp_cache_dir, namespace="ia")
    cache_crossref = cache.APICache(temp_cache_dir, namespace="crossref")

    cache_ia.set("key1", "ia_value")
    cache_crossref.set("key1", "crossref_value")

    # Both should coexist
    assert cache_ia.get("key1") == "ia_value"
    assert cache_crossref.get("key1") == "crossref_value"

    # Should have 2 cache files
    cache_files = list(temp_cache_dir.glob("*.json"))
    assert len(cache_files) == 2
