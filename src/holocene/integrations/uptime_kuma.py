"""Uptime Kuma integration for holocene monitoring."""

import logging
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

import requests

logger = logging.getLogger(__name__)

# Try to import uptime-kuma-api for monitor creation
try:
    from uptime_kuma_api import UptimeKumaApi, MonitorType as UKMonitorType
    UPTIME_KUMA_API_AVAILABLE = True
except ImportError:
    UPTIME_KUMA_API_AVAILABLE = False
    UptimeKumaApi = None
    UKMonitorType = None


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
    tags: list[str] = field(default_factory=list)

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

    def __init__(self, base_url: str, api_key: Optional[str] = None,
                 username: Optional[str] = None, password: Optional[str] = None):
        """
        Initialize Uptime Kuma client.

        Args:
            base_url: Uptime Kuma instance URL (e.g., http://192.168.1.103:3001)
            api_key: API key for simple REST calls
            username: Username for Socket.IO API (monitor creation)
            password: Password for Socket.IO API (monitor creation)
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.username = username
        self.password = password
        self.session = requests.Session()
        if api_key:
            self.session.headers["X-API-KEY"] = api_key
        self._socket_api = None

    def _get_socket_api(self):
        """Get or create Socket.IO API connection."""
        if not UPTIME_KUMA_API_AVAILABLE:
            raise ImportError(
                "uptime-kuma-api not installed. "
                "Install with: pip install holocene[monitoring]"
            )
        if not self.username or not self.password:
            raise ValueError(
                "Username and password required for monitor creation. "
                "Add uptime_kuma_username and uptime_kuma_password to config."
            )
        if not self._socket_api:
            self._socket_api = UptimeKumaApi(self.base_url)
            self._socket_api.login(self.username, self.password)
        return self._socket_api

    def disconnect(self):
        """Disconnect Socket.IO connection."""
        if self._socket_api:
            try:
                self._socket_api.disconnect()
            except Exception:
                pass
            self._socket_api = None

    def _request(self, method: str, endpoint: str, **kwargs) -> dict:
        """Make a simple API request."""
        url = f"{self.base_url}{endpoint}"
        try:
            response = self.session.request(method, url, timeout=10, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Uptime Kuma API error: {e}")
            raise

    def get_monitors(self) -> list[dict]:
        """Get all monitors via Socket.IO API."""
        api = self._get_socket_api()
        return api.get_monitors()

    def add_monitor(self, monitor: Monitor) -> dict:
        """
        Add a new monitor.

        Args:
            monitor: Monitor configuration

        Returns:
            Created monitor data including ID and push token (if push type)
        """
        api = self._get_socket_api()

        # Map our MonitorType to uptime-kuma-api MonitorType
        type_map = {
            MonitorType.HTTP: UKMonitorType.HTTP,
            MonitorType.TCP: UKMonitorType.PORT,
            MonitorType.PING: UKMonitorType.PING,
            MonitorType.PUSH: UKMonitorType.PUSH,
            MonitorType.DNS: UKMonitorType.DNS,
            MonitorType.DOCKER: UKMonitorType.DOCKER,
        }

        kwargs = {
            "type": type_map[monitor.type],
            "name": monitor.name,
            "interval": monitor.interval,
        }

        if monitor.url:
            kwargs["url"] = monitor.url
        if monitor.hostname:
            kwargs["hostname"] = monitor.hostname
        if monitor.port:
            kwargs["port"] = monitor.port

        result = api.add_monitor(**kwargs)
        logger.info(f"Created monitor: {monitor.name} (ID: {result.get('monitorID')})")
        return result

    def delete_monitor(self, monitor_id: int) -> bool:
        """Delete a monitor by ID."""
        api = self._get_socket_api()
        try:
            api.delete_monitor(monitor_id)
            return True
        except Exception as e:
            logger.error(f"Failed to delete monitor {monitor_id}: {e}")
            return False

    def get_monitor_by_name(self, name: str) -> Optional[dict]:
        """Find a monitor by name."""
        monitors = self.get_monitors()
        for m in monitors:
            if m.get("name") == name:
                return m
        return None

    def ping_push_monitor(self, push_token: str, status: str = "up",
                          msg: str = "", ping: Optional[int] = None) -> bool:
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


class HoloceneMonitorConfig:
    """
    Configuration for holocene services to monitor.

    This defines what monitors holocene should create in Uptime Kuma.
    """

    # Tag for holocene-managed monitors
    HOLOCENE_TAG = "holocene"

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
            tags=[HoloceneMonitorConfig.HOLOCENE_TAG],
        ))

        # holod Push monitor - daemon pings this
        monitors.append(Monitor(
            name="holod Daemon",
            type=MonitorType.PUSH,
            interval=60,
            tags=[HoloceneMonitorConfig.HOLOCENE_TAG],
        ))

        # ArchiveBox
        if config.integrations.archivebox_enabled:
            monitors.append(Monitor(
                name="ArchiveBox SSH",
                type=MonitorType.TCP,
                hostname=config.integrations.archivebox_host,
                port=22,
                interval=60,
                tags=[HoloceneMonitorConfig.HOLOCENE_TAG],
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
                tags=[HoloceneMonitorConfig.HOLOCENE_TAG],
            ))

        # Telegram bot - ping check to Telegram API
        if hasattr(config, 'telegram') and config.telegram.enabled:
            monitors.append(Monitor(
                name="Telegram API",
                type=MonitorType.HTTP,
                url="https://api.telegram.org",
                interval=300,
                tags=[HoloceneMonitorConfig.HOLOCENE_TAG],
            ))

        return monitors


def create_holocene_monitors(config, update_config_callback=None) -> dict:
    """
    Create all holocene monitors in Uptime Kuma.

    Args:
        config: Holocene Config object
        update_config_callback: Optional callback to save push token to config

    Returns:
        Dict with creation results
    """
    if not config.integrations.uptime_kuma_enabled:
        return {"success": False, "error": "Uptime Kuma integration not enabled"}

    if not UPTIME_KUMA_API_AVAILABLE:
        return {
            "success": False,
            "error": "uptime-kuma-api not installed. Install with: pip install holocene[monitoring]"
        }

    username = getattr(config.integrations, 'uptime_kuma_username', None)
    password = getattr(config.integrations, 'uptime_kuma_password', None)

    if not username or not password:
        return {
            "success": False,
            "error": "Username and password required. Add uptime_kuma_username and uptime_kuma_password to config."
        }

    client = UptimeKumaClient(
        config.integrations.uptime_kuma_url,
        api_key=config.integrations.uptime_kuma_api_key,
        username=username,
        password=password
    )

    try:
        # Get recommended monitors
        monitors = HoloceneMonitorConfig.get_monitors(config)
        results = {
            "success": True,
            "created": [],
            "skipped": [],
            "errors": [],
            "push_token": None,
        }

        # Get existing monitors to avoid duplicates
        existing = client.get_monitors()
        existing_names = {m.get("name") for m in existing}

        for monitor in monitors:
            if monitor.name in existing_names:
                results["skipped"].append(monitor.name)
                # If it's the push monitor, get the existing token
                if monitor.type == MonitorType.PUSH:
                    for m in existing:
                        if m.get("name") == monitor.name:
                            results["push_token"] = m.get("pushToken")
                            break
                continue

            try:
                result = client.add_monitor(monitor)
                results["created"].append(monitor.name)

                # Capture push token
                if monitor.type == MonitorType.PUSH:
                    # Get the created monitor to retrieve push token
                    created_monitor = client.get_monitor_by_name(monitor.name)
                    if created_monitor:
                        results["push_token"] = created_monitor.get("pushToken")

            except Exception as e:
                results["errors"].append(f"{monitor.name}: {e}")
                logger.error(f"Failed to create monitor {monitor.name}: {e}")

        # Update config with push token if callback provided
        if results["push_token"] and update_config_callback:
            update_config_callback(results["push_token"])

        return results

    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        client.disconnect()


def setup_holocene_monitoring(config) -> dict:
    """
    Get recommended monitors and setup instructions.

    Args:
        config: Holocene Config object

    Returns:
        Dict with setup status and instructions
    """
    if not config.integrations.uptime_kuma_enabled:
        return {"success": False, "error": "Uptime Kuma integration not enabled"}

    # Get recommended monitors
    monitors = HoloceneMonitorConfig.get_monitors(config)

    # Check if auto-creation is available
    can_auto_create = UPTIME_KUMA_API_AVAILABLE and bool(
        getattr(config.integrations, 'uptime_kuma_username', None) and
        getattr(config.integrations, 'uptime_kuma_password', None)
    )

    result = {
        "success": True,
        "uptime_kuma_url": config.integrations.uptime_kuma_url,
        "can_auto_create": can_auto_create,
        "uptime_kuma_api_available": UPTIME_KUMA_API_AVAILABLE,
        "recommended_monitors": [
            {
                "name": m.name,
                "type": m.type.value,
                "target": m.url or f"{m.hostname}:{m.port}" if m.hostname else "(push)",
                "interval": m.interval,
            }
            for m in monitors
        ],
    }

    if not can_auto_create:
        if not UPTIME_KUMA_API_AVAILABLE:
            result["instructions"] = [
                "Install monitoring extras: pip install holocene[monitoring]",
                "Add credentials to config:",
                "  uptime_kuma_username: your_username",
                "  uptime_kuma_password: your_password",
                "Then run: holo monitor setup --create",
            ]
        else:
            result["instructions"] = [
                "Add credentials to config:",
                "  uptime_kuma_username: your_username",
                "  uptime_kuma_password: your_password",
                "Then run: holo monitor setup --create",
            ]
    else:
        result["instructions"] = [
            "Run: holo monitor setup --create",
            "This will create all monitors and configure the push token automatically.",
        ]

    return result
