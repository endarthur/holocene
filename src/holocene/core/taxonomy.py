"""Inventory taxonomy system for Holocene.

This module provides hierarchical categorization for inventory items with
flexible, freeform input that normalizes to canonical codes.

License: CC0 1.0 Universal (Public Domain)
"""

import re
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from functools import lru_cache


class InventoryTaxonomy:
    """Manages inventory categorization with flexible matching."""

    def __init__(self, taxonomy_path: Optional[Path] = None):
        """Initialize taxonomy from YAML file.

        Args:
            taxonomy_path: Path to taxonomy YAML file (optional)
        """
        if taxonomy_path is None:
            # Default to bundled taxonomy
            taxonomy_path = Path(__file__).parent.parent / "data" / "inventory_taxonomy.yml"

        self.taxonomy_path = taxonomy_path
        self._taxonomy = None
        self._alias_map = None
        self._canonical_map = None

    @property
    def taxonomy(self) -> Dict:
        """Lazy load taxonomy data."""
        if self._taxonomy is None:
            with open(self.taxonomy_path, 'r', encoding='utf-8') as f:
                self._taxonomy = yaml.safe_load(f)
        return self._taxonomy

    @property
    def alias_map(self) -> Dict[str, str]:
        """Build alias -> canonical code mapping."""
        if self._alias_map is None:
            self._alias_map = {}
            self._build_alias_map(self.taxonomy['categories'])
        return self._alias_map

    @property
    def canonical_map(self) -> Dict[str, Dict]:
        """Build canonical code -> category data mapping."""
        if self._canonical_map is None:
            self._canonical_map = {}
            self._build_canonical_map(self.taxonomy['categories'])
        return self._canonical_map

    def _build_alias_map(self, categories: Dict, parent_code: str = ""):
        """Recursively build alias mapping.

        Args:
            categories: Category dict
            parent_code: Parent category code
        """
        for code, data in categories.items():
            if not isinstance(data, dict):
                continue

            # Full canonical code
            full_code = f"{parent_code}-{code}" if parent_code else code

            # Map code itself
            self._alias_map[code.lower()] = full_code

            # Map all aliases
            if 'aliases' in data:
                for alias in data['aliases']:
                    self._alias_map[alias.lower()] = full_code

            # Recurse into children
            children = {k: v for k, v in data.items()
                       if k not in ['label', 'description', 'aliases',
                                   'wikipedia', 'wikidata', 'schema_org']}
            if children:
                self._build_alias_map(children, full_code)

    def _build_canonical_map(self, categories: Dict, parent_code: str = ""):
        """Recursively build canonical code mapping.

        Args:
            categories: Category dict
            parent_code: Parent category code
        """
        for code, data in categories.items():
            if not isinstance(data, dict):
                continue

            full_code = f"{parent_code}-{code}" if parent_code else code

            self._canonical_map[full_code] = {
                'code': full_code,
                'label': data.get('label', code),
                'description': data.get('description'),
                'aliases': data.get('aliases', []),
                'wikipedia': data.get('wikipedia'),
                'wikidata': data.get('wikidata'),
                'schema_org': data.get('schema_org'),
            }

            # Recurse
            children = {k: v for k, v in data.items()
                       if k not in ['label', 'description', 'aliases',
                                   'wikipedia', 'wikidata', 'schema_org']}
            if children:
                self._build_canonical_map(children, full_code)

    def normalize_category(self, input_category: str) -> Optional[str]:
        """Normalize freeform category input to canonical code.

        Args:
            input_category: User input (e.g., "tools-measurement-caliper")

        Returns:
            Canonical code (e.g., "T-MEAS-CAL") or None if no match
        """
        if not input_category:
            return None

        # Clean input
        input_clean = input_category.lower().strip()

        # Check if it's already canonical
        if input_clean.upper() in self.canonical_map:
            return input_clean.upper()

        # Split on common separators
        parts = re.split(r'[-./\s_]+', input_clean)

        # Try to match each part against aliases
        matched_codes = []
        for part in parts:
            if part in self.alias_map:
                # Get the full code for this alias
                full_code = self.alias_map[part]
                # Take the last segment
                last_segment = full_code.split('-')[-1]
                matched_codes.append(last_segment)

        if not matched_codes:
            return None

        # Build candidate code
        candidate = '-'.join(matched_codes).upper()

        # Check if it exists
        if candidate in self.canonical_map:
            return candidate

        # Try partial matches (e.g., "T-MEAS" if "T-MEAS-CAL" doesn't exist)
        for i in range(len(matched_codes), 0, -1):
            partial = '-'.join(matched_codes[:i]).upper()
            if partial in self.canonical_map:
                return partial

        return None

    def get_category_info(self, code: str) -> Optional[Dict]:
        """Get full information for a category code.

        Args:
            code: Canonical code

        Returns:
            Category info dict or None
        """
        return self.canonical_map.get(code.upper())

    def search_categories(self, query: str) -> List[Tuple[str, str]]:
        """Search categories by label or alias.

        Args:
            query: Search query

        Returns:
            List of (code, label) tuples
        """
        query_lower = query.lower()
        results = []

        for code, data in self.canonical_map.items():
            # Check label
            if query_lower in data['label'].lower():
                results.append((code, data['label']))
                continue

            # Check aliases
            if any(query_lower in alias.lower() for alias in data.get('aliases', [])):
                results.append((code, data['label']))

        return results

    def get_children(self, parent_code: str) -> List[Tuple[str, str]]:
        """Get child categories of a parent.

        Args:
            parent_code: Parent category code

        Returns:
            List of (code, label) tuples for children
        """
        parent_code = parent_code.upper()
        children = []

        for code, data in self.canonical_map.items():
            if code == parent_code:
                continue

            # Check if this is a direct child
            if code.startswith(parent_code + '-'):
                # Make sure it's direct (not grandchild)
                remaining = code[len(parent_code) + 1:]
                if '-' not in remaining:
                    children.append((code, data['label']))

        return sorted(children)

    def format_tree(self, parent_code: Optional[str] = None, indent: int = 0) -> str:
        """Format category tree as text.

        Args:
            parent_code: Parent to start from (None = root)
            indent: Indentation level

        Returns:
            Formatted tree string
        """
        lines = []

        if parent_code is None:
            # Show root categories
            root_cats = [(code, data) for code, data in self.canonical_map.items()
                        if '-' not in code]
        else:
            parent_code = parent_code.upper()
            info = self.get_category_info(parent_code)
            if info:
                lines.append("  " * indent + f"{parent_code}: {info['label']}")
                if info['description']:
                    lines.append("  " * indent + f"  {info['description']}")

            # Get children
            root_cats = [(code, self.canonical_map[code])
                        for code, _ in self.get_children(parent_code)]
            indent += 1

        for code, data in sorted(root_cats):
            prefix = "  " * indent + "├─ "
            lines.append(f"{prefix}{code}: {data['label']}")

            # Recursively show children
            children = self.get_children(code)
            if children:
                child_tree = self.format_tree(code, indent + 1)
                if child_tree:
                    lines.append(child_tree)

        return "\n".join(lines)


# Global instance
_taxonomy = None


def get_taxonomy() -> InventoryTaxonomy:
    """Get global taxonomy instance."""
    global _taxonomy
    if _taxonomy is None:
        _taxonomy = InventoryTaxonomy()
    return _taxonomy
