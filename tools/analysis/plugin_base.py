# tools/analysis/plugin_base.py

from abc import ABC, abstractmethod
from core.state import PageContext
from typing import Any

class AnalysisPlugin(ABC):
    """
    Base class for all analysis plugins.
    Plugins can be injected into the pipeline to perform additional audits or data extraction.
    """

    @property
    @abstractmethod
    def plugin_id(self) -> str:
        """Unique identifier for the plugin."""
        pass

    @abstractmethod
    def run(self, ctx: PageContext) -> PageContext:
        """
        Execute the plugin logic and return the updated context.
        """
        pass

class ToolRegistry:
    """
    Registry for managing analysis plugins.
    """
    def __init__(self):
        self._plugins: dict[str, AnalysisPlugin] = {}

    def register(self, plugin: AnalysisPlugin):
        self._plugins[plugin.plugin_id] = plugin
        from monitoring.logger import get_logger
        get_logger(__name__).info("plugin.registered", id=plugin.plugin_id)

    def get_plugins(self) -> list[AnalysisPlugin]:
        return list(self._plugins.values())

# Global registry
plugin_registry = ToolRegistry()
