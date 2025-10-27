"""Dependency injection container for the application."""

import os
from typing import Optional

from src.domain.ports import AgentRepository
from src.domain.services import AgentService
from src.infrastructure.adapters.postgres import PostgresAgentRepository
from src.infrastructure.tools import ToolRegistry


class Container:
    """
    Dependency injection container.

    This container manages the lifecycle of application dependencies
    and provides a clean way to inject them where needed.
    """

    def __init__(self):
        """Initialize the container."""
        self._repository: Optional[AgentRepository] = None
        self._tool_registry: Optional[ToolRegistry] = None
        self._agent_service: Optional[AgentService] = None

    async def init_repository(self) -> AgentRepository:
        """
        Initialize and return the agent repository.

        Returns:
            AgentRepository instance
        """
        if self._repository is None:
            # Get database configuration from environment variables
            db_host = os.getenv("DB_HOST", "localhost")
            db_port = int(os.getenv("DB_PORT", "5432"))
            db_name = os.getenv("DB_NAME", "agents_db")
            db_user = os.getenv("DB_USER", "postgres")
            db_password = os.getenv("DB_PASSWORD", "postgres")

            # Create PostgreSQL repository
            self._repository = await PostgresAgentRepository.create(
                host=db_host,
                port=db_port,
                database=db_name,
                user=db_user,
                password=db_password,
            )

        return self._repository

    def get_tool_registry(self) -> ToolRegistry:
        """
        Get the tool registry.

        Returns:
            ToolRegistry instance
        """
        if self._tool_registry is None:
            self._tool_registry = ToolRegistry()

        return self._tool_registry

    async def get_agent_service(self) -> AgentService:
        """
        Get the agent service.

        Returns:
            AgentService instance
        """
        if self._agent_service is None:
            repository = await self.init_repository()
            tool_registry = self.get_tool_registry()
            self._agent_service = AgentService(repository, tool_registry)

        return self._agent_service

    async def close(self):
        """Close all resources."""
        if self._repository and isinstance(self._repository, PostgresAgentRepository):
            await self._repository.close()


# Global container instance
_container: Optional[Container] = None


def get_container() -> Container:
    """
    Get the global container instance.

    Returns:
        Container instance
    """
    global _container
    if _container is None:
        _container = Container()
    return _container


async def close_container():
    """Close the global container."""
    global _container
    if _container is not None:
        await _container.close()
        _container = None
