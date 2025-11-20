"""Plugin base class and infrastructure.

All Holocene plugins inherit from the Plugin base class, which provides:
- Access to core system (database, channels, config)
- Lifecycle hooks (on_load, on_enable, on_disable)
- Metadata declaration (name, runs_on, requires)
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from pathlib import Path
import logging

from .holocene_core import HoloceneCore
from .channels import Message

logger = logging.getLogger(__name__)


class Plugin(ABC):
    """Base class for all Holocene plugins.

    Plugins have access to:
    - self.core.db: Database
    - self.core.channels: Channel messaging
    - self.core.config: Configuration
    - self.core.run_in_background(): Background execution

    Lifecycle:
    1. __init__() - Plugin created
    2. on_load() - Plugin loaded into system
    3. on_enable() - Plugin activated (can subscribe to channels)
    4. [Plugin runs]
    5. on_disable() - Plugin deactivated (cleanup)

    Example:
        class BookEnricherPlugin(Plugin):
            def get_metadata(self):
                return {
                    "name": "book_enricher",
                    "version": "1.0.0",
                    "description": "Enriches books with LLM summaries",
                    "runs_on": ["rei", "wmut"],  # Where plugin can run
                    "requires": []
                }

            def on_load(self):
                print("Plugin loaded")

            def on_enable(self):
                # Subscribe to events
                self.subscribe('books.added', self._on_book_added)

            def _on_book_added(self, msg: Message):
                book_id = msg.data['book_id']
                self.core.run_in_background(
                    lambda: self._enrich_book(book_id)
                )

            def _enrich_book(self, book_id):
                # Do enrichment
                pass

            def on_disable(self):
                print("Plugin disabled")
    """

    def __init__(self, core: HoloceneCore):
        """Initialize plugin with core system access.

        Args:
            core: HoloceneCore instance
        """
        self.core = core
        self._subscriptions = []  # Track subscriptions for cleanup
        self.enabled = False

        metadata = self.get_metadata()
        self.name = metadata.get('name', self.__class__.__name__)
        self.logger = logging.getLogger(f"holocene.plugins.{self.name}")

    @abstractmethod
    def get_metadata(self) -> Dict[str, Any]:
        """Return plugin metadata.

        Must return dict with:
        - name: str - Unique plugin identifier
        - version: str - Semantic version
        - description: str - Short description
        - runs_on: List[str] - Where plugin runs ["rei", "wmut", "both"]
        - requires: List[str] - Plugin dependencies

        Returns:
            Metadata dictionary
        """
        pass

    def on_load(self):
        """Called when plugin is loaded into system.

        Use for:
        - One-time initialization
        - Registering CLI commands
        - Setting up resources

        Note: Don't subscribe to channels here - use on_enable()
        """
        pass

    def on_enable(self):
        """Called when plugin is activated.

        Use for:
        - Subscribing to channels
        - Starting background tasks
        - Activating features

        This is called after on_load().
        """
        pass

    def on_disable(self):
        """Called when plugin is deactivated.

        Use for:
        - Cleanup
        - Stopping background tasks
        - Saving state

        Note: Channel subscriptions are automatically cleaned up.
        """
        pass

    # Convenience methods

    def subscribe(self, channel: str, callback):
        """Subscribe to a channel (tracked for auto-cleanup).

        Args:
            channel: Channel name
            callback: Callback function
        """
        self.core.channels.subscribe(channel, callback)
        self._subscriptions.append((channel, callback))
        self.logger.debug(f"Subscribed to {channel}")

    def publish(self, channel: str, data: Any):
        """Publish to a channel.

        Args:
            channel: Channel name
            data: Message data
        """
        self.core.channels.publish(channel, data, sender=self.name)
        self.logger.debug(f"Published to {channel}")

    def run_in_background(self, task, callback=None, error_handler=None):
        """Execute task in background.

        Args:
            task: Callable to execute
            callback: Optional success callback
            error_handler: Optional error callback

        Returns:
            Future object
        """
        return self.core.run_in_background(task, callback, error_handler)

    def _cleanup_subscriptions(self):
        """Internal: Clean up channel subscriptions."""
        for channel, callback in self._subscriptions:
            self.core.channels.unsubscribe(channel, callback)
        self._subscriptions.clear()
        self.logger.debug("Cleaned up subscriptions")

    def enable(self):
        """Enable the plugin."""
        if not self.enabled:
            self.logger.info(f"Enabling plugin: {self.name}")
            self.on_enable()
            self.enabled = True

    def disable(self):
        """Disable the plugin."""
        if self.enabled:
            self.logger.info(f"Disabling plugin: {self.name}")
            self.on_disable()
            self._cleanup_subscriptions()
            self.enabled = False
