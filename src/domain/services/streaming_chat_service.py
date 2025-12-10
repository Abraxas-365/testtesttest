"""
Streaming Chat Service using Gemini's native streaming API.

Provides true token-by-token streaming for chat responses with
multimodal attachment support (PDFs, images, documents).
"""

import os
import logging
import uuid
import asyncio
from typing import Optional, List, Dict, Any, AsyncGenerator
from datetime import datetime

import asyncpg
from google import genai
from google.genai import types

from src.domain.models.text_editor_models import StreamEvent
from src.services.storage_service import StorageService

logger = logging.getLogger(__name__)

# Supported MIME types for attachments
SUPPORTED_ATTACHMENT_TYPES = {
    "application/pdf": "PDF Document",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "Word Document",
    "application/msword": "Word Document (Legacy)",
    "text/plain": "Text File",
    "text/csv": "CSV File",
    "text/html": "HTML File",
    "text/markdown": "Markdown File",
    "image/jpeg": "JPEG Image",
    "image/png": "PNG Image",
    "image/gif": "GIF Image",
    "image/webp": "WebP Image",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "Excel Spreadsheet",
    "application/vnd.ms-excel": "Excel Spreadsheet (Legacy)",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "PowerPoint",
    "application/vnd.ms-powerpoint": "PowerPoint (Legacy)",
}

# Maximum attachment size (20MB for Gemini)
MAX_ATTACHMENT_SIZE = 20 * 1024 * 1024


class StreamingChatService:
    """
    Chat service with true token-level streaming using Gemini's native API.

    Features:
    - Token-by-token streaming via generate_content_stream()
    - Multimodal attachment support (PDFs, images, documents)
    - Conversation history management
    - Session persistence
    """

    def __init__(
        self,
        storage_service: StorageService,
        db_pool: asyncpg.Pool,
        project_id: Optional[str] = None,
        location: str = "us-east4",
        model_name: str = "gemini-2.0-flash",
    ):
        """
        Initialize the streaming chat service.

        Args:
            storage_service: GCS storage service for attachments
            db_pool: AsyncPG database pool for session/history management
            project_id: GCP project ID
            location: GCP region for Vertex AI
            model_name: Gemini model to use for streaming
        """
        self.storage_service = storage_service
        self.db_pool = db_pool
        self.project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT")
        self.location = location
        self.model_name = model_name

        self.gemini_client = genai.Client(
            vertexai=True,
            project=self.project_id,
            location=self.location,
        )

        logger.info(f"StreamingChatService initialized with model: {model_name}")

    async def stream_message(
        self,
        user_id: str,
        prompt: str,
        session_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        agent_instruction: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_output_tokens: int = 8192,
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        Stream a chat message response with true token-level streaming.

        Args:
            user_id: User identifier
            prompt: User's message
            session_id: Session ID (created if not provided)
            agent_id: Agent ID for context
            agent_instruction: System instruction for the agent
            attachments: List of attachment dicts with id, filename, content_type, blob_path
            temperature: Model temperature (0.0-1.0)
            max_output_tokens: Maximum response length

        Yields:
            StreamEvent objects for SSE serialization
        """
        # Generate session ID if not provided
        if not session_id:
            session_id = f"sess_{uuid.uuid4().hex[:12]}"
            logger.info(f"Created new session: {session_id}")

        try:
            # Emit session info first
            yield StreamEvent(
                event_type="session",
                data={"session_id": session_id, "agent_id": agent_id}
            )

            # Build multimodal content
            contents = await self._build_content(
                user_id=user_id,
                session_id=session_id,
                prompt=prompt,
                agent_instruction=agent_instruction,
                attachments=attachments,
            )

            # Stream the response using Gemini's native streaming
            full_response = ""

            logger.info(f"Starting streaming for session {session_id[:20]}...")

            # Await the stream coroutine first to get the async iterator
            stream = await self.gemini_client.aio.models.generate_content_stream(
                model=self.model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                ),
            )

            async for chunk in stream:
                # Extract text from chunk
                if chunk.text:
                    full_response += chunk.text
                    yield StreamEvent(
                        event_type="content",
                        data={"content": chunk.text}
                    )

            # Save the conversation to database
            await self._save_conversation(
                session_id=session_id,
                user_id=user_id,
                agent_id=agent_id,
                user_message=prompt,
                assistant_response=full_response,
                attachments=attachments,
            )

            logger.info(f"Stream completed for session {session_id}, response: {len(full_response)} chars")

            # Signal completion
            yield StreamEvent(
                event_type="done",
                data={"session_id": session_id}
            )

        except asyncio.CancelledError:
            logger.info(f"Stream cancelled for session {session_id}")
            yield StreamEvent(
                event_type="cancelled",
                data={"session_id": session_id}
            )

        except Exception as e:
            logger.error(f"Stream error for session {session_id}: {e}", exc_info=True)
            yield StreamEvent(
                event_type="error",
                data={"message": str(e)}
            )

    async def _build_content(
        self,
        user_id: str,
        session_id: str,
        prompt: str,
        agent_instruction: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
    ) -> List[types.Content]:
        """
        Build multimodal content for Gemini request.

        Args:
            user_id: User identifier
            session_id: Session ID
            prompt: User's current message
            agent_instruction: System instruction for agent personality
            attachments: List of attachments to process

        Returns:
            List of Content objects for Gemini
        """
        contents = []

        # Add system instruction as a user-model turn (Gemini pattern)
        if agent_instruction:
            contents.append(types.Content(
                role="user",
                parts=[types.Part(text=f"System: {agent_instruction}")]
            ))
            contents.append(types.Content(
                role="model",
                parts=[types.Part(text="Understood. I will follow these instructions.")]
            ))

        # Load and add conversation history
        history = await self._load_conversation_history(session_id)
        contents.extend(history)

        # Build current user message parts
        user_parts = []

        # Process attachments
        if attachments:
            for attachment in attachments:
                try:
                    attachment_parts = await self._process_attachment(attachment)
                    user_parts.extend(attachment_parts)
                except Exception as e:
                    logger.error(f"Failed to process attachment {attachment.get('filename')}: {e}")
                    # Add error note to prompt
                    user_parts.append(types.Part(
                        text=f"[Error loading attachment: {attachment.get('filename')} - {str(e)}]"
                    ))

        # Add user prompt
        user_parts.append(types.Part(text=prompt))

        # Add current user message
        contents.append(types.Content(role="user", parts=user_parts))

        return contents

    async def _process_attachment(
        self,
        attachment: Dict[str, Any]
    ) -> List[types.Part]:
        """
        Process a single attachment and return Gemini Parts.

        Args:
            attachment: Dict with id, filename, content_type, blob_path

        Returns:
            List of Part objects for the attachment
        """
        blob_path = attachment.get("blob_path")
        filename = attachment.get("filename", "document")
        content_type = attachment.get("content_type", "application/octet-stream")

        if not blob_path:
            raise ValueError(f"No blob_path provided for attachment {filename}")

        # Check if content type is supported
        if content_type not in SUPPORTED_ATTACHMENT_TYPES:
            raise ValueError(
                f"Unsupported content type: {content_type}. "
                f"Supported types: {list(SUPPORTED_ATTACHMENT_TYPES.keys())}"
            )

        # Download file from GCS (run in thread as it's synchronous)
        logger.info(f"Downloading attachment: {filename} from {blob_path}")

        doc_bytes = await asyncio.to_thread(
            self.storage_service.get_document_bytes,
            blob_path
        )

        # Check file size
        if len(doc_bytes) > MAX_ATTACHMENT_SIZE:
            raise ValueError(
                f"Attachment {filename} exceeds maximum size "
                f"({len(doc_bytes)} > {MAX_ATTACHMENT_SIZE} bytes)"
            )

        logger.info(f"Downloaded {len(doc_bytes)} bytes for {filename}")

        parts = []

        # Add the file as inline data
        parts.append(types.Part(
            inline_data=types.Blob(
                mime_type=content_type,
                data=doc_bytes
            )
        ))

        # Add filename label for context
        type_label = SUPPORTED_ATTACHMENT_TYPES.get(content_type, "Document")
        parts.append(types.Part(
            text=f"\n[Attached {type_label}: {filename}]\n"
        ))

        return parts

    async def _load_conversation_history(
        self,
        session_id: str,
        limit: int = 20
    ) -> List[types.Content]:
        """
        Load conversation history from database.

        Args:
            session_id: Session ID
            limit: Maximum number of messages to load

        Returns:
            List of Content objects representing conversation history
        """
        try:
            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT content, author
                    FROM events
                    WHERE session_id = $1
                    ORDER BY timestamp ASC
                    LIMIT $2
                    """,
                    session_id,
                    limit
                )

            contents = []
            for row in rows:
                author = row['author']
                content_data = row['content']

                # Extract text from ADK event format
                text = ""
                if isinstance(content_data, dict):
                    parts = content_data.get('parts', [])
                    for part in parts:
                        if isinstance(part, dict) and 'text' in part:
                            text += part['text']
                elif isinstance(content_data, str):
                    text = content_data

                if text:
                    # Map author to Gemini role
                    role = "user" if author == "user" else "model"
                    contents.append(types.Content(
                        role=role,
                        parts=[types.Part(text=text)]
                    ))

            logger.info(f"Loaded {len(contents)} history messages for session {session_id[:20]}")
            return contents

        except Exception as e:
            logger.warning(f"Could not load conversation history: {e}")
            return []

    async def _save_conversation(
        self,
        session_id: str,
        user_id: str,
        agent_id: Optional[str],
        user_message: str,
        assistant_response: str,
        attachments: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """
        Save conversation turn to database.

        Args:
            session_id: Session ID
            user_id: User identifier
            agent_id: Agent identifier
            user_message: User's message
            assistant_response: Assistant's response
            attachments: List of attachments (for metadata)
        """
        try:
            async with self.db_pool.acquire() as conn:
                # Ensure session exists
                session_exists = await conn.fetchval(
                    "SELECT id FROM sessions WHERE id = $1",
                    session_id
                )

                if not session_exists:
                    # Create session
                    await conn.execute(
                        """
                        INSERT INTO sessions (id, app_name, user_id, agent_id, status, create_time, update_time)
                        VALUES ($1, $2, $3, $4, 'active', NOW(), NOW())
                        """,
                        session_id,
                        f"agent_{agent_id}" if agent_id else "chat",
                        user_id,
                        agent_id
                    )
                    logger.info(f"Created session record: {session_id}")

                # Save user message
                user_event_id = f"evt_{uuid.uuid4().hex[:12]}"
                user_content = {
                    "parts": [{"text": user_message}]
                }
                if attachments:
                    user_content["attachments"] = [
                        {"filename": a.get("filename"), "content_type": a.get("content_type")}
                        for a in attachments
                    ]

                await conn.execute(
                    """
                    INSERT INTO events (id, session_id, author, content, timestamp)
                    VALUES ($1, $2, 'user', $3, NOW())
                    """,
                    user_event_id,
                    session_id,
                    user_content
                )

                # Save assistant response
                assistant_event_id = f"evt_{uuid.uuid4().hex[:12]}"
                await conn.execute(
                    """
                    INSERT INTO events (id, session_id, author, content, timestamp)
                    VALUES ($1, $2, 'model', $3, NOW())
                    """,
                    assistant_event_id,
                    session_id,
                    {"parts": [{"text": assistant_response}]}
                )

                # Update session timestamp and title if needed
                await conn.execute(
                    """
                    UPDATE sessions
                    SET update_time = NOW(),
                        title = COALESCE(title, $2)
                    WHERE id = $1
                    """,
                    session_id,
                    user_message[:100] + "..." if len(user_message) > 100 else user_message
                )

                logger.info(f"Saved conversation turn to session {session_id[:20]}")

        except Exception as e:
            logger.error(f"Failed to save conversation: {e}", exc_info=True)
            # Don't raise - conversation saving is not critical for streaming

    def _sanitize_text(self, text: str, max_length: int = 100000) -> str:
        """
        Sanitize text for safe storage.

        Args:
            text: Raw text
            max_length: Maximum character length

        Returns:
            Sanitized text
        """
        if not text:
            return ""

        # Remove null bytes
        text = text.replace('\x00', '')

        # Remove control characters except newlines/tabs
        text = ''.join(
            char for char in text
            if char in ('\n', '\t', '\r') or ord(char) >= 32
        )

        # Truncate if needed
        if len(text) > max_length:
            text = text[:max_length] + "\n\n[... Content truncated ...]"

        return text
