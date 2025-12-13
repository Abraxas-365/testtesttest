"""Port interface for RBAC repository."""

from abc import ABC, abstractmethod
from typing import List, Optional

from src.domain.models.rbac_models import (
    Role, SuperadminEntry, EntraGroupRoleMapping
)


class RBACRepository(ABC):
    """Repository interface for RBAC operations."""

    # ============================================
    # SUPERADMIN WHITELIST
    # ============================================

    @abstractmethod
    async def is_superadmin(self, email: str) -> bool:
        """
        Check if email is in the superadmin whitelist.

        Args:
            email: Email address to check

        Returns:
            True if email is an enabled superadmin
        """
        pass

    @abstractmethod
    async def list_superadmins(self) -> List[SuperadminEntry]:
        """
        List all enabled superadmin entries.

        Returns:
            List of superadmin entries
        """
        pass

    @abstractmethod
    async def add_superadmin(
        self,
        email: str,
        added_by_email: str,
        notes: Optional[str] = None
    ) -> SuperadminEntry:
        """
        Add email to superadmin whitelist.

        Args:
            email: Email address to add
            added_by_email: Email of who is adding this entry
            notes: Optional notes about why they were added

        Returns:
            Created superadmin entry

        Raises:
            Exception if email already exists
        """
        pass

    @abstractmethod
    async def remove_superadmin(self, email: str) -> bool:
        """
        Remove email from superadmin whitelist (soft delete).

        Args:
            email: Email address to remove

        Returns:
            True if removed, False if not found
        """
        pass

    # ============================================
    # ROLES
    # ============================================

    @abstractmethod
    async def get_role(self, role_name: str) -> Optional[Role]:
        """
        Get role by name.

        Args:
            role_name: Name of the role

        Returns:
            Role or None if not found
        """
        pass

    @abstractmethod
    async def get_all_roles(self) -> List[Role]:
        """
        Get all enabled roles.

        Returns:
            List of roles ordered by weight (highest first)
        """
        pass

    @abstractmethod
    async def get_default_role(self) -> Role:
        """
        Get the default role for users with no group mappings.

        Returns:
            Default role (typically 'viewer')

        Raises:
            RuntimeError if default role not found
        """
        pass

    # ============================================
    # ENTRA GROUP -> ROLE MAPPINGS
    # ============================================

    @abstractmethod
    async def get_role_for_groups(self, group_names: List[str]) -> Optional[Role]:
        """
        Get the highest-priority role for given groups.

        Args:
            group_names: List of Entra ID group names

        Returns:
            Role with highest weight among mapped groups, or None
        """
        pass

    @abstractmethod
    async def list_group_role_mappings(
        self, enabled_only: bool = True
    ) -> List[EntraGroupRoleMapping]:
        """
        List all group to role mappings.

        Args:
            enabled_only: Only return enabled mappings

        Returns:
            List of group-role mappings
        """
        pass

    @abstractmethod
    async def get_group_role_mapping(
        self, group_name: str
    ) -> Optional[EntraGroupRoleMapping]:
        """
        Get mapping for specific group.

        Args:
            group_name: Entra ID group name

        Returns:
            Group-role mapping or None
        """
        pass

    @abstractmethod
    async def get_group_role_mapping_by_id(
        self, mapping_id: int
    ) -> Optional[EntraGroupRoleMapping]:
        """
        Get mapping by ID.

        Args:
            mapping_id: Mapping ID

        Returns:
            Group-role mapping or None
        """
        pass

    @abstractmethod
    async def create_group_role_mapping(
        self,
        group_name: str,
        role_name: str,
        created_by_email: str,
        group_id: Optional[str] = None,
        description: Optional[str] = None
    ) -> EntraGroupRoleMapping:
        """
        Create new group to role mapping.

        Args:
            group_name: Entra ID group display name
            role_name: Role name to assign
            created_by_email: Email of who created this
            group_id: Optional Entra ID group object ID
            description: Optional description

        Returns:
            Created mapping

        Raises:
            Exception if group already mapped
        """
        pass

    @abstractmethod
    async def update_group_role_mapping(
        self,
        mapping_id: int,
        role_name: Optional[str] = None,
        description: Optional[str] = None,
        enabled: Optional[bool] = None
    ) -> Optional[EntraGroupRoleMapping]:
        """
        Update existing mapping.

        Args:
            mapping_id: Mapping ID to update
            role_name: New role name (optional)
            description: New description (optional)
            enabled: New enabled status (optional)

        Returns:
            Updated mapping or None if not found
        """
        pass

    @abstractmethod
    async def delete_group_role_mapping(self, mapping_id: int) -> bool:
        """
        Delete group to role mapping.

        Args:
            mapping_id: Mapping ID to delete

        Returns:
            True if deleted, False if not found
        """
        pass

    # ============================================
    # AUDIT LOG
    # ============================================

    @abstractmethod
    async def log_audit_event(
        self,
        action: str,
        performed_by_email: str,
        target_resource: str,
        target_id: Optional[str] = None,
        old_value: Optional[dict] = None,
        new_value: Optional[dict] = None,
        ip_address: Optional[str] = None
    ) -> None:
        """
        Log an RBAC audit event.

        Args:
            action: Action performed (e.g., 'superadmin_added')
            performed_by_email: Email of who performed the action
            target_resource: Resource type (e.g., 'superadmin_whitelist')
            target_id: ID of affected resource
            old_value: Previous value (optional)
            new_value: New value (optional)
            ip_address: Client IP address (optional)
        """
        pass
