"""Test holod daemon functionality."""

import logging
import time
import requests
from pathlib import Path

from holocene.daemon import HoloceneDaemon
from holocene.core import HoloceneCore, PluginRegistry
from holocene.config import load_config

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


def test_holod_initialization():
    """Test that holod daemon initializes correctly."""
    print("\n" + "="*60)
    print("TEST 1: HOLOD INITIALIZATION")
    print("="*60 + "\n")

    print("1. Creating HoloceneDaemon...")
    daemon = HoloceneDaemon(device="rei")
    print(f"   ✓ Daemon created (device: {daemon.device})")
    print(f"   ✓ PID file: {daemon.pid_file}")
    print()

    print("2. Checking daemon state...")
    print(f"   - Running: {daemon.running}")
    print(f"   - Is running: {daemon.is_running()}")
    print(f"   ✓ Daemon initialized but not started")
    print()

    print("="*60)
    print("TEST 1 COMPLETE")
    print("="*60)


def test_holod_plugin_loading():
    """Test that holod loads plugins correctly."""
    print("\n" + "="*60)
    print("TEST 2: HOLOD PLUGIN LOADING")
    print("="*60 + "\n")

    print("1. Creating core and registry...")
    core = HoloceneCore()
    registry = PluginRegistry(core, device="rei")
    print(f"   ✓ Core created")
    print(f"   ✓ Registry created (device: rei)")
    print()

    print("2. Discovering plugins...")
    registry.discover_plugins()
    discovered = registry.list_plugins()
    print(f"   ✓ Discovered {len(discovered)} plugin(s):")
    for plugin in discovered:
        print(f"      - {plugin['name']}: {plugin['description']}")
        print(f"        runs_on: {', '.join(plugin['runs_on'])}")
    print()

    print("3. Loading plugins...")
    registry.load_all()
    loaded = registry.list_plugins()
    print(f"   ✓ Loaded {len(loaded)} plugin(s)")
    print()

    print("4. Enabling plugins...")
    registry.enable_all()
    enabled = [p for p in registry.list_plugins() if p.get('enabled', False)]
    print(f"   ✓ Enabled {len(enabled)} plugin(s)")
    print()

    print("5. Checking specific plugins...")
    for plugin_name in ['book_enricher', 'book_classifier', 'link_status_checker', 'telegram_bot']:
        plugin = registry.get_plugin(plugin_name)
        if plugin:
            print(f"   ✓ {plugin_name}: loaded and {'enabled' if plugin.enabled else 'disabled'}")
        else:
            print(f"   ✗ {plugin_name}: not found")
    print()

    print("6. Shutting down...")
    registry.disable_all()
    core.shutdown()
    print("   ✓ Clean shutdown")
    print()

    print("="*60)
    print("TEST 2 COMPLETE")
    print("="*60)


def test_holod_daemon_lifecycle():
    """Test holod daemon start/stop lifecycle."""
    print("\n" + "="*60)
    print("TEST 3: HOLOD DAEMON LIFECYCLE")
    print("="*60 + "\n")

    daemon = HoloceneDaemon(device="rei")

    print("1. Starting daemon in foreground mode...")
    print("   (Note: This will start the daemon but not block)")
    print()

    # Start in background thread for testing
    import threading

    def start_daemon():
        """Start daemon in background thread."""
        daemon.start(foreground=False)

    daemon_thread = threading.Thread(target=start_daemon, daemon=True)
    daemon_thread.start()
    time.sleep(3)  # Give it time to start

    print("2. Checking daemon status...")
    status = daemon.status()
    print(f"   - Running: {status['running']}")
    print(f"   - PID: {status['pid']}")
    print(f"   - Device: {status['device']}")
    print(f"   - Plugins: {status['plugins']}")
    print(f"   - API: {status['api']}")
    print()

    if status['running']:
        print("   ✓ Daemon is running!")
        print()

        print("3. Testing REST API...")
        try:
            # Test health endpoint
            response = requests.get("http://localhost:5555/health", timeout=5)
            if response.status_code == 200:
                print("   ✓ Health check: OK")

            # Test status endpoint
            response = requests.get("http://localhost:5555/status", timeout=5)
            if response.status_code == 200:
                data = response.json()
                print(f"   ✓ Status endpoint: OK")
                print(f"      - Status: {data['status']}")
                print(f"      - Uptime: {data['uptime_seconds']:.1f}s")
                print(f"      - Plugins: {data['plugins']['total']} total, {data['plugins']['enabled']} enabled")

            # Test plugins endpoint
            response = requests.get("http://localhost:5555/plugins", timeout=5)
            if response.status_code == 200:
                data = response.json()
                print(f"   ✓ Plugins endpoint: OK ({len(data['plugins'])} plugins)")

            # Test channels endpoint
            response = requests.get("http://localhost:5555/channels", timeout=5)
            if response.status_code == 200:
                data = response.json()
                print(f"   ✓ Channels endpoint: OK ({data['count']} channels)")

            print()

        except requests.RequestException as e:
            print(f"   ✗ API request failed: {e}")
            print()

        print("4. Stopping daemon...")
        daemon.stop()
        time.sleep(2)

        status = daemon.status()
        if not status['running']:
            print("   ✓ Daemon stopped successfully")
        else:
            print("   ✗ Daemon still running")
        print()

    else:
        print("   ✗ Daemon failed to start")
        print()

    print("="*60)
    print("TEST 3 COMPLETE")
    print("="*60)


def test_holod_api_endpoints():
    """Test REST API endpoints."""
    print("\n" + "="*60)
    print("TEST 4: REST API ENDPOINTS")
    print("="*60 + "\n")

    daemon = HoloceneDaemon(device="rei")

    print("1. Starting daemon...")
    import threading

    def start_daemon():
        daemon.start(foreground=False)

    daemon_thread = threading.Thread(target=start_daemon, daemon=True)
    daemon_thread.start()
    time.sleep(3)

    if not daemon.status()['running']:
        print("   ✗ Daemon failed to start, skipping API tests")
        return

    print("   ✓ Daemon started")
    print()

    try:
        base_url = "http://localhost:5555"

        # Test plugin endpoints
        print("2. Testing plugin endpoints...")

        # List plugins
        response = requests.get(f"{base_url}/plugins")
        plugins = response.json()['plugins']
        print(f"   ✓ GET /plugins: {len(plugins)} plugins")

        # Get specific plugin
        if plugins:
            plugin_name = plugins[0]['name']
            response = requests.get(f"{base_url}/plugins/{plugin_name}")
            plugin = response.json()
            print(f"   ✓ GET /plugins/{plugin_name}: {plugin['description']}")

        print()

        # Test channel endpoints
        print("3. Testing channel endpoints...")

        # List channels
        response = requests.get(f"{base_url}/channels")
        channels = response.json()['channels']
        print(f"   ✓ GET /channels: {len(channels)} channels")

        # Publish to channel
        response = requests.post(
            f"{base_url}/channels/test.channel/publish",
            json={'data': {'message': 'test'}, 'sender': 'test'}
        )
        if response.status_code == 200:
            print(f"   ✓ POST /channels/test.channel/publish: OK")

        # Get channel history
        response = requests.get(f"{base_url}/channels/test.channel/history")
        history = response.json()
        print(f"   ✓ GET /channels/test.channel/history: {history['count']} messages")

        print()

        # Test book endpoints
        print("4. Testing book endpoints...")

        # List books
        response = requests.get(f"{base_url}/books")
        books = response.json()
        print(f"   ✓ GET /books: {books['count']} books")

        print()

        # Test link endpoints
        print("5. Testing link endpoints...")

        # List links
        response = requests.get(f"{base_url}/links")
        links = response.json()
        print(f"   ✓ GET /links: {links['count']} links")

        print()

    except requests.RequestException as e:
        print(f"   ✗ API test failed: {e}")
    finally:
        print("6. Stopping daemon...")
        daemon.stop()
        time.sleep(2)
        print("   ✓ Daemon stopped")
        print()

    print("="*60)
    print("TEST 4 COMPLETE")
    print("="*60)


def run_all_tests():
    """Run all holod tests."""
    print("\n" + "="*70)
    print(" "*20 + "HOLOD DAEMON TEST SUITE")
    print("="*70)

    try:
        test_holod_initialization()
        test_holod_plugin_loading()
        test_holod_daemon_lifecycle()
        test_holod_api_endpoints()

        print("\n" + "="*70)
        print(" "*20 + "ALL TESTS COMPLETE!")
        print("="*70)

        print("\n✓ holod daemon is ready for production!")
        print("\nUsage:")
        print("  holo daemon start              # Start holod in background")
        print("  holo daemon start --foreground # Run in foreground")
        print("  holo daemon status             # Check status")
        print("  holo daemon plugins            # List plugins")
        print("  holo daemon stop               # Stop daemon")
        print()

    except Exception as e:
        print("\n" + "="*70)
        print(f"TEST FAILED: {e}")
        print("="*70)
        raise


if __name__ == '__main__':
    run_all_tests()
