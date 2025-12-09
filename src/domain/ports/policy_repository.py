"""Port interface for policy repository."""

from abc import ABC, abstractmethod
from typing import List, Optional, Tuple
from uuid import UUID

from src.domain.models.policy_models import (
    Policy, PolicyDocument, PolicyVersion, PolicyAccess,
    Questionnaire, Question, QuestionAttempt,
    PolicyStatus, AccessLevel
)


class PolicyRepository(ABC):
    """Repository interface for policy management."""

    # ============================================
    # POLICY CRUD
    # ============================================

    @abstractmethod
    async def create_policy(
        self,
        owner_user_id: str,
        title: str,
        description: Optional[str] = None,
        access_level: AccessLevel = AccessLevel.PRIVATE,
        metadata: Optional[dict] = None
    ) -> Policy:
        """Create a new policy."""
        pass

    @abstractmethod
    async def get_policy_by_id(self, policy_id: UUID) -> Optional[Policy]:
        """Get policy by ID."""
        pass

    @abstractmethod
    async def update_policy(
        self,
        policy_id: UUID,
        title: Optional[str] = None,
        description: Optional[str] = None,
        content: Optional[str] = None,
        content_format: Optional[str] = None,
        status: Optional[PolicyStatus] = None,
        access_level: Optional[AccessLevel] = None,
        editing_session_id: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> Optional[Policy]:
        """Update policy fields."""
        pass

    @abstractmethod
    async def update_policy_artifacts(
        self,
        policy_id: UUID,
        pdf_blob_path: str,
        jpeg_blob_path: str
    ) -> Optional[Policy]:
        """Update generated artifact paths."""
        pass

    @abstractmethod
    async def increment_policy_version(
        self,
        policy_id: UUID,
        changed_by_user_id: str,
        change_summary: Optional[str] = None
    ) -> int:
        """Increment policy version and create snapshot."""
        pass

    @abstractmethod
    async def list_policies(
        self,
        owner_user_id: Optional[str] = None,
        status: Optional[PolicyStatus] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[Policy], int]:
        """List policies with pagination. Returns (policies, total_count)."""
        pass

    @abstractmethod
    async def get_accessible_policies(
        self,
        user_id: str,
        user_groups: List[str],
        status: Optional[PolicyStatus] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[Policy], int]:
        """Get policies user can access based on ownership and groups."""
        pass

    @abstractmethod
    async def delete_policy(self, policy_id: UUID) -> bool:
        """Delete policy (CASCADE deletes related data)."""
        pass

    # ============================================
    # POLICY DOCUMENTS
    # ============================================

    @abstractmethod
    async def add_policy_document(
        self,
        policy_id: UUID,
        filename: str,
        content_type: str,
        size_bytes: int,
        blob_path: str,
        gcs_uri: str,
        display_order: int = 0,
        metadata: Optional[dict] = None
    ) -> PolicyDocument:
        """Add source document to policy."""
        pass

    @abstractmethod
    async def get_policy_documents(self, policy_id: UUID) -> List[PolicyDocument]:
        """Get all documents for a policy."""
        pass

    @abstractmethod
    async def delete_policy_document(self, document_id: UUID) -> bool:
        """Delete a policy document."""
        pass

    # ============================================
    # POLICY VERSIONS
    # ============================================

    @abstractmethod
    async def get_policy_versions(
        self,
        policy_id: UUID,
        limit: int = 10
    ) -> List[PolicyVersion]:
        """Get version history for policy."""
        pass

    @abstractmethod
    async def get_policy_version(
        self,
        policy_id: UUID,
        version_number: int
    ) -> Optional[PolicyVersion]:
        """Get specific version."""
        pass

    # ============================================
    # ACCESS CONTROL
    # ============================================

    @abstractmethod
    async def grant_policy_access(
        self,
        policy_id: UUID,
        group_name: str,
        can_view: bool = True,
        can_edit: bool = False,
        can_approve: bool = False,
        granted_by_user_id: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> PolicyAccess:
        """Grant access to Entra ID group."""
        pass

    @abstractmethod
    async def revoke_policy_access(
        self,
        policy_id: UUID,
        group_name: str
    ) -> bool:
        """Revoke group access."""
        pass

    @abstractmethod
    async def get_policy_access_list(
        self,
        policy_id: UUID
    ) -> List[PolicyAccess]:
        """Get all access rules for policy."""
        pass

    @abstractmethod
    async def check_user_access(
        self,
        policy_id: UUID,
        user_id: str,
        user_groups: List[str]
    ) -> bool:
        """Check if user can access policy."""
        pass

    # ============================================
    # QUESTIONNAIRES
    # ============================================

    @abstractmethod
    async def create_questionnaire(
        self,
        policy_id: UUID,
        title: str,
        description: Optional[str] = None,
        pass_threshold_percentage: int = 70,
        metadata: Optional[dict] = None
    ) -> Questionnaire:
        """Create questionnaire for policy."""
        pass

    @abstractmethod
    async def get_questionnaire_by_policy(
        self,
        policy_id: UUID
    ) -> Optional[Questionnaire]:
        """Get questionnaire for policy."""
        pass

    @abstractmethod
    async def update_questionnaire(
        self,
        questionnaire_id: UUID,
        title: Optional[str] = None,
        description: Optional[str] = None,
        pass_threshold_percentage: Optional[int] = None,
        is_active: Optional[bool] = None
    ) -> Optional[Questionnaire]:
        """Update questionnaire."""
        pass

    # ============================================
    # QUESTIONS
    # ============================================

    @abstractmethod
    async def add_question(
        self,
        questionnaire_id: UUID,
        question_text: str,
        question_type: str,
        correct_answer: any,
        options: Optional[List[dict]] = None,
        explanation: Optional[str] = None,
        difficulty: Optional[str] = None,
        points: int = 1,
        display_order: int = 0,
        metadata: Optional[dict] = None
    ) -> Question:
        """Add question to questionnaire."""
        pass

    @abstractmethod
    async def update_question(
        self,
        question_id: UUID,
        question_text: Optional[str] = None,
        correct_answer: Optional[any] = None,
        options: Optional[List[dict]] = None,
        explanation: Optional[str] = None,
        difficulty: Optional[str] = None,
        points: Optional[int] = None
    ) -> Optional[Question]:
        """Update question."""
        pass

    @abstractmethod
    async def get_questions(
        self,
        questionnaire_id: UUID
    ) -> List[Question]:
        """Get all questions for questionnaire."""
        pass

    @abstractmethod
    async def delete_question(self, question_id: UUID) -> bool:
        """Delete question."""
        pass

    # ============================================
    # QUESTION ATTEMPTS (Analytics)
    # ============================================

    @abstractmethod
    async def record_attempt(
        self,
        question_id: UUID,
        user_id: str,
        user_answer: any,
        is_correct: bool,
        time_spent_seconds: Optional[int] = None
    ) -> QuestionAttempt:
        """Record user's answer attempt."""
        pass

    @abstractmethod
    async def get_user_attempts(
        self,
        user_id: str,
        questionnaire_id: Optional[UUID] = None,
        limit: int = 100
    ) -> List[QuestionAttempt]:
        """Get user's attempt history."""
        pass
