"""Tests for BaseAPIClient."""

import time
from unittest.mock import Mock, patch, MagicMock

import pytest
import requests

from holocene.core import api_client, rate_limiter


@pytest.fixture(autouse=True)
def reset_global_limiter():
    """Reset global limiter before each test."""
    rate_limiter.set_global_limiter(None)
    yield
    rate_limiter.set_global_limiter(None)


@pytest.fixture
def mock_response():
    """Create a mock requests.Response."""
    response = Mock(spec=requests.Response)
    response.status_code = 200
    response.json.return_value = {"success": True, "data": "test"}
    response.raise_for_status = Mock()
    return response


def test_base_client_initialization():
    """Test basic client initialization."""
    client = api_client.BaseAPIClient()
    assert client.base_url is None
    assert client.rate_limiter is None  # No global limiter set


def test_base_client_with_base_url():
    """Test client with base URL."""
    client = api_client.BaseAPIClient(base_url="https://api.example.com")
    assert client.base_url == "https://api.example.com"


def test_base_client_uses_global_limiter():
    """Test that client uses global rate limiter when available."""
    limiter = rate_limiter.DomainRateLimiter(default_rate=5.0)
    rate_limiter.set_global_limiter(limiter)

    client = api_client.BaseAPIClient()
    assert client.rate_limiter is limiter


def test_base_client_custom_limiter():
    """Test client with custom rate limiter."""
    custom_limiter = rate_limiter.DomainRateLimiter(default_rate=10.0)
    client = api_client.BaseAPIClient(custom_limiter=custom_limiter)
    assert client.rate_limiter is custom_limiter


def test_base_client_no_global_limiter():
    """Test client without global limiter."""
    client = api_client.BaseAPIClient(use_global_limiter=False)
    assert client.rate_limiter is None


def test_base_client_isolated_limiter():
    """Test client creates isolated limiter when specified."""
    client = api_client.BaseAPIClient(
        use_global_limiter=False, rate_limit=3.0
    )
    assert client.rate_limiter is not None
    assert client.rate_limiter.default_rate == 3.0


def test_url_building_absolute():
    """Test that absolute URLs are not modified."""
    client = api_client.BaseAPIClient(base_url="https://api.example.com")
    url = client._build_url("https://other.example.com/endpoint")
    assert url == "https://other.example.com/endpoint"


def test_url_building_relative():
    """Test URL building with base URL and relative endpoint."""
    client = api_client.BaseAPIClient(base_url="https://api.example.com")
    url = client._build_url("/v1/users")
    assert url == "https://api.example.com/v1/users"


def test_url_building_no_base():
    """Test URL building without base URL."""
    client = api_client.BaseAPIClient()
    url = client._build_url("/endpoint")
    assert url == "/endpoint"


def test_url_building_trailing_slash():
    """Test URL building handles trailing slashes correctly."""
    client = api_client.BaseAPIClient(base_url="https://api.example.com/")
    url = client._build_url("/v1/users")
    assert url == "https://api.example.com/v1/users"


@patch('holocene.core.api_client.requests.Session.request')
def test_get_request(mock_request, mock_response):
    """Test GET request."""
    mock_request.return_value = mock_response

    client = api_client.BaseAPIClient(
        base_url="https://api.example.com",
        use_global_limiter=False  # Disable rate limiting for speed
    )

    response = client.get("/endpoint")

    mock_request.assert_called_once()
    args, kwargs = mock_request.call_args
    assert args[0] == "GET"
    assert "https://api.example.com/endpoint" in args[1]
    assert response.status_code == 200


@patch('holocene.core.api_client.requests.Session.request')
def test_post_request(mock_request, mock_response):
    """Test POST request."""
    mock_request.return_value = mock_response

    client = api_client.BaseAPIClient(use_global_limiter=False)
    response = client.post("https://api.example.com/data", json={"key": "value"})

    mock_request.assert_called_once()
    args, kwargs = mock_request.call_args
    assert args[0] == "POST"
    assert kwargs["json"] == {"key": "value"}


@patch('holocene.core.api_client.requests.Session.request')
def test_put_request(mock_request, mock_response):
    """Test PUT request."""
    mock_request.return_value = mock_response

    client = api_client.BaseAPIClient(use_global_limiter=False)
    response = client.put("https://api.example.com/update", data="test")

    mock_request.assert_called_once()
    args, kwargs = mock_request.call_args
    assert args[0] == "PUT"


@patch('holocene.core.api_client.requests.Session.request')
def test_delete_request(mock_request, mock_response):
    """Test DELETE request."""
    mock_request.return_value = mock_response

    client = api_client.BaseAPIClient(use_global_limiter=False)
    response = client.delete("https://api.example.com/resource/42")

    mock_request.assert_called_once()
    args, kwargs = mock_request.call_args
    assert args[0] == "DELETE"


@patch('holocene.core.api_client.requests.Session.request')
def test_get_json(mock_request, mock_response):
    """Test get_json convenience method."""
    mock_request.return_value = mock_response

    client = api_client.BaseAPIClient(use_global_limiter=False)
    data = client.get_json("https://api.example.com/data")

    assert data == {"success": True, "data": "test"}
    mock_response.raise_for_status.assert_called_once()


@patch('holocene.core.api_client.requests.Session.request')
def test_post_json(mock_request, mock_response):
    """Test post_json convenience method."""
    mock_request.return_value = mock_response

    client = api_client.BaseAPIClient(use_global_limiter=False)
    data = client.post_json(
        "https://api.example.com/submit",
        data={"key": "value"}
    )

    assert data == {"success": True, "data": "test"}
    args, kwargs = mock_request.call_args
    assert kwargs["json"] == {"key": "value"}


@patch('holocene.core.api_client.requests.Session.request')
def test_rate_limiting_applied(mock_request, mock_response):
    """Test that rate limiting is applied to requests."""
    mock_request.return_value = mock_response

    # Create limiter with low rate and low capacity
    # Capacity defaults to rate, so bucket starts with 5 tokens
    # We need to exceed capacity to trigger rate limiting
    limiter = rate_limiter.DomainRateLimiter(default_rate=5.0)
    client = api_client.BaseAPIClient(custom_limiter=limiter)

    # Make requests that exceed bucket capacity
    start = time.monotonic()
    for i in range(7):  # 7 requests at 5 req/s = need to wait after 5th
        client.get(f"https://example.com/{i}")
    elapsed = time.monotonic() - start

    # First 5 requests instant (bucket capacity = rate = 5.0)
    # Requests 6-7 need to wait for token refill
    # At 5 req/s, 2 extra requests need ~0.4s
    assert elapsed >= 0.3  # Allow some margin


@patch('holocene.core.api_client.requests.Session.request')
def test_rate_limiting_can_be_disabled(mock_request, mock_response):
    """Test that rate limiting can be disabled per request."""
    mock_request.return_value = mock_response

    limiter = rate_limiter.DomainRateLimiter(default_rate=1.0)
    client = api_client.BaseAPIClient(custom_limiter=limiter)

    # Make requests with rate limiting disabled
    start = time.monotonic()
    client.get("https://example.com/1", respect_rate_limit=False)
    client.get("https://example.com/2", respect_rate_limit=False)
    client.get("https://example.com/3", respect_rate_limit=False)
    elapsed = time.monotonic() - start

    # Should be instant without rate limiting
    assert elapsed < 0.1


@patch('holocene.core.api_client.requests.Session.request')
def test_separate_domains_separate_buckets(mock_request, mock_response):
    """Test that different domains have separate rate limit buckets."""
    mock_request.return_value = mock_response

    limiter = rate_limiter.DomainRateLimiter(default_rate=2.0)
    client = api_client.BaseAPIClient(custom_limiter=limiter)

    # Requests to different domains shouldn't interfere
    start = time.monotonic()
    client.get("https://domain1.com/1")
    client.get("https://domain2.com/1")
    client.get("https://domain1.com/2")
    client.get("https://domain2.com/2")
    elapsed = time.monotonic() - start

    # Each domain has own bucket, so should be relatively fast
    assert elapsed < 1.0  # Much faster than sequential (which would be ~1.5s)


def test_context_manager():
    """Test client works as context manager."""
    with api_client.BaseAPIClient() as client:
        assert client.session is not None

    # Session should be closed after context
    # (We can't easily test this without mocking, but at least verify no errors)


@patch('holocene.core.api_client.requests.Session.request')
def test_custom_timeout(mock_request, mock_response):
    """Test custom timeout parameter."""
    mock_request.return_value = mock_response

    client = api_client.BaseAPIClient(use_global_limiter=False)
    client.get("https://api.example.com/slow", timeout=60)

    args, kwargs = mock_request.call_args
    assert kwargs["timeout"] == 60


@patch('holocene.core.api_client.requests.Session.request')
def test_default_timeout(mock_request, mock_response):
    """Test default timeout is applied."""
    mock_request.return_value = mock_response

    client = api_client.BaseAPIClient(use_global_limiter=False)
    client.get("https://api.example.com/endpoint")

    args, kwargs = mock_request.call_args
    assert kwargs["timeout"] == 30  # Default


@patch('holocene.core.api_client.requests.Session.request')
def test_additional_kwargs_passed_through(mock_request, mock_response):
    """Test that additional kwargs are passed to requests."""
    mock_request.return_value = mock_response

    client = api_client.BaseAPIClient(use_global_limiter=False)
    client.get(
        "https://api.example.com/endpoint",
        headers={"Authorization": "Bearer token"},
        params={"q": "search"}
    )

    args, kwargs = mock_request.call_args
    assert kwargs["headers"] == {"Authorization": "Bearer token"}
    assert kwargs["params"] == {"q": "search"}


def test_custom_rate_limit_for_base_url():
    """Test that custom rate limit is set for base_url domain."""
    client = api_client.BaseAPIClient(
        base_url="https://api.example.com",
        rate_limit=10.0,
        use_global_limiter=False
    )

    assert client.rate_limiter is not None
    # Check that the domain rate was set
    bucket = client.rate_limiter._get_bucket("api.example.com")
    assert bucket.rate == 10.0
