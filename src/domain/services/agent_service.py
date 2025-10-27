"""Agent service for creating and managing ADK agents."""

from typing import Optional
from google.adk.agents import Agent, LlmAgent

from src.domain.models import AgentConfig
from src.domain.ports import AgentRepository
from src.infrastructure.tools import ToolRegistry


class AgentService:
    """
    Service for creating and managing ADK agents.

    This service uses the repository (port) to load agent configurations
    and the tool registry to resolve tool functions, then creates
    Google ADK Agent instances.
    """

    def __init__(self, repository: AgentRepository, tool_registry: ToolRegistry):
        """
        Initialize the agent service.

        Args:
            repository: The agent repository (port interface)
            tool_registry: The tool registry for resolving tools
        """
        self.repository = repository
        self.tool_registry = tool_registry
        self._agent_cache: dict[str, Agent] = {}

    async def get_agent(self, agent_id: str, use_cache: bool = True) -> Optional[Agent]:
        """
        Get an ADK agent by ID.

        Args:
            agent_id: The unique identifier of the agent
            use_cache: If True, return cached agent if available

        Returns:
            Agent instance if found, None otherwise
        """
        if use_cache and agent_id in self._agent_cache:
            return self._agent_cache[agent_id]

        config = await self.repository.get_agent_by_id(agent_id)
        if not config:
            return None

        agent = await self._create_agent_from_config(config)
        if agent and use_cache:
            self._agent_cache[agent_id] = agent

        return agent

    async def get_agent_by_name(self, name: str, use_cache: bool = True) -> Optional[Agent]:
        """
        Get an ADK agent by name.

        Args:
            name: The name of the agent
            use_cache: If True, return cached agent if available

        Returns:
            Agent instance if found, None otherwise
        """
        config = await self.repository.get_agent_by_name(name)
        if not config:
            return None

        # Check cache by agent_id
        if use_cache and config.agent_id in self._agent_cache:
            return self._agent_cache[config.agent_id]

        agent = await self._create_agent_from_config(config)
        if agent and use_cache:
            self._agent_cache[config.agent_id] = agent

        return agent

    async def list_agents(self, enabled_only: bool = True) -> list[Agent]:
        """
        List all ADK agents.

        Args:
            enabled_only: If True, return only enabled agents

        Returns:
            List of Agent instances
        """
        configs = await self.repository.list_agents(enabled_only)
        agents = []

        for config in configs:
            agent = await self._create_agent_from_config(config)
            if agent:
                agents.append(agent)

        return agents

    async def _create_agent_from_config(self, config: AgentConfig) -> Optional[Agent]:
        """
        Create an ADK agent from configuration.

        Args:
            config: The agent configuration

        Returns:
            Agent instance or None if creation fails
        """
        if not config.enabled:
            return None

        try:
            # Get tools for the agent (pass corpuses and agent_service for RAG/agent tools)
            tools = self.tool_registry.get_tools_for_configs(
                config.tools,
                corpuses=config.corpuses,
                agent_service=self
            )

            # Get sub-agents if any
            sub_agents = []
            if config.sub_agent_ids:
                for sub_agent_id in config.sub_agent_ids:
                    sub_agent = await self.get_agent(sub_agent_id)
                    if sub_agent:
                        sub_agents.append(sub_agent)

            # Create agent based on whether it has sub-agents
            if sub_agents:
                # Use LlmAgent for hierarchical agents
                agent = LlmAgent(
                    name=config.name,
                    model=config.model.model_name,
                    description=config.description,
                    instruction=config.instruction,
                    tools=tools if tools else None,
                    sub_agents=sub_agents,
                )
            else:
                # Use simple Agent for leaf agents
                agent = Agent(
                    name=config.name,
                    model=config.model.model_name,
                    description=config.description,
                    instruction=config.instruction,
                    tools=tools if tools else None,
                )

            return agent

        except Exception as e:
            print(f"Error creating agent {config.name}: {e}")
            return None

    async def reload_agent(self, agent_id: str) -> Optional[Agent]:
        """
        Reload an agent from the database, bypassing cache.

        Args:
            agent_id: The unique identifier of the agent

        Returns:
            Agent instance if found, None otherwise
        """
        # Remove from cache if present
        if agent_id in self._agent_cache:
            del self._agent_cache[agent_id]

        return await self.get_agent(agent_id, use_cache=False)

    def clear_cache(self):
        """Clear the agent cache."""
        self._agent_cache.clear()

    async def invoke_agent(
        self, agent_id: str, prompt: str, **kwargs
    ) -> str:
        """
        Invoke an agent with a prompt.

        Args:
            agent_id: The unique identifier of the agent
            prompt: The prompt to send to the agent
            **kwargs: Additional arguments to pass to the agent

        Returns:
            The agent's response as a string
        """
        agent = await self.get_agent(agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        # Invoke the agent (ADK agents can be called directly)
        response = agent(prompt, **kwargs)

        return response

    async def invoke_agent_by_name(
        self, name: str, prompt: str, **kwargs
    ) -> str:
        """
        Invoke an agent by name with a prompt.

        Args:
            name: The name of the agent
            prompt: The prompt to send to the agent
            **kwargs: Additional arguments to pass to the agent

        Returns:
            The agent's response as a string
        """
        agent = await self.get_agent_by_name(name)
        if not agent:
            raise ValueError(f"Agent {name} not found")

        response = agent(prompt, **kwargs)

        return response
