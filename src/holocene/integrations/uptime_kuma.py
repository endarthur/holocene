"""Uptime Kuma integration for holocene monitoring."""

import logging
from dataclasses import dataclass
from typing import Optional
from enum import Enum

import requests

logger = logging.getLogger(__name__)


class MonitorType(Enum):
    """Uptime Kuma monitor types."""
    HTTP = "http"
    TCP = "port"
    PING = "ping"
    PUSH = "push"
    DNS = "dns"
    DOCKER = "docker"


@dataclass
class Monitor:
    """Represents an Uptime Kuma monitor."""
    id: Optional[int] = None
    name: str = ""
    type: MonitorType = MonitorType.HTTP
    url: Optional[str] = None
    hostname: Optional[str] = None
    port: Optional[int] = None
    interval: int = 60  # seconds
    active: bool = True
    push_token: Optional[str] = None  # For push monitors

    def to_api_dict(self) -> dict:
        """Convert to Uptime Kuma API format."""
        data = {
            "name": self.name,
            "type": self.type.value,
            "interval": self.interval,
            "active": self.active,
        }
        if self.url:
            data["url"] = self.url
        if self.hostname:
            data["hostname"] = self.hostname
        if self.port:
            data["port"] = self.port
        return data


class UptimeKumaClient:
    """Client for interacting with Uptime Kuma API."""

    def __init__(self, base_url: str, api_key: str):
        """
        Initialize Uptime Kuma client.

        Args:
            base_url: Uptime Kuma instance URL (e.g., http://192.168.1.103:3001)
            api_key: API key for authentication
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers["X-API-KEY"] = api_key

    def _request(self, method: str, endpoint: str, **kwargs) -> dict:
        """Make an API request."""
        url = f"{self.base_url}{endpoint}"
        try:
            response = self.session.request(method, url, timeout=10, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Uptime Kuma API error: {e}")
            raise

    def get_monitors(self) -> list[dict]:
        """Get all monitors."""
        # Note: Uptime Kuma's REST API is limited
        # Most operations require Socket.IO
        # For now, we'll use what's available
        try:
            result = self._request("GET", "/api/status-page/holocene")
            return result.get("publicGroupList", [])
        except Exception:
            logger.warning("Could not fetch monitors via REST API")
            return []

    def ping_push_monitor(self, push_token: str, status: str = "up", msg: str = "", ping: Optional[int] = None) -> bool:
        """
        Ping a push monitor.

        Args:
            push_token: The push monitor's token/URL path
            status: "up" or "down"
            msg: Optional status message
            ping: Optional ping time in ms

        Returns:
            True if ping was successful
        """
        params = {"status": status}
        if msg:
            params["msg"] = msg
        if ping is not None:
            params["ping"] = ping

        try:
            url = f"{self.base_url}/api/push/{push_token}"
            response = self.session.get(url, params=params, timeout=10)
            data = response.json()
            if data.get("ok"):
                logger.debug(f"Push monitor ping successful: {push_token}")
                return True
            else:
                logger.warning(f"Push monitor ping failed: {data.get('msg', 'Unknown error')}")
                return False
        except Exception as e:
            logger.error(f"Push monitor ping error: {e}")
            return False

    def create_status_page(self, slug: str, title: str) -> bool:
        """
        Create a status page.

        Args:
            slug: URL slug for the status page
            title: Display title

        Returns:
            True if created successfully
        """
        try:
            data = {
                "slug": slug,
                "title": title,
                "theme": "auto",
                "published": True,
                "showTags": False,
                "showPoweredBy": False,
            }
            self._request("POST", "/api/status-page", json=data)
            logger.info(f"Created status page: {slug}")
            return True
        except Exception as e:
            logger.error(f"Failed to create status page: {e}")
            return False


class HoloceneMonitorConfig:
    """
    Configuration for holocene services to monitor.

    This defines what monitors holocene should create in Uptime Kuma.
    """

    @staticmethod
    def get_monitors(config) -> list[Monitor]:
        """
        Get list of monitors based on holocene config.

        Args:
            config: Holocene Config object

        Returns:
            List of Monitor objects to create
        """
        monitors = []

        # holod REST API - always monitor if daemon is used
        monitors.append(Monitor(
            name="holod API",
            type=MonitorType.HTTP,
            url="http://192.168.1.101:5555/health",
            interval=60,
        ))

        # ArchiveBox
        if config.integrations.archivebox_enabled:
            monitors.append(Monitor(
                name="ArchiveBox",
                type=MonitorType.TCP,
                hostname=config.integrations.archivebox_host,
                port=22,  # SSH port check
                interval=60,
            ))

        # Proxmox
        if config.integrations.proxmox_enabled:
            host = config.integrations.proxmox_host
            port = config.integrations.proxmox_port
            monitors.append(Monitor(
                name="Proxmox API",
                type=MonitorType.HTTP,
                url=f"https://{host}:{port}/api2/json/version",
                interval=120,
            ))

        # Telegram bot - ping check to Telegram API
        if hasattr(config, 'telegram') and config.telegram.enabled:
            monitors.append(Monitor(
                name="Telegram API",
                type=MonitorType.HTTP,
                url="https://api.telegram.org",
                interval=300,  # 5 minutes
            ))

        return monitors


def setup_holocene_monitoring(config) -> dict:
    """
    Set up Uptime Kuma monitoring for holocene services.

    This is a high-level function that:
    1. Connects to Uptime Kuma
    2. Creates necessary monitors
    3. Returns status information

    Note: Due to Uptime Kuma's Socket.IO-based API for creating monitors,
    this function primarily provides guidance for manual setup and handles
    push monitor functionality.

    Args:
        config: Holocene Config object

    Returns:
        Dict with setup status and instructions
    """
    if not config.integrations.uptime_kuma_enabled:
        return {"success": False, "error": "Uptime Kuma integration not enabled"}

    if not config.integrations.uptime_kuma_api_key:
        return {"success": False, "error": "Uptime Kuma API key not configured"}

    client = UptimeKumaClient(
        config.integrations.uptime_kuma_url,
        config.integrations.uptime_kuma_api_key
    )

    # Get recommended monitors
    monitors = HoloceneMonitorConfig.get_monitors(config)

    result = {
        "success": True,
        "uptime_kuma_url": config.integrations.uptime_kuma_url,
        "recommended_monitors": [
            {
                "name": m.name,
                "type": m.type.value,
                "target": m.url or f"{m.hostname}:{m.port}",
                "interval": m.interval,
            }
            for m in monitors
        ],
        "instructions": [
            f"1. Open {config.integrations.uptime_kuma_url}",
            "2. Click 'Add New Monitor' for each service below",
            "3. For holod, create a 'Push' monitor and copy the push URL",
            "4. Add the push token to your holocene config",
        ],
    }

    return result
