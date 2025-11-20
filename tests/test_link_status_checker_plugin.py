"""Test the link status checker plugin."""

import logging
import time
from holocene.core import HoloceneCore, PluginRegistry

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


def test_link_status_checker_plugin():
    """Test that the link status checker plugin loads and responds to events."""
    print("\n" + "="*60)
    print("TESTING LINK STATUS CHECKER PLUGIN")
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
    plugins_list = registry.list_plugins()
    print(f"   ✓ Discovered {len(plugins_list)} plugin(s):")
    for plugin in plugins_list:
        print(f"      - {plugin['name']}: {plugin['description']}")
    print()

    # Load plugins
    print("4. Loading plugins...")
    registry.load_all()
    print("   ✓ Plugins loaded\n")

    # Enable plugins
    print("5. Enabling plugins...")
    registry.enable_all()
    print("   ✓ Plugins enabled\n")

    # Check that link_status_checker is loaded
    checker = registry.get_plugin('link_status_checker')
    if checker:
        print("6. LinkStatusChecker plugin found!")
        print(f"   - Has session: {hasattr(checker, 'session')}")
        print(f"   - Checked count: {checker.checked_count}")
        print(f"   - Alive count: {checker.alive_count}")
        print(f"   - Dead count: {checker.dead_count}")
        print()
    else:
        print("   ✗ LinkStatusChecker plugin not found\n")

    # Test event subscriptions
    print("7. Testing event handling...")

    # Check subscriptions
    links_added_subs = core.channels.subscriber_count('links.added')
    check_stale_subs = core.channels.subscriber_count('links.check_stale')

    print(f"   Subscribers to 'links.added': {links_added_subs}")
    print(f"   Subscribers to 'links.check_stale': {check_stale_subs}")

    if links_added_subs > 0:
        print("   ✓ Plugin is listening for link events")
    if check_stale_subs > 0:
        print("   ✓ Plugin is listening for stale check events")
    print()

    # Test check event
    print("8. Testing link.checked event...")

    checked_events = []

    def on_link_checked(msg):
        checked_events.append(msg.data)
        print(f"   ✓ Link checked event received: {msg.data.get('url')}")

    core.channels.subscribe('link.checked', on_link_checked)

    # Simulate links.added event
    print("   Publishing links.added event (will fail - no real link)...")
    core.channels.publish('links.added', {'link_id': 999})
    time.sleep(0.3)
    print("   ✓ Event published\n")

    # Test stats
    print("9. Plugin stats:")
    if checker:
        print(f"   - Links checked: {checker.checked_count}")
        print(f"   - Alive: {checker.alive_count}")
        print(f"   - Dead: {checker.dead_count}")
        print(f"   - Failed: {checker.failed_count}")
    print()

    # Shutdown
    print("10. Shutting down...")
    registry.disable_all()
    core.shutdown()
    print("   ✓ Clean shutdown\n")

    print("="*60)
    print("LINK STATUS CHECKER PLUGIN TEST COMPLETE")
    print("="*60)
    print("\nNote: Actual link checking requires real links in database")


if __name__ == '__main__':
    test_link_status_checker_plugin()
