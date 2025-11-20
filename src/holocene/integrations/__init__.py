"""Integrations with external services."""

from .journel import JournelReader
from .git_scanner import GitScanner, GitRepo
from .internet_archive import InternetArchiveClient
from .bookmarks import BookmarksReader, Bookmark
from .calibre import CalibreIntegration

# Optional: MercadoLivre (requires beautifulsoup4)
try:
    from .mercadolivre import MercadoLivreClient, MercadoLivreOAuth, is_token_expired
    MERCADOLIVRE_AVAILABLE = True
except ImportError:
    MercadoLivreClient = None
    MercadoLivreOAuth = None
    is_token_expired = None
    MERCADOLIVRE_AVAILABLE = False

__all__ = [
    "JournelReader",
    "GitScanner",
    "GitRepo",
    "InternetArchiveClient",
    "BookmarksReader",
    "Bookmark",
    "CalibreIntegration",
    "MercadoLivreClient",
    "MercadoLivreOAuth",
    "is_token_expired",
    "MERCADOLIVRE_AVAILABLE",
]
