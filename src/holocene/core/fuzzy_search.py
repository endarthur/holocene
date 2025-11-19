"""
Fuzzy string matching for search queries.

Provides simple fuzzy matching using Python's difflib for typo-tolerant search.
"""

from difflib import SequenceMatcher
from typing import List, Tuple, Any, Callable, Optional


def fuzzy_match_ratio(query: str, text: str, case_sensitive: bool = False) -> float:
    """
    Calculate fuzzy match ratio between query and text.

    Args:
        query: Search query
        text: Text to match against
        case_sensitive: Whether to do case-sensitive matching

    Returns:
        Match ratio between 0.0 (no match) and 1.0 (perfect match)
    """
    if not query or not text:
        return 0.0

    if not case_sensitive:
        query = query.lower()
        text = text.lower()

    return SequenceMatcher(None, query, text).ratio()


def fuzzy_match(query: str, text: str, threshold: float = 0.6) -> bool:
    """
    Check if query fuzzy matches text above threshold.

    Args:
        query: Search query
        text: Text to match against
        threshold: Minimum match ratio (0.0-1.0)

    Returns:
        True if match ratio >= threshold
    """
    ratio = fuzzy_match_ratio(query, text)
    return ratio >= threshold


def fuzzy_search(
    query: str,
    items: List[Any],
    key_func: Callable[[Any], str],
    threshold: float = 0.6,
    limit: Optional[int] = None,
) -> List[Tuple[Any, float]]:
    """
    Fuzzy search items by extracting searchable text with key_func.

    Args:
        query: Search query
        items: List of items to search
        key_func: Function to extract searchable text from item
        threshold: Minimum match ratio (0.0-1.0)
        limit: Maximum number of results to return

    Returns:
        List of (item, score) tuples, sorted by score descending
    """
    if not query:
        return []

    # Calculate scores for all items
    scored_items = []
    for item in items:
        text = key_func(item)
        score = fuzzy_match_ratio(query, text)

        if score >= threshold:
            scored_items.append((item, score))

    # Sort by score (highest first)
    scored_items.sort(key=lambda x: x[1], reverse=True)

    # Apply limit if specified
    if limit:
        scored_items = scored_items[:limit]

    return scored_items


def fuzzy_search_multi_field(
    query: str,
    items: List[Any],
    key_funcs: List[Tuple[Callable[[Any], str], float]],
    threshold: float = 0.6,
    limit: Optional[int] = None,
) -> List[Tuple[Any, float]]:
    """
    Fuzzy search across multiple fields with weights.

    Args:
        query: Search query
        items: List of items to search
        key_funcs: List of (key_func, weight) tuples
                   e.g., [(lambda x: x.title, 1.0), (lambda x: x.author, 0.5)]
        threshold: Minimum weighted score (0.0-1.0)
        limit: Maximum number of results to return

    Returns:
        List of (item, weighted_score) tuples, sorted by score descending
    """
    if not query:
        return []

    # Normalize weights
    total_weight = sum(weight for _, weight in key_funcs)
    if total_weight == 0:
        return []

    # Calculate weighted scores
    scored_items = []
    for item in items:
        weighted_score = 0.0

        for key_func, weight in key_funcs:
            try:
                text = key_func(item)
                if text:  # Only score non-empty fields
                    score = fuzzy_match_ratio(query, text)
                    weighted_score += score * (weight / total_weight)
            except (AttributeError, TypeError):
                # Skip fields that don't exist or can't be converted to string
                continue

        if weighted_score >= threshold:
            scored_items.append((item, weighted_score))

    # Sort by score (highest first)
    scored_items.sort(key=lambda x: x[1], reverse=True)

    # Apply limit
    if limit:
        scored_items = scored_items[:limit]

    return scored_items


def contains_word(query: str, text: str, case_sensitive: bool = False) -> bool:
    """
    Check if text contains query as a whole word.

    Args:
        query: Search query
        text: Text to search in
        case_sensitive: Whether to do case-sensitive matching

    Returns:
        True if text contains query as a word
    """
    if not query or not text:
        return False

    if not case_sensitive:
        query = query.lower()
        text = text.lower()

    # Split into words and check
    words = text.split()
    return query in words


def substring_match(query: str, text: str, case_sensitive: bool = False) -> bool:
    """
    Check if text contains query as a substring.

    Args:
        query: Search query
        text: Text to search in
        case_sensitive: Whether to do case-sensitive matching

    Returns:
        True if text contains query as substring
    """
    if not query or not text:
        return False

    if not case_sensitive:
        query = query.lower()
        text = text.lower()

    return query in text


def best_fuzzy_match(
    query: str,
    texts: List[str],
    threshold: float = 0.6,
) -> Tuple[Optional[str], float]:
    """
    Find the best fuzzy match from a list of texts.

    Args:
        query: Search query
        texts: List of texts to match against
        threshold: Minimum match ratio

    Returns:
        Tuple of (best_match, score) or (None, 0.0) if no match above threshold
    """
    if not query or not texts:
        return None, 0.0

    best_match = None
    best_score = 0.0

    for text in texts:
        if not text:
            continue

        score = fuzzy_match_ratio(query, text)
        if score > best_score and score >= threshold:
            best_score = score
            best_match = text

    return best_match, best_score


def highlight_match(query: str, text: str) -> str:
    """
    Highlight matching parts of text (for display purposes).

    This is a simple implementation that highlights the query if it's a substring.
    For more complex highlighting, use a library like `rich`.

    Args:
        query: Search query
        text: Text to highlight in

    Returns:
        Text with match highlighted (using ANSI codes or markers)
    """
    if not query or not text:
        return text

    # Case-insensitive substring search
    lower_text = text.lower()
    lower_query = query.lower()

    if lower_query in lower_text:
        # Find the position
        pos = lower_text.find(lower_query)
        # Preserve original case in output
        before = text[:pos]
        match = text[pos : pos + len(query)]
        after = text[pos + len(query) :]
        return f"{before}[bold yellow]{match}[/bold yellow]{after}"

    return text
