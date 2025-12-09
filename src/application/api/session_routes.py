"""API routes for session management."""

import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import asyncpg

from src.application.di import get_container


router = APIRouter()

# Module-level pool for session queries
_db_pool: Optional[asyncpg.Pool] = None


async def get_db_pool() -> asyncpg.Pool:
    """Get or create the database pool for session queries."""
    global _db_pool

    if _db_pool is None:
        db_host = os.getenv("DB_HOST", "localhost")
        db_port = int(os.getenv("DB_PORT", "5432"))
        db_name = os.getenv("DB_NAME", "agents_db")
        db_user = os.getenv("DB_USER", "postgres")
        db_password = os.getenv("DB_PASSWORD", "postgres")

        _db_pool = await asyncpg.create_pool(
            host=db_host,
            port=db_port,
            database=db_name,
            user=db_user,
            password=db_password,
            min_size=2,
            max_size=10,
        )

    return _db_pool


class SessionInfo(BaseModel):
    """Session information."""
    session_id: str
    app_name: str
    user_id: str
    agent_id: Optional[str] = None
    status: str
    created_at: Optional[str] = None
    last_message_at: Optional[str] = None


class MessageInfo(BaseModel):
    """Message information."""
    message_id: str
    session_id: str
    role: str
    content: str
    created_at: Optional[str] = None


@router.get("/sessions", response_model=list[dict])
async def list_user_sessions(user_id: str = "default_user"):
    """
    List all sessions for a user.

    Args:
        user_id: The user identifier
    """
    container = get_container()
    agent_service = await container.get_agent_service()

    if not agent_service.persistent_session_service:
        raise HTTPException(
            status_code=501,
            detail="Persistent sessions not enabled. Set PERSIST_SESSIONS=true"
        )

    try:
        pool = await get_db_pool()

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT session_id, app_name, user_id, agent_id, status,
                       created_at, last_message_at
                FROM sessions
                WHERE user_id = $1 AND status IN ('active', 'closed')
                ORDER BY created_at DESC
                LIMIT 50
                """,
                user_id
            )

            return [
                {
                    "session_id": row['session_id'],
                    "app_name": row['app_name'],
                    "user_id": row['user_id'],
                    "agent_id": row['agent_id'],
                    "status": row['status'],
                    "created_at": row['created_at'].isoformat() if row['created_at'] else None,
                    "last_message_at": row['last_message_at'].isoformat() if row['last_message_at'] else None
                }
                for row in rows
            ]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing sessions: {str(e)}")


@router.get("/sessions/{session_id}", response_model=dict)
async def get_session(session_id: str, user_id: str = "default_user"):
    """
    Get session details with conversation history.

    Args:
        session_id: The session identifier
        user_id: The user identifier
    """
    container = get_container()
    agent_service = await container.get_agent_service()

    if not agent_service.persistent_session_service:
        raise HTTPException(
            status_code=501,
            detail="Persistent sessions not enabled"
        )

    try:
        pool = await get_db_pool()

        async with pool.acquire() as conn:
            session_row = await conn.fetchrow(
                """
                SELECT session_id, app_name, user_id, agent_id, status,
                       title, created_at, last_message_at
                FROM sessions
                WHERE session_id = $1 AND user_id = $2
                """,
                session_id, user_id
            )

            if not session_row:
                raise HTTPException(status_code=404, detail="Session not found")

            message_rows = await conn.fetch(
                """
                SELECT message_id, role, content, created_at,
                       tool_name, model_used
                FROM messages
                WHERE session_id = $1
                ORDER BY created_at ASC
                """,
                session_id
            )

            return {
                "session": {
                    "session_id": session_row['session_id'],
                    "app_name": session_row['app_name'],
                    "user_id": session_row['user_id'],
                    "agent_id": session_row['agent_id'],
                    "status": session_row['status'],
                    "title": session_row['title'],
                    "created_at": session_row['created_at'].isoformat() if session_row['created_at'] else None,
                    "last_message_at": session_row['last_message_at'].isoformat() if session_row['last_message_at'] else None
                },
                "messages": [
                    {
                        "message_id": msg['message_id'],
                        "role": msg['role'],
                        "content": msg['content'],
                        "created_at": msg['created_at'].isoformat() if msg['created_at'] else None,
                        "tool_name": msg['tool_name'],
                        "model_used": msg['model_used']
                    }
                    for msg in message_rows
                ]
            }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting session: {str(e)}")


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, user_id: str = "default_user"):
    """
    Delete (close) a session.

    Args:
        session_id: The session identifier
        user_id: The user identifier
    """
    container = get_container()
    agent_service = await container.get_agent_service()

    if not agent_service.persistent_session_service:
        raise HTTPException(
            status_code=501,
            detail="Persistent sessions not enabled"
        )

    try:
        pool = await get_db_pool()

        async with pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE sessions
                SET status = 'closed', closed_at = NOW()
                WHERE session_id = $1 AND user_id = $2
                """,
                session_id, user_id
            )

            if result == "UPDATE 0":
                raise HTTPException(status_code=404, detail="Session not found")

            return {"status": "success", "message": f"Session {session_id} closed"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting session: {str(e)}")
