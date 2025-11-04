"""Agent service for creating and managing ADK agents."""

from typing import Optional
from google.adk.agents import Agent, LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

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
        self._runner_cache: dict[str, Runner] = {}
        
        # Initialize session service for managing agent conversations
        self.session_service = InMemorySessionService()

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

    def _get_or_create_runner(self, agent_id: str, agent: Agent) -> Runner:
        """
        Get or create a runner for the agent.

        Args:
            agent_id: The unique identifier of the agent
            agent: The agent instance

        Returns:
            Runner instance for the agent
        """
        if agent_id not in self._runner_cache:
            runner = Runner(
                agent=agent,
                app_name=f"agent_{agent_id}",
                session_service=self.session_service
            )
            self._runner_cache[agent_id] = runner
        return self._runner_cache[agent_id]

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
        
        # Remove runner from cache too
        if agent_id in self._runner_cache:
            del self._runner_cache[agent_id]

        return await self.get_agent(agent_id, use_cache=False)

    def clear_cache(self):
        """Clear the agent and runner caches."""
        self._agent_cache.clear()
        self._runner_cache.clear()

    async def invoke_agent(
        self, agent_id: str, prompt: str, **kwargs
    ) -> str:
        """
        Invoke an agent with a prompt.

        Args:
            agent_id: The unique identifier of the agent
            prompt: The prompt to send to the agent
            **kwargs: Additional arguments (user_id, session_id, use_session)

        Returns:
            The agent's response as a string
        """
        agent = await self.get_agent(agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        # Check if we should use session-based approach (default: False for simplicity)
        use_session = kwargs.get("use_session", False)

        if use_session:
            # Use session-based runner approach
            return await self._invoke_with_session(agent_id, agent, prompt, **kwargs)
        else:
            # Use simple direct invocation (stateless)
            return await self._invoke_direct(agent, prompt)

    async def _invoke_direct(self, agent: Agent, prompt: str) -> str:
        """
        Invoke agent directly without session management (stateless).

        Args:
            agent: The agent instance
            prompt: The prompt to send

        Returns:
            The agent's response as a string
        """
        try:
            # For simple stateless invocation, just call the agent
            response = agent(prompt)

            # Handle different response types
            if isinstance(response, str):
                return response
            elif hasattr(response, 'text'):
                return response.text
            elif hasattr(response, 'content'):
                if hasattr(response.content, 'parts'):
                    text_parts = []
                    for part in response.content.parts:
                        if hasattr(part, 'text'):
                            text_parts.append(part.text)
                    return ''.join(text_parts)
                return str(response.content)
            else:
                return str(response)
        except Exception as e:
            raise RuntimeError(f"Error invoking agent: {str(e)}")

    async def _invoke_with_session(
        self, agent_id: str, agent: Agent, prompt: str, **kwargs
    ) -> str:
        """
        Invoke agent using session-based runner approach.

        Args:
            agent_id: The agent ID
            agent: The agent instance
            prompt: The prompt to send
            **kwargs: Additional arguments (user_id, session_id)

        Returns:
            The agent's response as a string
        """
        # Get or create runner for this agent
        runner = self._get_or_create_runner(agent_id, agent)

        # Extract user and session info
        user_id = kwargs.get("user_id", "default_user")
        session_id = kwargs.get("session_id")
        app_name = f"agent_{agent_id}"

        # Create a new session for each request if not provided
        if not session_id:
            import uuid
            session_id = f"session_{agent_id}_{uuid.uuid4().hex[:8]}"

        # Always create a fresh session for this request
        try:
            self.session_service.create_session(
                app_name=app_name,
                user_id=user_id,
                session_id=session_id
            )
        except Exception as e:
            # Session might already exist, which is fine
            print(f"Note: Session creation info: {e}")

        # Create message content in the format ADK expects
        message = types.Content(
            role="user",
            parts=[types.Part(text=prompt)]
        )

        # Run agent and collect response
        response_text = ""
        try:
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=message
            ):
                # Check if this is the final response
                if event.is_final_response() and event.content:
                    if event.content.parts:
                        for part in event.content.parts:
                            if hasattr(part, 'text') and part.text:
                                response_text += part.text
        except Exception as e:
            raise RuntimeError(f"Error running agent with session: {str(e)}")

        return response_text

    async def invoke_agent_by_name(
        self, name: str, prompt: str, **kwargs
    ) -> str:
        """
        Invoke an agent by name with a prompt.

        Args:
            name: The name of the agent
            prompt: The prompt to send to the agent
            **kwargs: Additional arguments (user_id, session_id, etc.)

        Returns:
            The agent's response as a string
        """
        # Get the agent config to find the agent_id
        config = await self.repository.get_agent_by_name(name)
        if not config:
            raise ValueError(f"Agent '{name}' not found")

        # Use invoke_agent with the agent_id
        return await self.invoke_agent(config.agent_id, prompt, **kwargs)
