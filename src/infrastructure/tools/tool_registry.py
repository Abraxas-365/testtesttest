"""Tool registry for dynamically loading and managing agent tools."""

import importlib
import inspect
import logging
from typing import Any, Callable, Optional
from src.domain.models import ToolConfig, CorpusConfig

logger = logging.getLogger(__name__)


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
            # ⚠️ This method is no longer used for RAG tools
            # RAG tools are now created per-corpus in get_tools_for_configs()
            logger.warning(f"⚠️ get_tool() called for RAG tool - this should be handled in get_tools_for_configs()")
            return None

        elif tool_config.tool_type == "agent":
            # For agent tools, return a reference that can call another agent
            return self._create_agent_tool(tool_config, agent_service)

        elif tool_config.tool_type == "third_party":
            # For third-party tools, attempt dynamic import
            return self._load_third_party_tool(tool_config)

        return None

    def _create_rag_tool_for_single_corpus(self, corpus: CorpusConfig) -> Optional[Callable]:
        """
        Create a RAG tool for a SINGLE corpus.
        
        This method creates one tool per corpus, allowing the agent to 
        explicitly choose which knowledge base to search.
        
        Args:
            corpus: Single corpus configuration
            
        Returns:
            A callable RAG tool function with corpus-specific name
        """
        from src.infrastructure.tools.rag_tool import create_rag_tool
        
        if not corpus.enabled:
            logger.warning(f"⏭️ Skipping disabled corpus: {corpus.corpus_name}")
            return None
        
        if not corpus.vertex_corpus_name:
            logger.warning(f"⏭️ Skipping corpus without vertex_corpus_name: {corpus.corpus_name}")
            return None
        
        try:
            rag_tool = create_rag_tool(corpus)
            
            tool_name = rag_tool.__name__ if hasattr(rag_tool, '__name__') else f"search_{corpus.corpus_name}"
            logger.info(f"✅ Created RAG tool: {tool_name} for corpus '{corpus.display_name}'")
            
            return rag_tool
            
        except Exception as e:
            logger.error(f"❌ Error creating RAG tool for {corpus.corpus_name}: {e}", exc_info=True)
            return None

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
            logger.warning(f"⚠️ Agent tool {tool_config.tool_name} requires agent_service")
            return None

        target_agent_id = tool_config.function_name or tool_config.parameters.get("agent_id")

        if not target_agent_id:
            logger.warning(f"⚠️ Agent tool {tool_config.tool_name} has no target agent_id")
            return None

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
            module_name = tool_config.parameters.get("module")
            attr_name = tool_config.parameters.get("attribute", tool_config.function_name)

            if not module_name:
                return None

            module = importlib.import_module(module_name)

            if attr_name:
                return getattr(module, attr_name)
            return module

        except (ImportError, AttributeError) as e:
            logger.error(f"❌ Error loading third-party tool {tool_config.tool_name}: {e}")
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
        
        ✅ NEW BEHAVIOR FOR RAG TOOLS:
        Instead of creating one RAG tool that searches all corpuses,
        this method creates ONE TOOL PER CORPUS, allowing the agent
        to explicitly choose which knowledge base to search.

        Args:
            tool_configs: List of tool configurations
            corpuses: List of corpus configurations (for RAG tools)
            agent_service: Agent service instance (for agent tools)

        Returns:
            List of tool functions (excluding None values)
        """
        tools = []
        
        for config in tool_configs:
            if config.tool_type == "rag":
                if corpuses:
                    logger.info(f"🔧 Creating RAG tools: 1 tool per corpus ({len(corpuses)} total)")
                    
                    for corpus in corpuses:
                        rag_tool = self._create_rag_tool_for_single_corpus(corpus)
                        if rag_tool is not None:
                            tools.append(rag_tool)
                            
                    logger.info(f"✅ Created {len([t for t in tools if callable(t)])} RAG tools")
                else:
                    logger.warning(f"⚠️ RAG tool '{config.tool_name}' has no corpuses configured")
            
            else:
                tool = self.get_tool(config, corpuses=corpuses, agent_service=agent_service)
                if tool is not None:
                    tools.append(tool)
        
        logger.info(f"📦 Total tools loaded: {len(tools)}")
        return tools
