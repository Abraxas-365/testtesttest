"""Agent service for creating and managing ADK agents."""

from typing import Optional, Any
from google.adk.agents import Agent, LlmAgent
from google.adk.runners import Runner
from google.genai import types
import logging
import uuid
import asyncio
from asyncio import Lock
from collections import defaultdict

from src.domain.models import AgentConfig
from src.domain.ports import AgentRepository
from src.infrastructure.tools import ToolRegistry

logger = logging.getLogger(__name__)


class SessionLockManager:
    """Manages locks for session access to prevent race conditions."""
    def __init__(self):
        self._locks: dict[str, Lock] = defaultdict(Lock)
    
    def get_lock(self, session_id: str) -> Lock:
        """Get or create a lock for a session."""
        return self._locks[session_id]


class AgentService:
    """Service for creating and managing ADK agents."""

    def __init__(
        self,
        repository: AgentRepository,
        tool_registry: ToolRegistry,
        session_service: Optional[Any] = None
    ):
        self.repository = repository
        self.tool_registry = tool_registry
        self._agent_cache: dict[str, Agent] = {}
        self.persistent_session_service = session_service
        self.lock_manager = SessionLockManager()

    async def get_agent(self, agent_id: str, use_cache: bool = True) -> Optional[Agent]:
        """Get an ADK agent by ID."""
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
        """Get an ADK agent by name."""
        config = await self.repository.get_agent_by_name(name)
        if not config:
            return None

        if use_cache and config.agent_id in self._agent_cache:
            return self._agent_cache[config.agent_id]

        agent = await self._create_agent_from_config(config)
        if agent and use_cache:
            self._agent_cache[config.agent_id] = agent

        return agent

    async def list_agents(self, enabled_only: bool = True) -> list[Agent]:
        """List all ADK agents."""
        configs = await self.repository.list_agents(enabled_only)
        agents = []

        for config in configs:
            agent = await self._create_agent_from_config(config)
            if agent:
                agents.append(agent)

        return agents

    async def _create_agent_from_config(self, config: AgentConfig) -> Optional[Agent]:
        """Create an ADK agent from configuration."""
        if not config.enabled:
            return None

        try:
            from src.infrastructure.callbacks.context_management import safe_context_management_callback
            
            tools = self.tool_registry.get_tools_for_configs(
                config.tools,
                corpuses=config.corpuses,
                agent_service=self
            )

            sub_agents = []
            if config.sub_agent_ids:
                for sub_agent_id in config.sub_agent_ids:
                    sub_agent = await self.get_agent(sub_agent_id)
                    if sub_agent:
                        sub_agents.append(sub_agent)

            if sub_agents:
                agent = LlmAgent(
                    name=config.name,
                    model=config.model.model_name,
                    description=config.description,
                    instruction=config.instruction,
                    tools=tools if tools else None,
                    sub_agents=sub_agents,
                    before_model_callback=safe_context_management_callback,
                )
            else:
                agent = Agent(
                    name=config.name,
                    model=config.model.model_name,
                    description=config.description,
                    instruction=config.instruction,
                    tools=tools if tools else None,
                    before_model_callback=safe_context_management_callback,
                )

            return agent

        except Exception as e:
            logger.error(f"Error creating agent {config.name}: {e}")
            return None

    async def reload_agent(self, agent_id: str) -> Optional[Agent]:
        """Reload an agent from the database, bypassing cache."""
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
        Sessions are ALWAYS persisted to database.
        Uses session locking to prevent race conditions.
        """
        agent = await self.get_agent(agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        session_id = kwargs.get("session_id")
        if not session_id:
            session_id = f"sess_{uuid.uuid4().hex[:12]}"
            kwargs["session_id"] = session_id
        
        async with self.lock_manager.get_lock(session_id):
            logger.info(f"🔒 Acquired lock for session {session_id[:20]}...")
            try:
                result = await self._invoke_with_runner(agent_id, agent, prompt, **kwargs)
                logger.info(f"🔓 Released lock for session {session_id[:20]}...")
                return result
            except Exception as e:
                logger.info(f"🔓 Released lock for session {session_id[:20]}... (error)")
                raise

    async def _invoke_with_runner(
        self, agent_id: str, agent: Agent, prompt: str, **kwargs
    ) -> str:
        """
        Invoke agent using Runner with proper session history loading.
        Sessions are ALWAYS persisted to database using DatabaseSessionService.
        """
        user_id = kwargs.get("user_id", "default_user")
        session_id = kwargs.get("session_id")

        if not session_id:
            session_id = f"sess_{uuid.uuid4().hex[:12]}"

        app_name = f"agent_{agent_id}"

        session_service = self.persistent_session_service
        
        if not session_service:
            raise RuntimeError(
                "DatabaseSessionService not initialized! "
                "Check database connection and configuration."
            )
        
        logger.info(f"💾 Using persistent DatabaseSessionService")

        session = None
        try:
            session = await session_service.get_session(
                app_name=app_name,
                user_id=user_id,
                session_id=session_id
            )
            if session:
                history_count = len(session.history) if hasattr(session, 'history') and session.history else 0
                logger.info(f"🔄 Loaded FRESH session {session_id[:50]}... with {history_count} messages")
                
                if hasattr(session, 'last_update_time'):
                    logger.info(f"📅 Session last updated: {session.last_update_time}")
            else:
                logger.info(f"📝 No existing session found")
        except Exception as e:
            logger.warning(f"⚠️ Error loading session: {e}")
            session = None

        if not session:
            try:
                logger.info(f"🆕 Creating new session {session_id[:50]}...")
                session = await session_service.create_session(
                    app_name=app_name,
                    user_id=user_id,
                    session_id=session_id
                )
            except Exception as e:
                logger.error(f"❌ Error creating session: {e}")
                raise RuntimeError(f"Failed to create session: {str(e)}")

        runner = Runner(
            agent=agent,
            app_name=app_name,
            session_service=session_service
        )

        message = types.Content(
            role="user",
            parts=[types.Part(text=prompt)]
        )

        history_count = 0
        if session and hasattr(session, 'history') and session.history:
            history_count = len(session.history)
        
        logger.info(f"🤖 Sending to LLM with {history_count} history messages")

        response_text = ""
        function_calls_made = 0
        
        try:
            async def run_with_timeout():
                nonlocal response_text, function_calls_made
                
                async for event in runner.run_async(
                    user_id=user_id,
                    session_id=session_id,
                    new_message=message
                ):
                    if hasattr(event, 'content') and event.content:
                        if hasattr(event.content, 'parts'):
                            for part in event.content.parts:
                                if hasattr(part, 'function_call') and part.function_call:
                                    function_calls_made += 1
                                    logger.info(f"🔧 Function call: {part.function_call.name}")
                                
                                if hasattr(part, 'text') and part.text:
                                    response_text += part.text
                    
                    if hasattr(event, 'text') and event.text:
                        response_text += event.text
            
            await asyncio.wait_for(run_with_timeout(), timeout=60.0)
            
            logger.info(f"✅ Collected response ({len(response_text)} chars, {function_calls_made} function calls)")
            
        except asyncio.TimeoutError:
            logger.error(f"⏱️ Agent processing timed out after 60 seconds")
            raise RuntimeError(
                "El procesamiento está tomando más tiempo del esperado. "
                "Por favor, intenta con una consulta más específica o un documento más corto."
            )
        except Exception as e:
            logger.error(f"❌ Error invoking agent: {e}", exc_info=True)
            raise RuntimeError(f"Error invoking agent: {str(e)}")

        if not response_text and function_calls_made > 0:
            response_text = "I've processed your request using my tools. How else can I help you?"
        
        if not response_text:
            response_text = "I apologize, but I couldn't generate a response. Could you please rephrase your question?"

        return response_text

    async def invoke_agent_by_name(
        self, name: str, prompt: str, **kwargs
    ) -> str:
        """
        Invoke an agent by name with a prompt.
        Sessions are ALWAYS persisted to database.
        """
        config = await self.repository.get_agent_by_name(name)
        if not config:
            raise ValueError(f"Agent '{name}' not found")

        return await self.invoke_agent(config.agent_id, prompt, **kwargs)
