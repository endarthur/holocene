#!/usr/bin/env python3
"""
Test Mercado Livre OAuth without redirect_uri parameter.
Workaround for CloudFront 403 error.
"""

import sys
from pathlib import Path
from urllib.parse import urlencode

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from holocene.config import load_config


def main():
    print("=" * 60)
    print("Mercado Livre OAuth - No Redirect URI Test")
    print("=" * 60)

    # Load config
    config = load_config()
    ml_config = config.mercadolivre

    if not ml_config.client_id:
        print("\n✗ Client ID not configured")
        return 1

    # Generate auth URL WITHOUT redirect_uri (workaround for CloudFront 403)
    params = {
        "response_type": "code",
        "client_id": ml_config.client_id,
        # NOTE: Intentionally omitting redirect_uri as workaround
    }

    auth_url = f"https://auth.mercadolivre.com.br/authorization?{urlencode(params)}"

    print("\nWorkaround: Trying authorization WITHOUT redirect_uri parameter")
    print("(This may work around the CloudFront 403 error)")
    print("\n" + "=" * 60)
    print("STEP 1: Open this URL in your browser:")
    print(f"\n{auth_url}\n")
    print("=" * 60)
    print("\nSTEP 2: After authorizing, you'll be redirected somewhere")
    print("Copy the 'code' parameter from the redirect URL")
    print("\nSTEP 3: Run the normal auth command:")
    print("  holo mercadolivre auth --manual")
    print("\nAnd paste the code when prompted.")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
