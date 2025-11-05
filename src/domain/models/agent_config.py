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


class AgentType(str, Enum):
    """Agent types."""
    ASSISTANT = "assistant"
    COORDINATOR = "coordinator"
    SPECIALIST = "specialist"
    RAG = "rag"
    TOOL = "tool"


class AreaType(str, Enum):
    """
    Agent area/domain types.

    Note: area_type is now flexible and can match any Azure AD group name.
    These are common examples, but not restricted to this list.
    """
    GENERAL = "general"
    MARKETING = "marketing"
    LEGAL = "legal"
    DEVELOPER = "developer"
    OPERATIONS = "operations"
    SALES = "sales"
    CUSTOMER_SUPPORT = "customer_support"
    FINANCE = "finance"
    HR = "hr"
    DATA_ANALYSIS = "data_analysis"


class VectorDBType(str, Enum):
    """Supported vector database types."""
    VERTEX_RAG = "vertex_rag"
    QDRANT = "qdrant"
    PINECONE = "pinecone"
    WEAVIATE = "weaviate"


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
class CorpusConfig:
    """Configuration for a RAG corpus."""

    corpus_id: str
    corpus_name: str
    display_name: str
    description: Optional[str] = None
    vertex_corpus_name: Optional[str] = None
    embedding_model: str = "text-embedding-005"
    vector_db_type: str = "vertex_rag"
    vector_db_config: dict[str, Any] = field(default_factory=dict)
    document_count: int = 0
    chunk_size: int = 1000
    chunk_overlap: int = 200
    priority: int = 1  # Priority when assigned to an agent
    metadata: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True

    def __post_init__(self):
        """Validate corpus configuration."""
        if not self.corpus_name:
            raise ValueError("Corpus name cannot be empty")
        if self.chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if self.chunk_overlap < 0:
            raise ValueError("chunk_overlap cannot be negative")


@dataclass(frozen=True)
class ToolConfig:
    """Configuration for an agent tool."""

    tool_id: str
    tool_name: str
    tool_type: str  # 'function', 'builtin', 'third_party', 'rag', 'agent'
    function_name: Optional[str] = None  # For function tools
    parameters: dict[str, Any] = field(default_factory=dict)
    description: Optional[str] = None
    enabled: bool = True

    def __post_init__(self):
        """Validate tool configuration."""
        valid_types = ['function', 'builtin', 'third_party', 'rag', 'agent']
        if self.tool_type not in valid_types:
            raise ValueError(f"tool_type must be one of {valid_types}")


@dataclass(frozen=True)
class AgentConfig:
    """Configuration for an AI agent."""

    agent_id: str
    name: str
    model: ModelConfig
    instruction: str
    description: str
    agent_type: str = "assistant"
    area_type: str = "general"
    tools: list[ToolConfig] = field(default_factory=list)
    corpuses: list[CorpusConfig] = field(default_factory=list)
    sub_agent_ids: list[str] = field(default_factory=list)
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate agent configuration."""
        if not self.name:
            raise ValueError("Agent name cannot be empty")
        if not self.instruction:
            raise ValueError("Agent instruction cannot be empty")

        # Validate agent_type
        valid_agent_types = [t.value for t in AgentType]
        if self.agent_type not in valid_agent_types:
            raise ValueError(f"agent_type must be one of {valid_agent_types}")

        # Validate area_type
        valid_area_types = [t.value for t in AreaType]
        if self.area_type not in valid_area_types:
            raise ValueError(f"area_type must be one of {valid_area_types}")
