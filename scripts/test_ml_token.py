#!/usr/bin/env python3
"""Test Mercado Livre access token to diagnose 403 issue."""

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from holocene.config import load_config
from holocene.integrations.mercadolivre import MercadoLivreClient

def main():
    print("=" * 60)
    print("Mercado Livre Token Diagnostic Test")
    print("=" * 60)

    config = load_config()
    ml_config = config.mercadolivre

    if not ml_config.access_token:
        print("\n✗ No access token found in config")
        return 1

    print(f"\n✓ Access token found: {ml_config.access_token[:20]}...")

    client = MercadoLivreClient(ml_config.access_token)

    # Test 1: Get user info (basic endpoint)
    print("\n" + "=" * 60)
    print("Test 1: GET /users/me (basic user info)")
    print("=" * 60)
    try:
        user_info = client.get_user_info()
        print(f"✓ Success! User ID: {user_info.get('id')}")
        print(f"  Nickname: {user_info.get('nickname')}")
        print(f"  Email: {user_info.get('email', 'N/A')}")
    except Exception as e:
        print(f"✗ Error: {e}")
        print("  → Basic user endpoint failed - token might be invalid")
        return 1

    # Test 2: Get bookmarks
    print("\n" + "=" * 60)
    print("Test 2: GET /users/me/bookmarks (favorites)")
    print("=" * 60)
    try:
        bookmarks = client.get_favorites()
        print(f"✓ Success! Found {len(bookmarks)} bookmarks")
        if bookmarks:
            print(f"  First bookmark: {bookmarks[0]}")
    except Exception as e:
        print(f"✗ Error: {e}")
        print("\n  Possible causes:")
        print("  1. Bookmarks endpoint requires app certification")
        print("  2. Personal accounts can't access their own bookmarks via API")
        print("  3. Missing specific scope beyond 'read/write'")
        print("  4. Endpoint only available for seller/business accounts")
        return 1

    print("\n" + "=" * 60)
    print("✓ All tests passed!")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
