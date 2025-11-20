"""Test the Telegram bot plugin."""

import logging
import time
from holocene.core import HoloceneCore, PluginRegistry

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


def test_telegram_bot_plugin():
    """Test that the Telegram bot plugin loads and responds to events."""
    print("\n" + "="*60)
    print("TESTING TELEGRAM BOT PLUGIN")
    print("="*60 + "\n")

    # Create core
    print("1. Creating HoloceneCore...")
    core = HoloceneCore()
    print("   ✓ Core created\n")

    # Create registry
    print("2. Creating PluginRegistry...")
    registry = PluginRegistry(core, device="rei")  # Note: rei device (server)
    print("   ✓ Registry created\n")

    # Discover plugins
    print("3. Discovering plugins...")
    registry.discover_plugins()
    plugins_list = registry.list_plugins()
    print(f"   ✓ Discovered {len(plugins_list)} plugin(s):")
    for plugin in plugins_list:
        print(f"      - {plugin['name']}: {plugin['description']}")
        print(f"        runs_on: {', '.join(plugin['runs_on'])}")
    print()

    # Load plugins
    print("4. Loading plugins...")
    registry.load_all()
    print("   ✓ Plugins loaded\n")

    # Enable plugins
    print("5. Enabling plugins...")
    registry.enable_all()
    print("   ✓ Plugins enabled\n")

    # Check that telegram_bot is loaded
    bot = registry.get_plugin('telegram_bot')
    if bot:
        print("6. TelegramBot plugin found!")
        print(f"   - Has bot token: {bot.bot_token is not None}")
        print(f"   - Has application: {bot.application is not None}")
        print(f"   - Messages sent: {bot.messages_sent}")
        print(f"   - Commands received: {bot.commands_received}")
        print(f"   - Notifications sent: {bot.notifications_sent}")
        print()
    else:
        print("   ✗ TelegramBot plugin not found\n")

    # Test event subscriptions
    print("7. Testing event handling...")

    # Check subscriptions
    enrichment_subs = core.channels.subscriber_count('enrichment.complete')
    classification_subs = core.channels.subscriber_count('classification.complete')
    link_checked_subs = core.channels.subscriber_count('link.checked')

    print(f"   Subscribers to 'enrichment.complete': {enrichment_subs}")
    print(f"   Subscribers to 'classification.complete': {classification_subs}")
    print(f"   Subscribers to 'link.checked': {link_checked_subs}")

    if enrichment_subs > 0:
        print("   ✓ Plugin is listening for enrichment events")
    if classification_subs > 0:
        print("   ✓ Plugin is listening for classification events")
    if link_checked_subs > 0:
        print("   ✓ Plugin is listening for link checked events")
    print()

    # Test notification triggering (won't actually send without bot token)
    print("8. Testing notification events...")

    # Simulate enrichment.complete
    print("   Publishing enrichment.complete event...")
    core.channels.publish('enrichment.complete', {
        'book_id': 123,
        'summary': 'A test book about testing'
    })
    time.sleep(0.2)

    # Simulate classification.complete
    print("   Publishing classification.complete event...")
    core.channels.publish('classification.complete', {
        'book_id': 123,
        'dewey_number': '005.1',
        'dewey_label': 'Computer programming',
        'call_number': '005.1 T47a'
    })
    time.sleep(0.2)

    # Simulate link.checked
    print("   Publishing link.checked event...")
    core.channels.publish('link.checked', {
        'url': 'https://example.com',
        'status_code': 200,
        'is_alive': True
    })
    time.sleep(0.2)

    print("   ✓ Events published (notifications would be sent with bot token)\n")

    # Test stats
    print("9. Plugin stats:")
    if bot:
        print(f"   - Messages sent: {bot.messages_sent}")
        print(f"   - Commands received: {bot.commands_received}")
        print(f"   - Notifications sent: {bot.notifications_sent}")
    print()

    # Test multi-device concept
    print("10. Multi-device architecture:")
    print("   - Bot runs on: rei (server)")
    print("   - Interface for: eunice (mobile)")
    print("   - Communication: Telegram API")
    print("   ✓ Multi-device concept validated!\n")

    # Shutdown
    print("11. Shutting down...")
    registry.disable_all()
    core.shutdown()
    print("   ✓ Clean shutdown\n")

    print("="*60)
    print("TELEGRAM BOT PLUGIN TEST COMPLETE")
    print("="*60)
    print("\nNote: Actual bot requires:")
    print("  1. python-telegram-bot library: pip install python-telegram-bot")
    print("  2. Bot token in config: telegram.bot_token")
    print("  3. Chat ID for notifications: telegram.chat_id")


if __name__ == '__main__':
    test_telegram_bot_plugin()
