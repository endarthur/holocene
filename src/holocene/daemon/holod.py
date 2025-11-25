"""Holocene Daemon (holod) - Background service for plugins.

holod runs 24/7 on rei (server), providing:
- Plugin runtime (enricher, classifier, link checker, etc.)
- REST API for wmut CLI communication
- Event bus for inter-plugin communication
- Telegram bot for eunice mobile interface
"""

import os
import sys
import signal
import logging
import time
import atexit
import threading
import requests
from pathlib import Path
from typing import Optional

from ..core import HoloceneCore, PluginRegistry
from ..config import load_config

logger = logging.getLogger(__name__)


class HoloceneDaemon:
    """Holocene background daemon (holod).

    Runs on rei (server), provides plugin runtime and API.

    Features:
    - Plugin management (load, enable, disable)
    - REST API on port 5555
    - Signal handling (SIGTERM, SIGINT)
    - PID file management
    - Graceful shutdown
    """

    def __init__(self, config_path: Optional[Path] = None, device: str = "rei"):
        """Initialize daemon.

        Args:
            config_path: Optional config file path
            device: Device identifier (default: "rei")
        """
        self.device = device
        self.config = load_config(config_path)

        # Core components
        self.core: Optional[HoloceneCore] = None
        self.registry: Optional[PluginRegistry] = None
        self.api: Optional['APIServer'] = None  # Forward reference

        # State
        self.running = False
        self.pid_file = self.config.data_dir / "holod.pid"

        # Healthcheck thread
        self._healthcheck_thread: Optional[threading.Thread] = None
        self._healthcheck_stop_event = threading.Event()

        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        # Ensure cleanup on exit
        atexit.register(self.cleanup)

        logger.info(f"HoloceneDaemon initialized (device: {device})")

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, initiating shutdown...")
        self.stop()

    def _write_pid_file(self):
        """Write PID file."""
        try:
            self.pid_file.parent.mkdir(parents=True, exist_ok=True)
            self.pid_file.write_text(str(os.getpid()))
            logger.info(f"PID file written: {self.pid_file}")
        except Exception as e:
            logger.error(f"Failed to write PID file: {e}")

    def _remove_pid_file(self):
        """Remove PID file."""
        try:
            if self.pid_file.exists():
                self.pid_file.unlink()
                logger.info("PID file removed")
        except Exception as e:
            logger.error(f"Failed to remove PID file: {e}")

    def _healthcheck_worker(self):
        """Background worker that pings healthchecks.io every 60 seconds."""
        if not self.config.healthcheck_url:
            return

        logger.info(f"Healthcheck worker started (URL: {self.config.healthcheck_url})")

        while not self._healthcheck_stop_event.is_set():
            try:
                # Ping healthchecks.io
                response = requests.get(self.config.healthcheck_url, timeout=10)
                if response.status_code == 200:
                    logger.debug("Healthcheck ping successful")
                else:
                    logger.warning(f"Healthcheck ping returned {response.status_code}")
            except Exception as e:
                # Don't crash daemon if healthchecks.io is down
                logger.error(f"Healthcheck ping failed: {e}")

            # Wait 60 seconds (or until stop event is set)
            self._healthcheck_stop_event.wait(60)

        logger.info("Healthcheck worker stopped")

    def _start_healthcheck(self):
        """Start healthcheck background thread."""
        if not self.config.healthcheck_url:
            logger.info("No healthcheck URL configured, skipping")
            return

        self._healthcheck_stop_event.clear()
        self._healthcheck_thread = threading.Thread(
            target=self._healthcheck_worker,
            daemon=True,
            name="healthcheck"
        )
        self._healthcheck_thread.start()
        logger.info("Healthcheck thread started")

    def _stop_healthcheck(self):
        """Stop healthcheck background thread."""
        if self._healthcheck_thread and self._healthcheck_thread.is_alive():
            logger.info("Stopping healthcheck thread...")
            self._healthcheck_stop_event.set()
            self._healthcheck_thread.join(timeout=5)
            logger.info("Healthcheck thread stopped")

    def is_running(self) -> bool:
        """Check if daemon is running.

        Returns:
            True if daemon is running
        """
        if not self.pid_file.exists():
            return False

        try:
            pid = int(self.pid_file.read_text().strip())

            # Check if process exists (cross-platform)
            if sys.platform == 'win32':
                import ctypes
                kernel32 = ctypes.windll.kernel32
                PROCESS_QUERY_INFORMATION = 0x0400
                handle = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION, False, pid)
                if handle:
                    kernel32.CloseHandle(handle)
                    return True
                return False
            else:
                # Unix: send signal 0 (doesn't actually send signal, just checks)
                os.kill(pid, 0)
                return True
        except (ValueError, ProcessLookupError, OSError):
            # PID file exists but process doesn't - clean up
            self._remove_pid_file()
            return False

    def start(self, foreground: bool = False):
        """Start the daemon.

        Args:
            foreground: Run in foreground (don't daemonize)
        """
        # Check if already running
        if self.is_running():
            logger.error("Daemon is already running")
            print("holod is already running")
            return False

        logger.info("Starting holod daemon...")
        print("Starting holod daemon...")

        # Write PID file
        self._write_pid_file()

        try:
            # Initialize core
            logger.info("Initializing HoloceneCore...")
            self.core = HoloceneCore()

            # Initialize plugin registry
            logger.info(f"Initializing PluginRegistry (device: {self.device})...")
            self.registry = PluginRegistry(self.core, device=self.device)

            # Make registry accessible to plugins via core
            self.core.registry = self.registry

            # Discover and load plugins
            logger.info("Discovering plugins...")
            self.registry.discover_plugins()

            logger.info("Loading plugins...")
            self.registry.load_all()

            # Enable configured plugins (for now, enable all)
            logger.info("Enabling plugins...")
            self.registry.enable_all()

            plugins = self.registry.list_plugins()
            logger.info(f"Loaded {len(plugins)} plugin(s):")
            for plugin in plugins:
                logger.info(f"  - {plugin['name']} v{plugin['version']}")
                print(f"  ✓ {plugin['name']}")

            # Start REST API (if available)
            try:
                from .api import APIServer
                logger.info("Starting REST API...")
                self.api = APIServer(self.core, self.registry)
                # API server runs in background thread
                self.api.start()
                logger.info(f"REST API listening on http://localhost:5555")
                print(f"✓ REST API: http://localhost:5555")
            except ImportError:
                logger.warning("Flask not installed - REST API disabled")
                print("⚠ REST API disabled (install Flask)")

            # Mark as running
            self.running = True

            # Start healthcheck pinger (if configured)
            self._start_healthcheck()
            if self.config.healthcheck_url:
                print(f"✓ Healthcheck: {self.config.healthcheck_url}")

            print(f"\n✓ holod started successfully!")
            print(f"  Device: {self.device}")
            print(f"  PID: {os.getpid()}")
            print(f"  PID file: {self.pid_file}")

            if foreground:
                print("\nRunning in foreground (Ctrl+C to stop)...")
                self._run_forever()
            else:
                print("\nRunning in background")
                print("Use 'holo daemon stop' to stop")

            return True

        except Exception as e:
            logger.error(f"Failed to start daemon: {e}", exc_info=True)
            print(f"✗ Failed to start: {e}")
            self.cleanup()
            return False

    def _run_forever(self):
        """Main daemon loop (for foreground mode)."""
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
            self.stop()

    def stop(self):
        """Stop the daemon."""
        if not self.running:
            logger.warning("Daemon is not running")
            return

        logger.info("Stopping holod daemon...")
        print("Stopping holod daemon...")

        self.running = False

        # Stop healthcheck
        self._stop_healthcheck()

        # Stop API
        if self.api:
            logger.info("Stopping REST API...")
            self.api.stop()

        # Disable plugins
        if self.registry:
            logger.info("Disabling plugins...")
            self.registry.disable_all()

        # Shutdown core (handle threading issues with SQLite)
        if self.core:
            logger.info("Shutting down HoloceneCore...")
            try:
                # Shutdown executor first
                if hasattr(self.core, '_executor'):
                    self.core._executor.shutdown(wait=True)

                # Close database (may fail if different thread)
                try:
                    if hasattr(self.core, 'db') and self.core.db:
                        self.core.db.close()
                except Exception as db_error:
                    # SQLite threading constraint - safe to ignore on shutdown
                    logger.debug(f"Database close skipped (threading): {db_error}")
            except Exception as e:
                logger.warning(f"Error during core shutdown: {e}")

        # Cleanup
        self.cleanup()

        logger.info("holod stopped")
        print("✓ holod stopped")

    def cleanup(self):
        """Cleanup resources."""
        self._remove_pid_file()

    def status(self) -> dict:
        """Get daemon status.

        Returns:
            Status dict with running state, PID, etc.
        """
        if not self.is_running():
            return {
                'running': False,
                'pid': None,
                'message': 'Daemon is not running'
            }

        pid = int(self.pid_file.read_text().strip())

        # Get plugin stats if core is available
        plugin_count = 0
        if self.registry:
            plugin_count = len(self.registry.list_plugins())

        return {
            'running': True,
            'pid': pid,
            'device': self.device,
            'plugins': plugin_count,
            'api': 'http://localhost:5555' if self.api else None,
            'message': 'Daemon is running'
        }
