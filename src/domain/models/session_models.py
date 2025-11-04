"""Domain models for session and conversation history."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from enum import Enum


class SessionStatus(str, Enum):
    """Session status types."""
    ACTIVE = "active"
    CLOSED = "closed"
    ARCHIVED = "archived"


class MessageRole(str, Enum):
    """Message role types."""
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"
    TOOL = "tool"


@dataclass(frozen=True)
class Message:
    """Represents a message in a conversation."""

    message_id: str
    session_id: str
    role: str
    content: str
    tool_name: Optional[str] = None
    tool_call_id: Optional[str] = None
    tokens_used: Optional[int] = None
    model_used: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None

    def __post_init__(self):
        """Validate message."""
        valid_roles = [r.value for r in MessageRole]
        if self.role not in valid_roles:
            raise ValueError(f"role must be one of {valid_roles}")


@dataclass(frozen=True)
class Session:
    """Represents a conversation session."""

    session_id: str
    app_name: str
    user_id: str
    agent_id: Optional[str] = None
    title: Optional[str] = None
    status: str = "active"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_message_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None

    def __post_init__(self):
        """Validate session."""
        valid_statuses = [s.value for s in SessionStatus]
        if self.status not in valid_statuses:
            raise ValueError(f"status must be one of {valid_statuses}")
