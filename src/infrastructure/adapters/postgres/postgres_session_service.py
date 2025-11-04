"""PostgreSQL-backed session service for ADK agents."""

import uuid
from datetime import datetime
from typing import Optional, List
from asyncpg import Pool

from google.adk.sessions import SessionService
from google.adk.sessions.session import Session as AdkSession
from google.genai import types

from src.domain.models import Session, Message


class PostgresSessionService(SessionService):
    """
    PostgreSQL implementation of ADK SessionService.

    This stores conversation sessions and messages in PostgreSQL for:
    - Persistent conversation history
    - Multi-instance support
    - Analytics and monitoring
    - Conversation resumption
    """

    def __init__(self, pool: Pool):
        """
        Initialize with database connection pool.

        Args:
            pool: AsyncPG connection pool
        """
        self.pool = pool

    def create_session(
        self,
        app_name: str,
        user_id: str,
        session_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> AdkSession:
        """
        Create a new session.

        Args:
            app_name: Application name
            user_id: User identifier
            session_id: Optional session ID (generated if not provided)
            agent_id: Optional agent ID

        Returns:
            ADK Session object
        """
        if not session_id:
            session_id = f"sess_{uuid.uuid4().hex[:12]}"

        # Store in database (sync wrapper for async)
        import asyncio
        loop = asyncio.get_event_loop()

        async def _create():
            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO sessions (session_id, app_name, user_id, agent_id, status)
                    VALUES ($1, $2, $3, $4, 'active')
                    ON CONFLICT (session_id) DO NOTHING
                    """,
                    session_id, app_name, user_id, agent_id
                )

        try:
            loop.run_until_complete(_create())
        except RuntimeError:
            # Event loop might not be running, use asyncio.run
            asyncio.run(_create())

        # Return ADK Session object
        return AdkSession(
            session_id=session_id,
            app_name=app_name,
            user_id=user_id,
            history=[]
        )

    def get_session(
        self,
        app_name: str,
        user_id: str,
        session_id: str
    ) -> Optional[AdkSession]:
        """
        Get an existing session with its history.

        Args:
            app_name: Application name
            user_id: User identifier
            session_id: Session identifier

        Returns:
            ADK Session object with history or None
        """
        import asyncio
        loop = asyncio.get_event_loop()

        async def _get():
            async with self.pool.acquire() as conn:
                # Get session
                session_row = await conn.fetchrow(
                    """
                    SELECT session_id, app_name, user_id, agent_id, status
                    FROM sessions
                    WHERE session_id = $1 AND app_name = $2 AND user_id = $3
                    """,
                    session_id, app_name, user_id
                )

                if not session_row:
                    return None

                # Get messages
                message_rows = await conn.fetch(
                    """
                    SELECT role, content, created_at
                    FROM messages
                    WHERE session_id = $1
                    ORDER BY created_at ASC
                    """,
                    session_id
                )

                # Convert to ADK Content objects
                history = []
                for msg in message_rows:
                    history.append(
                        types.Content(
                            role=msg['role'],
                            parts=[types.Part(text=msg['content'])]
                        )
                    )

                return AdkSession(
                    session_id=session_id,
                    app_name=app_name,
                    user_id=user_id,
                    history=history
                )

        try:
            return loop.run_until_complete(_get())
        except RuntimeError:
            return asyncio.run(_get())

    def list_sessions(
        self,
        app_name: str,
        user_id: str
    ) -> List[AdkSession]:
        """
        List all sessions for a user.

        Args:
            app_name: Application name
            user_id: User identifier

        Returns:
            List of ADK Session objects
        """
        import asyncio
        loop = asyncio.get_event_loop()

        async def _list():
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT session_id, app_name, user_id, agent_id
                    FROM sessions
                    WHERE app_name = $1 AND user_id = $2 AND status = 'active'
                    ORDER BY created_at DESC
                    """,
                    app_name, user_id
                )

                return [
                    AdkSession(
                        session_id=row['session_id'],
                        app_name=row['app_name'],
                        user_id=row['user_id'],
                        history=[]
                    )
                    for row in rows
                ]

        try:
            return loop.run_until_complete(_list())
        except RuntimeError:
            return asyncio.run(_list())

    def delete_session(
        self,
        app_name: str,
        user_id: str,
        session_id: str
    ) -> bool:
        """
        Delete a session (actually marks as closed).

        Args:
            app_name: Application name
            user_id: User identifier
            session_id: Session identifier

        Returns:
            True if deleted, False otherwise
        """
        import asyncio
        loop = asyncio.get_event_loop()

        async def _delete():
            async with self.pool.acquire() as conn:
                result = await conn.execute(
                    """
                    UPDATE sessions
                    SET status = 'closed', closed_at = NOW()
                    WHERE session_id = $1 AND app_name = $2 AND user_id = $3
                    """,
                    session_id, app_name, user_id
                )
                return result == "UPDATE 1"

        try:
            return loop.run_until_complete(_delete())
        except RuntimeError:
            return asyncio.run(_delete())

    def save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        tool_name: Optional[str] = None,
        tool_call_id: Optional[str] = None,
        model_used: Optional[str] = None,
        tokens_used: Optional[int] = None
    ) -> str:
        """
        Save a message to the session.

        Args:
            session_id: Session identifier
            role: Message role (user, agent, system, tool)
            content: Message content
            tool_name: Optional tool name
            tool_call_id: Optional tool call ID
            model_used: Optional model identifier
            tokens_used: Optional token count

        Returns:
            Message ID
        """
        import asyncio

        message_id = f"msg_{uuid.uuid4().hex[:12]}"
        loop = asyncio.get_event_loop()

        async def _save():
            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO messages (
                        message_id, session_id, role, content,
                        tool_name, tool_call_id, model_used, tokens_used
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    """,
                    message_id, session_id, role, content,
                    tool_name, tool_call_id, model_used, tokens_used
                )
            return message_id

        try:
            return loop.run_until_complete(_save())
        except RuntimeError:
            return asyncio.run(_save())

    async def save_message_async(
        self,
        session_id: str,
        role: str,
        content: str,
        tool_name: Optional[str] = None,
        model_used: Optional[str] = None
    ) -> str:
        """
        Async version of save_message.

        Args:
            session_id: Session identifier
            role: Message role
            content: Message content
            tool_name: Optional tool name
            model_used: Optional model identifier

        Returns:
            Message ID
        """
        message_id = f"msg_{uuid.uuid4().hex[:12]}"

        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO messages (
                    message_id, session_id, role, content,
                    tool_name, model_used
                )
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                message_id, session_id, role, content,
                tool_name, model_used
            )

        return message_id
