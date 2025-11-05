"""Domain models for Azure AD integration."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class AzureADGroupMapping:
    """
    Azure AD group to agent area_type mapping.

    Attributes:
        mapping_id: Unique identifier
        group_name: Azure AD group display name
        area_type: Agent area_type to route to
        weight: Priority weight (higher = higher priority)
        description: Optional description
        enabled: Whether mapping is active
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """
    mapping_id: int
    group_name: str
    area_type: str
    weight: int
    description: Optional[str] = None
    enabled: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
