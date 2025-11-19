"""
API response caching with configurable TTL.

Provides disk-based caching for API responses with flexible expiration policies.
"""

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Optional, Dict

logger = logging.getLogger("holocene.cache")


class APICache:
    """
    Disk-based cache for API responses with TTL support.

    Stores responses as JSON files with timestamps for expiration tracking.
    Useful for caching stable API data (DOIs, IA availability, etc.).
    """

    def __init__(
        self,
        cache_dir: Path | str,
        ttl_seconds: Optional[int] = None,
        namespace: Optional[str] = None,
    ):
        """
        Initialize API cache.

        Args:
            cache_dir: Directory to store cache files
            ttl_seconds: Time to live in seconds. None = never expire
            namespace: Optional namespace for key isolation (e.g., 'crossref', 'ia')
        """
        self.cache_dir = Path(cache_dir)
        self.ttl_seconds = ttl_seconds
        self.namespace = namespace

        # Create cache directory if needed
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        logger.debug(
            f"Initialized cache: {self.cache_dir} "
            f"(TTL: {ttl_seconds or 'forever'}, namespace: {namespace or 'global'})"
        )

    def _make_key(self, key: str) -> str:
        """
        Convert user key to safe filename.

        Uses SHA256 hash to ensure:
        - Safe filesystem names
        - Fixed length
        - No path traversal attacks

        Args:
            key: User-provided cache key (e.g., URL, DOI)

        Returns:
            Safe filename string
        """
        if self.namespace:
            key = f"{self.namespace}:{key}"

        # Hash to get safe, fixed-length filename
        key_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return f"{key_hash}.json"

    def _get_cache_path(self, key: str) -> Path:
        """Get full path to cache file for key."""
        filename = self._make_key(key)
        return self.cache_dir / filename

    def get(self, key: str) -> Optional[Any]:
        """
        Retrieve value from cache.

        Args:
            key: Cache key (e.g., URL, DOI)

        Returns:
            Cached value if found and not expired, None otherwise
        """
        cache_path = self._get_cache_path(key)

        if not cache_path.exists():
            logger.debug(f"Cache miss: {key}")
            return None

        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cache_data = json.load(f)

            # Check expiration if TTL is set
            if self.ttl_seconds is not None:
                timestamp = cache_data.get("timestamp", 0)
                age = time.time() - timestamp

                if age > self.ttl_seconds:
                    logger.debug(f"Cache expired: {key} (age: {age:.1f}s)")
                    # Delete expired cache file
                    cache_path.unlink()
                    return None

            logger.debug(f"Cache hit: {key}")
            return cache_data.get("value")

        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Cache read error for {key}: {e}")
            return None

    def set(self, key: str, value: Any) -> None:
        """
        Store value in cache.

        Args:
            key: Cache key
            value: Value to cache (must be JSON-serializable)
        """
        cache_path = self._get_cache_path(key)

        # Store the namespaced key for filtering in clear()
        stored_key = f"{self.namespace}:{key}" if self.namespace else key

        cache_data = {
            "key": stored_key,  # Store namespaced key for namespace filtering
            "value": value,
            "timestamp": time.time(),
            "ttl_seconds": self.ttl_seconds,
        }

        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, indent=2)

            logger.debug(f"Cache set: {key}")

        except (TypeError, OSError) as e:
            logger.warning(f"Cache write error for {key}: {e}")

    def delete(self, key: str) -> bool:
        """
        Delete cached value.

        Args:
            key: Cache key

        Returns:
            True if deleted, False if not found
        """
        cache_path = self._get_cache_path(key)

        if cache_path.exists():
            cache_path.unlink()
            logger.debug(f"Cache deleted: {key}")
            return True

        return False

    def clear(self) -> int:
        """
        Clear all cached values in this cache instance.

        Returns:
            Number of cache files deleted
        """
        count = 0

        for cache_file in self.cache_dir.glob("*.json"):
            # If namespaced, only delete files from this namespace
            should_delete = True

            if self.namespace:
                try:
                    with open(cache_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        # Check if this file belongs to our namespace
                        # The key is stored with namespace prefix: "namespace:original_key"
                        stored_key = data.get("key", "")
                        # Only delete if key starts with our namespace prefix
                        if not stored_key.startswith(f"{self.namespace}:"):
                            should_delete = False
                except (json.JSONDecodeError, OSError):
                    # If we can't read the file, skip it for safety
                    should_delete = False

            if should_delete:
                cache_file.unlink()
                count += 1

        logger.info(f"Cleared {count} cache files from {self.cache_dir}")
        return count

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dict with cache size, file count, oldest/newest entries
        """
        files = list(self.cache_dir.glob("*.json"))
        total_size = sum(f.stat().st_size for f in files)

        stats = {
            "cache_dir": str(self.cache_dir),
            "namespace": self.namespace,
            "ttl_seconds": self.ttl_seconds,
            "file_count": len(files),
            "total_size_bytes": total_size,
            "total_size_mb": total_size / (1024 * 1024),
        }

        if files:
            oldest = min(files, key=lambda f: f.stat().st_mtime)
            newest = max(files, key=lambda f: f.stat().st_mtime)

            stats.update(
                {
                    "oldest_entry": oldest.stat().st_mtime,
                    "newest_entry": newest.stat().st_mtime,
                }
            )

        return stats

    def prune_expired(self) -> int:
        """
        Remove expired cache entries.

        Returns:
            Number of expired entries removed
        """
        if self.ttl_seconds is None:
            logger.debug("No TTL set, no pruning needed")
            return 0

        count = 0
        now = time.time()

        for cache_file in self.cache_dir.glob("*.json"):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                timestamp = data.get("timestamp", 0)
                age = now - timestamp

                if age > self.ttl_seconds:
                    cache_file.unlink()
                    count += 1

            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Error checking {cache_file}: {e}")

        if count > 0:
            logger.info(f"Pruned {count} expired cache entries")

        return count


def get_cache_for_api(
    api_name: str, ttl_seconds: Optional[int] = None
) -> APICache:
    """
    Get or create cache instance for an API.

    Convenience function that creates cache in standard location.

    Args:
        api_name: Name of API (e.g., 'crossref', 'ia', 'wikipedia')
        ttl_seconds: Time to live, None = forever

    Returns:
        APICache instance
    """
    from pathlib import Path

    # Standard cache location: ~/.holocene/cache/<api_name>/
    cache_dir = Path.home() / ".holocene" / "cache" / api_name
    return APICache(cache_dir, ttl_seconds=ttl_seconds, namespace=api_name)
