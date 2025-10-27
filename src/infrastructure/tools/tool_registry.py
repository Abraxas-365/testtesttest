"""Tool registry for dynamically loading and managing agent tools."""

import importlib
import inspect
from typing import Any, Callable, Optional
from src.domain.models import ToolConfig, CorpusConfig


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

    def get_tool(self, tool_config: ToolConfig, corpuses: list = None, agent_service: Any = None) -> Optional[Callable]:
        """
        Get a tool function based on its configuration.

        Args:
            tool_config: The tool configuration
            corpuses: List of corpus configurations (for RAG tools)
            agent_service: Agent service instance (for agent tools)

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

        elif tool_config.tool_type == "rag":
            # For RAG tools, create a specialized RAG tool with corpuses
            return self._create_rag_tool(tool_config, corpuses)

        elif tool_config.tool_type == "agent":
            # For agent tools, return a reference that can call another agent
            return self._create_agent_tool(tool_config, agent_service)

        elif tool_config.tool_type == "third_party":
            # For third-party tools, attempt dynamic import
            return self._load_third_party_tool(tool_config)

        return None

    def _create_rag_tool(self, tool_config: ToolConfig, corpuses: list) -> Optional[Callable]:
        """
        Create a RAG tool with bound corpuses.

        Args:
            tool_config: The tool configuration
            corpuses: List of corpus configurations

        Returns:
            A callable RAG tool function
        """
        from src.infrastructure.tools.rag_tool import create_rag_tool

        if not corpuses:
            print(f"Warning: RAG tool {tool_config.tool_name} has no corpuses configured")
            return None

        rag_tool = create_rag_tool(corpuses)
        return rag_tool

    def _create_agent_tool(self, tool_config: ToolConfig, agent_service: Any) -> Optional[Callable]:
        """
        Create an agent tool that delegates to another agent.

        Args:
            tool_config: The tool configuration
            agent_service: The agent service instance

        Returns:
            A callable that invokes another agent
        """
        if not agent_service:
            print(f"Warning: Agent tool {tool_config.tool_name} requires agent_service")
            return None

        # Get the target agent ID from function_name or parameters
        target_agent_id = tool_config.function_name or tool_config.parameters.get("agent_id")

        if not target_agent_id:
            print(f"Warning: Agent tool {tool_config.tool_name} has no target agent_id")
            return None

        # Create a function that delegates to the target agent
        async def delegate_to_agent(prompt: str, **kwargs) -> dict[str, Any]:
            """Delegate task to another agent."""
            try:
                response = await agent_service.invoke_agent(target_agent_id, prompt, **kwargs)
                return {
                    "status": "success",
                    "agent_id": target_agent_id,
                    "response": response
                }
            except Exception as e:
                return {
                    "status": "error",
                    "agent_id": target_agent_id,
                    "error": str(e)
                }

        return delegate_to_agent

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

    def get_tools_for_configs(
        self,
        tool_configs: list[ToolConfig],
        corpuses: list[CorpusConfig] = None,
        agent_service: Any = None
    ) -> list[Any]:
        """
        Get all tool functions for a list of tool configurations.

        Args:
            tool_configs: List of tool configurations
            corpuses: List of corpus configurations (for RAG tools)
            agent_service: Agent service instance (for agent tools)

        Returns:
            List of tool functions (excluding None values)
        """
        tools = []
        for config in tool_configs:
            tool = self.get_tool(config, corpuses=corpuses, agent_service=agent_service)
            if tool is not None:
                tools.append(tool)
        return tools
