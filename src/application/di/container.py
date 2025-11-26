"""Dependency injection container for the application."""

import os
import logging
import asyncpg
from typing import Optional
from urllib.parse import quote_plus

from google.adk.sessions import DatabaseSessionService

from src.domain.ports import AgentRepository, CorpusRepository
from src.domain.ports.group_mapping_repository import GroupMappingRepository
from src.domain.services import AgentService
from src.infrastructure.adapters.postgres import (
    PostgresAgentRepository,
    PostgresCorpusRepository,
    PostgresGroupMappingRepository,
)
from src.infrastructure.tools import ToolRegistry

logger = logging.getLogger(__name__)


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
        self._session_service: Optional[DatabaseSessionService] = None

    async def init_repository(self) -> AgentRepository:
        """
        Initialize and return the agent repository.

        Returns:
            AgentRepository instance
        """
        if self._repository is None:
            db_host = os.getenv("DB_HOST", "localhost")
            db_port = int(os.getenv("DB_PORT", "5432"))
            db_name = os.getenv("DB_NAME", "agents_db")
            db_user = os.getenv("DB_USER", "postgres")
            db_password = os.getenv("DB_PASSWORD", "postgres")

            self._repository = await PostgresAgentRepository.create(
                host=db_host,
                port=db_port,
                database=db_name,
                user=db_user,
                password=db_password,
            )
            logger.info("✅ PostgresAgentRepository initialized")

        return self._repository

    async def init_corpus_repository(self) -> CorpusRepository:
        """
        Initialize and return the corpus repository.

        Uses the same database connection as the agent repository.

        Returns:
            CorpusRepository instance
        """
        if self._corpus_repository is None:
            db_host = os.getenv("DB_HOST", "localhost")
            db_port = int(os.getenv("DB_PORT", "5432"))
            db_name = os.getenv("DB_NAME", "agents_db")
            db_user = os.getenv("DB_USER", "postgres")
            db_password = os.getenv("DB_PASSWORD", "postgres")

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
            logger.info("✅ PostgresCorpusRepository initialized")

        return self._corpus_repository

    async def init_group_mapping_repository(self) -> GroupMappingRepository:
        """
        Initialize and return the group mapping repository.

        Uses the same database connection as the agent repository.

        Returns:
            GroupMappingRepository instance
        """
        if self._group_mapping_repository is None:
            db_host = os.getenv("DB_HOST", "localhost")
            db_port = int(os.getenv("DB_PORT", "5432"))
            db_name = os.getenv("DB_NAME", "agents_db")
            db_user = os.getenv("DB_USER", "postgres")
            db_password = os.getenv("DB_PASSWORD", "postgres")

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
            logger.info("✅ PostgresGroupMappingRepository initialized")

        return self._group_mapping_repository

    def get_tool_registry(self) -> ToolRegistry:
        """
        Get the tool registry.

        Returns:
            ToolRegistry instance
        """
        if self._tool_registry is None:
            self._tool_registry = ToolRegistry()
            logger.info("✅ ToolRegistry initialized")

        return self._tool_registry

    def get_session_service(self) -> DatabaseSessionService:
        """
        Get the session service - ALWAYS use DatabaseSessionService for persistence.
        
        Uses psycopg2 (synchronous driver) because ADK's DatabaseSessionService
        doesn't support async initialization.

        Returns:
            DatabaseSessionService for persistent sessions
        """
        if self._session_service is None:
            db_user = os.getenv("DB_USER", "postgres")
            db_password = os.getenv("DB_PASSWORD", "postgres")
            db_host = os.getenv("DB_HOST", "localhost")
            db_port = os.getenv("DB_PORT", "5432")
            db_name = os.getenv("DB_NAME", "agents_db")

            encoded_password = quote_plus(db_password)

            if db_host.startswith("/cloudsql/"):
                db_url = f"postgresql+psycopg2://{db_user}:{encoded_password}@/{db_name}?host={db_host}"
                logger.info(f"🔌 Using Cloud SQL Unix socket: {db_host}")
            else:
                db_url = f"postgresql+psycopg2://{db_user}:{encoded_password}@{db_host}:{db_port}/{db_name}"
                logger.info(f"🔌 Using TCP connection: {db_host}:{db_port}")

            try:
                self._session_service = DatabaseSessionService(db_url=db_url)
                logger.info("✅ DatabaseSessionService initialized successfully")
                logger.info(f"📊 Database: {db_name}")
                logger.info(f"👤 User: {db_user}")
                
                try:
                    logger.info("🔍 Session service ready (connection will be tested on first use)")
                except Exception as test_error:
                    logger.warning(f"⚠️ Could not test connection: {test_error}")
                    
            except Exception as e:
                logger.error(f"❌ Error initializing DatabaseSessionService: {e}")
                logger.error(f"💡 Check that:")
                logger.error(f"   1. Database exists: {db_name}")
                logger.error(f"   2. User has permissions: {db_user}")
                logger.error(f"   3. Tables exist (run migrations)")
                logger.error(f"   4. psycopg2-binary is installed")
                import traceback
                traceback.print_exc()
                raise  

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
            self._agent_service = AgentService(
                repository=repository,
                tool_registry=tool_registry,
                session_service=session_service
            )
            logger.info("✅ AgentService initialized")

        return self._agent_service

    async def close(self):
        """Close all resources."""
        logger.info("🧹 Closing container resources...")
        
        if self._repository and isinstance(self._repository, PostgresAgentRepository):
            await self._repository.close()
            logger.info("✅ Agent repository closed")
            
        if self._corpus_repository and isinstance(self._corpus_repository, PostgresCorpusRepository):
            await self._corpus_repository.pool.close()
            logger.info("✅ Corpus repository closed")
            
        if self._group_mapping_repository and isinstance(self._group_mapping_repository, PostgresGroupMappingRepository):
            await self._group_mapping_repository.pool.close()
            logger.info("✅ Group mapping repository closed")
        
        if self._session_service:
            logger.info("✅ Session service cleanup (managed by ADK)")


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
        logger.info("🚀 Container created")
    return _container


async def close_container():
    """Close the global container."""
    global _container
    if _container is not None:
        await _container.close()
        _container = None
        logger.info("✅ Container closed")
