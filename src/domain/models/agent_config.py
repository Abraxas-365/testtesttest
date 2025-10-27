"""Domain models for agent configuration."""

from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum


class ModelType(str, Enum):
    """Supported model types."""
    GEMINI_2_5_FLASH = "gemini-2.5-flash"
    GEMINI_2_5_PRO = "gemini-2.5-pro"
    GEMINI_2_0_FLASH = "gemini-2.0-flash"
    GEMINI_1_5_PRO = "gemini-1.5-pro"
    GEMINI_1_5_FLASH = "gemini-1.5-flash"


@dataclass(frozen=True)
class ModelConfig:
    """Configuration for the AI model."""

    model_name: str
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    top_k: Optional[int] = None

    def __post_init__(self):
        """Validate model configuration."""
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError("Temperature must be between 0.0 and 2.0")
        if self.max_tokens is not None and self.max_tokens <= 0:
            raise ValueError("max_tokens must be positive")


@dataclass(frozen=True)
class ToolConfig:
    """Configuration for an agent tool."""

    tool_id: str
    tool_name: str
    tool_type: str  # 'function', 'builtin', 'third_party'
    function_name: Optional[str] = None  # For function tools
    parameters: dict[str, Any] = field(default_factory=dict)
    description: Optional[str] = None
    enabled: bool = True

    def __post_init__(self):
        """Validate tool configuration."""
        if self.tool_type not in ['function', 'builtin', 'third_party']:
            raise ValueError("tool_type must be 'function', 'builtin', or 'third_party'")


@dataclass(frozen=True)
class AgentConfig:
    """Configuration for an AI agent."""

    agent_id: str
    name: str
    model: ModelConfig
    instruction: str
    description: str
    tools: list[ToolConfig] = field(default_factory=list)
    sub_agent_ids: list[str] = field(default_factory=list)
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate agent configuration."""
        if not self.name:
            raise ValueError("Agent name cannot be empty")
        if not self.instruction:
            raise ValueError("Agent instruction cannot be empty")
