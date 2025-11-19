#!/usr/bin/env python3
"""Generate curl command with actual access token for testing."""

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from holocene.config import load_config

def main():
    config = load_config()
    ml_config = config.mercadolivre

    if not ml_config.access_token:
        print("✗ No access token found in config")
        return 1

    token = ml_config.access_token

    print("=" * 80)
    print("Mercado Livre API Test Commands")
    print("=" * 80)

    print("\n1. Test user info endpoint (should work):")
    print("-" * 80)
    print(f'curl -X GET -H "Authorization: Bearer {token}" https://api.mercadolibre.com/users/me')

    print("\n\n2. Test bookmarks endpoint (currently getting 403):")
    print("-" * 80)
    print(f'curl -X GET -H "Authorization: Bearer {token}" https://api.mercadolibre.com/users/me/bookmarks')

    print("\n\n3. Verbose bookmarks request (shows full HTTP response):")
    print("-" * 80)
    print(f'curl -v -X GET -H "Authorization: Bearer {token}" https://api.mercadolibre.com/users/me/bookmarks')

    print("\n" + "=" * 80)
    print("Copy and paste the command above into your terminal")
    print("=" * 80)

    return 0


if __name__ == "__main__":
    sys.exit(main())
