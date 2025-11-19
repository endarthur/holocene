"""
Base API client with rate limiting for all HTTP integrations.

Provides centralized rate limiting, request handling, and future support
for caching, retry logic, and error handling.
"""

import logging
from typing import Optional, Dict, Any
from urllib.parse import urlparse

import requests

from holocene.core import rate_limiter

logger = logging.getLogger("holocene.api_client")


class BaseAPIClient:
    """
    Base class for all API clients in Holocene.

    Provides:
    - Centralized rate limiting (token bucket)
    - Request wrapper with consistent error handling
    - Future: caching, retry queue, error tracking

    All API integrations should inherit from this class.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        rate_limit: Optional[float] = None,
        use_global_limiter: bool = True,
        custom_limiter: Optional[rate_limiter.DomainRateLimiter] = None,
    ):
        """
        Initialize base API client.

        Args:
            base_url: Base URL for the API (optional)
            rate_limit: Custom rate limit for this client (requests/second)
                       If None, uses global limiter's default
            use_global_limiter: Whether to use the global rate limiter
            custom_limiter: Custom DomainRateLimiter instance (overrides global)
        """
        self.base_url = base_url
        self.session = requests.Session()

        # Rate limiter configuration
        if custom_limiter:
            self.rate_limiter = custom_limiter
        elif use_global_limiter:
            self.rate_limiter = rate_limiter.get_global_limiter()
        else:
            # Create isolated limiter for this client
            self.rate_limiter = (
                rate_limiter.DomainRateLimiter(default_rate=rate_limit)
                if rate_limit
                else None
            )

        if self.rate_limiter and rate_limit:
            # Override rate for base_url domain if specified
            if base_url:
                domain = urlparse(base_url).netloc
                if domain:
                    self.rate_limiter.domain_rates[domain] = rate_limit
                    logger.debug(
                        f"Set custom rate limit for {domain}: {rate_limit} req/s"
                    )

    def _build_url(self, endpoint: str) -> str:
        """
        Build full URL from endpoint.

        Args:
            endpoint: API endpoint (can be relative or absolute)

        Returns:
            Full URL string
        """
        if endpoint.startswith(("http://", "https://")):
            # Already a full URL
            return endpoint

        if self.base_url:
            # Join base URL with endpoint
            base = self.base_url.rstrip("/")
            endpoint = endpoint.lstrip("/")
            return f"{base}/{endpoint}"

        return endpoint

    def request(
        self,
        method: str,
        endpoint: str,
        respect_rate_limit: bool = True,
        timeout: int = 30,
        **kwargs,
    ) -> requests.Response:
        """
        Make HTTP request with rate limiting.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint or full URL
            respect_rate_limit: Whether to apply rate limiting (default True)
            timeout: Request timeout in seconds (default 30)
            **kwargs: Additional arguments passed to requests.request()

        Returns:
            requests.Response object

        Raises:
            requests.exceptions.RequestException: On request failures
        """
        url = self._build_url(endpoint)

        # Apply rate limiting if enabled
        if respect_rate_limit and self.rate_limiter:
            self.rate_limiter.wait_for_token(url)

        # Make request
        logger.debug(f"{method} {url}")
        response = self.session.request(method, url, timeout=timeout, **kwargs)

        return response

    def get(self, endpoint: str, **kwargs) -> requests.Response:
        """Convenience method for GET requests."""
        return self.request("GET", endpoint, **kwargs)

    def post(self, endpoint: str, **kwargs) -> requests.Response:
        """Convenience method for POST requests."""
        return self.request("POST", endpoint, **kwargs)

    def put(self, endpoint: str, **kwargs) -> requests.Response:
        """Convenience method for PUT requests."""
        return self.request("PUT", endpoint, **kwargs)

    def delete(self, endpoint: str, **kwargs) -> requests.Response:
        """Convenience method for DELETE requests."""
        return self.request("DELETE", endpoint, **kwargs)

    def get_json(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """
        GET request that returns parsed JSON.

        Args:
            endpoint: API endpoint or full URL
            **kwargs: Additional arguments for request

        Returns:
            Parsed JSON response as dict

        Raises:
            requests.exceptions.HTTPError: On HTTP errors
            requests.exceptions.JSONDecodeError: On invalid JSON
        """
        response = self.get(endpoint, **kwargs)
        response.raise_for_status()
        return response.json()

    def post_json(
        self, endpoint: str, data: Optional[Dict[str, Any]] = None, **kwargs
    ) -> Dict[str, Any]:
        """
        POST request that sends and receives JSON.

        Args:
            endpoint: API endpoint or full URL
            data: Data to send as JSON
            **kwargs: Additional arguments for request

        Returns:
            Parsed JSON response as dict

        Raises:
            requests.exceptions.HTTPError: On HTTP errors
            requests.exceptions.JSONDecodeError: On invalid JSON
        """
        kwargs.setdefault("json", data)
        response = self.post(endpoint, **kwargs)
        response.raise_for_status()
        return response.json()

    def close(self):
        """Close the session."""
        self.session.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
