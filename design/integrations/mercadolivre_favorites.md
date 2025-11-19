# Mercado Livre Favorites Integration

**Date:** 2025-11-18
**Status:** Planned (Phase 4.3)
**API:** https://developers.mercadolivre.com.br/pt_br/favoritos

---

## Overview

Mercado Livre (Mercado Libre) has an API for accessing user bookmarks/favorites. Users can save product listings to favorites, which sync across mobile and web apps.

**Use case for Holocene:** Track items user is interested in, classify them by category (e.g., books, tools, electronics), and optionally add notes about why they were favorited.

---

## API Details

### Authentication

**Protocol:** OAuth 2.0 (Authorization Code Grant)
**Base URL:** `https://api.mercadolibre.com`
**Documentation:** https://developers.mercadolivre.com.br/en_us/authentication-and-authorization

**Required Scopes:**
- `read` - Read user favorites
- `write` - Add/remove favorites (if needed)

**Token Expiration:** 6 hours

### Endpoints

**1. Get User's Favorites**
```
GET https://api.mercadolibre.com/users/me/bookmarks
Authorization: Bearer {ACCESS_TOKEN}
```

**Response:**
```json
[
  {
    "item_id": "MLB1234567890",
    "bookmarked_date": "2025-11-18T10:30:00.000Z"
  },
  {
    "item_id": "MLB0987654321",
    "bookmarked_date": "2025-11-17T15:45:00.000Z"
  }
]
```

**2. Add to Favorites**
```
POST https://api.mercadolibre.com/users/me/bookmarks
Authorization: Bearer {ACCESS_TOKEN}
Content-Type: application/json

{"item_id": "MLB1234567890"}
```

**3. Remove from Favorites**
```
DELETE https://api.mercadolibre.com/users/me/bookmarks/MLB1234567890
Authorization: Bearer {ACCESS_TOKEN}
```

### Item Details

Once you have item IDs, fetch full details:

```
GET https://api.mercadolibre.com/items/{ITEM_ID}
```

**Response includes:**
- `title` - Product title
- `price` - Current price
- `category_id` - Mercado Livre category
- `permalink` - Product URL
- `thumbnail` - Image URL
- `seller_id` - Seller information
- `attributes` - Product specifications

---

## Holocene Integration Design

### Database Schema

```sql
CREATE TABLE mercadolivre_favorites (
    id INTEGER PRIMARY KEY,
    item_id TEXT UNIQUE,
    title TEXT,
    price REAL,
    currency TEXT,
    category_id TEXT,
    category_name TEXT,
    url TEXT,
    thumbnail_url TEXT,

    -- Holocene classification
    dewey_class TEXT,           -- Extended Dewey (e.g., W380.1 for commerce)
    call_number TEXT,           -- Full call number
    tags TEXT,                  -- JSON array
    user_notes TEXT,            -- Why favorited?

    -- Tracking
    bookmarked_date TEXT,       -- When user favorited
    first_synced TEXT,          -- When Holocene first saw it
    last_checked TEXT,          -- Last price check
    is_available BOOLEAN,       -- Still for sale?

    FOREIGN KEY (dewey_class) REFERENCES classifications(dewey_class)
);
```

### Extractor Implementation

```python
# src/holocene/integrations/mercadolivre.py

import requests
from typing import List, Dict, Optional
from datetime import datetime

class MercadoLivreClient:
    """Client for Mercado Livre API"""

    BASE_URL = "https://api.mercadolibre.com"

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

    def get_favorites(self) -> List[Dict]:
        """Get user's favorited items"""
        url = f"{self.BASE_URL}/users/me/bookmarks"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def get_item_details(self, item_id: str) -> Dict:
        """Get full item details"""
        url = f"{self.BASE_URL}/items/{item_id}"
        response = requests.get(url)
        response.raise_for_status()
        return response.json()

    def sync_favorites(self) -> List[Dict]:
        """Fetch favorites with full details"""
        bookmarks = self.get_favorites()

        items = []
        for bookmark in bookmarks:
            item_id = bookmark["item_id"]
            bookmarked_date = bookmark["bookmarked_date"]

            # Get full details
            details = self.get_item_details(item_id)

            items.append({
                "item_id": item_id,
                "title": details["title"],
                "price": details["price"],
                "currency": details["currency_id"],
                "category_id": details["category_id"],
                "url": details["permalink"],
                "thumbnail": details.get("thumbnail"),
                "bookmarked_date": bookmarked_date,
            })

        return items
```

### OAuth Flow Implementation

```python
# src/holocene/integrations/mercadolivre_oauth.py

class MercadoLivreOAuth:
    """OAuth 2.0 flow for Mercado Livre"""

    AUTHORIZE_URL = "https://auth.mercadolibre.com.br/authorization"
    TOKEN_URL = "https://api.mercadolibre.com/oauth/token"

    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    def get_authorization_url(self) -> str:
        """Generate authorization URL for user"""
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
        }
        return f"{self.AUTHORIZE_URL}?{urlencode(params)}"

    def exchange_code_for_token(self, code: str) -> Dict:
        """Exchange authorization code for access token"""
        data = {
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": self.redirect_uri,
        }

        response = requests.post(self.TOKEN_URL, json=data)
        response.raise_for_status()
        return response.json()
        # Returns: {"access_token": "...", "token_type": "bearer", "expires_in": 21600}

    def refresh_token(self, refresh_token: str) -> Dict:
        """Refresh expired access token"""
        data = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token,
        }

        response = requests.post(self.TOKEN_URL, json=data)
        response.raise_for_status()
        return response.json()
```

---

## CLI Commands

### Setup

```bash
# First time setup - opens browser for OAuth
holo mercadolivre auth
# → Opens https://auth.mercadolibre.com.br/authorization?...
# → User logs in and authorizes
# → Redirects to localhost with code
# → Exchanges code for token
# → Stores token in config

# Check auth status
holo mercadolivre status
# → "Authenticated as: user@email.com"
# → "Token expires in: 4 hours 23 minutes"
```

### Sync Favorites

```bash
# Import favorites
holo mercadolivre sync
# → Fetches all favorited items
# → Classifies by category (books, tools, electronics)
# → Stores in database
# → Output: "Synced 42 favorites (15 new, 27 updated)"

# List favorites
holo mercadolivre list
# → Shows all synced favorites with Dewey classification

# Classify favorites
holo mercadolivre classify
# → Uses LLM to assign Dewey classes
# → Example: Book → W020 (bibliography)
# → Example: Tool → W621 (mechanical engineering)
```

### Integration with Research

```bash
# Find favorited books
holo books list --source mercadolivre
# → Shows books that were favorited on Mercado Livre

# Add favorited book to collection
holo books import mercadolivre MLB1234567890
# → Fetches details, creates book entry
```

---

## Classification Strategy

Mercado Livre items should use **W prefix** (web content):

**Books on Mercado Livre:**
```
W020 - Bibliography category
W800 - Literature category
W500 - Science books
```

**Tools/Equipment:**
```
W621 - Mechanical engineering tools
W621.9 - Hand tools
W681 - Precision instruments
```

**Electronics:**
```
W621.38 - Electronics
W004 - Computer hardware
```

**Why W prefix:**
- These are *products for sale*, not the books/tools themselves
- Links to marketplace, not primary content
- Separates from actual book collection

---

## Use Cases

### 1. Book Wishlist Management

```bash
# Sync favorites from Mercado Livre
holo mercadolivre sync

# See which favorited items are books
holo mercadolivre list --category books

# Add to reading wishlist
holo books wishlist add-from-mercadolivre MLB1234567890

# Price tracking (future)
holo mercadolivre check-prices
# → Alerts if favorited book goes on sale
```

### 2. Research Tools Tracking

```bash
# Favorited research equipment on ML
holo mercadolivre list --category tools

# Add notes about why you need it
holo mercadolivre note MLB1234567890 "Need for field work in Cerro Rico"

# Export shopping list
holo mercadolivre export --format markdown > shopping_list.md
```

### 3. Price History (Future Enhancement)

```python
# Track price changes
CREATE TABLE mercadolivre_price_history (
    id INTEGER PRIMARY KEY,
    item_id TEXT,
    price REAL,
    checked_at TEXT,
    FOREIGN KEY (item_id) REFERENCES mercadolivre_favorites(item_id)
);

# Alert on price drop
holo mercadolivre watch MLB1234567890 --notify-on-drop
```

---

## Configuration

Add to `~/.holocene/config.yaml`:

```yaml
mercadolivre:
  enabled: true
  client_id: "YOUR_CLIENT_ID"
  client_secret: "YOUR_CLIENT_SECRET"
  redirect_uri: "http://localhost:8080/auth/callback"

  # Token storage (encrypted)
  access_token: "..."
  refresh_token: "..."
  token_expires_at: "2025-11-18T16:30:00Z"

  # Sync settings
  auto_sync: false           # Auto-sync on startup?
  sync_interval_hours: 24    # How often to check

  # Classification
  auto_classify: true        # Use LLM to classify items?
  classify_as_web: true      # Use W prefix for all items
```

---

## Implementation Plan

### Phase 4.3: Basic Integration

**Tasks:**
1. Create Mercado Livre developer app (get client ID/secret)
2. Implement OAuth flow (`MercadoLivreOAuth`)
3. Implement API client (`MercadoLivreClient`)
4. Database schema for favorites
5. CLI commands: `auth`, `sync`, `list`

**Deliverables:**
- Can authenticate with Mercado Livre
- Can fetch and store favorites
- Can list synced items

### Phase 4.4: Classification & Integration

**Tasks:**
1. LLM-based classification of items
2. Extended Dewey assignment (W prefix)
3. Integration with research mode
4. Export capabilities

**Deliverables:**
- Favorites have Dewey classifications
- Can search across favorites
- Can export shopping lists

### Phase 5: Advanced Features

**Tasks:**
1. Price tracking and history
2. Price drop notifications (via notify.run)
3. Automatic wishlist management
4. Book detection and import to collection

**Deliverables:**
- Price alerts
- Smart shopping lists
- Seamless book importing

---

## Rate Limiting

Mercado Livre API limits (to verify from docs):
- Likely similar to other e-commerce APIs
- Use our token bucket rate limiter
- Conservative: 1 request per second

```python
# In MercadoLivreClient.__init__
from holocene.core.rate_limiter import get_global_limiter

self.rate_limiter = get_global_limiter()

# Before each request
if self.rate_limiter:
    self.rate_limiter.wait_for_token(url)
```

---

## Privacy Considerations

**Data stored:**
- Item IDs, titles, prices (public marketplace data)
- Bookmark dates (when user favorited)
- User notes (private, local only)

**NOT stored:**
- Mercado Livre account credentials (only tokens)
- Purchase history
- Payment information

**Token security:**
- Tokens stored encrypted in config
- Never logged or transmitted except to Mercado Livre API
- Refresh tokens used to maintain access

---

## Future Enhancements

**1. Smart Shopping Assistant**
```bash
holo mercadolivre recommend
# → "You favorited 3 geology books. Related items you might like..."
```

**2. Budget Tracking**
```bash
holo mercadolivre budget
# → "Total value of favorites: R$ 2,450.00"
# → "3 items have price drops (save R$ 150.00)"
```

**3. Cross-Platform Integration**
```bash
holo mercadolivre sync --to-goodreads
# → Sync book favorites to Goodreads wishlist
```

**4. Seller Analysis**
```bash
holo mercadolivre sellers
# → "Top sellers in your favorites: ..."
# → "Average seller rating: 4.8/5.0"
```

---

## Testing Without Full OAuth

For development/testing, can use:

**Manual token:** Get token from Mercado Livre developer dashboard, paste into config

**Mock data:** Create sample favorites for testing classification

```python
# tests/fixtures/mercadolivre_favorites.json
[
  {
    "item_id": "MLB1234567890",
    "title": "Livro: Geostatistics for Engineers",
    "price": 129.90,
    "category_id": "MLB1196",
    "url": "https://produto.mercadolivre.com.br/..."
  }
]
```

---

**Last Updated:** 2025-11-18
**Status:** Documented, ready for Phase 4.3 implementation
**Priority:** Medium (after core infrastructure)
