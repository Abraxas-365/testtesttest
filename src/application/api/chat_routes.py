"""RESTful Chat API for frontend integration."""

import logging
import json
import asyncio
from fastapi import APIRouter, HTTPException, Depends, Request, Query
from fastapi.responses import StreamingResponse
from typing import Optional, List
from pydantic import BaseModel, Field

from src.middleware.teams_auth import require_auth
from src.application.di import get_container
from src.domain.services.chat_service import ChatService
from src.domain.services.streaming_chat_service import StreamingChatService
from src.domain.models.chat_models import (
    ChatMessageRequest, SessionMessageRequest,
    ChatResponse, SessionListResponse, SessionDetailResponse
)

logger = logging.getLogger(__name__)
router = APIRouter()


async def get_chat_service() -> ChatService:
    """Dependency to get chat service."""
    container = get_container()
    agent_service = await container.get_agent_service()
    return ChatService(agent_service)


async def get_streaming_chat_service() -> StreamingChatService:
    """Dependency to get streaming chat service."""
    container = get_container()
    return await container.get_streaming_chat_service()


# =============================================================================
# Request Models for Streaming
# =============================================================================


class AttachmentInfoRequest(BaseModel):
    """Attachment info in streaming requests."""
    id: str
    filename: str
    content_type: str
    blob_path: Optional[str] = None


class StreamChatRequest(BaseModel):
    """Request for streaming chat messages."""
    prompt: str = Field(..., description="User's message")
    agent_id: Optional[str] = Field(None, description="Specific agent ID")
    agent_name: Optional[str] = Field(None, description="Agent name (alternative to agent_id)")
    session_id: Optional[str] = Field(None, description="Session ID for continuing conversation")
    attachments: List[AttachmentInfoRequest] = Field(default_factory=list, description="File attachments")
    metadata: Optional[dict] = Field(None, description="Additional context")


# =============================================================================
# SSE Generator
# =============================================================================


async def _sse_generator(events):
    """
    Async generator that formats StreamEvents as SSE data.

    SSE Format:
    - data: {"content": "..."} for content chunks
    - data: {"session": {...}} for session info
    - data: [DONE] for completion
    - data: {"error": {"message": "..."}} for errors
    """
    try:
        async for event in events:
            yield event.to_sse()
    except asyncio.CancelledError:
        # Client disconnected - this is normal, don't log as error
        logger.info("SSE stream cancelled by client")
        yield "data: [CANCELLED]\n\n"
    except Exception as e:
        logger.error(f"SSE generator error: {e}", exc_info=True)
        yield f"data: {json.dumps({'error': {'message': str(e)}})}\n\n"


# =============================================================================
# Streaming Endpoint
# =============================================================================


@router.post("/chat/stream")
async def stream_chat_message(
    request: StreamChatRequest,
    user: dict = Depends(require_auth),
    chat_service: ChatService = Depends(get_chat_service),
    streaming_service: StreamingChatService = Depends(get_streaming_chat_service)
):
    """
    Stream a chat message response using SSE with true token-level streaming.

    **Authentication:** Required JWT token

    **Response Format:** Server-Sent Events (SSE)
    - Session info: `data: {"session_id": "...", "agent_id": "..."}`
    - Content chunks: `data: {"content": "..."}` (token-by-token)
    - Completion: `data: [DONE]`
    - Errors: `data: {"error": "..."}`

    **Attachments:** Supports PDFs, images, Word docs, Excel, PowerPoint.
    Files are downloaded from GCS and sent to Gemini for multimodal analysis.

    **Client Usage:**
    ```javascript
    const response = await fetch('/api/v1/chat/stream', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
            prompt: "Hola, necesito ayuda...",
            agent_name: "mi_agente",  // opcional
            session_id: "sess_abc123",  // opcional, para continuar sesion
            attachments: [{  // opcional
                id: "doc-123",
                filename: "report.pdf",
                content_type: "application/pdf",
                blob_path: "uploads/user/doc-123/report.pdf"
            }]
        })
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\\n');
        buffer = lines.pop() || "";  // Keep incomplete line

        for (const line of lines) {
            if (line.startsWith('data: ')) {
                const data = line.slice(6);
                if (data === '[DONE]') {
                    // Stream complete
                } else {
                    const parsed = JSON.parse(data);
                    if (parsed.content) {
                        // Append content token to message
                    }
                }
            }
        }
    }
    ```

    **Cancellation:** Client can abort using AbortController.
    """
    try:
        user_id = user["user_id"]

        logger.info(f"🌊 Stream request from {user['email']}: {request.prompt[:50]}...")

        # Convert attachments to dict format
        attachments = [
            {
                "id": a.id,
                "filename": a.filename,
                "content_type": a.content_type,
                "blob_path": a.blob_path
            }
            for a in request.attachments
        ] if request.attachments else None

        # Resolve agent ID and get agent instruction
        agent_id = None
        agent_instruction = None

        if request.agent_id or request.agent_name:
            container = get_container()
            agent_service = await container.get_agent_service()

            if request.agent_id:
                agent_config = await agent_service.repository.get_agent_by_id(request.agent_id)
            else:
                agent_config = await agent_service.repository.get_agent_by_name(request.agent_name)

            if agent_config:
                agent_id = agent_config.agent_id
                agent_instruction = agent_config.instruction

        # Use the new streaming service with true token-level streaming
        event_stream = streaming_service.stream_message(
            user_id=user_id,
            prompt=request.prompt,
            session_id=request.session_id,
            agent_id=agent_id,
            agent_instruction=agent_instruction,
            attachments=attachments,
        )

        return StreamingResponse(
            _sse_generator(event_stream),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
            }
        )

    except Exception as e:
        logger.error(f"❌ Stream endpoint error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Non-Streaming Endpoints
# =============================================================================


@router.post("/chat", response_model=ChatResponse)
async def send_chat_message(
    request: ChatMessageRequest,
    user: dict = Depends(require_auth),
    chat_service: ChatService = Depends(get_chat_service)
):
    """
    Send a chat message (creates new session if needed).

    **Authentication:** Required JWT token

    **Request Body:**
    - prompt: User's message (required)
    - agent_id: Specific agent ID (optional)
    - agent_name: Agent name (optional, alternative to agent_id)
    - metadata: Additional context (optional)

    **Response:**
    - message: Agent's response with metadata
    - session_id: Session ID for subsequent messages
    - agent_id: Agent handling this conversation
    - agent_name: Display name of agent
    """
    user_id = user["user_id"]

    logger.info(f"💬 Chat message from {user['email']}: {request.prompt[:50]}...")

    try:
        response = await chat_service.send_message(
            user_id=user_id,
            prompt=request.prompt,
            agent_id=request.agent_id,
            agent_name=request.agent_name,
            metadata=request.metadata
        )

        logger.info(f"✅ Message sent, session: {response.session_id}")
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error sending message: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error sending message: {str(e)}"
        )


@router.post("/chat/sessions/{session_id}", response_model=ChatResponse)
async def send_session_message(
    session_id: str,
    request: SessionMessageRequest,
    user: dict = Depends(require_auth),
    chat_service: ChatService = Depends(get_chat_service)
):
    """
    Send a message to existing session.

    **Authentication:** Required JWT token

    **Path Parameters:**
    - session_id: Existing session ID

    **Request Body:**
    - prompt: User's message (required)
    - metadata: Additional context (optional)

    **Response:**
    - message: Agent's response
    - session_id: Same session ID
    - agent_id: Agent handling this session
    """
    user_id = user["user_id"]

    logger.info(f"💬 Session message from {user['email']} to {session_id}")

    try:
        response = await chat_service.send_message(
            user_id=user_id,
            prompt=request.prompt,
            session_id=session_id,
            metadata=request.metadata
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error sending session message: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error sending message: {str(e)}"
        )


@router.get("/chat/sessions", response_model=SessionListResponse)
async def list_sessions(
    user: dict = Depends(require_auth),
    chat_service: ChatService = Depends(get_chat_service),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    status: Optional[str] = Query(None, regex="^(active|closed|archived)$", description="Filter by status")
):
    """
    List user's chat sessions.

    **Authentication:** Required JWT token

    **Query Parameters:**
    - page: Page number (default: 1)
    - page_size: Items per page (default: 20, max: 100)
    - status: Filter by status: 'active', 'closed', 'archived' (optional)

    **Response:**
    - sessions: Array of session summaries
    - total: Total number of sessions
    - page: Current page
    - page_size: Items per page
    - has_more: Whether there are more pages
    """
    user_id = user["user_id"]

    logger.info(f"📋 Listing sessions for {user['email']} (page {page})")

    try:
        return await chat_service.list_sessions(
            user_id=user_id,
            page=page,
            page_size=page_size,
            status=status
        )
    except Exception as e:
        logger.error(f"❌ Error listing sessions: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error listing sessions: {str(e)}"
        )


@router.get("/chat/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session_history(
    session_id: str,
    user: dict = Depends(require_auth),
    chat_service: ChatService = Depends(get_chat_service),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of messages to return"),
    before_message_id: Optional[str] = Query(None, description="For pagination: get messages before this ID")
):
    """
    Get session details with message history.

    **Authentication:** Required JWT token

    **Path Parameters:**
    - session_id: Session ID to retrieve

    **Query Parameters:**
    - limit: Maximum messages to return (default: 50, max: 200)
    - before_message_id: Cursor for pagination (optional)

    **Response:**
    - session_id: Session identifier
    - agent_id: Agent for this session
    - agent_name: Agent display name
    - user_id: Session owner
    - status: Session status
    - title: Session title
    - messages: Full conversation history
    - total_messages: Number of messages
    """
    user_id = user["user_id"]

    logger.info(f"📖 Getting session {session_id} for {user['email']}")

    try:
        return await chat_service.get_session_detail(
            session_id=session_id,
            user_id=user_id,
            limit=limit,
            before_message_id=before_message_id
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error getting session: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error getting session: {str(e)}"
        )


@router.delete("/chat/sessions/{session_id}")
async def delete_session(
    session_id: str,
    user: dict = Depends(require_auth),
    chat_service: ChatService = Depends(get_chat_service)
):
    """
    Delete (close) a session.

    **Authentication:** Required JWT token

    **Path Parameters:**
    - session_id: Session ID to delete

    **Response:**
    - status: "success"
    - message: Confirmation message
    - session_id: Deleted session ID
    """
    user_id = user["user_id"]

    logger.info(f"🗑️  Deleting session {session_id} for {user['email']}")

    try:
        return await chat_service.delete_session(
            session_id=session_id,
            user_id=user_id
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error deleting session: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error deleting session: {str(e)}"
        )
