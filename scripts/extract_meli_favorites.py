#!/usr/bin/env python3
"""Extract favorites from Mercado Livre saved HTML pages."""

import re
import json
import sys
from pathlib import Path

def extract_preloaded_state(html_content: str) -> dict:
    """Extract __PRELOADED_STATE__ JSON from HTML."""
    # Find the __PRELOADED_STATE__ assignment
    pattern = r'__PRELOADED_STATE__\s*=\s*({.*?});'
    match = re.search(pattern, html_content, re.DOTALL)

    if not match:
        raise ValueError("Could not find __PRELOADED_STATE__ in HTML")

    json_str = match.group(1)
    return json.loads(json_str)


def parse_favorites(preloaded_state: dict) -> list:
    """Parse favorites from preloaded state."""
    favorites = []

    # Navigate the JSON structure
    try:
        elements = preloaded_state.get('initialState', {}).get('elements', {})
        polycards = elements.get('polycards', [])

        print(f"Found {len(polycards)} items in polycards")

        for polycard in polycards:
            metadata = polycard.get('metadata', {})
            components = polycard.get('components', [])

            # Extract data from components
            title = None
            price = None
            currency = None
            condition = None

            for component in components:
                comp_type = component.get('type')

                if comp_type == 'title':
                    title = component.get('title', {}).get('text')

                elif comp_type == 'price':
                    price_data = component.get('price', {}).get('current_price', {})
                    price = price_data.get('value')
                    currency = price_data.get('currency')

                elif comp_type == 'attributes':
                    # Condition might be here
                    attrs = component.get('attributes', [])
                    for attr in attrs:
                        if attr.get('id') == 'ITEM_CONDITION':
                            condition = attr.get('text')

            # Build full URL
            url_base = metadata.get('url', '')
            url_params = metadata.get('url_params', '')
            permalink = f"https://{url_base}{url_params}" if url_base else None

            favorites.append({
                'item_id': metadata.get('id'),
                'bookmark_id': metadata.get('bookmarks_id'),
                'variation_id': metadata.get('variation_id'),
                'title': title,
                'price': price,
                'currency': currency,
                'permalink': permalink,
                'condition': condition,
                'thumbnail_id': polycard.get('pictures', {}).get('pictures', [{}])[0].get('id'),
            })

    except Exception as e:
        print(f"Error parsing: {e}")
        import traceback
        traceback.print_exc()

    return favorites


def main(html_file: Path):
    """Main extraction function."""
    print(f"Reading {html_file}...")

    with open(html_file, 'r', encoding='utf-8') as f:
        html_content = f.read()

    print("Extracting __PRELOADED_STATE__...")
    try:
        state = extract_preloaded_state(html_content)
    except ValueError as e:
        print(f"Error: {e}")
        return 1

    # Save raw JSON for inspection
    debug_file = html_file.with_suffix('.json')
    with open(debug_file, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    print(f"✓ Saved raw JSON to: {debug_file}")

    print("\nParsing favorites...")
    favorites = parse_favorites(state)

    print(f"\n✓ Found {len(favorites)} favorites")

    if favorites:
        print("\nFirst 3 items:")
        for fav in favorites[:3]:
            print(f"  - {fav['item_id']}: {fav['title']}")

    # Save favorites
    output_file = html_file.parent / f"{html_file.stem}_favorites.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(favorites, f, indent=2, ensure_ascii=False)
    print(f"\n✓ Saved favorites to: {output_file}")

    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extract_meli_favorites.py <html_file>")
        print("\nExample:")
        print("  python extract_meli_favorites.py personal/meli_2025-11-18_p1-28.html")
        sys.exit(1)

    html_file = Path(sys.argv[1])
    if not html_file.exists():
        print(f"Error: File not found: {html_file}")
        sys.exit(1)

    sys.exit(main(html_file))
