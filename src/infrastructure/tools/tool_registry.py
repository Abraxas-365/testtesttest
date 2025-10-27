"""Tool registry for dynamically loading and managing agent tools."""

import importlib
import inspect
from typing import Any, Callable, Optional
from src.domain.models import ToolConfig


class ToolRegistry:
    """
    Registry for managing and loading tools dynamically.

    This class handles the mapping between tool configurations stored in
    the database and actual Python functions that can be used by ADK agents.
    """

    def __init__(self):
        """Initialize the tool registry."""
        self._tools: dict[str, Callable] = {}
        self._register_builtin_tools()

    def _register_builtin_tools(self):
        """Register built-in tools."""
        from src.infrastructure.tools import sample_tools

        # Auto-register all functions from sample_tools module
        for name, func in inspect.getmembers(sample_tools, inspect.isfunction):
            if not name.startswith("_"):
                self._tools[name] = func

    def register_tool(self, name: str, func: Callable) -> None:
        """
        Register a new tool function.

        Args:
            name: The name of the tool
            func: The function to register
        """
        if not callable(func):
            raise ValueError(f"Tool {name} must be callable")

        self._tools[name] = func

    def get_tool(self, tool_config: ToolConfig) -> Optional[Callable]:
        """
        Get a tool function based on its configuration.

        Args:
            tool_config: The tool configuration

        Returns:
            The tool function if found, None otherwise
        """
        if not tool_config.enabled:
            return None

        if tool_config.tool_type == "function":
            # For function tools, look up by function_name
            function_name = tool_config.function_name or tool_config.tool_name
            return self._tools.get(function_name)

        elif tool_config.tool_type == "builtin":
            # For built-in ADK tools, return the tool name
            # The agent service will handle loading these
            return tool_config.tool_name

        elif tool_config.tool_type == "third_party":
            # For third-party tools, attempt dynamic import
            return self._load_third_party_tool(tool_config)

        return None

    def _load_third_party_tool(self, tool_config: ToolConfig) -> Optional[Callable]:
        """
        Dynamically load a third-party tool.

        Args:
            tool_config: The tool configuration

        Returns:
            The loaded tool function or None
        """
        try:
            # Expect parameters to have 'module' and optionally 'attribute'
            module_name = tool_config.parameters.get("module")
            attr_name = tool_config.parameters.get("attribute", tool_config.function_name)

            if not module_name:
                return None

            module = importlib.import_module(module_name)

            if attr_name:
                return getattr(module, attr_name)
            return module

        except (ImportError, AttributeError) as e:
            print(f"Error loading third-party tool {tool_config.tool_name}: {e}")
            return None

    def list_tools(self) -> list[str]:
        """
        List all registered tool names.

        Returns:
            List of tool names
        """
        return list(self._tools.keys())

    def get_tools_for_configs(self, tool_configs: list[ToolConfig]) -> list[Any]:
        """
        Get all tool functions for a list of tool configurations.

        Args:
            tool_configs: List of tool configurations

        Returns:
            List of tool functions (excluding None values)
        """
        tools = []
        for config in tool_configs:
            tool = self.get_tool(config)
            if tool is not None:
                tools.append(tool)
        return tools
