"""Repository port (interface) for agent configuration."""

from abc import ABC, abstractmethod
from typing import Optional
from src.domain.models import AgentConfig, ToolConfig


class AgentRepository(ABC):
    """
    Port (interface) for agent configuration repository.

    This defines the contract that any adapter (like PostgreSQL) must implement
    to provide agent configuration data.
    """

    @abstractmethod
    async def get_agent_by_id(self, agent_id: str) -> Optional[AgentConfig]:
        """
        Retrieve an agent configuration by ID.

        Args:
            agent_id: The unique identifier of the agent

        Returns:
            AgentConfig if found, None otherwise
        """
        pass

    @abstractmethod
    async def get_agent_by_name(self, name: str) -> Optional[AgentConfig]:
        """
        Retrieve an agent configuration by name.

        Args:
            name: The name of the agent

        Returns:
            AgentConfig if found, None otherwise
        """
        pass

    @abstractmethod
    async def list_agents(self, enabled_only: bool = True) -> list[AgentConfig]:
        """
        List all agent configurations.

        Args:
            enabled_only: If True, return only enabled agents

        Returns:
            List of AgentConfig objects
        """
        pass

    @abstractmethod
    async def get_tools_for_agent(self, agent_id: str) -> list[ToolConfig]:
        """
        Get all tools configured for a specific agent.

        Args:
            agent_id: The unique identifier of the agent

        Returns:
            List of ToolConfig objects
        """
        pass

    @abstractmethod
    async def get_tool_by_id(self, tool_id: str) -> Optional[ToolConfig]:
        """
        Retrieve a tool configuration by ID.

        Args:
            tool_id: The unique identifier of the tool

        Returns:
            ToolConfig if found, None otherwise
        """
        pass

    @abstractmethod
    async def save_agent(self, agent: AgentConfig) -> AgentConfig:
        """
        Save or update an agent configuration.

        Args:
            agent: The agent configuration to save

        Returns:
            The saved AgentConfig
        """
        pass

    @abstractmethod
    async def delete_agent(self, agent_id: str) -> bool:
        """
        Delete an agent configuration.

        Args:
            agent_id: The unique identifier of the agent

        Returns:
            True if deleted, False if not found
        """
        pass
