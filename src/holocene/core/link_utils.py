"""Link extraction and management utilities."""

import re
from typing import List, Set
from urllib.parse import urlparse


def extract_urls(text: str) -> Set[str]:
    """
    Extract URLs from text.

    Args:
        text: Text to extract URLs from

    Returns:
        Set of unique URLs found
    """
    if not text:
        return set()

    # Match http/https URLs
    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
    matches = re.findall(url_pattern, text)

    # Clean up URLs (remove trailing punctuation)
    cleaned = set()
    for url in matches:
        # Remove trailing punctuation
        url = url.rstrip('.,;:!?)')
        cleaned.add(url)

    return cleaned


def is_valid_url(url: str) -> bool:
    """Check if a URL is valid and well-formed."""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except:
        return False


def should_archive_url(url: str, exclude_domains: List[str] = None) -> bool:
    """
    Determine if a URL should be archived.

    Args:
        url: URL to check
        exclude_domains: List of domains to exclude (e.g., localhost, private sites)

    Returns:
        True if should be archived
    """
    if not is_valid_url(url):
        return False

    exclude_domains = exclude_domains or [
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
        "*.local",
        "*.internal",
    ]

    parsed = urlparse(url)
    domain = parsed.netloc.lower()

    # Check exclusions
    for exclude in exclude_domains:
        if exclude.startswith("*."):
            # Wildcard domain
            suffix = exclude[2:]
            if domain.endswith(suffix):
                return False
        elif domain == exclude or domain.startswith(exclude + ":"):
            return False

    return True
