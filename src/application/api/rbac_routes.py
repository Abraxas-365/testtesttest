"""API routes for RBAC management."""

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field, EmailStr

from src.middleware.rbac import (
    get_user_rbac,
    require_permission,
    require_superadmin,
    get_client_ip
)
from src.domain.models.rbac_models import UserRBAC
from src.domain.services.rbac_service import RBACService
from src.application.di import get_container

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================
# PYDANTIC MODELS
# ============================================

class SuperadminResponse(BaseModel):
    """Response model for superadmin entry."""
    email: str
    added_by_email: str
    added_at: Optional[str] = None
    notes: Optional[str] = None


class AddSuperadminRequest(BaseModel):
    """Request model for adding a superadmin."""
    email: EmailStr = Field(..., description="Email address to add as superadmin")
    notes: Optional[str] = Field(None, description="Optional notes about why they were added")


class GroupRoleMappingResponse(BaseModel):
    """Response model for group-role mapping."""
    mapping_id: int
    group_id: Optional[str] = None
    group_name: str
    role_name: str
    description: Optional[str] = None
    enabled: bool
    created_by_email: Optional[str] = None
    created_at: Optional[str] = None


class CreateGroupRoleMappingRequest(BaseModel):
    """Request model for creating a group-role mapping."""
    group_name: str = Field(..., description="Entra ID group display name")
    role_name: str = Field(..., description="Role to assign: admin, editor, viewer")
    group_id: Optional[str] = Field(None, description="Optional Entra ID group object ID")
    description: Optional[str] = Field(None, description="Optional description")


class UpdateGroupRoleMappingRequest(BaseModel):
    """Request model for updating a group-role mapping."""
    role_name: Optional[str] = Field(None, description="New role name")
    description: Optional[str] = Field(None, description="New description")
    enabled: Optional[bool] = Field(None, description="Enable/disable the mapping")


class RoleResponse(BaseModel):
    """Response model for role."""
    role_name: str
    display_name: str
    description: Optional[str] = None
    weight: int
    permissions: List[str]


class CurrentUserRBACResponse(BaseModel):
    """Response model for current user's RBAC info."""
    user_id: str
    email: str
    is_superadmin: bool
    role_name: str
    role_display_name: str
    permissions: List[str]
    entra_groups: List[str]


class SuccessResponse(BaseModel):
    """Generic success response."""
    success: bool
    message: str


# ============================================
# CURRENT USER ENDPOINTS
# ============================================

@router.get("/rbac/me", response_model=CurrentUserRBACResponse, tags=["rbac"])
async def get_current_user_rbac(
    user_rbac: UserRBAC = Depends(get_user_rbac)
):
    """
    Get the current user's RBAC information.

    Returns the user's role, permissions, superadmin status, and Entra ID groups.

    **Authentication:** Required
    """
    return CurrentUserRBACResponse(
        user_id=user_rbac.user_id,
        email=user_rbac.email,
        is_superadmin=user_rbac.is_superadmin,
        role_name=user_rbac.role.role_name,
        role_display_name=user_rbac.role.display_name,
        permissions=user_rbac.permissions,
        entra_groups=user_rbac.entra_groups
    )


@router.get("/rbac/roles", response_model=List[RoleResponse], tags=["rbac"])
async def list_roles(
    user_rbac: UserRBAC = Depends(get_user_rbac)
):
    """
    List all available roles in the system.

    **Authentication:** Required
    """
    container = get_container()
    rbac_repo = await container.init_rbac_repository()
    service = RBACService(rbac_repo)

    roles = await service.list_roles()

    return [
        RoleResponse(
            role_name=r.role_name,
            display_name=r.display_name,
            description=r.description,
            weight=r.weight,
            permissions=r.permissions
        )
        for r in roles
    ]


# ============================================
# SUPERADMIN WHITELIST ENDPOINTS
# ============================================

@router.get("/rbac/superadmins", response_model=List[SuperadminResponse], tags=["rbac"])
async def list_superadmins(
    user_rbac: UserRBAC = Depends(require_superadmin())
):
    """
    List all superadmins in the whitelist.

    **Authentication:** Required
    **Authorization:** Superadmin only
    """
    container = get_container()
    rbac_repo = await container.init_rbac_repository()
    service = RBACService(rbac_repo)

    entries = await service.list_superadmins(user_rbac)

    return [
        SuperadminResponse(
            email=e.email,
            added_by_email=e.added_by_email,
            added_at=e.added_at.isoformat() if e.added_at else None,
            notes=e.notes
        )
        for e in entries
    ]


@router.post(
    "/rbac/superadmins",
    response_model=SuperadminResponse,
    status_code=201,
    tags=["rbac"]
)
async def add_superadmin(
    request_body: AddSuperadminRequest,
    request: Request,
    user_rbac: UserRBAC = Depends(require_superadmin())
):
    """
    Add a new superadmin to the whitelist.

    **Authentication:** Required
    **Authorization:** Superadmin only
    """
    container = get_container()
    rbac_repo = await container.init_rbac_repository()
    service = RBACService(rbac_repo)

    try:
        entry = await service.add_superadmin(
            email=request_body.email,
            added_by=user_rbac,
            notes=request_body.notes,
            ip_address=get_client_ip(request)
        )

        return SuperadminResponse(
            email=entry.email,
            added_by_email=entry.added_by_email,
            added_at=entry.added_at.isoformat() if entry.added_at else None,
            notes=entry.notes
        )

    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.delete("/rbac/superadmins/{email}", response_model=SuccessResponse, tags=["rbac"])
async def remove_superadmin(
    email: str,
    request: Request,
    user_rbac: UserRBAC = Depends(require_superadmin())
):
    """
    Remove a superadmin from the whitelist.

    **Authentication:** Required
    **Authorization:** Superadmin only

    Note: Cannot remove the last superadmin.
    """
    container = get_container()
    rbac_repo = await container.init_rbac_repository()
    service = RBACService(rbac_repo)

    try:
        success = await service.remove_superadmin(
            email=email,
            removed_by=user_rbac,
            ip_address=get_client_ip(request)
        )

        if not success:
            raise HTTPException(status_code=404, detail="Superadmin not found")

        return SuccessResponse(success=True, message=f"Superadmin {email} removed")

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


# ============================================
# GROUP-ROLE MAPPING ENDPOINTS
# ============================================

@router.get(
    "/rbac/group-mappings",
    response_model=List[GroupRoleMappingResponse],
    tags=["rbac"]
)
async def list_group_role_mappings(
    enabled_only: bool = True,
    user_rbac: UserRBAC = Depends(require_permission("group_mappings:list"))
):
    """
    List all Entra ID group to role mappings.

    **Authentication:** Required
    **Authorization:** Admin or Superadmin (group_mappings:list permission)

    Args:
        enabled_only: Only return enabled mappings (default: true)
    """
    container = get_container()
    rbac_repo = await container.init_rbac_repository()
    service = RBACService(rbac_repo)

    try:
        mappings = await service.list_group_role_mappings(
            user_rbac, enabled_only=enabled_only
        )

        return [
            GroupRoleMappingResponse(
                mapping_id=m.mapping_id,
                group_id=m.group_id,
                group_name=m.group_name,
                role_name=m.role_name,
                description=m.description,
                enabled=m.enabled,
                created_by_email=m.created_by_email,
                created_at=m.created_at.isoformat() if m.created_at else None
            )
            for m in mappings
        ]

    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.get(
    "/rbac/group-mappings/{mapping_id}",
    response_model=GroupRoleMappingResponse,
    tags=["rbac"]
)
async def get_group_role_mapping(
    mapping_id: int,
    user_rbac: UserRBAC = Depends(require_permission("group_mappings:view"))
):
    """
    Get a specific group to role mapping.

    **Authentication:** Required
    **Authorization:** Admin or Superadmin (group_mappings:view permission)
    """
    container = get_container()
    rbac_repo = await container.init_rbac_repository()
    service = RBACService(rbac_repo)

    try:
        mapping = await service.get_group_role_mapping(mapping_id, user_rbac)

        if not mapping:
            raise HTTPException(status_code=404, detail="Mapping not found")

        return GroupRoleMappingResponse(
            mapping_id=mapping.mapping_id,
            group_id=mapping.group_id,
            group_name=mapping.group_name,
            role_name=mapping.role_name,
            description=mapping.description,
            enabled=mapping.enabled,
            created_by_email=mapping.created_by_email,
            created_at=mapping.created_at.isoformat() if mapping.created_at else None
        )

    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post(
    "/rbac/group-mappings",
    response_model=GroupRoleMappingResponse,
    status_code=201,
    tags=["rbac"]
)
async def create_group_role_mapping(
    request_body: CreateGroupRoleMappingRequest,
    request: Request,
    user_rbac: UserRBAC = Depends(require_superadmin())
):
    """
    Create a new Entra ID group to role mapping.

    **Authentication:** Required
    **Authorization:** Superadmin only

    Valid role names: admin, editor, viewer
    """
    container = get_container()
    rbac_repo = await container.init_rbac_repository()
    service = RBACService(rbac_repo)

    try:
        mapping = await service.create_group_role_mapping(
            group_name=request_body.group_name,
            role_name=request_body.role_name,
            created_by=user_rbac,
            group_id=request_body.group_id,
            description=request_body.description,
            ip_address=get_client_ip(request)
        )

        return GroupRoleMappingResponse(
            mapping_id=mapping.mapping_id,
            group_id=mapping.group_id,
            group_name=mapping.group_name,
            role_name=mapping.role_name,
            description=mapping.description,
            enabled=mapping.enabled,
            created_by_email=mapping.created_by_email,
            created_at=mapping.created_at.isoformat() if mapping.created_at else None
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.put(
    "/rbac/group-mappings/{mapping_id}",
    response_model=GroupRoleMappingResponse,
    tags=["rbac"]
)
async def update_group_role_mapping(
    mapping_id: int,
    request_body: UpdateGroupRoleMappingRequest,
    request: Request,
    user_rbac: UserRBAC = Depends(require_superadmin())
):
    """
    Update an existing group to role mapping.

    **Authentication:** Required
    **Authorization:** Superadmin only
    """
    container = get_container()
    rbac_repo = await container.init_rbac_repository()
    service = RBACService(rbac_repo)

    try:
        mapping = await service.update_group_role_mapping(
            mapping_id=mapping_id,
            updated_by=user_rbac,
            role_name=request_body.role_name,
            description=request_body.description,
            enabled=request_body.enabled,
            ip_address=get_client_ip(request)
        )

        if not mapping:
            raise HTTPException(status_code=404, detail="Mapping not found")

        return GroupRoleMappingResponse(
            mapping_id=mapping.mapping_id,
            group_id=mapping.group_id,
            group_name=mapping.group_name,
            role_name=mapping.role_name,
            description=mapping.description,
            enabled=mapping.enabled,
            created_by_email=mapping.created_by_email,
            created_at=mapping.created_at.isoformat() if mapping.created_at else None
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.delete(
    "/rbac/group-mappings/{mapping_id}",
    response_model=SuccessResponse,
    tags=["rbac"]
)
async def delete_group_role_mapping(
    mapping_id: int,
    request: Request,
    user_rbac: UserRBAC = Depends(require_superadmin())
):
    """
    Delete a group to role mapping.

    **Authentication:** Required
    **Authorization:** Superadmin only
    """
    container = get_container()
    rbac_repo = await container.init_rbac_repository()
    service = RBACService(rbac_repo)

    try:
        success = await service.delete_group_role_mapping(
            mapping_id=mapping_id,
            deleted_by=user_rbac,
            ip_address=get_client_ip(request)
        )

        if not success:
            raise HTTPException(status_code=404, detail="Mapping not found")

        return SuccessResponse(success=True, message="Mapping deleted")

    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
