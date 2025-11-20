"""Test the book classifier plugin."""

import logging
import time
from holocene.core import HoloceneCore, PluginRegistry

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


def test_book_classifier_plugin():
    """Test that the book classifier plugin loads and responds to events."""
    print("\n" + "="*60)
    print("TESTING BOOK CLASSIFIER PLUGIN")
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

    # Check that book_classifier is loaded
    classifier = registry.get_plugin('book_classifier')
    if classifier:
        print("6. BookClassifier plugin found!")
        print(f"   - Has classifier: {classifier.classifier is not None}")
        print(f"   - Classified count: {classifier.classified_count}")
        print()
    else:
        print("   ✗ BookClassifier plugin not found\n")

    # Test event subscriptions
    print("7. Testing event handling...")

    # Check subscriptions
    books_added_subs = core.channels.subscriber_count('books.added')
    enrichment_complete_subs = core.channels.subscriber_count('enrichment.complete')

    print(f"   Subscribers to 'books.added': {books_added_subs}")
    print(f"   Subscribers to 'enrichment.complete': {enrichment_complete_subs}")

    if books_added_subs > 0:
        print("   ✓ Plugin is listening for book events")
    if enrichment_complete_subs > 0:
        print("   ✓ Plugin is listening for enrichment events")
    print()

    # Test event chaining
    print("8. Testing event chaining (enrichment → classification)...")

    classification_events = []

    def on_classification_complete(msg):
        classification_events.append(msg.data)
        print(f"   ✓ Classification complete event received: {msg.data.get('book_id')}")

    core.channels.subscribe('classification.complete', on_classification_complete)

    # Simulate enrichment.complete event
    print("   Publishing enrichment.complete event...")
    core.channels.publish('enrichment.complete', {
        'book_id': 999,
        'summary': 'A book about testing',
        'tags': ['testing', 'software']
    })
    time.sleep(0.3)
    print("   ✓ Event published (classification skipped without real book)\n")

    # Test stats
    print("9. Plugin stats:")
    if classifier:
        print(f"   - Books classified: {classifier.classified_count}")
        print(f"   - Failed classifications: {classifier.failed_count}")
    print()

    # Shutdown
    print("10. Shutting down...")
    registry.disable_all()
    core.shutdown()
    print("   ✓ Clean shutdown\n")

    print("="*60)
    print("BOOK CLASSIFIER PLUGIN TEST COMPLETE")
    print("="*60)
    print("\nNote: Actual classification requires NanoGPT API key in config")
    print("      and a real book in the database")


if __name__ == '__main__':
    test_book_classifier_plugin()
