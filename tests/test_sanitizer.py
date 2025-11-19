"""Tests for privacy sanitizer."""

import pytest
from holocene.core.models import Activity, ActivityType, Context
from holocene.core.sanitizer import PrivacySanitizer


def test_should_block_domain():
    """Test domain blocking with wildcards."""
    sanitizer = PrivacySanitizer(
        blacklist_domains=["*.vale.com", "mail.google.com"],
        whitelist_domains=["github.com"],
    )

    assert sanitizer.should_block_domain("internal.vale.com") is True
    assert sanitizer.should_block_domain("mail.google.com") is True
    assert sanitizer.should_block_domain("github.com") is False
    assert sanitizer.should_block_domain("example.com") is False


def test_whitelist_overrides_blacklist():
    """Test that whitelist takes priority over blacklist."""
    sanitizer = PrivacySanitizer(
        blacklist_domains=["*.com"],
        whitelist_domains=["github.com"],
    )

    assert sanitizer.should_block_domain("github.com") is False
    assert sanitizer.should_block_domain("example.com") is True


def test_redact_keywords():
    """Test keyword redaction."""
    sanitizer = PrivacySanitizer(
        blacklist_keywords=["confidential", "secret"],
    )

    text = "This is confidential information about secret projects."
    redacted = sanitizer.redact_keywords(text)

    assert "confidential" not in redacted.lower()
    assert "secret" not in redacted.lower()
    assert "[REDACTED]" in redacted


def test_sanitize_activity_redacts_keywords():
    """Test that activity descriptions have keywords redacted."""
    sanitizer = PrivacySanitizer(
        blacklist_keywords=["tonnage"],
    )

    activity = Activity(
        description="Analyzed tonnage estimates for project",
        activity_type=ActivityType.CODING,
        context=Context.WORK,
    )

    sanitized = sanitizer.sanitize_activity(activity)

    assert sanitized is not None
    assert "tonnage" not in sanitized.description.lower()
    assert "[REDACTED]" in sanitized.description


def test_sanitize_activity_blocks_sensitive_paths():
    """Test that activities referencing blocked paths are blocked entirely."""
    sanitizer = PrivacySanitizer(
        blacklist_paths=["/work/proprietary"],
    )

    activity = Activity(
        description="Edited file at /work/proprietary/data.csv",
        activity_type=ActivityType.CODING,
        context=Context.WORK,
    )

    sanitized = sanitizer.sanitize_activity(activity)

    assert sanitized is None  # Should be completely blocked


def test_sanitize_activity_blocks_domain_in_metadata():
    """Test that activities with blocked domains in metadata are blocked."""
    sanitizer = PrivacySanitizer(
        blacklist_domains=["*.vale.com"],
    )

    activity = Activity(
        description="Browsing internal site",
        activity_type=ActivityType.RESEARCH,
        context=Context.WORK,
        metadata={"domain": "internal.vale.com"},
    )

    sanitized = sanitizer.sanitize_activity(activity)

    assert sanitized is None  # Should be blocked


def test_sanitize_activity_strips_urls():
    """Test that URLs are stripped from descriptions."""
    sanitizer = PrivacySanitizer()

    activity = Activity(
        description="Found article at https://example.com/article",
        activity_type=ActivityType.RESEARCH,
        context=Context.PERSONAL,
    )

    sanitized = sanitizer.sanitize_activity(activity)

    assert "https://example.com" not in sanitized.description
    assert "[URL]" in sanitized.description


def test_is_safe_for_external_api():
    """Test external API safety check."""
    sanitizer = PrivacySanitizer(
        blacklist_keywords=["confidential"],
        blacklist_domains=["*.internal.com"],
    )

    # Safe activity
    safe_activity = Activity(
        description="Working on open source project",
        activity_type=ActivityType.CODING,
        context=Context.OPEN_SOURCE,
    )
    assert sanitizer.is_safe_for_external_api(safe_activity) is True

    # Unsafe - has keyword
    unsafe_activity = Activity(
        description="Reviewing confidential documents",
        activity_type=ActivityType.RESEARCH,
        context=Context.WORK,
    )
    assert sanitizer.is_safe_for_external_api(unsafe_activity) is False

    # Unsafe - blocked domain
    unsafe_activity2 = Activity(
        description="Browsing site",
        activity_type=ActivityType.RESEARCH,
        context=Context.WORK,
        metadata={"domain": "app.internal.com"},
    )
    assert sanitizer.is_safe_for_external_api(unsafe_activity2) is False
