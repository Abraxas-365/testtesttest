"""Dependency injection container for the application."""

import os
import asyncpg
from typing import Optional

from google.adk.sessions import DatabaseSessionService, InMemorySessionService

from src.domain.ports import AgentRepository, CorpusRepository
from src.domain.ports.group_mapping_repository import GroupMappingRepository
from src.domain.services import AgentService
from src.infrastructure.adapters.postgres import PostgresAgentRepository, PostgresCorpusRepository
from src.infrastructure.adapters.postgres.postgres_group_mapping_repository import PostgresGroupMappingRepository
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
        self._corpus_repository: Optional[CorpusRepository] = None
        self._group_mapping_repository: Optional[GroupMappingRepository] = None
        self._tool_registry: Optional[ToolRegistry] = None
        self._agent_service: Optional[AgentService] = None
        self._session_service: Optional[any] = None

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

    async def init_corpus_repository(self) -> CorpusRepository:
        """
        Initialize and return the corpus repository.

        Uses the same database connection as the agent repository.

        Returns:
            CorpusRepository instance
        """
        if self._corpus_repository is None:
            # Get database configuration from environment variables
            db_host = os.getenv("DB_HOST", "localhost")
            db_port = int(os.getenv("DB_PORT", "5432"))
            db_name = os.getenv("DB_NAME", "agents_db")
            db_user = os.getenv("DB_USER", "postgres")
            db_password = os.getenv("DB_PASSWORD", "postgres")

            # For simplicity, create a new pool for corpus repository
            # In production, you might want to share the pool
            pool = await asyncpg.create_pool(
                host=db_host,
                port=db_port,
                database=db_name,
                user=db_user,
                password=db_password,
                min_size=5,
                max_size=10,
            )
            self._corpus_repository = PostgresCorpusRepository(pool)

        return self._corpus_repository

    async def init_group_mapping_repository(self) -> GroupMappingRepository:
        """
        Initialize and return the group mapping repository.

        Uses the same database connection as the agent repository.

        Returns:
            GroupMappingRepository instance
        """
        if self._group_mapping_repository is None:
            # Get database configuration from environment variables
            db_host = os.getenv("DB_HOST", "localhost")
            db_port = int(os.getenv("DB_PORT", "5432"))
            db_name = os.getenv("DB_NAME", "agents_db")
            db_user = os.getenv("DB_USER", "postgres")
            db_password = os.getenv("DB_PASSWORD", "postgres")

            # Create a pool for group mapping repository
            pool = await asyncpg.create_pool(
                host=db_host,
                port=db_port,
                database=db_name,
                user=db_user,
                password=db_password,
                min_size=5,
                max_size=10,
            )
            self._group_mapping_repository = PostgresGroupMappingRepository(pool)

        return self._group_mapping_repository

    def get_tool_registry(self) -> ToolRegistry:
        """
        Get the tool registry.

        Returns:
            ToolRegistry instance
        """
        if self._tool_registry is None:
            self._tool_registry = ToolRegistry()

        return self._tool_registry

    def get_session_service(self):
        """
        Get the session service based on PERSIST_SESSIONS environment variable.

        Returns:
            DatabaseSessionService for persistent sessions, or None for ephemeral
        """
        if self._session_service is None:
            persist_sessions = os.getenv("PERSIST_SESSIONS", "false").lower() == "true"

            if persist_sessions:
                # Build PostgreSQL connection URL for ADK's DatabaseSessionService
                db_user = os.getenv("DB_USER", "postgres")
                db_password = os.getenv("DB_PASSWORD", "postgres")
                db_host = os.getenv("DB_HOST", "localhost")
                db_port = os.getenv("DB_PORT", "5432")
                db_name = os.getenv("DB_NAME", "agents_db")

                # PostgreSQL connection URL
                db_url = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

                # Use ADK's built-in DatabaseSessionService
                self._session_service = DatabaseSessionService(db_url=db_url)
            else:
                # Return None to use ephemeral in-memory sessions per request
                self._session_service = None

        return self._session_service

    async def get_agent_service(self) -> AgentService:
        """
        Get the agent service.

        Returns:
            AgentService instance
        """
        if self._agent_service is None:
            repository = await self.init_repository()
            tool_registry = self.get_tool_registry()
            session_service = self.get_session_service()
            self._agent_service = AgentService(repository, tool_registry, session_service)

        return self._agent_service

    async def close(self):
        """Close all resources."""
        if self._repository and isinstance(self._repository, PostgresAgentRepository):
            await self._repository.close()
        if self._corpus_repository and isinstance(self._corpus_repository, PostgresCorpusRepository):
            await self._corpus_repository.pool.close()
        if self._group_mapping_repository and isinstance(self._group_mapping_repository, PostgresGroupMappingRepository):
            await self._group_mapping_repository.pool.close()


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
