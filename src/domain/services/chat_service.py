"""Business logic for chat and session management."""

from typing import Optional, List, Dict, Any, AsyncGenerator
from datetime import datetime
import logging
import uuid
import json
import asyncio

from google.adk.runners import Runner
from google.genai import types

from src.domain.services.agent_service import AgentService
from src.domain.models.chat_models import (
    ChatResponse, MessageResponse, SessionListItem,
    SessionListResponse, SessionDetailResponse
)
from src.domain.models.text_editor_models import StreamEvent
from fastapi import HTTPException

logger = logging.getLogger(__name__)


class ChatService:
    """Service for chat session management."""

    def __init__(self, agent_service: AgentService):
        self.agent_service = agent_service
        self.session_service = agent_service.persistent_session_service

    async def send_message(
        self,
        user_id: str,
        prompt: str,
        agent_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> ChatResponse:
        """
        Send a message and get agent response.
        Creates new session if session_id not provided.
        """
        # 1. Determine agent
        resolved_agent_id = await self._resolve_agent(agent_id, agent_name)

        # 2. If session_id provided, validate ownership and agent match
        if session_id:
            await self._validate_session_ownership(
                session_id, user_id, resolved_agent_id
            )
        else:
            # Generate session ID for new session
            session_id = f"sess_{uuid.uuid4().hex[:12]}"
            logger.info(f"🆕 Creating new session: {session_id}")

        # 3. Invoke agent (will create or load session)
        response_text = await self.agent_service.invoke_agent(
            agent_id=resolved_agent_id,
            prompt=prompt,
            user_id=user_id,
            session_id=session_id,
            metadata=metadata
        )

        # 4. Get agent info
        agent_config = await self.agent_service.repository.get_agent_by_id(
            resolved_agent_id
        )

        if not agent_config:
            raise HTTPException(
                status_code=500,
                detail=f"Agent config not found for agent_id: {resolved_agent_id}"
            )

        # 5. Update session with agent_id and title (if new session)
        await self._update_session_metadata(
            session_id=session_id,
            user_id=user_id,
            agent_id=resolved_agent_id,
            prompt=prompt  # Will use first message as title
        )

        # 6. Build response
        return ChatResponse(
            message=MessageResponse(
                message_id=f"msg_{uuid.uuid4().hex[:8]}",
                session_id=session_id,
                role="agent",
                content=response_text,
                agent_id=resolved_agent_id,
                agent_name=agent_config.name,
                created_at=datetime.utcnow()
            ),
            session_id=session_id,
            agent_id=resolved_agent_id,
            agent_name=agent_config.name,
            agent_area=agent_config.metadata.get("area_type", "general") if agent_config.metadata else "general"
        )

    async def stream_message(
        self,
        user_id: str,
        prompt: str,
        agent_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[dict] = None,
        attachments: Optional[List[Dict[str, Any]]] = None
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        Stream a chat message response using SSE.
        Creates new session if session_id not provided.

        Yields StreamEvent objects for SSE serialization.
        """
        # 1. Determine agent
        resolved_agent_id = await self._resolve_agent(agent_id, agent_name)

        # 2. If session_id provided, validate ownership and agent match
        if session_id:
            await self._validate_session_ownership(
                session_id, user_id, resolved_agent_id
            )
        else:
            # Generate session ID for new session
            session_id = f"sess_{uuid.uuid4().hex[:12]}"
            logger.info(f"🆕 Creating new streaming session: {session_id}")

        try:
            # 3. Get the agent
            agent = await self.agent_service.get_agent(resolved_agent_id)
            if not agent:
                yield StreamEvent(
                    event_type="error",
                    data={"message": f"Agent {resolved_agent_id} not found"}
                )
                return

            # 4. Get session service
            session_service = self.session_service
            if not session_service:
                yield StreamEvent(
                    event_type="error",
                    data={"message": "Session service not initialized"}
                )
                return

            # 5. Create runner
            app_name = f"agent_{resolved_agent_id}"
            runner = Runner(
                agent=agent,
                app_name=app_name,
                session_service=session_service
            )

            # 6. Build message parts
            parts = [types.Part(text=prompt)]

            # Add attachment info to prompt if present
            if attachments:
                attachment_text = "\n\n[Archivos adjuntos: "
                attachment_text += ", ".join(a.get("filename", "archivo") for a in attachments)
                attachment_text += "]"
                parts.append(types.Part(text=attachment_text))

            content_message = types.Content(role="user", parts=parts)

            # 7. Stream the response with lock
            async with self.agent_service.lock_manager.get_lock(session_id):
                logger.info(f"🔒 Streaming started for session {session_id[:20]}...")

                # Emit session info first
                yield StreamEvent(
                    event_type="session",
                    data={"session_id": session_id, "agent_id": resolved_agent_id}
                )

                try:
                    async for event in runner.run_async(
                        user_id=user_id,
                        session_id=session_id,
                        new_message=content_message
                    ):
                        # Extract text content from event
                        chunk_text = self._extract_text_from_event(event)
                        if chunk_text:
                            yield StreamEvent(
                                event_type="content",
                                data={"content": chunk_text}
                            )

                except asyncio.CancelledError:
                    logger.info(f"Stream cancelled for session {session_id}")
                    yield StreamEvent(
                        event_type="cancelled",
                        data={"session_id": session_id}
                    )
                    return

            # 8. Update session metadata
            await self._update_session_metadata(
                session_id=session_id,
                user_id=user_id,
                agent_id=resolved_agent_id,
                prompt=prompt
            )

            # 9. Signal completion
            logger.info(f"✅ Stream completed for session {session_id}")
            yield StreamEvent(
                event_type="done",
                data={"session_id": session_id}
            )

        except Exception as e:
            logger.error(f"❌ Stream error: {e}", exc_info=True)
            yield StreamEvent(
                event_type="error",
                data={"message": str(e)}
            )

    def _extract_text_from_event(self, event: Any) -> str:
        """Extract text content from an ADK event."""
        text = ""

        if hasattr(event, "content") and event.content:
            if hasattr(event.content, "parts"):
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text:
                        text += part.text

        if hasattr(event, "text") and event.text:
            text += event.text

        return text

    async def list_sessions(
        self,
        user_id: str,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None
    ) -> SessionListResponse:
        """List user's sessions with pagination."""
        if not self.session_service or not hasattr(self.session_service, 'pool'):
            raise HTTPException(
                status_code=503,
                detail="Session service not available"
            )

        pool = self.session_service.pool
        offset = (page - 1) * page_size

        async with pool.acquire() as conn:
            # Get total count
            count_query = """
                SELECT COUNT(*)
                FROM sessions
                WHERE user_id = $1
                  AND ($2::text IS NULL OR status = $2)
            """
            total = await conn.fetchval(count_query, user_id, status)

            # Get sessions
            query = """
                SELECT
                    id as session_id,
                    agent_id,
                    title,
                    status,
                    create_time as created_at,
                    update_time as last_message_at,
                    (SELECT COUNT(*) FROM events WHERE session_id = sessions.id) as message_count
                FROM sessions
                WHERE user_id = $1
                  AND ($2::text IS NULL OR status = $2)
                ORDER BY update_time DESC NULLS LAST
                LIMIT $3 OFFSET $4
            """

            rows = await conn.fetch(query, user_id, status, page_size, offset)

            # Fetch agent names for sessions
            sessions = []
            for row in rows:
                agent_name = None
                if row['agent_id']:
                    try:
                        agent_config = await self.agent_service.repository.get_agent_by_id(
                            row['agent_id']
                        )
                        if agent_config:
                            agent_name = agent_config.name
                    except Exception as e:
                        logger.warning(f"Could not fetch agent name for {row['agent_id']}: {e}")

                sessions.append(SessionListItem(
                    session_id=row['session_id'],
                    agent_id=row['agent_id'],
                    agent_name=agent_name,
                    title=row['title'],
                    status=row['status'] or 'active',
                    message_count=row['message_count'] or 0,
                    created_at=row['created_at'],
                    last_message_at=row['last_message_at']
                ))

            return SessionListResponse(
                sessions=sessions,
                total=total,
                page=page,
                page_size=page_size,
                has_more=offset + page_size < total
            )

    async def get_session_detail(
        self,
        session_id: str,
        user_id: str,
        limit: int = 50,
        before_message_id: Optional[str] = None
    ) -> SessionDetailResponse:
        """Get session with message history."""
        if not self.session_service or not hasattr(self.session_service, 'pool'):
            raise HTTPException(
                status_code=503,
                detail="Session service not available"
            )

        pool = self.session_service.pool

        async with pool.acquire() as conn:
            # Get session
            session_row = await conn.fetchrow(
                """
                SELECT id, agent_id, user_id, status, title,
                       create_time, update_time
                FROM sessions
                WHERE id = $1 AND user_id = $2
                """,
                session_id, user_id
            )

            if not session_row:
                raise HTTPException(
                    status_code=404,
                    detail="Session not found or access denied"
                )

            # Get agent name
            agent_name = None
            if session_row['agent_id']:
                try:
                    agent_config = await self.agent_service.repository.get_agent_by_id(
                        session_row['agent_id']
                    )
                    if agent_config:
                        agent_name = agent_config.name
                except Exception as e:
                    logger.warning(f"Could not fetch agent name: {e}")

            # Get messages from events table
            # ADK stores messages in events.content (JSONB)
            messages_query = """
                SELECT id, content, author, timestamp
                FROM events
                WHERE session_id = $1
                ORDER BY timestamp ASC
                LIMIT $2
            """

            message_rows = await conn.fetch(messages_query, session_id, limit)

            # Parse messages (ADK event format)
            messages = []
            for row in message_rows:
                try:
                    # ADK stores content as JSONB with 'parts' array
                    content_data = row['content']
                    message_text = ""

                    if isinstance(content_data, dict):
                        parts = content_data.get('parts', [])
                        for part in parts:
                            if isinstance(part, dict) and 'text' in part:
                                message_text += part['text']
                    elif isinstance(content_data, str):
                        message_text = content_data

                    messages.append(MessageResponse(
                        message_id=row['id'],
                        session_id=session_id,
                        role=row['author'] or "unknown",
                        content=message_text,
                        created_at=row['timestamp']
                    ))
                except Exception as e:
                    logger.error(f"Error parsing message {row['id']}: {e}")
                    continue

            return SessionDetailResponse(
                session_id=session_id,
                agent_id=session_row['agent_id'],
                agent_name=agent_name,
                user_id=user_id,
                status=session_row['status'] or 'active',
                title=session_row['title'],
                created_at=session_row['create_time'],
                last_message_at=session_row['update_time'],
                messages=messages,
                total_messages=len(messages)
            )

    async def delete_session(
        self,
        session_id: str,
        user_id: str
    ) -> Dict[str, str]:
        """Delete (close) a session."""
        if not self.session_service or not hasattr(self.session_service, 'pool'):
            raise HTTPException(
                status_code=503,
                detail="Session service not available"
            )

        pool = self.session_service.pool

        async with pool.acquire() as conn:
            # Check ownership first
            exists = await conn.fetchrow(
                "SELECT id FROM sessions WHERE id = $1 AND user_id = $2",
                session_id, user_id
            )

            if not exists:
                raise HTTPException(
                    status_code=404,
                    detail="Session not found or access denied"
                )

            # Update session to closed status
            result = await conn.execute(
                """
                UPDATE sessions
                SET status = 'closed', closed_at = NOW()
                WHERE id = $1 AND user_id = $2
                """,
                session_id, user_id
            )

            logger.info(f"🗑️  Closed session {session_id} for user {user_id}")

            return {
                "status": "success",
                "message": f"Session {session_id} deleted",
                "session_id": session_id
            }

    async def _resolve_agent(
        self,
        agent_id: Optional[str],
        agent_name: Optional[str]
    ) -> str:
        """Resolve agent ID from either agent_id or agent_name."""
        if agent_id:
            # Validate agent exists
            agent = await self.agent_service.repository.get_agent_by_id(agent_id)
            if not agent:
                raise HTTPException(
                    status_code=404,
                    detail=f"Agent '{agent_id}' not found"
                )
            return agent_id

        if agent_name:
            agent = await self.agent_service.repository.get_agent_by_name(
                agent_name
            )
            if not agent:
                raise HTTPException(
                    status_code=404,
                    detail=f"Agent '{agent_name}' not found"
                )
            return agent.agent_id

        # No agent specified - get default or first enabled agent
        agents = await self.agent_service.repository.list_agents(enabled_only=True)
        if not agents:
            raise HTTPException(
                status_code=503,
                detail="No enabled agents available"
            )

        # Return first enabled agent
        logger.info(f"No agent specified, using default: {agents[0].agent_id}")
        return agents[0].agent_id

    async def _validate_session_ownership(
        self,
        session_id: str,
        user_id: str,
        agent_id: str
    ) -> None:
        """Validate user owns session and agent matches."""
        if not self.session_service or not hasattr(self.session_service, 'pool'):
            raise HTTPException(
                status_code=503,
                detail="Session service not available"
            )

        pool = self.session_service.pool

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT user_id, agent_id
                FROM sessions
                WHERE id = $1
                """,
                session_id
            )

            if not row:
                raise HTTPException(
                    status_code=404,
                    detail="Session not found"
                )

            if row['user_id'] != user_id:
                raise HTTPException(
                    status_code=403,
                    detail="Access denied: session belongs to different user"
                )

            # Check if agent matches (if session has an agent assigned)
            if row['agent_id'] and row['agent_id'] != agent_id:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "agent_mismatch",
                        "message": "Cannot change agent in existing session. Create a new session to use a different agent.",
                        "current_agent": row['agent_id'],
                        "requested_agent": agent_id
                    }
                )

    async def _update_session_metadata(
        self,
        session_id: str,
        user_id: str,
        agent_id: str,
        prompt: str
    ) -> None:
        """Update session with agent_id and title (from first message)."""
        if not self.session_service or not hasattr(self.session_service, 'pool'):
            return

        pool = self.session_service.pool

        try:
            async with pool.acquire() as conn:
                # Check if session needs metadata update
                existing = await conn.fetchrow(
                    "SELECT agent_id, title FROM sessions WHERE id = $1",
                    session_id
                )

                if not existing:
                    logger.warning(f"Session {session_id} not found for metadata update")
                    return

                # Update agent_id if not set
                if not existing['agent_id']:
                    await conn.execute(
                        "UPDATE sessions SET agent_id = $1 WHERE id = $2",
                        agent_id, session_id
                    )

                # Set title from first message (truncated to 100 chars)
                if not existing['title']:
                    title = prompt[:100] + "..." if len(prompt) > 100 else prompt
                    await conn.execute(
                        "UPDATE sessions SET title = $1 WHERE id = $2",
                        title, session_id
                    )

                logger.debug(f"Updated metadata for session {session_id}")

        except Exception as e:
            # Don't fail the request if metadata update fails
            logger.error(f"Error updating session metadata: {e}")
