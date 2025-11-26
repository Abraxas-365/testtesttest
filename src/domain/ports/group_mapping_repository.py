"""Port interface for Azure AD group mapping repository."""

from abc import ABC, abstractmethod
from typing import List, Optional

from src.domain.models.azure_ad_models import AzureADGroupMapping


class GroupMappingRepository(ABC):
    """Repository interface for Azure AD group mappings."""

    @abstractmethod
    async def get_all_mappings(self, enabled_only: bool = True) -> List[AzureADGroupMapping]:
        """
        Get all group mappings.

        Args:
            enabled_only: Only return enabled mappings

        Returns:
            List of group mappings
        """
        pass

    @abstractmethod
    async def get_mapping_by_group_name(self, group_name: str) -> Optional[AzureADGroupMapping]:
        """
        Get mapping for specific group.

        Args:
            group_name: Azure AD group name

        Returns:
            Group mapping or None
        """
        pass

    @abstractmethod
    async def get_mappings_by_group_names(self, group_names: List[str]) -> List[AzureADGroupMapping]:
        """
        Get mappings for multiple groups.

        Args:
            group_names: List of Azure AD group names

        Returns:
            List of matching group mappings
        """
        pass

    @abstractmethod
    async def create_mapping(
        self,
        group_name: str,
        area_type: str,
        weight: int,
        description: Optional[str] = None,
        enabled: bool = True
    ) -> AzureADGroupMapping:
        """
        Create new group mapping.

        Args:
            group_name: Azure AD group name
            area_type: Agent area_type
            weight: Priority weight
            description: Optional description
            enabled: Whether enabled

        Returns:
            Created mapping
        """
        pass

    @abstractmethod
    async def update_mapping(
        self,
        mapping_id: int,
        area_type: Optional[str] = None,
        weight: Optional[int] = None,
        description: Optional[str] = None,
        enabled: Optional[bool] = None
    ) -> Optional[AzureADGroupMapping]:
        """
        Update existing mapping.

        Args:
            mapping_id: Mapping ID to update
            area_type: New area_type (optional)
            weight: New weight (optional)
            description: New description (optional)
            enabled: New enabled status (optional)

        Returns:
            Updated mapping or None
        """
        pass

    @abstractmethod
    async def delete_mapping(self, mapping_id: int) -> bool:
        """
        Delete mapping.

        Args:
            mapping_id: Mapping ID to delete

        Returns:
            True if deleted, False otherwise
        """
        pass
