"""Tests for rate limiting functionality."""

import threading
import time

import pytest

from holocene.core import rate_limiter


def test_token_bucket_single_request():
    """Test that a single request consumes token immediately."""
    bucket = rate_limiter.TokenBucket(rate=1.0)
    start = time.monotonic()
    result = bucket.consume(1.0, block=False)
    elapsed = time.monotonic() - start

    assert result is True
    assert elapsed < 0.1  # Should be instant


def test_token_bucket_rate_limiting():
    """Test that token bucket enforces rate limit."""
    bucket = rate_limiter.TokenBucket(rate=2.0, capacity=2.0)  # 2 req/s

    # First 2 requests should be immediate (bucket full)
    assert bucket.consume(1.0, block=False) is True
    assert bucket.consume(1.0, block=False) is True

    # Third request should fail without blocking
    assert bucket.consume(1.0, block=False) is False


def test_token_bucket_blocking():
    """Test that token bucket blocks until tokens available."""
    bucket = rate_limiter.TokenBucket(rate=2.0, capacity=1.0)  # 2 req/s

    # Consume initial token
    bucket.consume(1.0, block=False)

    # Next request should wait ~0.5s for token to refill
    start = time.monotonic()
    bucket.consume(1.0, block=True)
    elapsed = time.monotonic() - start

    # Should wait approximately 0.5 seconds (1 token / 2 tokens per second)
    assert 0.4 < elapsed < 0.7  # Allow some margin


def test_token_bucket_refill():
    """Test that tokens refill over time."""
    bucket = rate_limiter.TokenBucket(rate=10.0, capacity=1.0)

    # Consume token
    bucket.consume(1.0, block=False)

    # Wait for refill
    time.sleep(0.15)  # 10 tokens/s = 0.1s per token

    # Should have token again
    assert bucket.consume(1.0, block=False) is True


def test_token_bucket_thread_safety():
    """Test that token bucket is thread-safe."""
    bucket = rate_limiter.TokenBucket(rate=5.0, capacity=10.0)
    consumed = []

    def consumer(n):
        for _ in range(n):
            bucket.consume(1.0, block=True)
            consumed.append(1)

    # Launch multiple threads
    threads = [threading.Thread(target=consumer, args=(5,)) for _ in range(3)]
    start = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.monotonic() - start

    # 15 total requests at 5 req/s should take ~3 seconds
    # First 10 are instant (bucket capacity), next 5 take 1 second
    assert len(consumed) == 15
    assert 0.8 < elapsed < 1.5  # Should take about 1 second after initial 10


def test_domain_rate_limiter_default():
    """Test domain rate limiter with default rate."""
    limiter = rate_limiter.DomainRateLimiter(default_rate=10.0)

    start = time.monotonic()
    limiter.wait_for_token("https://example.com/page1")
    limiter.wait_for_token("https://example.com/page2")
    elapsed = time.monotonic() - start

    # Both should be instant since bucket starts with capacity tokens
    # and capacity defaults to rate (10.0), so both requests fit in the bucket
    assert elapsed < 0.1


def test_domain_rate_limiter_custom_domain():
    """Test domain rate limiter with custom domain rates."""
    limiter = rate_limiter.DomainRateLimiter(
        default_rate=10.0, domain_rates={"slow.example.com": 1.0}
    )

    # Fast domain should be quick
    start = time.monotonic()
    limiter.wait_for_token("https://fast.example.com/page1")
    limiter.wait_for_token("https://fast.example.com/page2")
    fast_elapsed = time.monotonic() - start

    # Slow domain should enforce stricter limit
    start = time.monotonic()
    limiter.wait_for_token("https://slow.example.com/page1")
    limiter.wait_for_token("https://slow.example.com/page2")
    slow_elapsed = time.monotonic() - start

    assert fast_elapsed < 0.2  # ~0.1s
    assert 0.8 < slow_elapsed < 1.3  # ~1.0s


def test_domain_rate_limiter_separate_buckets():
    """Test that different domains have separate buckets."""
    limiter = rate_limiter.DomainRateLimiter(default_rate=2.0)

    # Requests to different domains shouldn't interfere
    start = time.monotonic()
    limiter.wait_for_token("https://domain1.com/page")
    limiter.wait_for_token("https://domain2.com/page")
    limiter.wait_for_token("https://domain1.com/page2")
    limiter.wait_for_token("https://domain2.com/page2")
    elapsed = time.monotonic() - start

    # Each domain has own bucket, so should be relatively fast
    # 2 requests per domain at 2 req/s = ~0.5s per domain (parallel)
    assert elapsed < 1.0  # Should be faster than sequential


def test_domain_rate_limiter_can_proceed():
    """Test non-blocking check for rate limit."""
    limiter = rate_limiter.DomainRateLimiter(default_rate=1.0)

    # First request should succeed
    assert limiter.can_proceed("https://example.com/page1") is True

    # Second immediate request should fail
    assert limiter.can_proceed("https://example.com/page2") is False

    # After waiting, should succeed again
    time.sleep(1.1)
    assert limiter.can_proceed("https://example.com/page3") is True


def test_global_limiter():
    """Test global rate limiter get/set."""
    limiter = rate_limiter.DomainRateLimiter(default_rate=5.0)
    rate_limiter.set_global_limiter(limiter)

    assert rate_limiter.get_global_limiter() is limiter

    # Clean up
    rate_limiter.set_global_limiter(None)


def test_wait_for_request_with_global():
    """Test wait_for_request uses global limiter."""
    limiter = rate_limiter.DomainRateLimiter(default_rate=5.0)
    rate_limiter.set_global_limiter(limiter)

    start = time.monotonic()
    rate_limiter.wait_for_request("https://example.com/1")
    rate_limiter.wait_for_request("https://example.com/2")
    elapsed = time.monotonic() - start

    # Both should be instant since bucket starts with capacity tokens (5.0)
    assert elapsed < 0.1

    # Clean up
    rate_limiter.set_global_limiter(None)


def test_wait_for_request_without_global():
    """Test wait_for_request works without global limiter."""
    rate_limiter.set_global_limiter(None)

    # Should not raise, just do nothing
    start = time.monotonic()
    rate_limiter.wait_for_request("https://example.com/1")
    rate_limiter.wait_for_request("https://example.com/2")
    elapsed = time.monotonic() - start

    # Should be instant without limiter
    assert elapsed < 0.05


def test_url_without_scheme():
    """Test that URLs without scheme are handled correctly."""
    limiter = rate_limiter.DomainRateLimiter(default_rate=1.0)

    # Should not raise
    limiter.wait_for_token("example.com/page")
    assert limiter.can_proceed("example.com/page2") is False  # Rate limited
