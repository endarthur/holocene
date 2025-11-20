"""Example plugin demonstrating the plugin system.

This is a simple plugin that:
- Subscribes to book.added events
- Logs messages
- Demonstrates background task execution
"""

import time
from holocene.core import Plugin, Message


class ExamplePlugin(Plugin):
    """Example plugin for testing."""

    def get_metadata(self):
        return {
            "name": "example",
            "version": "1.0.0",
            "description": "Example plugin for testing the plugin system",
            "runs_on": ["both"],  # Runs on any device
            "requires": []  # No dependencies
        }

    def on_load(self):
        """Called when plugin is loaded."""
        self.logger.info("Example plugin loaded!")
        self.book_count = 0

    def on_enable(self):
        """Called when plugin is enabled."""
        self.logger.info("Example plugin enabled!")

        # Subscribe to events
        self.subscribe('books.added', self._on_book_added)
        self.subscribe('test.ping', self._on_ping)

    def _on_book_added(self, msg: Message):
        """Handle book.added events."""
        self.book_count += 1
        self.logger.info(f"Book added: {msg.data}")
        self.logger.info(f"Total books processed: {self.book_count}")

        # Publish acknowledgment
        self.publish('books.processed', {
            'book_id': msg.data.get('book_id'),
            'processed_by': self.name,
            'count': self.book_count
        })

    def _on_ping(self, msg: Message):
        """Handle test.ping events."""
        self.logger.info(f"Received ping: {msg.data}")

        # Respond with pong (simulate async work)
        def do_work():
            time.sleep(0.1)  # Simulate work
            return {"status": "pong", "from": self.name}

        def on_complete(result):
            self.publish('test.pong', result)

        self.run_in_background(do_work, callback=on_complete)

    def on_disable(self):
        """Called when plugin is disabled."""
        self.logger.info(f"Example plugin disabled! Processed {self.book_count} books total")
