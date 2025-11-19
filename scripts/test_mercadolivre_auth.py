#!/usr/bin/env python3
"""
Test script for Mercado Livre OAuth manual flow.

This script helps you test the OAuth flow without running the full CLI.
"""

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from holocene.integrations.mercadolivre import MercadoLivreOAuth


def test_manual_oauth():
    """Test the manual OAuth flow."""
    print("Mercado Livre OAuth Manual Flow Test")
    print("=" * 50)

    # Get credentials
    client_id = input("\nEnter your Client ID: ").strip()
    client_secret = input("Enter your Client Secret: ").strip()
    redirect_uri = input("Enter redirect URI (default: https://google.com): ").strip() or "https://google.com"

    # Initialize OAuth
    oauth = MercadoLivreOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
    )

    # Generate auth URL
    auth_url = oauth.get_authorization_url()

    print("\n" + "=" * 50)
    print("STEP 1: Open this URL in your browser:")
    print(f"\n{auth_url}\n")

    print("STEP 2: After authorizing, copy the 'code' from the redirect URL")
    print(f"Example: {redirect_uri}?code=TG-abc123xyz")
    print("Copy only: TG-abc123xyz")

    code = input("\nAuthorization code: ").strip()

    # Exchange code for token
    print("\nExchanging code for token...")
    try:
        token_data = oauth.exchange_code_for_token(code)

        print("\n" + "=" * 50)
        print("✓ SUCCESS! Token received:")
        print(f"  Access Token: {token_data['access_token'][:20]}...")
        print(f"  Token Type: {token_data.get('token_type', 'N/A')}")
        print(f"  Expires In: {token_data.get('expires_in', 'N/A')} seconds")

        if "refresh_token" in token_data:
            print(f"  Refresh Token: {token_data['refresh_token'][:20]}...")
            print("\n✓ Refresh token saved - you can auto-refresh!")

        print("\nYou can now use these credentials in your config.yml:")
        print(f"""
mercadolivre:
  enabled: true
  client_id: "{client_id}"
  client_secret: "{client_secret}"
  redirect_uri: "{redirect_uri}"
  access_token: "{token_data['access_token']}"
  refresh_token: "{token_data.get('refresh_token', '')}"
""")

    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        print("\nCommon issues:")
        print("  - Code expired (try again quickly)")
        print("  - Invalid client ID/secret")
        print("  - Wrong redirect_uri (must match app config)")
        return False

    return True


if __name__ == "__main__":
    success = test_manual_oauth()
    sys.exit(0 if success else 1)
