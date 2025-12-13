"""RBAC Service - Business logic for role-based access control."""

import logging
from typing import List, Optional

from src.domain.models.rbac_models import (
    Role, SuperadminEntry, EntraGroupRoleMapping, UserRBAC
)
from src.domain.ports.rbac_repository import RBACRepository

logger = logging.getLogger(__name__)


class RBACService:
    """Service for RBAC operations and authorization decisions."""

    def __init__(self, repository: RBACRepository):
        """
        Initialize RBAC service.

        Args:
            repository: RBAC repository implementation
        """
        self.repository = repository

    async def resolve_user_rbac(
        self,
        user_id: str,
        email: str,
        tenant_id: Optional[str],
        entra_groups: List[str]
    ) -> UserRBAC:
        """
        Resolve the complete RBAC context for a user.

        This is the main entry point called during authentication to build
        the user's permissions based on their email and group memberships.

        Args:
            user_id: User's unique identifier (Azure AD Object ID)
            email: User's email address
            tenant_id: Azure AD tenant ID
            entra_groups: List of user's Entra ID group names

        Returns:
            UserRBAC context with resolved role and permissions
        """
        # Check superadmin status first (email-based whitelist)
        is_superadmin = await self.repository.is_superadmin(email)

        if is_superadmin:
            role = await self.repository.get_role("superadmin")
            logger.info(f"User {email} resolved as SUPERADMIN")
        else:
            # Get role based on Entra ID group membership
            role = await self.repository.get_role_for_groups(entra_groups)

            if not role:
                # Default to viewer if no group mapping found
                role = await self.repository.get_default_role()
                logger.info(
                    f"User {email} has no group mapping, using default role: {role.role_name}"
                )
            else:
                logger.info(
                    f"User {email} resolved to role: {role.role_name} "
                    f"from groups {entra_groups}"
                )

        return UserRBAC(
            user_id=user_id,
            email=email,
            tenant_id=tenant_id,
            is_superadmin=is_superadmin,
            role=role,
            entra_groups=entra_groups
        )

    # ============================================
    # SUPERADMIN MANAGEMENT
    # ============================================

    async def add_superadmin(
        self,
        email: str,
        added_by: UserRBAC,
        notes: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> SuperadminEntry:
        """
        Add a new superadmin to the whitelist.

        Args:
            email: Email address to add
            added_by: RBAC context of who is adding
            notes: Optional notes about why they were added
            ip_address: Client IP for audit

        Returns:
            Created superadmin entry

        Raises:
            PermissionError: If added_by is not a superadmin
            ValueError: If email is already a superadmin
        """
        if not added_by.is_superadmin:
            raise PermissionError("Only superadmins can add other superadmins")

        # Check if already exists
        if await self.repository.is_superadmin(email):
            raise ValueError(f"Email {email} is already a superadmin")

        entry = await self.repository.add_superadmin(
            email=email,
            added_by_email=added_by.email,
            notes=notes
        )

        # Audit log
        await self.repository.log_audit_event(
            action="superadmin_added",
            performed_by_email=added_by.email,
            target_resource="superadmin_whitelist",
            target_id=email,
            new_value={"email": email, "notes": notes},
            ip_address=ip_address
        )

        logger.info(f"Superadmin added: {email} by {added_by.email}")
        return entry

    async def remove_superadmin(
        self,
        email: str,
        removed_by: UserRBAC,
        ip_address: Optional[str] = None
    ) -> bool:
        """
        Remove a superadmin from the whitelist.

        Args:
            email: Email address to remove
            removed_by: RBAC context of who is removing
            ip_address: Client IP for audit

        Returns:
            True if removed, False if not found

        Raises:
            PermissionError: If removed_by is not a superadmin
            ValueError: If trying to remove the last superadmin
        """
        if not removed_by.is_superadmin:
            raise PermissionError("Only superadmins can remove superadmins")

        # Prevent removing yourself if you're the last superadmin
        superadmins = await self.repository.list_superadmins()
        if len(superadmins) <= 1 and email.lower() == removed_by.email.lower():
            raise ValueError("Cannot remove the last superadmin")

        success = await self.repository.remove_superadmin(email)

        if success:
            await self.repository.log_audit_event(
                action="superadmin_removed",
                performed_by_email=removed_by.email,
                target_resource="superadmin_whitelist",
                target_id=email,
                old_value={"email": email},
                ip_address=ip_address
            )
            logger.info(f"Superadmin removed: {email} by {removed_by.email}")

        return success

    async def list_superadmins(self, requested_by: UserRBAC) -> List[SuperadminEntry]:
        """
        List all superadmins.

        Args:
            requested_by: RBAC context of who is requesting

        Returns:
            List of superadmin entries

        Raises:
            PermissionError: If requested_by is not a superadmin
        """
        if not requested_by.is_superadmin:
            raise PermissionError("Only superadmins can view the superadmin list")

        return await self.repository.list_superadmins()

    # ============================================
    # GROUP-ROLE MAPPING MANAGEMENT
    # ============================================

    async def create_group_role_mapping(
        self,
        group_name: str,
        role_name: str,
        created_by: UserRBAC,
        group_id: Optional[str] = None,
        description: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> EntraGroupRoleMapping:
        """
        Create a new group to role mapping.

        Args:
            group_name: Entra ID group display name
            role_name: Role to assign to group members
            created_by: RBAC context of who is creating
            group_id: Optional Entra ID group object ID
            description: Optional description
            ip_address: Client IP for audit

        Returns:
            Created mapping

        Raises:
            PermissionError: If created_by is not a superadmin
            ValueError: If role doesn't exist or group already mapped
        """
        if not created_by.is_superadmin:
            raise PermissionError("Only superadmins can create group-role mappings")

        # Validate role exists
        role = await self.repository.get_role(role_name)
        if not role:
            raise ValueError(f"Role '{role_name}' does not exist")

        # Check for duplicate
        existing = await self.repository.get_group_role_mapping(group_name)
        if existing:
            raise ValueError(f"Mapping for group '{group_name}' already exists")

        mapping = await self.repository.create_group_role_mapping(
            group_name=group_name,
            role_name=role_name,
            created_by_email=created_by.email,
            group_id=group_id,
            description=description
        )

        await self.repository.log_audit_event(
            action="group_role_mapping_created",
            performed_by_email=created_by.email,
            target_resource="entra_group_role_mappings",
            target_id=group_name,
            new_value={
                "group_name": group_name,
                "role_name": role_name,
                "description": description
            },
            ip_address=ip_address
        )

        logger.info(
            f"Group-role mapping created: {group_name} -> {role_name} "
            f"by {created_by.email}"
        )
        return mapping

    async def update_group_role_mapping(
        self,
        mapping_id: int,
        updated_by: UserRBAC,
        role_name: Optional[str] = None,
        description: Optional[str] = None,
        enabled: Optional[bool] = None,
        ip_address: Optional[str] = None
    ) -> Optional[EntraGroupRoleMapping]:
        """
        Update an existing group to role mapping.

        Args:
            mapping_id: Mapping ID to update
            updated_by: RBAC context of who is updating
            role_name: New role name (optional)
            description: New description (optional)
            enabled: New enabled status (optional)
            ip_address: Client IP for audit

        Returns:
            Updated mapping or None if not found

        Raises:
            PermissionError: If updated_by is not a superadmin
            ValueError: If role doesn't exist
        """
        if not updated_by.is_superadmin:
            raise PermissionError("Only superadmins can update group-role mappings")

        if role_name:
            role = await self.repository.get_role(role_name)
            if not role:
                raise ValueError(f"Role '{role_name}' does not exist")

        # Get old value for audit
        old_mapping = await self.repository.get_group_role_mapping_by_id(mapping_id)

        mapping = await self.repository.update_group_role_mapping(
            mapping_id=mapping_id,
            role_name=role_name,
            description=description,
            enabled=enabled
        )

        if mapping:
            await self.repository.log_audit_event(
                action="group_role_mapping_updated",
                performed_by_email=updated_by.email,
                target_resource="entra_group_role_mappings",
                target_id=str(mapping_id),
                old_value={
                    "group_name": old_mapping.group_name if old_mapping else None,
                    "role_name": old_mapping.role_name if old_mapping else None
                } if old_mapping else None,
                new_value={
                    "role_name": role_name,
                    "description": description,
                    "enabled": enabled
                },
                ip_address=ip_address
            )
            logger.info(
                f"Group-role mapping updated: {mapping_id} by {updated_by.email}"
            )

        return mapping

    async def delete_group_role_mapping(
        self,
        mapping_id: int,
        deleted_by: UserRBAC,
        ip_address: Optional[str] = None
    ) -> bool:
        """
        Delete a group to role mapping.

        Args:
            mapping_id: Mapping ID to delete
            deleted_by: RBAC context of who is deleting
            ip_address: Client IP for audit

        Returns:
            True if deleted, False if not found

        Raises:
            PermissionError: If deleted_by is not a superadmin
        """
        if not deleted_by.is_superadmin:
            raise PermissionError("Only superadmins can delete group-role mappings")

        # Get old value for audit
        old_mapping = await self.repository.get_group_role_mapping_by_id(mapping_id)

        success = await self.repository.delete_group_role_mapping(mapping_id)

        if success:
            await self.repository.log_audit_event(
                action="group_role_mapping_deleted",
                performed_by_email=deleted_by.email,
                target_resource="entra_group_role_mappings",
                target_id=str(mapping_id),
                old_value={
                    "group_name": old_mapping.group_name if old_mapping else None,
                    "role_name": old_mapping.role_name if old_mapping else None
                } if old_mapping else None,
                ip_address=ip_address
            )
            logger.info(
                f"Group-role mapping deleted: {mapping_id} by {deleted_by.email}"
            )

        return success

    async def list_group_role_mappings(
        self,
        requested_by: UserRBAC,
        enabled_only: bool = True
    ) -> List[EntraGroupRoleMapping]:
        """
        List all group to role mappings.

        Args:
            requested_by: RBAC context of who is requesting
            enabled_only: Only return enabled mappings

        Returns:
            List of group-role mappings

        Raises:
            PermissionError: If user lacks permission
        """
        if not requested_by.has_permission("group_mappings:list"):
            raise PermissionError("You don't have permission to view group mappings")

        return await self.repository.list_group_role_mappings(enabled_only)

    async def get_group_role_mapping(
        self,
        mapping_id: int,
        requested_by: UserRBAC
    ) -> Optional[EntraGroupRoleMapping]:
        """
        Get a specific group to role mapping.

        Args:
            mapping_id: Mapping ID to get
            requested_by: RBAC context of who is requesting

        Returns:
            Group-role mapping or None

        Raises:
            PermissionError: If user lacks permission
        """
        if not requested_by.has_permission("group_mappings:view"):
            raise PermissionError("You don't have permission to view group mappings")

        return await self.repository.get_group_role_mapping_by_id(mapping_id)

    # ============================================
    # ROLES
    # ============================================

    async def list_roles(self) -> List[Role]:
        """
        List all available roles.

        Returns:
            List of roles ordered by weight (highest first)
        """
        return await self.repository.get_all_roles()
