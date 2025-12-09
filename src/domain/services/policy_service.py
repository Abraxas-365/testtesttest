"""Business logic for policy lifecycle management."""

from typing import Optional, List, Tuple
from uuid import UUID
import logging

from src.domain.ports.policy_repository import PolicyRepository
from src.domain.models.policy_models import (
    Policy, PolicyDocument, PolicyVersion, PolicyAccess,
    PolicyStatus, AccessLevel
)
from src.services.storage_service import StorageService
from fastapi import HTTPException

logger = logging.getLogger(__name__)


class PolicyService:
    """Service for policy lifecycle orchestration."""

    def __init__(
        self,
        repository: PolicyRepository,
        storage_service: StorageService
    ):
        self.repository = repository
        self.storage = storage_service

    async def create_policy(
        self,
        owner_user_id: str,
        title: str,
        description: Optional[str] = None,
        access_level: AccessLevel = AccessLevel.PRIVATE,
        metadata: Optional[dict] = None
    ) -> Policy:
        """
        Create a new policy.

        Args:
            owner_user_id: Azure AD Object ID of owner
            title: Policy title
            description: Policy description
            access_level: Access control level
            metadata: Additional metadata

        Returns:
            Created policy
        """
        logger.info(f"Creating policy: {title} for user {owner_user_id}")

        policy = await self.repository.create_policy(
            owner_user_id=owner_user_id,
            title=title,
            description=description,
            access_level=access_level,
            metadata=metadata
        )

        logger.info(f"Policy created: {policy.policy_id}")
        return policy

    async def upload_source_document(
        self,
        policy_id: UUID,
        user_id: str,
        filename: str,
        content_type: str
    ) -> dict:
        """
        Generate presigned URL for document upload.

        Args:
            policy_id: Target policy ID
            user_id: User uploading document
            filename: Original filename
            content_type: MIME type

        Returns:
            Upload URL and metadata
        """
        # Verify policy exists and user owns it
        policy = await self.repository.get_policy_by_id(policy_id)
        if not policy:
            raise HTTPException(status_code=404, detail="Policy not found")

        if policy.owner_user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied")

        # Generate presigned URL with policy-specific path
        upload_info = self.storage.generate_presigned_upload_url(
            user_id=user_id,
            filename=filename,
            content_type=content_type,
            expiration_minutes=15
        )

        logger.info(f"Generated upload URL for policy {policy_id}, document {upload_info['document_id']}")

        return {
            **upload_info,
            "policy_id": str(policy_id)
        }

    async def confirm_document_upload(
        self,
        policy_id: UUID,
        document_id: str,
        filename: str,
        content_type: str,
        size_bytes: int,
        blob_path: str,
        gcs_uri: str,
        display_order: int = 0
    ) -> PolicyDocument:
        """
        Confirm document upload and link to policy.

        Args:
            policy_id: Parent policy ID
            document_id: Document identifier
            filename: Original filename
            content_type: MIME type
            size_bytes: File size
            blob_path: GCS blob path
            gcs_uri: Full GCS URI
            display_order: Display order

        Returns:
            Created policy document
        """
        # Verify document exists in GCS
        verification = self.storage.verify_upload(blob_path)
        if not verification or not verification.get("exists"):
            raise HTTPException(
                status_code=400,
                detail="Document upload not found. Please retry upload."
            )

        # Add to policy
        doc = await self.repository.add_policy_document(
            policy_id=policy_id,
            filename=filename,
            content_type=content_type,
            size_bytes=size_bytes,
            blob_path=blob_path,
            gcs_uri=gcs_uri,
            display_order=display_order
        )

        logger.info(f"Document {document_id} linked to policy {policy_id}")
        return doc

    async def get_policy_documents(
        self,
        policy_id: UUID,
        user_id: str,
        user_groups: List[str]
    ) -> List[PolicyDocument]:
        """
        Get all documents for a policy (with access check).

        Args:
            policy_id: Policy ID
            user_id: Requesting user ID
            user_groups: User's Azure AD groups

        Returns:
            List of policy documents
        """
        # Check access
        has_access = await self.repository.check_user_access(
            policy_id=policy_id,
            user_id=user_id,
            user_groups=user_groups
        )

        if not has_access:
            raise HTTPException(status_code=403, detail="Access denied")

        return await self.repository.get_policy_documents(policy_id)

    async def update_policy_content(
        self,
        policy_id: UUID,
        user_id: str,
        user_groups: List[str],
        content: str,
        content_format: str = "markdown",
        create_version_snapshot: bool = True
    ) -> Policy:
        """
        Update policy content (typically from conversational editing).

        Args:
            policy_id: Policy ID
            user_id: User making changes
            user_groups: User's Azure AD groups
            content: New content
            content_format: Content format
            create_version_snapshot: Whether to create version snapshot

        Returns:
            Updated policy
        """
        # Verify user has edit access
        policy = await self.repository.get_policy_by_id(policy_id)
        if not policy:
            raise HTTPException(status_code=404, detail="Policy not found")

        # Owner or users with edit permission
        if policy.owner_user_id != user_id:
            access_list = await self.repository.get_policy_access_list(policy_id)
            user_has_edit = any(
                a.group_name in user_groups and a.can_edit
                for a in access_list
            )
            if not user_has_edit:
                raise HTTPException(status_code=403, detail="Edit access denied")

        # Create version snapshot if requested
        if create_version_snapshot:
            await self.repository.increment_policy_version(
                policy_id=policy_id,
                changed_by_user_id=user_id,
                change_summary="Content updated via conversational editing"
            )

        # Update content
        updated_policy = await self.repository.update_policy(
            policy_id=policy_id,
            content=content,
            content_format=content_format,
            status=PolicyStatus.IN_REVIEW
        )

        logger.info(f"Policy {policy_id} content updated by user {user_id}")
        return updated_policy

    async def approve_policy(
        self,
        policy_id: UUID,
        user_id: str,
        user_groups: List[str]
    ) -> Policy:
        """
        Approve policy (ready for artifact generation).

        Args:
            policy_id: Policy ID
            user_id: Approving user
            user_groups: User's Azure AD groups

        Returns:
            Approved policy
        """
        policy = await self.repository.get_policy_by_id(policy_id)
        if not policy:
            raise HTTPException(status_code=404, detail="Policy not found")

        # Check approval permission
        if policy.owner_user_id != user_id:
            access_list = await self.repository.get_policy_access_list(policy_id)
            user_can_approve = any(
                a.group_name in user_groups and a.can_approve
                for a in access_list
            )
            if not user_can_approve:
                raise HTTPException(status_code=403, detail="Approve access denied")

        # Update status
        approved_policy = await self.repository.update_policy(
            policy_id=policy_id,
            status=PolicyStatus.APPROVED
        )

        logger.info(f"Policy {policy_id} approved by user {user_id}")
        return approved_policy

    async def list_policies_for_user(
        self,
        user_id: str,
        user_groups: List[str],
        status: Optional[PolicyStatus] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[List[Policy], int, bool]:
        """
        List policies accessible by user.

        Args:
            user_id: User ID
            user_groups: User's Azure AD groups
            status: Filter by status
            page: Page number (1-indexed)
            page_size: Items per page

        Returns:
            Tuple of (policies, total_count, has_more)
        """
        offset = (page - 1) * page_size

        policies, total = await self.repository.get_accessible_policies(
            user_id=user_id,
            user_groups=user_groups,
            status=status,
            limit=page_size,
            offset=offset
        )

        has_more = offset + page_size < total

        logger.info(f"Listed {len(policies)} policies for user {user_id} (page {page})")
        return policies, total, has_more

    async def get_policy_with_access_check(
        self,
        policy_id: UUID,
        user_id: str,
        user_groups: List[str]
    ) -> Policy:
        """
        Get policy with access check.

        Args:
            policy_id: Policy ID
            user_id: Requesting user
            user_groups: User's Azure AD groups

        Returns:
            Policy if user has access

        Raises:
            HTTPException: If access denied or not found
        """
        policy = await self.repository.get_policy_by_id(policy_id)
        if not policy:
            raise HTTPException(status_code=404, detail="Policy not found")

        has_access = await self.repository.check_user_access(
            policy_id=policy_id,
            user_id=user_id,
            user_groups=user_groups
        )

        if not has_access:
            raise HTTPException(status_code=403, detail="Access denied")

        return policy

    async def grant_group_access(
        self,
        policy_id: UUID,
        user_id: str,
        group_name: str,
        can_view: bool = True,
        can_edit: bool = False,
        can_approve: bool = False
    ) -> PolicyAccess:
        """
        Grant access to Entra ID group.

        Args:
            policy_id: Policy ID
            user_id: User granting access (must be owner)
            group_name: Azure AD group name
            can_view: View permission
            can_edit: Edit permission
            can_approve: Approve permission

        Returns:
            Created access rule
        """
        policy = await self.repository.get_policy_by_id(policy_id)
        if not policy:
            raise HTTPException(status_code=404, detail="Policy not found")

        # Only owner can grant access
        if policy.owner_user_id != user_id:
            raise HTTPException(
                status_code=403,
                detail="Only policy owner can grant access"
            )

        access = await self.repository.grant_policy_access(
            policy_id=policy_id,
            group_name=group_name,
            can_view=can_view,
            can_edit=can_edit,
            can_approve=can_approve,
            granted_by_user_id=user_id
        )

        logger.info(f"Access granted to group {group_name} for policy {policy_id}")
        return access

    async def revoke_group_access(
        self,
        policy_id: UUID,
        user_id: str,
        group_name: str
    ) -> bool:
        """
        Revoke group access.

        Args:
            policy_id: Policy ID
            user_id: User revoking access (must be owner)
            group_name: Azure AD group name

        Returns:
            True if revoked
        """
        policy = await self.repository.get_policy_by_id(policy_id)
        if not policy:
            raise HTTPException(status_code=404, detail="Policy not found")

        # Only owner can revoke access
        if policy.owner_user_id != user_id:
            raise HTTPException(
                status_code=403,
                detail="Only policy owner can revoke access"
            )

        result = await self.repository.revoke_policy_access(
            policy_id=policy_id,
            group_name=group_name
        )

        logger.info(f"Access revoked for group {group_name} on policy {policy_id}")
        return result

    async def get_policy_access_list(
        self,
        policy_id: UUID,
        user_id: str
    ) -> List[PolicyAccess]:
        """
        Get access list for policy.

        Args:
            policy_id: Policy ID
            user_id: Requesting user (must be owner)

        Returns:
            List of access rules
        """
        policy = await self.repository.get_policy_by_id(policy_id)
        if not policy:
            raise HTTPException(status_code=404, detail="Policy not found")

        # Only owner can view access list
        if policy.owner_user_id != user_id:
            raise HTTPException(
                status_code=403,
                detail="Only policy owner can view access list"
            )

        return await self.repository.get_policy_access_list(policy_id)

    async def link_editing_session(
        self,
        policy_id: UUID,
        session_id: str,
        user_id: str
    ) -> Policy:
        """
        Link ADK chat session to policy for conversational editing.

        Args:
            policy_id: Policy ID
            session_id: ADK session ID
            user_id: User who owns session

        Returns:
            Updated policy
        """
        policy = await self.repository.get_policy_by_id(policy_id)
        if not policy:
            raise HTTPException(status_code=404, detail="Policy not found")

        if policy.owner_user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied")

        updated_policy = await self.repository.update_policy(
            policy_id=policy_id,
            editing_session_id=session_id
        )

        logger.info(f"Session {session_id} linked to policy {policy_id}")
        return updated_policy
