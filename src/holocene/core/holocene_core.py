"""HoloceneCore - Central coordinator for the Holocene system.

Provides the core API that plugins use to interact with the system.
"""

import logging
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor
import threading

from ..storage.database import Database
from ..config import Config, load_config
from .channels import ChannelManager

logger = logging.getLogger(__name__)


class HoloceneCore:
    """Central coordinator for Holocene.

    This class provides the core API that plugins interact with:
    - Database access
    - Channel messaging (pub/sub)
    - Background task execution
    - Configuration access
    - LLM client access (future)

    Example:
        core = HoloceneCore()

        # Database
        books = core.db.get_books(limit=10)

        # Messaging
        core.channels.subscribe('books.added', my_callback)
        core.channels.publish('books.added', {'title': 'TAOCP'})

        # Background tasks
        core.run_in_background(expensive_task, callback=on_complete)
    """

    def __init__(self, config: Optional[Config] = None, db: Optional[Database] = None):
        """Initialize Holocene core.

        Args:
            config: Configuration (loads default if not provided)
            db: Database instance (creates new if not provided)
        """
        # Configuration
        self.config = config or load_config()

        # Database
        if db:
            self.db = db
        else:
            db_path = self.config.data_dir / "holocene.db"
            self.db = Database(db_path)

        # Messaging system
        self.channels = ChannelManager()

        # Background task executor
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="holocene-bg")
        self._shutdown_event = threading.Event()

        logger.info("HoloceneCore initialized")

    def run_in_background(self, task, callback=None, error_handler=None):
        """Execute a task in the background.

        Non-blocking execution for expensive operations like LLM calls.

        Args:
            task: Callable to execute
            callback: Optional callback on success, receives task result
            error_handler: Optional callback on error, receives exception

        Returns:
            Future object

        Example:
            def enrich_book(book_id):
                # Call LLM, analyze, etc.
                return result

            def on_complete(result):
                print(f"Enrichment complete: {result}")

            core.run_in_background(
                lambda: enrich_book(123),
                callback=on_complete
            )
        """
        def wrapper():
            try:
                result = task()
                if callback:
                    callback(result)
                return result
            except Exception as e:
                logger.error(f"Background task failed: {e}", exc_info=True)
                if error_handler:
                    error_handler(e)
                raise

        future = self._executor.submit(wrapper)
        return future

    def shutdown(self):
        """Shutdown core and cleanup resources."""
        logger.info("Shutting down HoloceneCore...")

        # Signal shutdown
        self._shutdown_event.set()

        # Shutdown executor
        self._executor.shutdown(wait=True, cancel_futures=False)

        # Close database
        if self.db:
            self.db.close()

        logger.info("HoloceneCore shutdown complete")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.shutdown()
