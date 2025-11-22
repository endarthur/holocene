# Integration Guidelines

**Purpose:** Document patterns for adding new integrations to Holocene.

**Last Updated:** 2025-11-21

---

## Quick Decision Tree

```
Adding a new integration?
│
├─ Uses HTTP REST API?
│  ├─ Yes → Use BaseAPIClient
│  │
│  └─ Needs proxy/caching? (paid scraping)
│     └─ Yes → Use HTTPFetcher
│
├─ Official SDK/Library available?
│  └─ Yes → Use SDK directly (e.g., Apify)
│
├─ CLI tool?
│  └─ Yes → subprocess wrapper (e.g., Calibre)
│
└─ File/local operations?
   └─ Custom implementation (e.g., journel, bookmarks)
```

---

## Pattern 1: BaseAPIClient (Recommended for HTTP APIs)

**When to use:**
- Interacting with RESTful HTTP APIs
- Need rate limiting
- Want consistent error handling
- Future plans for retries/caching

**Example integrations:**
- ✅ Internet Archive (`internet_archive.py`)
- ✅ Mercado Livre (`mercadolivre.py`)
- ✅ arXiv (`arxiv.py`)

### Template

```python
"""Integration with ServiceName API."""

import logging
from typing import Dict, Optional
from holocene.integrations.base_api_client import BaseAPIClient

logger = logging.getLogger(__name__)


class ServiceNameClient(BaseAPIClient):
    """Client for ServiceName API."""

    def __init__(self, api_key: Optional[str] = None, rate_limit: float = 1.0):
        """Initialize ServiceName client.

        Args:
            api_key: Optional API key
            rate_limit: Minimum seconds between requests (default: 1.0)
        """
        super().__init__(
            base_url="https://api.servicename.com/v1",
            rate_limit=rate_limit
        )
        self.api_key = api_key

    def _get_headers(self) -> Dict[str, str]:
        """Get headers for API requests."""
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def get_item(self, item_id: str) -> Dict:
        """Fetch item by ID.

        Args:
            item_id: Item identifier

        Returns:
            Item metadata dictionary
        """
        response = self.get(
            f"/items/{item_id}",
            headers=self._get_headers()
        )
        return response.json()
```

### Benefits

- ✅ Automatic rate limiting (domain-based token bucket)
- ✅ Consistent error handling
- ✅ Session management
- ✅ User-Agent handling
- ✅ Timeout configuration
- ✅ Future-proof for caching/retries

---

## Pattern 2: HTTPFetcher (For Paid Proxies + Caching)

**When to use:**
- Scraping websites (not APIs)
- Using paid proxy service (Bright Data, etc.)
- Need to cache HTML responses
- Want proxy toggle (dev vs production)

**Example integrations:**
- ✅ Mercado Livre scraping (`mercadolivre.py` - uses both!)

### Template

```python
"""Integration with ServiceName scraping."""

import logging
from holocene.integrations.http_fetcher import HTTPFetcher
from holocene.config import Config

logger = logging.getLogger(__name__)


class ServiceNameScraper:
    """Scraper for ServiceName with proxy support."""

    def __init__(self, config: Config):
        """Initialize scraper.

        Args:
            config: Holocene configuration
        """
        self.config = config
        self.fetcher = HTTPFetcher.from_config(
            config,
            use_proxy=config.integrations.brightdata_enabled,
            integration_name='servicename'
        )

    def scrape_page(self, item_id: str) -> str:
        """Scrape page HTML.

        Args:
            item_id: Item identifier

        Returns:
            HTML content (from cache or fresh fetch)
        """
        url = f"https://www.servicename.com/item/{item_id}"

        # Fetch with caching
        html, cached_path = self.fetcher.fetch(
            url,
            cache_key=item_id  # Used for cache filename
        )

        if cached_path:
            logger.info(f"Loaded from cache: {cached_path}")

        return html
```

### Benefits

- ✅ Bright Data proxy routing
- ✅ HTML caching (saves money!)
- ✅ Cache hit/miss logging
- ✅ Configurable cache directory
- ✅ Proxy toggle via config

### Configuration

```yaml
integrations:
  brightdata_enabled: true
  brightdata_proxy_url: "http://username:password@proxy.brightdata.com:port"

mercadolivre:
  cache_html: true
```

---

## Pattern 3: SDK/Library (When Official Client Exists)

**When to use:**
- Official SDK is well-maintained
- SDK handles auth/rate limiting
- More features than raw HTTP

**Example integrations:**
- ✅ Apify (`apify.py` - uses `apify-client`)
- ⚠️ Future: Telegram (when upgrading from custom to SDK)

### Template

```python
"""Integration with ServiceName using official SDK."""

import logging
from servicename_sdk import ServiceNameClient as SDKClient

logger = logging.getLogger(__name__)


class ServiceNameIntegration:
    """Wrapper around ServiceName SDK."""

    def __init__(self, api_key: str):
        """Initialize SDK client.

        Args:
            api_key: ServiceName API key
        """
        self.client = SDKClient(api_key)

    def get_item(self, item_id: str) -> dict:
        """Fetch item using SDK.

        Args:
            item_id: Item identifier

        Returns:
            Item data dictionary
        """
        result = self.client.items.get(item_id)
        return result.to_dict()
```

### Benefits

- ✅ Maintained by service provider
- ✅ Handles API changes automatically
- ✅ Often includes helpful utilities
- ⚠️ Additional dependency

---

## Pattern 4: CLI Tool Wrapper (For Command-Line Tools)

**When to use:**
- Tool has CLI but no Python API
- CLI is stable and well-documented
- Don't want to reimplement complex logic

**Example integrations:**
- ✅ Calibre (`calibre.py` - wraps `calibredb`)

### Template

```python
"""Integration with ToolName CLI."""

import logging
import subprocess
import json
from pathlib import Path
from typing import List, Dict

logger = logging.getLogger(__name__)


class ToolNameCLI:
    """Wrapper for toolname CLI."""

    def __init__(self, library_path: Path):
        """Initialize CLI wrapper.

        Args:
            library_path: Path to library directory
        """
        self.library_path = library_path

    def list_items(self) -> List[Dict]:
        """List items via CLI.

        Returns:
            List of item dictionaries
        """
        cmd = [
            "toolname",
            "list",
            "--library-path", str(self.library_path),
            "--for-machine"  # JSON output
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )

        return json.loads(result.stdout)
```

### Benefits

- ✅ Leverage existing tool functionality
- ✅ No need to understand internal formats
- ⚠️ Requires tool to be installed
- ⚠️ Slower than native library

---

## Pattern 5: File/Local Operations (Custom Implementation)

**When to use:**
- Reading local files
- No external API involved
- Simple parsing logic

**Example integrations:**
- ✅ journel (`journel.py` - reads `.journel` files)
- ✅ Git scanner (`git_scanner.py` - uses GitPython)
- ✅ Bookmarks (`bookmarks.py` - parses JSON)

### Template

```python
"""Integration with local file format."""

import logging
from pathlib import Path
from typing import List, Dict
import json

logger = logging.getLogger(__name__)


class FileFormatReader:
    """Reader for custom file format."""

    def __init__(self, file_path: Path):
        """Initialize reader.

        Args:
            file_path: Path to file
        """
        self.file_path = file_path

    def read_items(self) -> List[Dict]:
        """Read items from file.

        Returns:
            List of item dictionaries
        """
        with open(self.file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        return data.get('items', [])
```

### Benefits

- ✅ Simple and direct
- ✅ No external dependencies
- ✅ Fast

---

## Integration Checklist

When adding a new integration, ensure:

- [ ] **Pattern selected** - Chose appropriate pattern from above
- [ ] **Config section added** - Added to `config/loader.py` if needed
- [ ] **CLI commands created** - Added to `cli/` for user access
- [ ] **Rate limiting configured** - If HTTP API, set appropriate rate
- [ ] **Error handling** - Uses logger, not print statements
- [ ] **Documentation** - Added to this guide and CLAUDE.md
- [ ] **Tests written** - At least basic integration test
- [ ] **SUMMARY.md updated** - Added to implemented features list

---

## Rate Limiting Guidelines

**Conservative Defaults:**
- Unknown APIs: 2.0 sec/request (30/min)
- Documented limits: Use 80% of stated limit
- Free tier APIs: Be extra conservative

**Known Limits:**
- Internet Archive: 2.0 sec (30/min)
- arXiv: 3.0 sec (20/min) - per their policy
- Mercado Livre: 1.0 sec (60/min) - undocumented, conservative

**Override in config:**
```yaml
integrations:
  internet_archive_rate_limit: 2.0  # seconds between requests
```

---

## Error Handling Pattern

**Consistent pattern across all integrations:**

```python
def fetch_data(self, item_id: str) -> Dict:
    """Fetch data with proper error handling."""
    try:
        response = self.get(f"/items/{item_id}")
        response.raise_for_status()
        return response.json()
    except requests.HTTPError as e:
        logger.error(f"HTTP error fetching {item_id}: {e}")
        raise
    except requests.RequestException as e:
        logger.error(f"Request failed for {item_id}: {e}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON response for {item_id}: {e}")
        raise
```

**CLI commands should catch and display friendly errors:**

```python
@click.command()
def sync():
    """Sync data from ServiceName."""
    try:
        client = ServiceNameClient()
        items = client.fetch_items()
        console.print(f"[green]✓[/green] Synced {len(items)} items")
    except Exception as e:
        console.print(f"[red]✗ Error:[/red] {e}")
        sys.exit(1)
```

---

## Examples from Codebase

### BaseAPIClient: Internet Archive

```python
class InternetArchiveClient(BaseAPIClient):
    def __init__(self, rate_limit: float = 2.0):
        super().__init__(
            base_url="https://archive.org",
            rate_limit=rate_limit
        )

    def get_metadata(self, identifier: str) -> Dict:
        response = self.get(f"/metadata/{identifier}")
        return response.json()
```

**Location:** `src/holocene/integrations/internet_archive.py`

### HTTPFetcher: Mercado Livre Scraping

```python
fetcher = HTTPFetcher.from_config(
    config,
    use_proxy=config.integrations.brightdata_enabled,
    integration_name='mercadolivre'
)

html, cached_path = fetcher.fetch(
    url=item_url,
    cache_key=item_id
)
```

**Location:** `src/holocene/integrations/mercadolivre.py`

### SDK: Apify

```python
from apify_client import ApifyClient

class ApifyIntegration:
    def __init__(self, api_token: str):
        self.client = ApifyClient(api_token)
```

**Location:** `src/holocene/integrations/apify.py`

---

## Future Patterns

### Pattern: GraphQL API

When GraphQL API integration is needed:

```python
class GraphQLClient(BaseAPIClient):
    def query(self, query: str, variables: Dict = None) -> Dict:
        response = self.post(
            "/graphql",
            json={"query": query, "variables": variables or {}}
        )
        return response.json()
```

### Pattern: WebSocket

For real-time integrations (future daemon mode):

```python
import websockets

class WebSocketIntegration:
    async def connect(self):
        async with websockets.connect("wss://api.example.com") as ws:
            await ws.send(json.dumps({"type": "subscribe"}))
            async for message in ws:
                await self.handle_message(message)
```

---

## Questions?

**Not sure which pattern to use?**
- Check existing similar integrations
- Ask in project discussion
- Default to BaseAPIClient for HTTP APIs

**Need a new pattern?**
- Document it here after implementation
- Update CLAUDE.md with the new approach
- Add example to this guide

---

**See Also:**
- `CLAUDE.md` - Project conventions
- `design/SUMMARY.md` - Current integrations list
- `src/holocene/integrations/base_api_client.py` - BaseAPIClient implementation
- `src/holocene/integrations/http_fetcher.py` - HTTPFetcher implementation
