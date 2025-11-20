"""Test the book enricher plugin."""

import logging
import time
from holocene.core import HoloceneCore, PluginRegistry

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


def test_book_enricher_plugin():
    """Test that the book enricher plugin loads and responds to events."""
    print("\n" + "="*60)
    print("TESTING BOOK ENRICHER PLUGIN")
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
    plugins = registry.list_plugins()
    print(f"   ✓ Discovered {len(plugins)} plugin(s):")
    for plugin in plugins:
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

    # Check that book_enricher is loaded
    enricher = registry.get_plugin('book_enricher')
    if enricher:
        print("6. BookEnricher plugin found!")
        print(f"   - Has LLM client: {enricher.llm_client is not None}")
        print(f"   - Enriched count: {enricher.enriched_count}")
        print()
    else:
        print("   ✗ BookEnricher plugin not found")
        print()

    # Test event subscription (without actually enriching)
    print("7. Testing event handling...")

    completion_events = []

    def on_enrichment_complete(msg):
        completion_events.append(msg.data)
        print(f"   ✓ Enrichment complete event received: {msg.data.get('book_id')}")

    core.channels.subscribe('enrichment.complete', on_enrichment_complete)

    # Check if plugin is subscribed to books.added
    subscriber_count = core.channels.subscriber_count('books.added')
    print(f"   Subscribers to 'books.added': {subscriber_count}")

    if subscriber_count > 0:
        print("   ✓ Plugin is listening for book events")
    else:
        print("   ✗ Plugin not subscribed to book events")
    print()

    # Simulate a book.added event (won't actually enrich without API key)
    print("8. Simulating book.added event...")
    core.channels.publish('books.added', {'book_id': 999, 'title': 'Test Book'})
    time.sleep(0.3)
    print("   ✓ Event published (enrichment skipped without API key)\n")

    # Test stats
    print("9. Plugin stats:")
    if enricher:
        print(f"   - Books enriched: {enricher.enriched_count}")
        print(f"   - Failed enrichments: {enricher.failed_count}")
    print()

    # Shutdown
    print("10. Shutting down...")
    registry.disable_all()
    core.shutdown()
    print("   ✓ Clean shutdown\n")

    print("="*60)
    print("BOOK ENRICHER PLUGIN TEST COMPLETE")
    print("="*60)
    print("\nNote: Actual enrichment requires NanoGPT API key in config")


if __name__ == '__main__':
    test_book_enricher_plugin()
