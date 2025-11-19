"""Privacy sanitization layer for Holocene."""

import re
from typing import List
from fnmatch import fnmatch
from .models import Activity


class PrivacySanitizer:
    """Sanitizes activities to protect privacy."""

    def __init__(
        self,
        blacklist_domains: List[str] = None,
        blacklist_keywords: List[str] = None,
        blacklist_paths: List[str] = None,
        whitelist_domains: List[str] = None,
    ):
        """
        Initialize sanitizer with blacklists and whitelists.

        Args:
            blacklist_domains: List of domains to block (supports wildcards like *.example.com)
            blacklist_keywords: List of keywords to redact
            blacklist_paths: List of file paths to block
            whitelist_domains: List of domains explicitly allowed
        """
        self.blacklist_domains = blacklist_domains or []
        self.blacklist_keywords = blacklist_keywords or []
        self.blacklist_paths = blacklist_paths or []
        self.whitelist_domains = whitelist_domains or []

    def should_block_domain(self, domain: str) -> bool:
        """Check if a domain should be blocked."""
        if not domain:
            return False

        domain = domain.lower().strip()

        # Check whitelist first (whitelist overrides blacklist)
        for pattern in self.whitelist_domains:
            if fnmatch(domain, pattern.lower()):
                return False

        # Check blacklist
        for pattern in self.blacklist_domains:
            if fnmatch(domain, pattern.lower()):
                return True

        return False

    def should_block_path(self, path: str) -> bool:
        """Check if a file path should be blocked."""
        if not path:
            return False

        path = path.strip()

        for pattern in self.blacklist_paths:
            # Support wildcards and direct path matching
            if fnmatch(path, pattern) or path.startswith(pattern):
                return True

        return False

    def redact_keywords(self, text: str) -> str:
        """Redact blacklisted keywords from text."""
        if not text:
            return text

        result = text
        for keyword in self.blacklist_keywords:
            # Case-insensitive replacement
            pattern = re.compile(re.escape(keyword), re.IGNORECASE)
            result = pattern.sub("[REDACTED]", result)

        return result

    def sanitize_activity(self, activity: Activity) -> Activity:
        """
        Sanitize an activity for privacy.

        Returns a copy of the activity with sensitive data removed/redacted.
        If the activity should be completely blocked, returns None.
        """
        # Create a copy to avoid modifying the original
        sanitized = activity.model_copy(deep=True)

        # Check if description contains blocked paths
        for path in self.blacklist_paths:
            if path in sanitized.description:
                # Block entire activity if it references sensitive paths
                return None

        # Redact keywords from description
        sanitized.description = self.redact_keywords(sanitized.description)

        # Remove URLs from description (basic privacy measure)
        sanitized.description = self._strip_urls(sanitized.description)

        # Redact keywords from tags
        sanitized.tags = [
            self.redact_keywords(tag) for tag in sanitized.tags
            if not any(kw.lower() in tag.lower() for kw in self.blacklist_keywords)
        ]

        # Check metadata for sensitive domains (if source is browser/window)
        if "domain" in sanitized.metadata:
            domain = sanitized.metadata["domain"]
            if self.should_block_domain(domain):
                # Block entire activity
                return None

        return sanitized

    def _strip_urls(self, text: str) -> str:
        """Remove URLs from text (basic implementation)."""
        # Match http/https URLs
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        return re.sub(url_pattern, "[URL]", text)

    def is_safe_for_external_api(self, activity: Activity) -> bool:
        """
        Check if an activity is safe to send to external APIs.

        Returns True if safe, False if should be kept local-only.
        """
        # Check for blocked domains in metadata
        if "domain" in activity.metadata:
            if self.should_block_domain(activity.metadata["domain"]):
                return False

        # Check for blocked keywords
        for keyword in self.blacklist_keywords:
            if keyword.lower() in activity.description.lower():
                return False

            if any(keyword.lower() in tag.lower() for tag in activity.tags):
                return False

        # Check for blocked paths
        for path in self.blacklist_paths:
            if path in activity.description:
                return False

        return True
