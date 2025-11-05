"""API routes for Azure AD group mappings management."""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from src.application.di import get_container


router = APIRouter()


# Request/Response Models
class GroupMappingCreate(BaseModel):
    """Request model for creating a group mapping."""
    group_name: str = Field(..., description="Azure AD group display name")
    area_type: str = Field(..., description="Agent area_type to route to")
    weight: int = Field(default=500, description="Priority weight (higher = higher priority)")
    description: Optional[str] = Field(None, description="Optional description")
    enabled: bool = Field(default=True, description="Whether mapping is active")


class GroupMappingUpdate(BaseModel):
    """Request model for updating a group mapping."""
    area_type: Optional[str] = Field(None, description="New area_type")
    weight: Optional[int] = Field(None, description="New priority weight")
    description: Optional[str] = Field(None, description="New description")
    enabled: Optional[bool] = Field(None, description="New enabled status")


class GroupMappingResponse(BaseModel):
    """Response model for group mapping."""
    mapping_id: int
    group_name: str
    area_type: str
    weight: int
    description: Optional[str]
    enabled: bool
    created_at: Optional[str]
    updated_at: Optional[str]


@router.get("/groups/mappings", response_model=List[GroupMappingResponse])
async def list_group_mappings(enabled_only: bool = True):
    """
    List all Azure AD group to area_type mappings.

    Args:
        enabled_only: Only return enabled mappings

    Returns:
        List of group mappings sorted by weight (descending)
    """
    try:
        container = get_container()
        group_repo = await container.init_group_mapping_repository()

        mappings = await group_repo.get_all_mappings(enabled_only=enabled_only)

        return [
            GroupMappingResponse(
                mapping_id=m.mapping_id,
                group_name=m.group_name,
                area_type=m.area_type,
                weight=m.weight,
                description=m.description,
                enabled=m.enabled,
                created_at=m.created_at.isoformat() if m.created_at else None,
                updated_at=m.updated_at.isoformat() if m.updated_at else None
            )
            for m in mappings
        ]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing group mappings: {str(e)}"
        )


@router.get("/groups/mappings/{mapping_id}", response_model=GroupMappingResponse)
async def get_group_mapping(mapping_id: int):
    """
    Get a specific group mapping by ID.

    Args:
        mapping_id: Mapping ID to retrieve

    Returns:
        Group mapping details
    """
    try:
        container = get_container()
        group_repo = await container.init_group_mapping_repository()

        mapping = await group_repo.get_mapping_by_id(mapping_id)

        if not mapping:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Group mapping with ID {mapping_id} not found"
            )

        return GroupMappingResponse(
            mapping_id=mapping.mapping_id,
            group_name=mapping.group_name,
            area_type=mapping.area_type,
            weight=mapping.weight,
            description=mapping.description,
            enabled=mapping.enabled,
            created_at=mapping.created_at.isoformat() if mapping.created_at else None,
            updated_at=mapping.updated_at.isoformat() if mapping.updated_at else None
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving group mapping: {str(e)}"
        )


@router.post("/groups/mappings", response_model=GroupMappingResponse, status_code=status.HTTP_201_CREATED)
async def create_group_mapping(mapping: GroupMappingCreate):
    """
    Create a new Azure AD group to area_type mapping.

    Args:
        mapping: Group mapping details

    Returns:
        Created group mapping
    """
    try:
        container = get_container()
        group_repo = await container.init_group_mapping_repository()

        # Check if group name already exists
        existing = await group_repo.get_mapping_by_group_name(mapping.group_name)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Group mapping for '{mapping.group_name}' already exists"
            )

        created = await group_repo.create_mapping(
            group_name=mapping.group_name,
            area_type=mapping.area_type,
            weight=mapping.weight,
            description=mapping.description,
            enabled=mapping.enabled
        )

        return GroupMappingResponse(
            mapping_id=created.mapping_id,
            group_name=created.group_name,
            area_type=created.area_type,
            weight=created.weight,
            description=created.description,
            enabled=created.enabled,
            created_at=created.created_at.isoformat() if created.created_at else None,
            updated_at=created.updated_at.isoformat() if created.updated_at else None
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating group mapping: {str(e)}"
        )


@router.put("/groups/mappings/{mapping_id}", response_model=GroupMappingResponse)
async def update_group_mapping(mapping_id: int, mapping: GroupMappingUpdate):
    """
    Update an existing group mapping.

    Args:
        mapping_id: Mapping ID to update
        mapping: Updated mapping details

    Returns:
        Updated group mapping
    """
    try:
        container = get_container()
        group_repo = await container.init_group_mapping_repository()

        updated = await group_repo.update_mapping(
            mapping_id=mapping_id,
            area_type=mapping.area_type,
            weight=mapping.weight,
            description=mapping.description,
            enabled=mapping.enabled
        )

        if not updated:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Group mapping with ID {mapping_id} not found"
            )

        return GroupMappingResponse(
            mapping_id=updated.mapping_id,
            group_name=updated.group_name,
            area_type=updated.area_type,
            weight=updated.weight,
            description=updated.description,
            enabled=updated.enabled,
            created_at=updated.created_at.isoformat() if updated.created_at else None,
            updated_at=updated.updated_at.isoformat() if updated.updated_at else None
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating group mapping: {str(e)}"
        )


@router.delete("/groups/mappings/{mapping_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group_mapping(mapping_id: int):
    """
    Delete a group mapping.

    Args:
        mapping_id: Mapping ID to delete

    Returns:
        No content on success
    """
    try:
        container = get_container()
        group_repo = await container.init_group_mapping_repository()

        deleted = await group_repo.delete_mapping(mapping_id)

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Group mapping with ID {mapping_id} not found"
            )

        return None
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting group mapping: {str(e)}"
        )


@router.get("/groups/mappings/by-group/{group_name}", response_model=GroupMappingResponse)
async def get_group_mapping_by_name(group_name: str):
    """
    Get a group mapping by Azure AD group name.

    Args:
        group_name: Azure AD group display name

    Returns:
        Group mapping details
    """
    try:
        container = get_container()
        group_repo = await container.init_group_mapping_repository()

        mapping = await group_repo.get_mapping_by_group_name(group_name)

        if not mapping:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Group mapping for '{group_name}' not found"
            )

        return GroupMappingResponse(
            mapping_id=mapping.mapping_id,
            group_name=mapping.group_name,
            area_type=mapping.area_type,
            weight=mapping.weight,
            description=mapping.description,
            enabled=mapping.enabled,
            created_at=mapping.created_at.isoformat() if mapping.created_at else None,
            updated_at=mapping.updated_at.isoformat() if mapping.updated_at else None
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving group mapping: {str(e)}"
        )
