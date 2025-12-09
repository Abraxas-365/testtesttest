"""Domain models for policy creation system."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
from uuid import UUID


class PolicyStatus(str, Enum):
    """Policy workflow states."""
    DRAFT = "draft"
    GENERATING = "generating"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class AccessLevel(str, Enum):
    """Policy access control levels."""
    PRIVATE = "private"
    GROUP = "group"
    ORGANIZATION = "organization"


class QuestionType(str, Enum):
    """Question types for questionnaires."""
    MULTIPLE_CHOICE = "multiple_choice"
    TRUE_FALSE = "true_false"
    MULTIPLE_SELECT = "multiple_select"
    SHORT_ANSWER = "short_answer"


class ContentFormat(str, Enum):
    """Policy content formats."""
    MARKDOWN = "markdown"
    HTML = "html"
    PLAIN = "plain"


@dataclass(frozen=True)
class Policy:
    """
    Core policy entity.

    Attributes:
        policy_id: Unique policy identifier
        owner_user_id: Azure AD Object ID of owner
        title: Policy title
        description: Policy description
        content: Policy content (markdown/HTML/plain)
        content_format: Format of content
        status: Current workflow status
        access_level: Access control level
        pdf_blob_path: GCS path to PDF artifact
        jpeg_blob_path: GCS path to JPEG artifact
        editing_session_id: Linked ADK session for editing
        metadata: Additional metadata
        version: Current version number
        created_at: Creation timestamp
        updated_at: Last update timestamp
        approved_at: Approval timestamp
        published_at: Publication timestamp
        archived_at: Archive timestamp
    """
    policy_id: UUID
    owner_user_id: str
    title: str
    description: Optional[str]
    content: Optional[str]
    content_format: ContentFormat
    status: PolicyStatus
    access_level: AccessLevel
    pdf_blob_path: Optional[str] = None
    jpeg_blob_path: Optional[str] = None
    editing_session_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    version: int = 1
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    archived_at: Optional[datetime] = None


@dataclass(frozen=True)
class PolicyDocument:
    """
    Source document for policy generation.

    Attributes:
        document_id: Unique document identifier
        policy_id: Parent policy ID
        filename: Original filename
        content_type: MIME type
        size_bytes: File size
        blob_path: GCS blob path
        gcs_uri: Full GCS URI
        display_order: Order for multi-doc policies
        metadata: Additional metadata
        uploaded_at: Upload timestamp
    """
    document_id: UUID
    policy_id: UUID
    filename: str
    content_type: str
    size_bytes: Optional[int]
    blob_path: str
    gcs_uri: str
    display_order: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    uploaded_at: Optional[datetime] = None


@dataclass(frozen=True)
class PolicyVersion:
    """
    Policy version snapshot for audit trail.

    Attributes:
        version_id: Unique version identifier
        policy_id: Parent policy ID
        version_number: Version number
        content: Snapshot of content
        content_format: Format of content
        status: Status at time of snapshot
        changed_by_user_id: User who made changes
        change_summary: Summary of changes
        metadata: Additional metadata
        created_at: Snapshot timestamp
    """
    version_id: UUID
    policy_id: UUID
    version_number: int
    content: str
    content_format: str
    status: PolicyStatus
    changed_by_user_id: str
    change_summary: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None


@dataclass(frozen=True)
class PolicyAccess:
    """
    Group-based access control for policies.

    Attributes:
        access_id: Unique access rule identifier
        policy_id: Parent policy ID
        group_name: Azure AD group name
        can_view: View permission
        can_edit: Edit permission
        can_approve: Approve permission
        metadata: Additional metadata
        granted_at: Grant timestamp
        granted_by_user_id: User who granted access
    """
    access_id: UUID
    policy_id: UUID
    group_name: str
    can_view: bool = True
    can_edit: bool = False
    can_approve: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    granted_at: Optional[datetime] = None
    granted_by_user_id: Optional[str] = None


@dataclass(frozen=True)
class Questionnaire:
    """
    Auto-generated questionnaire for policy validation.

    Attributes:
        questionnaire_id: Unique questionnaire identifier
        policy_id: Parent policy ID
        title: Questionnaire title
        description: Questionnaire description
        pass_threshold_percentage: Required score to pass
        randomize_questions: Randomize question order
        randomize_options: Randomize option order
        is_active: Whether questionnaire is active
        metadata: Additional metadata
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """
    questionnaire_id: UUID
    policy_id: UUID
    title: str
    description: Optional[str] = None
    pass_threshold_percentage: int = 70
    randomize_questions: bool = False
    randomize_options: bool = False
    is_active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass(frozen=True)
class Question:
    """
    Individual question in questionnaire.

    Attributes:
        question_id: Unique question identifier
        questionnaire_id: Parent questionnaire ID
        question_text: Question text
        question_type: Type of question
        correct_answer: Correct answer(s)
        options: Answer options (for multiple choice)
        explanation: Explanation shown after answering
        difficulty: Question difficulty level
        points: Points awarded for correct answer
        display_order: Display order in questionnaire
        generated_from_content: Reference to source content
        metadata: Additional metadata
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """
    question_id: UUID
    questionnaire_id: UUID
    question_text: str
    question_type: QuestionType
    correct_answer: Any  # JSON serializable
    options: Optional[List[Dict[str, str]]] = None
    explanation: Optional[str] = None
    difficulty: Optional[str] = None
    points: int = 1
    display_order: int = 0
    generated_from_content: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass(frozen=True)
class QuestionAttempt:
    """
    User answer attempt for analytics.

    Attributes:
        attempt_id: Unique attempt identifier
        question_id: Parent question ID
        user_id: User who attempted
        user_answer: User's answer
        is_correct: Whether answer was correct
        time_spent_seconds: Time spent on question
        attempted_at: Attempt timestamp
    """
    attempt_id: UUID
    question_id: UUID
    user_id: str
    user_answer: Any  # JSON serializable
    is_correct: bool
    time_spent_seconds: Optional[int] = None
    attempted_at: Optional[datetime] = None
