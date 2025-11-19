"""AI-powered categorization for inventory items."""

from typing import Optional, Dict, List, Tuple
from holocene.llm.nanogpt import NanoGPTClient
from holocene.core.taxonomy import InventoryTaxonomy


def suggest_category(
    title: str,
    description: Optional[str],
    taxonomy: InventoryTaxonomy,
    llm_client: NanoGPTClient,
    model: str = "deepseek-ai/DeepSeek-V3.1"
) -> Tuple[Optional[str], float, str]:
    """
    Use DeepSeek to suggest a category for an item.

    Args:
        title: Item title
        description: Item description (optional)
        taxonomy: Taxonomy instance
        llm_client: NanoGPT client
        model: Model to use

    Returns:
        Tuple of (category_code, confidence, reasoning)
    """
    # Build taxonomy reference for the prompt
    taxonomy_ref = _build_taxonomy_reference(taxonomy)

    # Build prompt
    item_info = f"Title: {title}"
    if description:
        # Truncate long descriptions
        desc_preview = description[:500] + "..." if len(description) > 500 else description
        item_info += f"\nDescription: {desc_preview}"

    prompt = f"""You are categorizing an item for a personal inventory system.

ITEM TO CATEGORIZE:
{item_info}

AVAILABLE CATEGORIES:
{taxonomy_ref}

Your task:
1. Analyze the item and determine the most appropriate category
2. Respond with ONLY a JSON object in this exact format:
{{
  "category": "CATEGORY-CODE",
  "confidence": 0.95,
  "reasoning": "Brief explanation"
}}

Rules:
- Use the most specific category that fits (e.g., T-MEAS-CAL rather than T-MEAS)
- Confidence should be 0.0 to 1.0 (0.8+ for clear matches, 0.5-0.8 for uncertain, below 0.5 for unclear)
- If no good match exists, use confidence below 0.3 and explain why
- Reasoning should be 1-2 sentences max

Response:"""

    try:
        response_text = llm_client.simple_prompt(
            prompt=prompt,
            model=model,
            temperature=0.1,  # Low temperature for consistent categorization
        )

        # Parse JSON response
        import json
        # Extract JSON from response (handle code blocks)
        json_text = response_text.strip()
        if json_text.startswith("```"):
            # Remove code block markers
            lines = json_text.split("\n")
            json_text = "\n".join(lines[1:-1]) if len(lines) > 2 else json_text

        result = json.loads(json_text)

        category = result.get("category")
        confidence = float(result.get("confidence", 0.0))
        reasoning = result.get("reasoning", "")

        # Validate category exists in taxonomy
        if category:
            cat_info = taxonomy.get_category_info(category)
            if not cat_info:
                # Try to normalize it
                normalized = taxonomy.normalize_category(category)
                if normalized:
                    category = normalized
                else:
                    # Invalid category
                    return None, 0.0, f"Invalid category suggested: {category}"

        return category, confidence, reasoning

    except Exception as e:
        return None, 0.0, f"Error during categorization: {str(e)}"


def _build_taxonomy_reference(taxonomy: InventoryTaxonomy, max_categories: int = 50) -> str:
    """Build a concise taxonomy reference for the prompt.

    Args:
        taxonomy: Taxonomy instance
        max_categories: Maximum categories to include

    Returns:
        Formatted taxonomy reference string
    """
    lines = []

    # Get all categories sorted by code
    categories = sorted(taxonomy.canonical_map.items())

    # Limit to avoid token bloat
    if len(categories) > max_categories:
        # Include all top-level and some children
        top_level = [(code, data) for code, data in categories if '-' not in code]
        children = [(code, data) for code, data in categories if '-' in code]

        # Take top-level + sample of children
        selected = top_level + children[:max_categories - len(top_level)]
    else:
        selected = categories

    for code, data in selected:
        label = data['label']
        aliases = data.get('aliases', [])

        # Format: CODE: Label (aliases: ...)
        line = f"{code}: {label}"
        if aliases:
            # Show first 3 aliases
            alias_str = ", ".join(aliases[:3])
            line += f" (e.g., {alias_str})"

        lines.append(line)

    return "\n".join(lines)


def batch_suggest_categories(
    items: List[Dict],
    taxonomy: InventoryTaxonomy,
    llm_client: NanoGPTClient,
    confidence_threshold: float = 0.5,
    model: str = "deepseek-ai/DeepSeek-V3.1"
) -> List[Dict]:
    """
    Suggest categories for multiple items.

    Args:
        items: List of item dicts with 'title' and optional 'description'
        taxonomy: Taxonomy instance
        llm_client: NanoGPT client
        confidence_threshold: Minimum confidence to include suggestion
        model: Model to use

    Returns:
        List of dicts with 'item', 'category', 'confidence', 'reasoning'
    """
    results = []

    for item in items:
        title = item.get('title', '')
        description = item.get('description')

        if not title:
            results.append({
                'item': item,
                'category': None,
                'confidence': 0.0,
                'reasoning': 'No title provided'
            })
            continue

        category, confidence, reasoning = suggest_category(
            title=title,
            description=description,
            taxonomy=taxonomy,
            llm_client=llm_client,
            model=model
        )

        # Only include if meets threshold
        if confidence >= confidence_threshold:
            results.append({
                'item': item,
                'category': category,
                'confidence': confidence,
                'reasoning': reasoning
            })
        else:
            results.append({
                'item': item,
                'category': None,
                'confidence': confidence,
                'reasoning': reasoning
            })

    return results
