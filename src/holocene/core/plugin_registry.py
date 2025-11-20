"""Plugin registry for discovering and managing plugins."""

import logging
import importlib
import inspect
from pathlib import Path
from typing import Dict, List, Optional, Type
import sys

from .plugin import Plugin
from .holocene_core import HoloceneCore

logger = logging.getLogger(__name__)


class PluginRegistry:
    """Manages plugin discovery, loading, and lifecycle.

    Features:
    - Auto-discover plugins from holocene/plugins/ directory
    - Load/unload plugins
    - Enable/disable plugins
    - Dependency resolution
    - Device filtering (runs_on)

    Example:
        core = HoloceneCore()
        registry = PluginRegistry(core)

        # Auto-discover and load all plugins
        registry.discover_plugins()
        registry.load_all()

        # Enable specific plugin
        registry.enable_plugin('book_enricher')

        # Disable all
        registry.disable_all()
    """

    def __init__(self, core: HoloceneCore, device: str = "wmut"):
        """Initialize plugin registry.

        Args:
            core: HoloceneCore instance
            device: Current device identifier ("rei", "wmut", "eunice", etc.)
        """
        self.core = core
        self.device = device
        self._plugins: Dict[str, Plugin] = {}  # name -> instance
        self._plugin_classes: Dict[str, Type[Plugin]] = {}  # name -> class
        self._load_order: List[str] = []  # For dependency resolution

    def discover_plugins(self, plugin_dir: Optional[Path] = None):
        """Discover plugins from directory.

        Args:
            plugin_dir: Directory to scan (defaults to holocene/plugins/)
        """
        if plugin_dir is None:
            # Default to holocene/plugins/
            import holocene
            holocene_dir = Path(holocene.__file__).parent
            plugin_dir = holocene_dir / "plugins"

        if not plugin_dir.exists():
            logger.warning(f"Plugin directory doesn't exist: {plugin_dir}")
            return

        logger.info(f"Discovering plugins in: {plugin_dir}")

        # Find all Python files in plugins directory
        plugin_files = list(plugin_dir.glob("*.py"))
        plugin_files = [f for f in plugin_files if f.name != "__init__.py"]

        for plugin_file in plugin_files:
            try:
                self._load_plugin_file(plugin_file)
            except Exception as e:
                logger.error(f"Failed to load plugin from {plugin_file}: {e}", exc_info=True)

        logger.info(f"Discovered {len(self._plugin_classes)} plugin(s)")

    def _load_plugin_file(self, plugin_file: Path):
        """Load plugin classes from a Python file.

        Args:
            plugin_file: Path to plugin .py file
        """
        module_name = f"holocene.plugins.{plugin_file.stem}"

        # Import module
        spec = importlib.util.spec_from_file_location(module_name, plugin_file)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # Find Plugin subclasses
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, Plugin) and obj != Plugin:
                    # Create instance to get metadata
                    instance = obj(self.core)
                    metadata = instance.get_metadata()
                    plugin_name = metadata.get('name', name)

                    # Check if plugin can run on this device
                    runs_on = metadata.get('runs_on', ['both'])
                    if 'both' in runs_on or self.device in runs_on:
                        self._plugin_classes[plugin_name] = obj
                        logger.info(f"Found plugin: {plugin_name} (from {plugin_file.name})")
                    else:
                        logger.debug(f"Skipping plugin {plugin_name} (runs_on: {runs_on}, device: {self.device})")

    def load_plugin(self, plugin_name: str) -> bool:
        """Load a plugin by name.

        Args:
            plugin_name: Plugin name

        Returns:
            True if loaded successfully
        """
        if plugin_name in self._plugins:
            logger.warning(f"Plugin already loaded: {plugin_name}")
            return True

        if plugin_name not in self._plugin_classes:
            logger.error(f"Plugin not found: {plugin_name}")
            return False

        try:
            plugin_class = self._plugin_classes[plugin_name]
            instance = plugin_class(self.core)

            # Check dependencies
            metadata = instance.get_metadata()
            requires = metadata.get('requires', [])

            for dep in requires:
                if dep not in self._plugins:
                    logger.error(f"Plugin {plugin_name} requires {dep}, but it's not loaded")
                    return False

            # Call on_load()
            instance.on_load()

            self._plugins[plugin_name] = instance
            self._load_order.append(plugin_name)

            logger.info(f"Loaded plugin: {plugin_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to load plugin {plugin_name}: {e}", exc_info=True)
            return False

    def load_all(self):
        """Load all discovered plugins."""
        for plugin_name in self._plugin_classes.keys():
            self.load_plugin(plugin_name)

    def enable_plugin(self, plugin_name: str) -> bool:
        """Enable a plugin.

        Args:
            plugin_name: Plugin name

        Returns:
            True if enabled successfully
        """
        if plugin_name not in self._plugins:
            logger.error(f"Plugin not loaded: {plugin_name}")
            return False

        plugin = self._plugins[plugin_name]
        if plugin.enabled:
            logger.warning(f"Plugin already enabled: {plugin_name}")
            return True

        try:
            plugin.enable()
            return True
        except Exception as e:
            logger.error(f"Failed to enable plugin {plugin_name}: {e}", exc_info=True)
            return False

    def disable_plugin(self, plugin_name: str) -> bool:
        """Disable a plugin.

        Args:
            plugin_name: Plugin name

        Returns:
            True if disabled successfully
        """
        if plugin_name not in self._plugins:
            logger.error(f"Plugin not loaded: {plugin_name}")
            return False

        plugin = self._plugins[plugin_name]
        if not plugin.enabled:
            return True

        try:
            plugin.disable()
            return True
        except Exception as e:
            logger.error(f"Failed to disable plugin {plugin_name}: {e}", exc_info=True)
            return False

    def enable_all(self):
        """Enable all loaded plugins."""
        for plugin_name in self._load_order:
            self.enable_plugin(plugin_name)

    def disable_all(self):
        """Disable all plugins."""
        # Disable in reverse order
        for plugin_name in reversed(self._load_order):
            self.disable_plugin(plugin_name)

    def get_plugin(self, plugin_name: str) -> Optional[Plugin]:
        """Get a loaded plugin by name.

        Args:
            plugin_name: Plugin name

        Returns:
            Plugin instance or None
        """
        return self._plugins.get(plugin_name)

    def list_plugins(self) -> List[Dict]:
        """List all loaded plugins with status.

        Returns:
            List of plugin info dictionaries
        """
        result = []
        for plugin_name in self._load_order:
            plugin = self._plugins[plugin_name]
            metadata = plugin.get_metadata()
            result.append({
                'name': plugin_name,
                'enabled': plugin.enabled,
                'version': metadata.get('version', 'unknown'),
                'description': metadata.get('description', ''),
                'runs_on': metadata.get('runs_on', []),
            })
        return result

    def shutdown(self):
        """Shutdown all plugins."""
        logger.info("Shutting down plugin registry...")
        self.disable_all()
        self._plugins.clear()
        self._plugin_classes.clear()
        self._load_order.clear()
