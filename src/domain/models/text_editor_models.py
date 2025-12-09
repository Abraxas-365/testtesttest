"""Domain models for AI Text Editor."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Any, Dict
from enum import Enum


class DiffType(str, Enum):
    """Types of text modifications."""
    ADDITION = "addition"
    DELETION = "deletion"
    MODIFICATION = "modification"


@dataclass(frozen=True)
class DiffSuggestion:
    """
    A single diff suggestion for document modification.

    Represents a proposed change to the document content with
    precise location information for applying the change.
    """
    id: str
    type: DiffType
    original_text: str
    new_text: str
    start_index: int
    end_index: int

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with camelCase keys for API response."""
        return {
            "id": self.id,
            "type": self.type.value,
            "originalText": self.original_text,
            "newText": self.new_text,
            "startIndex": self.start_index,
            "endIndex": self.end_index,
        }


@dataclass(frozen=True)
class AttachmentInfo:
    """
    Reference to an uploaded attachment.

    Contains metadata about a file attachment that can be
    included in AI processing requests.
    """
    id: str
    url: str
    name: str
    mime_type: str
    size: int
    blob_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with camelCase keys for API response."""
        return {
            "id": self.id,
            "url": self.url,
            "name": self.name,
            "mimeType": self.mime_type,
            "size": self.size,
            "blobPath": self.blob_path,
        }


@dataclass
class DocumentContext:
    """
    Current document state for context in AI requests.

    Provides the AI with information about the document
    being edited including its content and metadata.
    """
    id: Optional[str] = None
    content: str = ""
    title: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with camelCase keys."""
        return {
            "id": self.id,
            "content": self.content,
            "title": self.title,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }


@dataclass
class EditorDocument:
    """
    Persisted document for the text editor.

    Represents a document stored in the database with
    full content and metadata for persistence.
    """
    document_id: str
    user_id: str
    title: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with camelCase keys for API response."""
        return {
            "id": self.document_id,
            "title": self.title,
            "content": self.content,
            "metadata": self.metadata,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }

    def to_document_context(self) -> DocumentContext:
        """Convert to DocumentContext for AI requests."""
        return DocumentContext(
            id=self.document_id,
            content=self.content,
            title=self.title,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


@dataclass
class StreamEvent:
    """
    Represents an SSE event for streaming responses.

    Used internally to structure events before
    serialization to SSE format.
    """
    event_type: str  # "content", "diff", "error", "done", "cancelled"
    data: Any

    def to_sse(self) -> str:
        """Convert to SSE format string."""
        import json

        if self.event_type == "content":
            return f"data: {json.dumps(self.data)}\n\n"
        elif self.event_type == "diff":
            return f"data: {json.dumps({'diff': self.data})}\n\n"
        elif self.event_type == "session":
            return f"data: {json.dumps({'session': self.data})}\n\n"
        elif self.event_type == "done":
            return "data: [DONE]\n\n"
        elif self.event_type == "cancelled":
            return "data: [CANCELLED]\n\n"
        elif self.event_type == "error":
            return f"data: {json.dumps({'error': self.data})}\n\n"
        else:
            return f"data: {json.dumps(self.data)}\n\n"
