"""Text Editor Service for streaming AI responses with diff suggestions."""

import uuid
import logging
import asyncio
from typing import AsyncGenerator, Optional, List, Any

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.genai import types

from src.domain.models import (
    DocumentContext,
    AttachmentInfo,
    DiffSuggestion,
    StreamEvent,
)
from src.domain.services.agent_service import AgentService
from src.services.storage_service import StorageService
from src.services.diff_generator import DiffGenerator

logger = logging.getLogger(__name__)


# Text editor system instruction appended to agent instruction
TEXT_EDITOR_INSTRUCTION = """
You are an AI text editor assistant. When the user provides document content and asks for modifications:

1. Analyze the current document content carefully
2. When suggesting changes, format them as JSON diff blocks using this exact format:

```diff
{"type": "modification", "original": "original text", "new": "replacement text"}
```

3. For additions, use:
```diff
{"type": "addition", "position": "after: [context text]", "new": "text to add"}
```

4. For deletions, use:
```diff
{"type": "deletion", "original": "text to remove"}
```

5. Always explain your changes in natural language before or after the diff blocks
6. Be precise with the original text - it must match exactly for the diff to apply
7. Respond in the same language as the user message
8. When the user asks you to write or rewrite content, provide the full text without diff blocks
9. Only use diff blocks when making targeted modifications to existing text
"""


class TextEditorService:
    """
    Service for AI-powered text editing with streaming support.

    Integrates with the existing AgentService and ADK infrastructure
    to provide streaming responses with diff suggestions.
    """

    DEFAULT_AGENT_NAME = "text_editor_agent"

    def __init__(
        self,
        agent_service: AgentService,
        storage_service: Optional[StorageService] = None,
        diff_generator: Optional[DiffGenerator] = None,
    ):
        """
        Initialize the text editor service.

        Args:
            agent_service: The agent service for ADK integration
            storage_service: Optional storage service for fetching attachments
            diff_generator: Optional diff generator for parsing AI output
        """
        self.agent_service = agent_service
        self.storage_service = storage_service
        self.diff_generator = diff_generator or DiffGenerator()

    async def stream_response(
        self,
        message: str,
        user_id: str,
        document: Optional[DocumentContext] = None,
        attachments: Optional[List[AttachmentInfo]] = None,
        session_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        Stream AI response with content chunks and diff suggestions.

        This method:
        1. Builds context from document and attachments
        2. Creates/retrieves agent
        3. Streams response using runner.run_async()
        4. Parses content for diff suggestions
        5. Yields SSE-compatible events

        Args:
            message: The user's message/prompt
            user_id: Authenticated user ID
            document: Optional document context
            attachments: Optional list of attachments
            session_id: Optional session ID for conversation continuity
            agent_id: Optional specific agent ID (uses default if not provided)

        Yields:
            StreamEvent objects for SSE serialization
        """
        if not session_id:
            session_id = f"editor_{uuid.uuid4().hex[:12]}"

        try:
            # Get the text editor agent
            agent = await self._get_text_editor_agent(agent_id)
            if not agent:
                yield StreamEvent(
                    event_type="error",
                    data={"message": "Text editor agent not available"}
                )
                return

            # Build the prompt with context
            full_prompt = self._build_prompt(message, document)

            # Get the session service from agent_service
            session_service = self.agent_service.persistent_session_service
            if not session_service:
                yield StreamEvent(
                    event_type="error",
                    data={"message": "Session service not initialized"}
                )
                return

            # Create runner
            app_name = f"text_editor_{agent.name}"
            runner = Runner(
                agent=agent,
                app_name=app_name,
                session_service=session_service
            )

            # Build message parts
            parts = [types.Part(text=full_prompt)]

            # Add attachment content if available
            if attachments and self.storage_service:
                attachment_parts = await self._load_attachments(attachments)
                parts.extend(attachment_parts)

            # Create message
            content_message = types.Content(role="user", parts=parts)

            # Original document content for diff calculation
            original_content = document.content if document else ""

            # Stream the response with lock
            async with self.agent_service.lock_manager.get_lock(session_id):
                logger.info(f"Starting streaming for session {session_id[:20]}...")

                accumulated_text = ""
                last_processed_length = 0

                try:
                    async for event in runner.run_async(
                        user_id=user_id,
                        session_id=session_id,
                        new_message=content_message
                    ):
                        # Extract text content from event
                        chunk_text = self._extract_text_from_event(event)
                        if chunk_text:
                            accumulated_text += chunk_text

                            # Check for complete diff blocks periodically
                            if len(accumulated_text) - last_processed_length > 50:
                                diffs, remaining = self.diff_generator.extract_diffs(
                                    accumulated_text[last_processed_length:],
                                    original_content
                                )

                                # Yield any extracted diffs
                                for diff in diffs:
                                    yield StreamEvent(
                                        event_type="diff",
                                        data=diff.to_dict()
                                    )

                                # Yield clean content chunk
                                clean_chunk = self.diff_generator.remove_diff_blocks(chunk_text)
                                if clean_chunk.strip():
                                    yield StreamEvent(
                                        event_type="content",
                                        data={"content": clean_chunk}
                                    )

                                last_processed_length = len(accumulated_text)
                            else:
                                # For small chunks, just yield the content
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

            # Final processing - extract any remaining diffs
            final_diffs, _ = self.diff_generator.extract_diffs(
                accumulated_text,
                original_content
            )
            for diff in final_diffs:
                yield StreamEvent(
                    event_type="diff",
                    data=diff.to_dict()
                )

            # Signal completion
            logger.info(f"Stream completed for session {session_id}")
            yield StreamEvent(
                event_type="done",
                data={"session_id": session_id}
            )

        except Exception as e:
            logger.error(f"Stream error: {e}", exc_info=True)
            yield StreamEvent(
                event_type="error",
                data={"message": str(e)}
            )

    async def get_non_streaming_response(
        self,
        message: str,
        user_id: str,
        document: Optional[DocumentContext] = None,
        attachments: Optional[List[AttachmentInfo]] = None,
        session_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> tuple[str, List[DiffSuggestion], str]:
        """
        Get a non-streaming response from the AI.

        Args:
            message: The user's message/prompt
            user_id: Authenticated user ID
            document: Optional document context
            attachments: Optional list of attachments
            session_id: Optional session ID
            agent_id: Optional specific agent ID

        Returns:
            Tuple of (content, list of diffs, session_id)
        """
        full_content = ""
        all_diffs = []
        result_session_id = session_id or f"editor_{uuid.uuid4().hex[:12]}"

        async for event in self.stream_response(
            message=message,
            user_id=user_id,
            document=document,
            attachments=attachments,
            session_id=result_session_id,
            agent_id=agent_id,
        ):
            if event.event_type == "content":
                full_content += event.data.get("content", "")
            elif event.event_type == "diff":
                all_diffs.append(DiffSuggestion(
                    id=event.data["id"],
                    type=event.data["type"],
                    original_text=event.data["originalText"],
                    new_text=event.data["newText"],
                    start_index=event.data["startIndex"],
                    end_index=event.data["endIndex"],
                ))
            elif event.event_type == "done":
                result_session_id = event.data.get("session_id", result_session_id)
            elif event.event_type == "error":
                raise RuntimeError(event.data.get("message", "Unknown error"))

        # Clean up the content (remove diff blocks)
        clean_content = self.diff_generator.remove_diff_blocks(full_content)

        return clean_content, all_diffs, result_session_id

    async def _get_text_editor_agent(
        self, agent_id: Optional[str] = None
    ) -> Optional[Agent]:
        """Get or create a text editor agent."""
        if agent_id:
            return await self.agent_service.get_agent(agent_id)

        # Try to get by name first
        agent = await self.agent_service.get_agent_by_name(self.DEFAULT_AGENT_NAME)
        if agent:
            return agent

        # Fall back to first available agent
        logger.warning(
            f"Text editor agent '{self.DEFAULT_AGENT_NAME}' not found, "
            "using first available agent"
        )
        agents = await self.agent_service.list_agents(enabled_only=True)
        return agents[0] if agents else None

    def _build_prompt(
        self,
        message: str,
        document: Optional[DocumentContext] = None
    ) -> str:
        """Build the full prompt with document context."""
        parts = [TEXT_EDITOR_INSTRUCTION, "\n\n"]

        if document and document.content:
            parts.append("=== CURRENT DOCUMENT ===\n")
            if document.title:
                parts.append(f"Title: {document.title}\n")
            parts.append(f"\n{document.content}\n")
            parts.append("=== END DOCUMENT ===\n\n")

        parts.append(f"User Request: {message}")

        return "".join(parts)

    async def _load_attachments(
        self,
        attachments: List[AttachmentInfo]
    ) -> List[types.Part]:
        """Load attachment content and create message parts."""
        parts = []

        for attachment in attachments:
            try:
                if attachment.blob_path and self.storage_service:
                    # Fetch from GCS
                    content = await asyncio.to_thread(
                        self.storage_service.get_document_bytes,
                        attachment.blob_path
                    )
                    if content:
                        parts.append(types.Part(
                            inline_data=types.Blob(
                                mime_type=attachment.mime_type,
                                data=content
                            )
                        ))
                        parts.append(types.Part(
                            text=f"\n[Attachment: {attachment.name}]\n"
                        ))
                        logger.info(f"Loaded attachment: {attachment.name}")
            except Exception as e:
                logger.warning(f"Failed to load attachment {attachment.name}: {e}")

        return parts

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
