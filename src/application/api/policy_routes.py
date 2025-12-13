"""RESTful Policy API for policy creation and management."""

import logging
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Any, Optional, List
from uuid import UUID
from pydantic import BaseModel, Field

from src.middleware.rbac import require_permission
from src.domain.models.rbac_models import UserRBAC
from src.application.di import get_container
from src.domain.services.policy_service import PolicyService
from src.domain.services.policy_generation_service import PolicyGenerationService
from src.domain.services.questionnaire_service import QuestionnaireService
from src.domain.models.policy_models import PolicyStatus, AccessLevel

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================
# PYDANTIC MODELS (Request/Response)
# ============================================

class CreatePolicyRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = None
    access_level: str = Field(default="private")


class UpdatePolicyRequest(BaseModel):
    title: Optional[str] = Field(None, max_length=500)
    description: Optional[str] = None
    content: Optional[str] = None
    content_format: Optional[str] = None


class GrantAccessRequest(BaseModel):
    group_name: str
    can_view: bool = True
    can_edit: bool = False
    can_approve: bool = False


class GenerateQuestionnaireRequest(BaseModel):
    num_questions: int = Field(default=5, ge=1, le=20)


class UpdateCorrectAnswerRequest(BaseModel):
    correct_answer: Any


# ============================================
# DEPENDENCY INJECTION
# ============================================

async def get_policy_service() -> PolicyService:
    """Get PolicyService from DI container."""
    container = get_container()
    return await container.get_policy_service()


async def get_generation_service() -> PolicyGenerationService:
    """Get PolicyGenerationService from DI container."""
    container = get_container()
    return await container.get_policy_generation_service()


async def get_questionnaire_service() -> QuestionnaireService:
    """Get QuestionnaireService from DI container."""
    container = get_container()
    return await container.get_questionnaire_service()


def get_user_groups(user: UserRBAC) -> List[str]:
    """Extract user groups from RBAC context."""
    return user.entra_groups


# ============================================
# POLICY CRUD ENDPOINTS
# ============================================

@router.post("/policies")
async def create_policy(
    request: CreatePolicyRequest,
    user: UserRBAC = Depends(require_permission("policies:create")),
    policy_service: PolicyService = Depends(get_policy_service)
):
    """
    Create a new policy.

    **Authentication:** Required
    **Authorization:** Requires policies:create permission

    **Request Body:**
    - title: Policy title (required)
    - description: Policy description (optional)
    - access_level: 'private', 'group', or 'organization' (default: private)
    """
    user_id = user.user_id

    try:
        access_level = AccessLevel(request.access_level)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid access_level. Must be one of: private, group, organization"
        )

    policy = await policy_service.create_policy(
        owner_user_id=user_id,
        title=request.title,
        description=request.description,
        access_level=access_level
    )

    return {
        "policy_id": str(policy.policy_id),
        "title": policy.title,
        "status": policy.status.value,
        "access_level": policy.access_level.value,
        "created_at": policy.created_at.isoformat() if policy.created_at else None
    }


@router.get("/policies")
async def list_policies(
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: UserRBAC = Depends(require_permission("policies:list")),
    policy_service: PolicyService = Depends(get_policy_service)
):
    """
    List policies accessible by current user.

    **Authentication:** Required
    **Authorization:** Requires policies:list permission

    **Query Parameters:**
    - status: Filter by status (optional)
    - page: Page number (default: 1)
    - page_size: Items per page (default: 20, max: 100)
    """
    user_id = user.user_id
    user_groups = get_user_groups(user)

    status_filter = None
    if status:
        try:
            status_filter = PolicyStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status. Must be one of: draft, generating, in_review, approved, published, archived"
            )

    policies, total, has_more = await policy_service.list_policies_for_user(
        user_id=user_id,
        user_groups=user_groups,
        status=status_filter,
        page=page,
        page_size=page_size
    )

    return {
        "policies": [
            {
                "policy_id": str(p.policy_id),
                "title": p.title,
                "description": p.description,
                "status": p.status.value,
                "access_level": p.access_level.value,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None
            }
            for p in policies
        ],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "has_more": has_more
        }
    }


@router.get("/policies/{policy_id}")
async def get_policy(
    policy_id: UUID,
    user: UserRBAC = Depends(require_permission("policies:view")),
    policy_service: PolicyService = Depends(get_policy_service)
):
    """
    Get policy details by ID.

    **Authentication:** Required
    **Authorization:** Requires policies:view permission and access to the policy
    """
    user_id = user.user_id
    user_groups = get_user_groups(user)

    policy = await policy_service.get_policy_with_access_check(
        policy_id=policy_id,
        user_id=user_id,
        user_groups=user_groups
    )

    return {
        "policy_id": str(policy.policy_id),
        "title": policy.title,
        "description": policy.description,
        "content": policy.content,
        "content_format": policy.content_format.value,
        "status": policy.status.value,
        "access_level": policy.access_level.value,
        "version": policy.version,
        "pdf_blob_path": policy.pdf_blob_path,
        "jpeg_blob_path": policy.jpeg_blob_path,
        "owner_user_id": policy.owner_user_id,
        "created_at": policy.created_at.isoformat() if policy.created_at else None,
        "updated_at": policy.updated_at.isoformat() if policy.updated_at else None,
        "approved_at": policy.approved_at.isoformat() if policy.approved_at else None,
        "published_at": policy.published_at.isoformat() if policy.published_at else None
    }


@router.put("/policies/{policy_id}")
async def update_policy(
    policy_id: UUID,
    request: UpdatePolicyRequest,
    user: UserRBAC = Depends(require_permission("policies:edit")),
    policy_service: PolicyService = Depends(get_policy_service)
):
    """
    Update policy metadata or content.

    **Authentication:** Required
    **Authorization:** Requires policies:edit permission
    """
    user_id = user.user_id
    user_groups = get_user_groups(user)

    if request.content:
        # Update content (requires edit permission)
        policy = await policy_service.update_policy_content(
            policy_id=policy_id,
            user_id=user_id,
            user_groups=user_groups,
            content=request.content,
            content_format=request.content_format or "markdown"
        )
    else:
        # Update metadata only (owner only)
        existing_policy = await policy_service.get_policy_with_access_check(
            policy_id=policy_id,
            user_id=user_id,
            user_groups=user_groups
        )

        if existing_policy.owner_user_id != user_id:
            raise HTTPException(status_code=403, detail="Only owner can update metadata")

        from src.domain.ports.policy_repository import PolicyRepository
        container = get_container()
        repo = await container.init_policy_repository()

        policy = await repo.update_policy(
            policy_id=policy_id,
            title=request.title,
            description=request.description
        )

    return {
        "policy_id": str(policy.policy_id),
        "title": policy.title,
        "status": policy.status.value,
        "updated_at": policy.updated_at.isoformat() if policy.updated_at else None
    }


@router.post("/policies/{policy_id}/approve")
async def approve_policy(
    policy_id: UUID,
    user: UserRBAC = Depends(require_permission("policies:edit")),
    policy_service: PolicyService = Depends(get_policy_service)
):
    """
    Approve policy for publication.

    **Authentication:** Required
    **Authorization:** Requires policies:edit permission
    """
    user_id = user.user_id
    user_groups = get_user_groups(user)

    policy = await policy_service.approve_policy(
        policy_id=policy_id,
        user_id=user_id,
        user_groups=user_groups
    )

    return {
        "policy_id": str(policy.policy_id),
        "status": policy.status.value,
        "approved_at": policy.approved_at.isoformat() if policy.approved_at else None
    }


@router.post("/policies/{policy_id}/publish")
async def publish_policy(
    policy_id: UUID,
    user: UserRBAC = Depends(require_permission("policies:publish")),
    generation_service: PolicyGenerationService = Depends(get_generation_service)
):
    """
    Generate PDF/JPEG artifacts and publish policy.

    **Authentication:** Required
    **Authorization:** Requires policies:publish permission
    """
    user_id = user.user_id

    pdf_uri, jpeg_uri = await generation_service.generate_and_publish_policy(
        policy_id=policy_id,
        user_id=user_id
    )

    return {
        "policy_id": str(policy_id),
        "status": "published",
        "pdf_uri": pdf_uri,
        "jpeg_uri": jpeg_uri
    }


@router.get("/policies/{policy_id}/download/{format}")
async def download_policy(
    policy_id: UUID,
    format: str,
    user: UserRBAC = Depends(require_permission("policies:view")),
    generation_service: PolicyGenerationService = Depends(get_generation_service)
):
    """
    Get presigned download URL for policy artifact.

    **Authentication:** Required
    **Authorization:** Requires policies:view permission
    **Path Parameters:**
    - format: 'pdf' or 'jpeg'
    """
    user_id = user.user_id
    user_groups = get_user_groups(user)

    download_url = await generation_service.generate_download_url(
        policy_id=policy_id,
        format=format,
        user_id=user_id,
        user_groups=user_groups,
        expiration_minutes=60
    )

    return {
        "download_url": download_url,
        "expires_in_minutes": 60
    }


# ============================================
# ACCESS CONTROL ENDPOINTS
# ============================================

@router.post("/policies/{policy_id}/access")
async def grant_access(
    policy_id: UUID,
    request: GrantAccessRequest,
    user: UserRBAC = Depends(require_permission("policies:share")),
    policy_service: PolicyService = Depends(get_policy_service)
):
    """
    Grant Entra ID group access to policy.

    **Authentication:** Required
    **Authorization:** Requires policies:share permission
    """
    user_id = user.user_id

    access = await policy_service.grant_group_access(
        policy_id=policy_id,
        user_id=user_id,
        group_name=request.group_name,
        can_view=request.can_view,
        can_edit=request.can_edit,
        can_approve=request.can_approve
    )

    return {
        "access_id": str(access.access_id),
        "policy_id": str(access.policy_id),
        "group_name": access.group_name,
        "can_view": access.can_view,
        "can_edit": access.can_edit,
        "can_approve": access.can_approve
    }


@router.delete("/policies/{policy_id}/access/{group_name}")
async def revoke_access(
    policy_id: UUID,
    group_name: str,
    user: UserRBAC = Depends(require_permission("policies:share")),
    policy_service: PolicyService = Depends(get_policy_service)
):
    """
    Revoke group access to policy.

    **Authentication:** Required
    **Authorization:** Requires policies:share permission
    """
    user_id = user.user_id

    result = await policy_service.revoke_group_access(
        policy_id=policy_id,
        user_id=user_id,
        group_name=group_name
    )

    return {"success": result}


@router.get("/policies/{policy_id}/access")
async def list_access_rules(
    policy_id: UUID,
    user: UserRBAC = Depends(require_permission("policies:view")),
    policy_service: PolicyService = Depends(get_policy_service)
):
    """
    Get access rules for policy.

    **Authentication:** Required
    **Authorization:** Requires policies:view permission
    """
    user_id = user.user_id

    access_list = await policy_service.get_policy_access_list(
        policy_id=policy_id,
        user_id=user_id
    )

    return {
        "access_rules": [
            {
                "access_id": str(a.access_id),
                "group_name": a.group_name,
                "can_view": a.can_view,
                "can_edit": a.can_edit,
                "can_approve": a.can_approve,
                "granted_at": a.granted_at.isoformat() if a.granted_at else None
            }
            for a in access_list
        ]
    }


# ============================================
# QUESTIONNAIRE ENDPOINTS
# ============================================

@router.post("/policies/{policy_id}/questionnaire")
async def generate_questionnaire(
    policy_id: UUID,
    request: GenerateQuestionnaireRequest,
    user: UserRBAC = Depends(require_permission("policies:edit")),
    questionnaire_service: QuestionnaireService = Depends(get_questionnaire_service)
):
    """
    Generate questionnaire from policy content.

    **Authentication:** Required
    **Authorization:** Requires policies:edit permission
    """
    user_id = user.user_id

    questionnaire = await questionnaire_service.generate_questionnaire(
        policy_id=policy_id,
        user_id=user_id,
        num_questions=request.num_questions
    )

    return {
        "questionnaire_id": str(questionnaire.questionnaire_id),
        "title": questionnaire.title,
        "pass_threshold_percentage": questionnaire.pass_threshold_percentage
    }


@router.get("/policies/{policy_id}/questionnaire")
async def get_questionnaire(
    policy_id: UUID,
    user: UserRBAC = Depends(require_permission("policies:view"))
):
    """
    Get questionnaire for policy.

    **Authentication:** Required
    **Authorization:** Requires policies:view permission
    """
    user_id = user.user_id
    container = get_container()
    repo = await container.init_policy_repository()

    questionnaire = await repo.get_questionnaire_by_policy(policy_id)
    if not questionnaire:
        raise HTTPException(status_code=404, detail="Questionnaire not found")

    questions = await repo.get_questions(questionnaire.questionnaire_id)

    return {
        "questionnaire_id": str(questionnaire.questionnaire_id),
        "title": questionnaire.title,
        "description": questionnaire.description,
        "pass_threshold_percentage": questionnaire.pass_threshold_percentage,
        "questions": [
            {
                "question_id": str(q.question_id),
                "question_text": q.question_text,
                "question_type": q.question_type.value,
                "options": q.options,
                "explanation": q.explanation,
                "difficulty": q.difficulty,
                "points": q.points
            }
            for q in questions
        ]
    }


@router.put("/policies/{policy_id}/questionnaire/questions/{question_id}")
async def update_question(
    policy_id: UUID,
    question_id: UUID,
    request: UpdateCorrectAnswerRequest,
    user: UserRBAC = Depends(require_permission("policies:edit")),
    questionnaire_service: QuestionnaireService = Depends(get_questionnaire_service)
):
    """
    Update correct answer for a question (user validation).

    **Authentication:** Required
    **Authorization:** Requires policies:edit permission
    """
    user_id = user.user_id

    question = await questionnaire_service.update_correct_answer(
        question_id=question_id,
        user_id=user_id,
        correct_answer=request.correct_answer
    )

    return {
        "question_id": str(question.question_id),
        "correct_answer": question.correct_answer
    }
