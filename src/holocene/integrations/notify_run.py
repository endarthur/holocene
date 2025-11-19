"""Notify.run integration for notifications."""

import requests
from typing import Optional


class NotifyRunClient:
    """Client for notify.run webhook notifications."""

    def __init__(self, channel: Optional[str] = None):
        """
        Initialize notify.run client.

        Args:
            channel: Notify.run channel ID (from config)
        """
        self.channel = channel

    @property
    def channel_url(self) -> Optional[str]:
        """Get the full channel URL."""
        if not self.channel:
            return None
        return f"https://notify.run/{self.channel}"

    def send(self, message: str, action: Optional[str] = None) -> bool:
        """
        Send a notification to the channel.

        Args:
            message: Notification message
            action: Optional action URL to open when tapped

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.channel_url:
            return False

        try:
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
            }

            if action:
                headers['Action'] = action

            response = requests.post(
                self.channel_url,
                headers=headers,
                data=message,
                timeout=5
            )
            response.raise_for_status()
            return True

        except Exception:
            # Silently fail - notifications shouldn't break workflows
            return False

    def notify_task_complete(self, task_name: str, details: Optional[str] = None):
        """Send task completion notification."""
        message = f"✅ {task_name} complete"
        if details:
            message += f"\n{details}"
        return self.send(message)

    def notify_task_failed(self, task_name: str, error: Optional[str] = None):
        """Send task failure notification."""
        message = f"❌ {task_name} failed"
        if error:
            message += f"\n{error}"
        return self.send(message)

    def notify_task_progress(self, task_name: str, current: int, total: int):
        """Send task progress notification."""
        percentage = (current / total * 100) if total > 0 else 0
        message = f"⏳ {task_name}: {current}/{total} ({percentage:.1f}%)"
        return self.send(message)


# Global instance (can be set from config)
_global_client: Optional[NotifyRunClient] = None


def set_global_client(client: NotifyRunClient):
    """Set the global notify.run client."""
    global _global_client
    _global_client = client


def get_global_client() -> Optional[NotifyRunClient]:
    """Get the global notify.run client."""
    return _global_client


def notify(message: str, action: Optional[str] = None) -> bool:
    """
    Send notification using global client.

    Args:
        message: Notification message
        action: Optional action URL

    Returns:
        True if sent, False otherwise
    """
    client = get_global_client()
    if client:
        return client.send(message, action)
    return False
