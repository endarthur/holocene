"""Channel-based messaging system for Holocene.

Provides a lightweight pub/sub messaging system for decoupled communication
between plugins and core components.

Design inspired by Scissors Runner's channel system.
"""

import logging
from typing import Callable, Dict, List, Any, Optional
from dataclasses import dataclass
from datetime import datetime
import queue
import threading

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """A message sent through a channel."""
    channel: str
    data: Any
    timestamp: datetime
    sender: Optional[str] = None


class ChannelManager:
    """Manages pub/sub channels for inter-component communication.

    Features:
    - Subscribe to channels with callbacks
    - Publish messages to channels
    - Async message delivery (non-blocking)
    - Message history for debugging

    Example:
        channels = ChannelManager()

        # Subscribe
        def on_book_added(msg):
            print(f"New book: {msg.data['title']}")

        channels.subscribe('books.added', on_book_added)

        # Publish
        channels.publish('books.added', {'title': 'TAOCP', 'author': 'Knuth'})
    """

    def __init__(self, history_size: int = 100):
        """Initialize channel manager.

        Args:
            history_size: Number of recent messages to keep per channel
        """
        self._subscribers: Dict[str, List[Callable]] = {}
        self._history: Dict[str, List[Message]] = {}
        self._history_size = history_size
        self._lock = threading.Lock()

    def subscribe(self, channel: str, callback: Callable[[Message], None]):
        """Subscribe to a channel.

        Args:
            channel: Channel name (e.g., 'books.added', 'enrichment.complete')
            callback: Function to call when message received
        """
        with self._lock:
            if channel not in self._subscribers:
                self._subscribers[channel] = []
                self._history[channel] = []

            self._subscribers[channel].append(callback)
            logger.debug(f"Subscribed to channel: {channel}")

    def unsubscribe(self, channel: str, callback: Callable[[Message], None]):
        """Unsubscribe from a channel.

        Args:
            channel: Channel name
            callback: Callback to remove
        """
        with self._lock:
            if channel in self._subscribers:
                try:
                    self._subscribers[channel].remove(callback)
                    logger.debug(f"Unsubscribed from channel: {channel}")
                except ValueError:
                    pass

    def publish(self, channel: str, data: Any, sender: Optional[str] = None):
        """Publish a message to a channel.

        Args:
            channel: Channel name
            data: Message data (any JSON-serializable object)
            sender: Optional sender identifier
        """
        message = Message(
            channel=channel,
            data=data,
            timestamp=datetime.now(),
            sender=sender
        )

        # Add to history
        with self._lock:
            if channel not in self._history:
                self._history[channel] = []

            self._history[channel].append(message)

            # Trim history
            if len(self._history[channel]) > self._history_size:
                self._history[channel] = self._history[channel][-self._history_size:]

            # Get subscribers (copy list to avoid modification during iteration)
            subscribers = self._subscribers.get(channel, []).copy()

        # Notify subscribers (outside lock to avoid blocking)
        logger.debug(f"Publishing to {channel}: {len(subscribers)} subscriber(s)")

        for callback in subscribers:
            try:
                callback(message)
            except Exception as e:
                logger.error(f"Error in subscriber callback for {channel}: {e}", exc_info=True)

    def get_history(self, channel: str, limit: Optional[int] = None) -> List[Message]:
        """Get recent messages from a channel.

        Args:
            channel: Channel name
            limit: Max number of messages to return

        Returns:
            List of messages (most recent last)
        """
        with self._lock:
            history = self._history.get(channel, [])
            if limit:
                return history[-limit:]
            return history.copy()

    def clear_history(self, channel: Optional[str] = None):
        """Clear message history.

        Args:
            channel: Specific channel to clear, or None for all channels
        """
        with self._lock:
            if channel:
                self._history[channel] = []
            else:
                self._history.clear()

    def list_channels(self) -> List[str]:
        """Get list of all active channels.

        Returns:
            List of channel names
        """
        with self._lock:
            return list(self._subscribers.keys())

    def subscriber_count(self, channel: str) -> int:
        """Get number of subscribers for a channel.

        Args:
            channel: Channel name

        Returns:
            Number of subscribers
        """
        with self._lock:
            return len(self._subscribers.get(channel, []))
