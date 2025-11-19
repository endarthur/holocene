"""
Rate limiting for HTTP requests using token bucket algorithm.

Provides thread-safe rate limiting with per-domain limits to prevent
overwhelming servers and avoid IP bans.
"""

import logging
import threading
import time
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger("holocene.rate_limiter")


class TokenBucket:
    """
    Thread-safe token bucket rate limiter.

    Allows bursts up to bucket capacity while maintaining average rate.
    Based on the token bucket algorithm - tokens are added at a fixed rate,
    and requests consume tokens. If no tokens available, request waits.
    """

    def __init__(self, rate: float, capacity: Optional[float] = None):
        """
        Initialize token bucket.

        Args:
            rate: Tokens added per second (requests per second)
            capacity: Maximum tokens in bucket. If None, defaults to rate.
                     Higher capacity allows larger bursts.
        """
        self.rate = rate
        self.capacity = capacity if capacity is not None else rate
        self.tokens = self.capacity
        self.last_update = time.monotonic()
        self.lock = threading.Lock()

    def consume(self, tokens: float = 1.0, block: bool = True) -> bool:
        """
        Consume tokens from the bucket.

        Args:
            tokens: Number of tokens to consume (default 1.0 = one request)
            block: If True, wait until tokens available. If False, return immediately.

        Returns:
            bool: True if tokens were consumed, False if not available (only when block=False)
        """
        with self.lock:
            # Refill tokens based on elapsed time
            now = time.monotonic()
            elapsed = now - self.last_update
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.last_update = now

            # Check if we have enough tokens
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True

            if not block:
                return False

            # Calculate wait time
            deficit = tokens - self.tokens
            wait_time = deficit / self.rate

        # Wait outside the lock so other threads can proceed
        logger.debug(f"Rate limit reached, waiting {wait_time:.2f}s")
        time.sleep(wait_time)

        # Try again after waiting
        with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.last_update = now
            self.tokens -= tokens
            return True


class DomainRateLimiter:
    """
    Rate limiter with per-domain limits.

    Maintains separate token buckets for each domain, allowing
    different rate limits for different APIs (e.g., slower for
    heavily rate-limited APIs, faster for generous ones).
    """

    def __init__(self, default_rate: float = 1.0, domain_rates: Optional[dict] = None):
        """
        Initialize domain rate limiter.

        Args:
            default_rate: Default requests per second for all domains
            domain_rates: Dict mapping domain names to custom rates
                         (e.g., {'api.crossref.org': 0.5, 'archive.org': 0.2})
        """
        self.default_rate = default_rate
        self.domain_rates = domain_rates or {}
        self.buckets = {}
        self.lock = threading.Lock()

    def _get_bucket(self, domain: str) -> TokenBucket:
        """Get or create token bucket for a domain."""
        with self.lock:
            if domain not in self.buckets:
                rate = self.domain_rates.get(domain, self.default_rate)
                self.buckets[domain] = TokenBucket(rate)
                logger.debug(f"Created rate limiter for {domain}: {rate} req/s")
            return self.buckets[domain]

    def wait_for_token(self, url: str) -> None:
        """
        Wait until a request to the given URL can proceed.

        Args:
            url: Full URL to make request to
        """
        # Handle URLs without scheme by adding https://
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        domain = urlparse(url).netloc
        if not domain:
            logger.warning(f"Could not extract domain from URL: {url}")
            return

        bucket = self._get_bucket(domain)
        bucket.consume(tokens=1.0, block=True)

    def can_proceed(self, url: str) -> bool:
        """
        Check if request can proceed without blocking.

        Args:
            url: Full URL to make request to

        Returns:
            bool: True if request can proceed immediately
        """
        # Handle URLs without scheme
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        domain = urlparse(url).netloc
        if not domain:
            return True

        bucket = self._get_bucket(domain)
        return bucket.consume(tokens=1.0, block=False)


# Global rate limiter instance (initialized from config)
_global_limiter: Optional[DomainRateLimiter] = None


def set_global_limiter(limiter: Optional[DomainRateLimiter]) -> None:
    """Set the global rate limiter instance."""
    global _global_limiter
    _global_limiter = limiter
    if limiter is not None:
        logger.info(f"Set global rate limiter: {limiter.default_rate} req/s default")
    else:
        logger.debug("Cleared global rate limiter")


def get_global_limiter() -> Optional[DomainRateLimiter]:
    """Get the global rate limiter instance."""
    return _global_limiter


def wait_for_request(url: str) -> None:
    """
    Wait until a request can proceed according to global rate limiter.

    Convenience function that uses the global limiter if set.

    Args:
        url: URL to make request to
    """
    limiter = get_global_limiter()
    if limiter:
        limiter.wait_for_token(url)
