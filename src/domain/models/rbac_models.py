"""Domain models for RBAC (Role-Based Access Control) system."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
from enum import Enum


class RoleName(str, Enum):
    """Predefined role names in the system."""
    SUPERADMIN = "superadmin"
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"


@dataclass(frozen=True)
class Role:
    """
    RBAC Role definition.

    Attributes:
        role_id: Unique identifier
        role_name: Role name (matches RoleName enum)
        display_name: Human-readable display name
        description: Optional description of the role
        weight: Priority weight (higher = more privileged)
        permissions: List of permission strings (e.g., "agents:list")
        enabled: Whether role is active
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """
    role_id: int
    role_name: str
    display_name: str
    weight: int
    permissions: List[str]
    description: Optional[str] = None
    enabled: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def has_permission(self, permission: str) -> bool:
        """
        Check if this role has a specific permission.

        Args:
            permission: Permission string to check (e.g., "agents:list")

        Returns:
            True if role has the permission or wildcard access
        """
        if "*" in self.permissions:
            return True
        return permission in self.permissions

    def has_any_permission(self, permissions: List[str]) -> bool:
        """
        Check if this role has any of the specified permissions.

        Args:
            permissions: List of permission strings to check

        Returns:
            True if role has at least one of the permissions
        """
        if "*" in self.permissions:
            return True
        return any(perm in self.permissions for perm in permissions)


@dataclass(frozen=True)
class SuperadminEntry:
    """
    Superadmin whitelist entry.

    Attributes:
        whitelist_id: Unique identifier
        email: Email address of the superadmin
        added_by_email: Email of who added this superadmin
        added_at: When the entry was created
        notes: Optional notes about why they were added
        enabled: Whether this entry is active
    """
    whitelist_id: int
    email: str
    added_by_email: str
    added_at: Optional[datetime] = None
    notes: Optional[str] = None
    enabled: bool = True


@dataclass(frozen=True)
class EntraGroupRoleMapping:
    """
    Maps an Entra ID (Azure AD) group to an RBAC role.

    Attributes:
        mapping_id: Unique identifier
        group_id: Azure AD Group Object ID (optional, for validation)
        group_name: Azure AD group display name
        role_name: Role name to assign to group members
        description: Optional description of the mapping
        enabled: Whether mapping is active
        created_by_email: Email of who created this mapping
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """
    mapping_id: int
    group_name: str
    role_name: str
    group_id: Optional[str] = None
    description: Optional[str] = None
    enabled: bool = True
    created_by_email: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class UserRBAC:
    """
    Computed RBAC context for an authenticated user.

    This is created at request time based on the user's email
    and Entra ID group memberships. It contains all the information
    needed to make authorization decisions.

    Attributes:
        user_id: User's unique identifier (Azure AD Object ID)
        email: User's email address
        tenant_id: Azure AD tenant ID
        is_superadmin: Whether user is in superadmin whitelist
        role: User's resolved role
        entra_groups: List of user's Entra ID group names
        permissions: Flattened list of permission strings
    """
    user_id: str
    email: str
    is_superadmin: bool
    role: Role
    tenant_id: Optional[str] = None
    entra_groups: List[str] = field(default_factory=list)

    @property
    def permissions(self) -> List[str]:
        """Get the user's permissions from their role."""
        return self.role.permissions

    def has_permission(self, permission: str) -> bool:
        """
        Check if user has a specific permission.

        Superadmins always have all permissions.

        Args:
            permission: Permission string to check (e.g., "agents:list")

        Returns:
            True if user has the permission
        """
        if self.is_superadmin:
            return True
        return self.role.has_permission(permission)

    def has_any_permission(self, permissions: List[str]) -> bool:
        """
        Check if user has any of the specified permissions.

        Args:
            permissions: List of permission strings to check

        Returns:
            True if user has at least one permission
        """
        if self.is_superadmin:
            return True
        return self.role.has_any_permission(permissions)

    def can_access_resource(self, resource: str, action: str) -> bool:
        """
        Check access for a resource:action combination.

        Args:
            resource: Resource name (e.g., "agents", "policies")
            action: Action name (e.g., "list", "create", "delete")

        Returns:
            True if user can perform the action on the resource
        """
        return self.has_permission(f"{resource}:{action}")


@dataclass(frozen=True)
class RBACAuditEntry:
    """
    Audit log entry for RBAC changes.

    Attributes:
        log_id: Unique identifier
        action: Action performed (e.g., "superadmin_added")
        performed_by_email: Email of who performed the action
        target_resource: Resource type affected
        target_id: ID of the affected resource
        old_value: Previous value (if applicable)
        new_value: New value (if applicable)
        ip_address: IP address of the request
        created_at: When the action occurred
    """
    log_id: int
    action: str
    performed_by_email: str
    target_resource: str
    target_id: Optional[str] = None
    old_value: Optional[dict] = None
    new_value: Optional[dict] = None
    ip_address: Optional[str] = None
    created_at: Optional[datetime] = None
