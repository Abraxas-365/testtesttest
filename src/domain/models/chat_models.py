"""Pydantic models for chat API request and response."""

from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime


# ============================================
# REQUEST MODELS
# ============================================

class ChatMessageRequest(BaseModel):
    """Send a chat message (auto-create session if needed)."""
    prompt: str = Field(..., min_length=1, max_length=10000, description="User's message")
    agent_id: Optional[str] = Field(None, description="Specific agent ID to use")
    agent_name: Optional[str] = Field(None, description="Agent name (alternative to agent_id)")
    metadata: Optional[dict] = Field(default_factory=dict, description="Additional context metadata")

    @validator('prompt')
    def validate_prompt(cls, v):
        """Ensure prompt is not empty after stripping whitespace."""
        if not v.strip():
            raise ValueError("Prompt cannot be empty")
        return v.strip()

    @validator('agent_id', 'agent_name')
    def validate_agent_selection(cls, v, values):
        """Ensure not both agent_id and agent_name are provided."""
        if v and 'agent_id' in values and values.get('agent_id') and 'agent_name' in values and values.get('agent_name'):
            raise ValueError("Provide either agent_id or agent_name, not both")
        return v


class SessionMessageRequest(BaseModel):
    """Send message to existing session (agent already determined)."""
    prompt: str = Field(..., min_length=1, max_length=10000, description="User's message")
    metadata: Optional[dict] = Field(default_factory=dict, description="Additional context metadata")

    @validator('prompt')
    def validate_prompt(cls, v):
        """Ensure prompt is not empty after stripping whitespace."""
        if not v.strip():
            raise ValueError("Prompt cannot be empty")
        return v.strip()


# ============================================
# RESPONSE MODELS
# ============================================

class MessageResponse(BaseModel):
    """Single message in conversation."""
    message_id: str = Field(..., description="Unique message identifier")
    session_id: str = Field(..., description="Session this message belongs to")
    role: str = Field(..., description="Message role: 'user', 'agent', or 'system'")
    content: str = Field(..., description="Message text content")
    agent_id: Optional[str] = Field(None, description="Agent that sent this message")
    agent_name: Optional[str] = Field(None, description="Human-readable agent name")
    metadata: Optional[dict] = Field(None, description="Tool calls, citations, etc.")
    created_at: datetime = Field(..., description="When the message was created")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ChatResponse(BaseModel):
    """Response from chat endpoint."""
    message: MessageResponse = Field(..., description="The agent's response message")
    session_id: str = Field(..., description="Session ID for subsequent messages")
    agent_id: str = Field(..., description="Agent handling this conversation")
    agent_name: str = Field(..., description="Display name of the agent")
    agent_area: Optional[str] = Field(None, description="Agent's area (e.g., 'legal', 'finance')")


class SessionListItem(BaseModel):
    """Session summary in list view."""
    session_id: str = Field(..., description="Unique session identifier")
    agent_id: Optional[str] = Field(None, description="Agent for this session")
    agent_name: Optional[str] = Field(None, description="Display name of agent")
    title: Optional[str] = Field(None, description="Session title (first message preview)")
    status: str = Field(..., description="Session status: 'active', 'closed', 'archived'")
    message_count: int = Field(..., description="Total number of messages in session")
    created_at: datetime = Field(..., description="When session was created")
    last_message_at: Optional[datetime] = Field(None, description="When last message was sent")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class SessionListResponse(BaseModel):
    """Paginated list of sessions."""
    sessions: List[SessionListItem] = Field(..., description="List of sessions for current page")
    total: int = Field(..., description="Total number of sessions (all pages)")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of items per page")
    has_more: bool = Field(..., description="Whether there are more pages")


class SessionDetailResponse(BaseModel):
    """Full session with message history."""
    session_id: str = Field(..., description="Unique session identifier")
    agent_id: Optional[str] = Field(None, description="Agent for this session")
    agent_name: Optional[str] = Field(None, description="Display name of agent")
    user_id: str = Field(..., description="User who owns this session")
    status: str = Field(..., description="Session status")
    title: Optional[str] = Field(None, description="Session title")
    created_at: datetime = Field(..., description="When session was created")
    last_message_at: Optional[datetime] = Field(None, description="When last message was sent")
    messages: List[MessageResponse] = Field(..., description="Full conversation history")
    total_messages: int = Field(..., description="Total number of messages")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
