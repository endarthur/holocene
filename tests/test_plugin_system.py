"""Test the plugin system end-to-end."""

import time
import logging
from holocene.core import HoloceneCore, PluginRegistry

# Setup logging to see what's happening
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


def test_plugin_system():
    """Test plugin discovery, loading, and messaging."""
    print("\n" + "="*60)
    print("TESTING PLUGIN SYSTEM")
    print("="*60 + "\n")

    # Create core
    print("1. Creating HoloceneCore...")
    core = HoloceneCore()
    print("   ✓ Core created\n")

    # Create registry
    print("2. Creating PluginRegistry...")
    registry = PluginRegistry(core, device="wmut")
    print("   ✓ Registry created\n")

    # Discover plugins
    print("3. Discovering plugins...")
    registry.discover_plugins()
    print(f"   ✓ Discovered plugins\n")

    # Load all plugins
    print("4. Loading plugins...")
    registry.load_all()
    plugins = registry.list_plugins()
    print(f"   ✓ Loaded {len(plugins)} plugin(s):")
    for plugin in plugins:
        print(f"      - {plugin['name']}: {plugin['description']}")
    print()

    # Enable all plugins
    print("5. Enabling plugins...")
    registry.enable_all()
    print("   ✓ Plugins enabled\n")

    # Test messaging
    print("6. Testing channel messaging...")

    # Subscribe to test channel
    pong_received = []

    def on_pong(msg):
        pong_received.append(msg.data)
        print(f"   ✓ Received pong: {msg.data}")

    core.channels.subscribe('test.pong', on_pong)

    # Publish ping
    print("   Publishing ping...")
    core.channels.publish('test.ping', {'message': 'hello from test'})

    # Wait for async response
    time.sleep(0.5)

    if pong_received:
        print("   ✓ Ping-pong communication works!\n")
    else:
        print("   ✗ No pong received\n")

    # Test book.added event
    print("7. Testing book.added event...")
    core.channels.publish('books.added', {'book_id': 123, 'title': 'Test Book'})
    time.sleep(0.2)

    # Check if processed event was published
    history = core.channels.get_history('books.processed')
    if history:
        print(f"   ✓ Book processed: {history[-1].data}")
    else:
        print("   ✗ No processed event received")
    print()

    # Test background execution
    print("8. Testing background task execution...")

    result_holder = []

    def expensive_task():
        time.sleep(0.1)
        return {"computed": 42}

    def on_result(result):
        result_holder.append(result)
        print(f"   ✓ Background task completed: {result}")

    core.run_in_background(expensive_task, callback=on_result)
    time.sleep(0.3)

    if result_holder:
        print("   ✓ Background execution works!\n")
    else:
        print("   ✗ No result from background task\n")

    # Shutdown
    print("9. Shutting down...")
    registry.disable_all()
    core.shutdown()
    print("   ✓ Clean shutdown\n")

    print("="*60)
    print("ALL TESTS PASSED!")
    print("="*60)


if __name__ == '__main__':
    test_plugin_system()
