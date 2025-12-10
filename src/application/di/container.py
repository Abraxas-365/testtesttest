"""Dependency injection container for the application."""

import os
import logging
import asyncpg
from typing import Optional
from urllib.parse import quote_plus

from google.adk.sessions import DatabaseSessionService

from src.domain.ports import AgentRepository, CorpusRepository, TextEditorRepository
from src.domain.ports.group_mapping_repository import GroupMappingRepository
from src.domain.ports.policy_repository import PolicyRepository
from src.domain.services import AgentService
from src.domain.services.policy_service import PolicyService
from src.domain.services.policy_generation_service import PolicyGenerationService
from src.domain.services.questionnaire_service import QuestionnaireService
from src.domain.services.streaming_chat_service import StreamingChatService
from src.infrastructure.adapters.postgres import (
    PostgresAgentRepository,
    PostgresCorpusRepository,
    PostgresGroupMappingRepository,
    PostgresTextEditorRepository,
)
from src.infrastructure.adapters.postgres.postgres_policy_repository import PostgresPolicyRepository
from src.infrastructure.tools import ToolRegistry
from src.services.storage_service import StorageService

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
        self._text_editor_repository: Optional[TextEditorRepository] = None
        self._tool_registry: Optional[ToolRegistry] = None
        self._agent_service: Optional[AgentService] = None
        self._session_service: Optional[DatabaseSessionService] = None
        # Policy system services
        self._policy_repository = None
        self._storage_service = None
        self._policy_service = None
        self._policy_generation_service = None
        self._questionnaire_service = None
        # Streaming chat service
        self._streaming_chat_service: Optional[StreamingChatService] = None
        self._shared_db_pool: Optional[asyncpg.Pool] = None

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

        Uses the shared database pool.

        Returns:
            CorpusRepository instance
        """
        if self._corpus_repository is None:
            pool = await self._get_shared_db_pool()
            self._corpus_repository = PostgresCorpusRepository(pool)
            logger.info("✅ PostgresCorpusRepository initialized (shared pool)")

        return self._corpus_repository

    async def init_group_mapping_repository(self) -> GroupMappingRepository:
        """
        Initialize and return the group mapping repository.

        Uses the shared database pool.

        Returns:
            GroupMappingRepository instance
        """
        if self._group_mapping_repository is None:
            pool = await self._get_shared_db_pool()
            self._group_mapping_repository = PostgresGroupMappingRepository(pool)
            logger.info("✅ PostgresGroupMappingRepository initialized (shared pool)")

        return self._group_mapping_repository

    async def get_text_editor_repository(self) -> TextEditorRepository:
        """
        Initialize and return the text editor repository.

        Uses the same database connection pattern as other repositories.

        Returns:
            TextEditorRepository instance
        """
        if self._text_editor_repository is None:
            db_host = os.getenv("DB_HOST", "localhost")
            db_port = int(os.getenv("DB_PORT", "5432"))
            db_name = os.getenv("DB_NAME", "agents_db")
            db_user = os.getenv("DB_USER", "postgres")
            db_password = os.getenv("DB_PASSWORD", "postgres")

            self._text_editor_repository = await PostgresTextEditorRepository.create(
                host=db_host,
                port=db_port,
                database=db_name,
                user=db_user,
                password=db_password,
            )
            logger.info("✅ PostgresTextEditorRepository initialized")

        return self._text_editor_repository

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

    # ============================================
    # POLICY SYSTEM SERVICES
    # ============================================

    async def init_policy_repository(self) -> PolicyRepository:
        """
        Initialize and return the policy repository.

        Uses the shared database pool.

        Returns:
            PolicyRepository instance
        """
        if self._policy_repository is None:
            pool = await self._get_shared_db_pool()
            self._policy_repository = PostgresPolicyRepository(pool)
            logger.info("✅ PostgresPolicyRepository initialized (shared pool)")

        return self._policy_repository

    def get_storage_service(self) -> StorageService:
        """
        Get or create storage service singleton.

        Returns:
            StorageService instance
        """
        if self._storage_service is None:
            self._storage_service = StorageService()
            logger.info("✅ StorageService initialized")

        return self._storage_service

    async def get_policy_service(self) -> PolicyService:
        """
        Get policy service with dependencies.

        Returns:
            PolicyService instance
        """
        if self._policy_service is None:
            repo = await self.init_policy_repository()
            storage = self.get_storage_service()
            self._policy_service = PolicyService(repo, storage)
            logger.info("✅ PolicyService initialized")

        return self._policy_service

    async def get_policy_generation_service(self) -> PolicyGenerationService:
        """
        Get policy generation service.

        Returns:
            PolicyGenerationService instance
        """
        if self._policy_generation_service is None:
            repo = await self.init_policy_repository()
            storage = self.get_storage_service()
            self._policy_generation_service = PolicyGenerationService(repo, storage)
            logger.info("✅ PolicyGenerationService initialized")

        return self._policy_generation_service

    async def get_questionnaire_service(self) -> QuestionnaireService:
        """
        Get questionnaire service.

        Returns:
            QuestionnaireService instance
        """
        if self._questionnaire_service is None:
            repo = await self.init_policy_repository()
            self._questionnaire_service = QuestionnaireService(repo)
            logger.info("✅ QuestionnaireService initialized")

        return self._questionnaire_service

    async def _get_shared_db_pool(self) -> asyncpg.Pool:
        """
        Get or create a shared database pool for ALL services.

        This is the single source of database connections for the entire application.
        All repositories and services should use this pool.

        Returns:
            AsyncPG pool instance
        """
        if self._shared_db_pool is None:
            db_host = os.getenv("DB_HOST", "localhost")
            db_port = int(os.getenv("DB_PORT", "5432"))
            db_name = os.getenv("DB_NAME", "agents_db")
            db_user = os.getenv("DB_USER", "postgres")
            db_password = os.getenv("DB_PASSWORD", "postgres")

            # Use conservative pool settings to avoid connection exhaustion
            # Cloud SQL free tier: max_connections = 25
            # Cloud SQL basic: max_connections = 100
            self._shared_db_pool = await asyncpg.create_pool(
                host=db_host,
                port=db_port,
                database=db_name,
                user=db_user,
                password=db_password,
                min_size=2,  # Reduced from 5
                max_size=10,  # Reduced from 20 - leaves headroom for ADK sessions
                command_timeout=60,
            )
            logger.info(f"✅ Shared database pool initialized (min=2, max=10)")

        return self._shared_db_pool

    async def get_streaming_chat_service(self) -> StreamingChatService:
        """
        Get the streaming chat service for token-level streaming with attachments.

        Returns:
            StreamingChatService instance
        """
        if self._streaming_chat_service is None:
            storage_service = self.get_storage_service()
            db_pool = await self._get_shared_db_pool()

            self._streaming_chat_service = StreamingChatService(
                storage_service=storage_service,
                db_pool=db_pool,
            )
            logger.info("✅ StreamingChatService initialized")

        return self._streaming_chat_service

    async def get_db_pool(self) -> asyncpg.Pool:
        """
        Public method to get the shared database pool.

        Use this when services need direct access to the pool.

        Returns:
            AsyncPG pool instance
        """
        return await self._get_shared_db_pool()

    async def close(self):
        """Close all resources."""
        logger.info("🧹 Closing container resources...")

        if self._repository and isinstance(self._repository, PostgresAgentRepository):
            await self._repository.close()
            logger.info("✅ Agent repository closed")

        if self._text_editor_repository and isinstance(self._text_editor_repository, PostgresTextEditorRepository):
            await self._text_editor_repository.close()
            logger.info("✅ Text editor repository closed")

        if self._session_service:
            logger.info("✅ Session service cleanup (managed by ADK)")

        # Close the shared pool LAST since all repositories use it
        if self._shared_db_pool:
            await self._shared_db_pool.close()
            logger.info("✅ Shared database pool closed")


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
