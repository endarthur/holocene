"""Tests for Extended Dewey classification with W prefix."""

import pytest
from unittest.mock import Mock, patch

from holocene.research.extended_dewey import ExtendedDeweyClassifier, WEB_CONTENT_CATEGORIES


def test_web_content_categories():
    """Test that web content categories are defined."""
    assert "W000" in WEB_CONTENT_CATEGORIES
    assert "W380.1" in WEB_CONTENT_CATEGORIES
    assert "W621.9" in WEB_CONTENT_CATEGORIES
    assert "W550" in WEB_CONTENT_CATEGORIES


def test_extract_author_from_title():
    """Test author extraction from titles."""
    classifier = ExtendedDeweyClassifier()

    # Book with "by Author" pattern
    author = classifier._extract_author_from_title("Introduction to Geostatistics by Isaaks")
    assert author == "Isaaks"

    # Brand name
    author = classifier._extract_author_from_title("Samsung Galaxy S24")
    assert author == "Samsung"

    # Tool with brand ("Tool" is a common word, so skips to "Adjustable")
    author = classifier._extract_author_from_title("Tool - Adjustable Wrench - Stanley")
    assert author == "Adjustable"  # Skips common words like "Tool"

    # No clear author/brand
    author = classifier._extract_author_from_title("cheap widget")
    assert author == "cheap"  # Falls back to first word


def test_extract_url_context():
    """Test URL context extraction."""
    classifier = ExtendedDeweyClassifier()

    # GitHub
    context = classifier._extract_url_context("https://github.com/user/repo")
    assert "Software repository" in context

    # Stack Overflow
    context = classifier._extract_url_context("https://stackoverflow.com/questions/12345")
    assert "Programming Q&A" in context

    # Wikipedia
    context = classifier._extract_url_context("https://en.wikipedia.org/wiki/Topic")
    assert "Encyclopedia/Wiki" in context

    # arXiv
    context = classifier._extract_url_context("https://arxiv.org/abs/2401.12345")
    assert "Academic preprint" in context

    # E-commerce
    context = classifier._extract_url_context("https://mercadolivre.com.br/product")
    assert "E-commerce listing" in context

    # Blog
    context = classifier._extract_url_context("https://medium.com/@user/article")
    assert "Blog/Article" in context

    # .edu domain
    context = classifier._extract_url_context("https://university.edu/resource")
    assert "Educational resource" in context

    # Unknown domain
    context = classifier._extract_url_context("https://example.com/page")
    assert context is None


@patch('holocene.research.extended_dewey.NanoGPTClient')
@patch('holocene.research.extended_dewey.load_config')
def test_classify_web_content_success(mock_config, mock_client):
    """Test successful web content classification."""
    # Mock config
    mock_cfg = Mock()
    mock_cfg.llm.api_key = "test_key"
    mock_cfg.llm.base_url = "https://api.test.com"
    mock_cfg.llm.primary = "test-model"
    mock_cfg.classification.generate_cutter_numbers = True
    mock_cfg.classification.cutter_length = 3
    mock_cfg.classification.generate_full_call_numbers = True
    mock_config.return_value = mock_cfg

    # Mock LLM response
    mock_llm = Mock()
    mock_llm.simple_prompt.return_value = """{
        "dewey_number": "W550",
        "dewey_label": "Earth sciences & geology",
        "alternative_numbers": ["W550.1"],
        "confidence": "high",
        "reasoning": "Geology-related web resource"
    }"""
    mock_client.return_value = mock_llm

    classifier = ExtendedDeweyClassifier()
    result = classifier.classify_web_content(
        title="Geology Tutorial",
        url="https://example.com/geology",
        description="Educational geology resource",
    )

    assert result["dewey_number"] == "W550"
    assert result["dewey_label"] == "Earth sciences & geology"
    assert result["confidence"] == "high"
    assert result["classification_system"] == "Extended Dewey"
    assert result["is_web_content"] is True
    assert "cutter_number" in result
    assert "call_number" in result


@patch('holocene.research.extended_dewey.NanoGPTClient')
@patch('holocene.research.extended_dewey.load_config')
def test_classify_marketplace_item(mock_config, mock_client):
    """Test marketplace item classification."""
    # Mock config
    mock_cfg = Mock()
    mock_cfg.llm.api_key = "test_key"
    mock_cfg.llm.base_url = "https://api.test.com"
    mock_cfg.llm.primary = "test-model"
    mock_cfg.classification.generate_cutter_numbers = False
    mock_config.return_value = mock_cfg

    # Mock LLM response for a book
    mock_llm = Mock()
    mock_llm.simple_prompt.return_value = """{
        "dewey_number": "W020",
        "dewey_label": "Bibliography & book trade",
        "alternative_numbers": [],
        "confidence": "high",
        "reasoning": "Book for sale on marketplace"
    }"""
    mock_client.return_value = mock_llm

    classifier = ExtendedDeweyClassifier()
    result = classifier.classify_marketplace_item(
        title="Livro: Introdução à Geoestatística",
        price=129.90,
        category="Livros",
        condition="new",
    )

    assert result["dewey_number"] == "W020"
    assert result["is_web_content"] is True


@patch('holocene.research.extended_dewey.NanoGPTClient')
@patch('holocene.research.extended_dewey.load_config')
def test_classify_bookmark(mock_config, mock_client):
    """Test bookmark classification."""
    mock_cfg = Mock()
    mock_cfg.llm.api_key = "test_key"
    mock_cfg.llm.base_url = "https://api.test.com"
    mock_cfg.llm.primary = "test-model"
    mock_cfg.classification.generate_cutter_numbers = False
    mock_config.return_value = mock_cfg

    mock_llm = Mock()
    mock_llm.simple_prompt.return_value = """{
        "dewey_number": "W004",
        "dewey_label": "Computer hardware & devices",
        "alternative_numbers": [],
        "confidence": "medium",
        "reasoning": "GitHub repository for hardware project"
    }"""
    mock_client.return_value = mock_llm

    classifier = ExtendedDeweyClassifier()
    result = classifier.classify_bookmark(
        title="Arduino Mega 2560 Repository",
        url="https://github.com/arduino/ArduinoCore-avr",
    )

    assert result["dewey_number"].startswith("W")
    assert result["is_web_content"] is True


@patch('holocene.research.extended_dewey.NanoGPTClient')
@patch('holocene.research.extended_dewey.load_config')
def test_classify_link(mock_config, mock_client):
    """Test link classification."""
    mock_cfg = Mock()
    mock_cfg.llm.api_key = "test_key"
    mock_cfg.llm.base_url = "https://api.test.com"
    mock_cfg.llm.primary = "test-model"
    mock_cfg.classification.generate_cutter_numbers = False
    mock_config.return_value = mock_cfg

    mock_llm = Mock()
    mock_llm.simple_prompt.return_value = """{
        "dewey_number": "W550.182",
        "dewey_label": "Geostatistics",
        "alternative_numbers": [],
        "confidence": "high",
        "reasoning": "Academic paper on geostatistics"
    }"""
    mock_client.return_value = mock_llm

    classifier = ExtendedDeweyClassifier()
    result = classifier.classify_link(
        url="https://arxiv.org/abs/2401.12345",
        title="Novel Geostatistical Methods",
        context="Found in research notes",
    )

    assert result["dewey_number"].startswith("W")
    assert result["is_web_content"] is True


@patch('holocene.research.extended_dewey.NanoGPTClient')
@patch('holocene.research.extended_dewey.load_config')
def test_missing_w_prefix_added(mock_config, mock_client):
    """Test that W prefix is added if missing from LLM response."""
    mock_cfg = Mock()
    mock_cfg.llm.api_key = "test_key"
    mock_cfg.llm.base_url = "https://api.test.com"
    mock_cfg.llm.primary = "test-model"
    mock_cfg.classification.generate_cutter_numbers = False
    mock_config.return_value = mock_cfg

    # LLM accidentally returns regular Dewey instead of W-prefix
    mock_llm = Mock()
    mock_llm.simple_prompt.return_value = """{
        "dewey_number": "550",
        "dewey_label": "Earth sciences",
        "alternative_numbers": [],
        "confidence": "high",
        "reasoning": "Test"
    }"""
    mock_client.return_value = mock_llm

    classifier = ExtendedDeweyClassifier()
    result = classifier.classify_web_content(
        title="Test Resource",
        url="https://example.com/test",
    )

    # Should add W prefix automatically
    assert result["dewey_number"] == "W550"


@patch('holocene.research.extended_dewey.NanoGPTClient')
@patch('holocene.research.extended_dewey.load_config')
def test_classification_error_handling(mock_config, mock_client):
    """Test error handling in classification."""
    mock_cfg = Mock()
    mock_cfg.llm.api_key = "test_key"
    mock_cfg.llm.base_url = "https://api.test.com"
    mock_cfg.llm.primary = "test-model"
    mock_cfg.classification.generate_cutter_numbers = False
    mock_config.return_value = mock_cfg

    # LLM returns invalid JSON
    mock_llm = Mock()
    mock_llm.simple_prompt.return_value = "This is not JSON"
    mock_client.return_value = mock_llm

    classifier = ExtendedDeweyClassifier()
    result = classifier.classify_web_content(
        title="Test",
        url="https://example.com",
    )

    assert "error" in result
    assert result["confidence"] == "low"
    assert result["classification_system"] == "Extended Dewey"
