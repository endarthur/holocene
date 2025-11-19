"""Mercado Livre API integration for favorites/bookmarks."""

from typing import List, Dict, Optional
from datetime import datetime, timedelta
from urllib.parse import urlencode
import re
import json
import time
import random

import requests
from bs4 import BeautifulSoup

from holocene.core.api_client import BaseAPIClient
from holocene.core.rate_limiter import get_global_limiter


class MercadoLivreOAuth:
    """OAuth 2.0 flow for Mercado Livre."""

    AUTHORIZE_URL = "https://auth.mercadolivre.com.br/authorization"
    TOKEN_URL = "https://api.mercadolibre.com/oauth/token"
    API_BASE_URL = "https://api.mercadolibre.com"

    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        """Initialize OAuth handler.

        Args:
            client_id: Mercado Livre app client ID
            client_secret: Mercado Livre app client secret
            redirect_uri: OAuth redirect URI (usually http://localhost:8080/auth/callback)
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    def get_authorization_url(self, scope: str = "read write offline_access") -> str:
        """Generate authorization URL for user to visit.

        Args:
            scope: Space-separated OAuth scopes (default: "read write offline_access")
                   - read: Read user data and bookmarks
                   - write: Modify bookmarks and user data
                   - offline_access: Get refresh token for auto-renewal

        Returns:
            Full authorization URL to open in browser
        """
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": scope,
        }
        return f"{self.AUTHORIZE_URL}?{urlencode(params)}"

    def exchange_code_for_token(self, code: str) -> Dict:
        """Exchange authorization code for access token.

        Args:
            code: Authorization code from OAuth redirect

        Returns:
            Token response dict with access_token, refresh_token, expires_in
        """
        # Use BaseAPIClient for the request
        with BaseAPIClient(base_url=self.API_BASE_URL, use_global_limiter=False) as client:
            data = {
                "grant_type": "authorization_code",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "redirect_uri": self.redirect_uri,
            }

            response = client.post("/oauth/token", json=data)
            response.raise_for_status()
            return response.json()
            # Returns: {"access_token": "...", "token_type": "bearer",
            #           "expires_in": 21600, "refresh_token": "..."}

    def refresh_token(self, refresh_token: str) -> Dict:
        """Refresh expired access token.

        Args:
            refresh_token: Refresh token from previous auth

        Returns:
            New token response
        """
        with BaseAPIClient(base_url=self.API_BASE_URL, use_global_limiter=False) as client:
            data = {
                "grant_type": "refresh_token",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": refresh_token,
            }

            response = client.post("/oauth/token", json=data)
            response.raise_for_status()
            return response.json()


class MercadoLivreClient(BaseAPIClient):
    """Client for Mercado Livre API."""

    BASE_URL = "https://api.mercadolibre.com"

    def __init__(self, access_token: str, use_rate_limiting: bool = True):
        """Initialize Mercado Livre API client.

        Args:
            access_token: OAuth access token
            use_rate_limiting: Whether to use rate limiting (default True)
        """
        super().__init__(
            base_url=self.BASE_URL,
            use_global_limiter=use_rate_limiting,
            rate_limit=1.0,  # Conservative: 1 req/sec
        )
        self.access_token = access_token
        self.session.headers.update({
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        })

    def get_user_info(self) -> Dict:
        """Get authenticated user's info.

        Returns:
            User info dict with id, nickname, email, etc.
        """
        response = self.get("/users/me")
        response.raise_for_status()
        return response.json()

    def get_favorites(self) -> List[Dict]:
        """Get user's favorited items (bookmarks).

        Returns:
            List of bookmark dicts with item_id and bookmarked_date
        """
        response = self.get("/users/me/bookmarks")
        response.raise_for_status()
        return response.json()

    def add_favorite(self, item_id: str) -> Dict:
        """Add item to favorites.

        Args:
            item_id: Mercado Livre item ID (e.g., "MLB1234567890")

        Returns:
            Response dict
        """
        response = self.post("/users/me/bookmarks", json={"item_id": item_id})
        response.raise_for_status()
        return response.json()

    def remove_favorite(self, item_id: str) -> Dict:
        """Remove item from favorites.

        Args:
            item_id: Mercado Livre item ID

        Returns:
            Response dict
        """
        response = self.delete(f"/users/me/bookmarks/{item_id}")
        response.raise_for_status()
        return response.json()

    def get_item_details(self, item_id: str) -> Dict:
        """Get full details for an item.

        Args:
            item_id: Mercado Livre item ID

        Returns:
            Item details dict with title, price, category, permalink, etc.
        """
        response = self.get(f"/items/{item_id}")
        response.raise_for_status()
        return response.json()

    def get_category(self, category_id: str) -> Dict:
        """Get category name and details.

        Args:
            category_id: Mercado Livre category ID

        Returns:
            Category dict with name, path_from_root, etc.
        """
        response = self.get(f"/categories/{category_id}")
        response.raise_for_status()
        return response.json()

    def sync_favorites(self) -> List[Dict]:
        """Fetch all favorites with full item details.

        Returns:
            List of enriched favorite dicts with full item info
        """
        bookmarks = self.get_favorites()

        items = []
        for bookmark in bookmarks:
            item_id = bookmark["item_id"]
            bookmarked_date = bookmark.get("bookmarked_date")

            # Get full item details
            try:
                details = self.get_item_details(item_id)

                # Get category name
                category_name = None
                if "category_id" in details:
                    try:
                        category = self.get_category(details["category_id"])
                        category_name = category.get("name")
                    except Exception:
                        pass

                items.append({
                    "item_id": item_id,
                    "title": details.get("title"),
                    "price": details.get("price"),
                    "currency": details.get("currency_id"),
                    "category_id": details.get("category_id"),
                    "category_name": category_name,
                    "url": details.get("permalink"),
                    "thumbnail": details.get("thumbnail"),
                    "condition": details.get("condition"),
                    "available_quantity": details.get("available_quantity", 0),
                    "bookmarked_date": bookmarked_date,
                    "is_available": details.get("status") == "active",
                })

            except Exception as e:
                # Item might be deleted or unavailable
                items.append({
                    "item_id": item_id,
                    "title": f"[Unavailable: {item_id}]",
                    "bookmarked_date": bookmarked_date,
                    "is_available": False,
                    "error": str(e),
                })

        return items


def is_token_expired(token_data: Dict) -> bool:
    """Check if OAuth token is expired.

    Args:
        token_data: Dict with 'expires_at' or 'issued_at' and 'expires_in'

    Returns:
        True if token is expired or will expire in <5 minutes
    """
    if "expires_at" in token_data:
        expires_at = datetime.fromisoformat(token_data["expires_at"])
        return datetime.utcnow() >= expires_at - timedelta(minutes=5)

    if "issued_at" in token_data and "expires_in" in token_data:
        issued_at = datetime.fromisoformat(token_data["issued_at"])
        expires_in = token_data["expires_in"]
        expires_at = issued_at + timedelta(seconds=expires_in)
        return datetime.utcnow() >= expires_at - timedelta(minutes=5)

    # If we can't determine, assume expired
    return True


def fetch_product_page(url: str, delay: float = 2.5) -> Dict:
    """Fetch and parse a Mercado Livre product page.

    Args:
        url: Product page URL
        delay: Delay before making request (default 2.5s, polite crawling)

    Returns:
        Dict with enriched product data including description, specs, seller info
    """
    # Polite delay
    if delay > 0:
        time.sleep(delay + random.uniform(-0.5, 0.5))  # Add jitter

    # Fetch page with browser-like headers
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }

    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()

    html = response.text
    soup = BeautifulSoup(html, 'html.parser')

    result = {
        'url': url,
        'fetched_at': datetime.utcnow().isoformat(),
    }

    # Extract JSON-LD structured data (schema.org format)
    json_ld_scripts = soup.find_all('script', type='application/ld+json')

    for script in json_ld_scripts:
        try:
            data = json.loads(script.string)

            # Product/Offer data
            if data.get('@type') == 'Product' or 'offers' in data:
                if 'name' in data:
                    result['title'] = data['name']

                if 'image' in data:
                    result['image_url'] = data['image'] if isinstance(data['image'], str) else data['image'][0]

                if 'offers' in data:
                    offers = data['offers']
                    if 'price' in offers:
                        result['price'] = float(offers['price'])
                    if 'priceCurrency' in offers:
                        result['currency'] = offers['priceCurrency']
                    if 'availability' in offers:
                        result['availability'] = 'InStock' in offers['availability']

                if 'aggregateRating' in data:
                    rating = data['aggregateRating']
                    result['reviews'] = {
                        'rating_average': float(rating.get('ratingValue', 0)),
                        'total': int(rating.get('reviewCount', 0)),
                    }

            # Breadcrumb for category
            if data.get('@type') == 'BreadcrumbList':
                items = data.get('itemListElement', [])
                if items:
                    # Last item is the most specific category
                    result['category'] = items[-1].get('item', {}).get('name')
                    result['category_path'] = ' > '.join([
                        item.get('item', {}).get('name', '') for item in items
                    ])

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            continue

    # Fallback: scrape from HTML if JSON-LD didn't have everything
    if 'title' not in result:
        title_tag = soup.find('h1', class_='ui-pdp-title')
        if title_tag:
            result['title'] = title_tag.get_text(strip=True)

    if 'price' not in result:
        price_tag = soup.find('span', class_='andes-money-amount__fraction')
        if price_tag:
            try:
                result['price'] = float(price_tag.get_text(strip=True).replace('.', '').replace(',', '.'))
            except:
                pass

    # Extract description from meta tags or main content
    description_meta = soup.find('meta', property='og:description')
    if description_meta and description_meta.get('content'):
        result['description'] = description_meta.get('content')

    # Extract seller info from page
    seller_link = soup.find('a', class_=re.compile('.*seller.*'))
    if seller_link:
        result['seller_info'] = {
            'nickname': seller_link.get_text(strip=True) if seller_link else None
        }

    # Extract shipping info
    if soup.find(text=re.compile('Frete grátis|frete gr[aá]tis', re.I)):
        result['shipping'] = {'free_shipping': True}

    return result
