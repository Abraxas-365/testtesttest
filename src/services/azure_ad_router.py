"""
Azure AD Group to Agent Router Service.

This service maps Azure AD groups to agent area_types for automatic routing.
Mappings are stored in database with configurable weights.
"""
from typing import Optional, Dict, List
import logging

from src.domain.ports.group_mapping_repository import GroupMappingRepository

logger = logging.getLogger(__name__)


class AzureADGroupMapper:
    """Maps Azure AD groups to agent area types using database-stored mappings."""

    def __init__(self, group_mapping_repository: GroupMappingRepository):
        """
        Initialize group mapper.

        Args:
            group_mapping_repository: Repository for group mappings
        """
        self.repository = group_mapping_repository

    async def get_area_type_from_groups(self, user_groups: List[str]) -> str:
        """
        Get the appropriate area_type based on user's Azure AD groups.

        Uses weight-based selection: if user is in multiple groups,
        the group with the highest weight determines the area_type.

        Args:
            user_groups: List of Azure AD group names the user belongs to

        Returns:
            area_type to use for agent selection (defaults to 'general')
        """
        if not user_groups:
            logger.info("No user groups found, defaulting to 'general'")
            return 'general'

        try:
            # Get mappings for all user's groups from database
            mappings = await self.repository.get_mappings_by_group_names(user_groups)

            if not mappings:
                logger.info(f"No mappings found for groups {user_groups}, defaulting to 'general'")
                return 'general'

            # Sort by weight (descending) - highest weight wins
            # Already sorted by repository, but let's be explicit
            sorted_mappings = sorted(mappings, key=lambda m: m.weight, reverse=True)

            # Use the highest weight mapping
            highest_priority = sorted_mappings[0]

            logger.info(
                f"User in {len(user_groups)} group(s). "
                f"Selected '{highest_priority.group_name}' (weight={highest_priority.weight}) "
                f"-> area_type '{highest_priority.area_type}'"
            )

            return highest_priority.area_type

        except Exception as e:
            logger.error(f"Error getting area_type from groups: {e}")
            return 'general'

    async def get_all_area_types_for_user(self, user_groups: List[str]) -> List[Dict[str, any]]:
        """
        Get all possible area_types for a user based on their groups.
        Includes weight information for transparency.

        Args:
            user_groups: List of Azure AD group names

        Returns:
            List of dicts with area_type, weight, and group_name
        """
        if not user_groups:
            return [{'area_type': 'general', 'weight': 0, 'group_name': 'default'}]

        try:
            mappings = await self.repository.get_mappings_by_group_names(user_groups)

            result = [
                {
                    'area_type': m.area_type,
                    'weight': m.weight,
                    'group_name': m.group_name,
                    'description': m.description
                }
                for m in mappings
            ]

            # Sort by weight descending
            result.sort(key=lambda x: x['weight'], reverse=True)

            # Always include 'general' as fallback if not already present
            if not any(r['area_type'] == 'general' for r in result):
                result.append({
                    'area_type': 'general',
                    'weight': 0,
                    'group_name': 'fallback',
                    'description': 'General fallback agent'
                })

            return result

        except Exception as e:
            logger.error(f"Error getting all area_types: {e}")
            return [{'area_type': 'general', 'weight': 0, 'group_name': 'error'}]

    async def can_access_area(self, user_groups: List[str], area_type: str) -> bool:
        """
        Check if user can access a specific area based on their groups.

        Args:
            user_groups: List of Azure AD group names
            area_type: area_type to check access for

        Returns:
            True if user has access, False otherwise
        """
        user_areas = await self.get_all_area_types_for_user(user_groups)
        accessible_areas = [a['area_type'] for a in user_areas]

        # Admin area grants access to everything
        if 'admin' in accessible_areas:
            return True

        return area_type in accessible_areas


class AgentRouter:
    """Routes user messages to appropriate agents based on Azure AD groups."""

    def __init__(self, agent_repository, group_mapping_repository: GroupMappingRepository):
        """
        Initialize agent router.

        Args:
            agent_repository: Repository for accessing agents
            group_mapping_repository: Repository for group mappings
        """
        self.agent_repository = agent_repository
        self.group_mapper = AzureADGroupMapper(group_mapping_repository)

    async def get_agent_for_user(self, user_groups: List[str]) -> Optional[Dict]:
        """
        Get the appropriate agent for a user based on their Azure AD groups.

        Uses weight-based selection for users in multiple groups.

        Args:
            user_groups: List of Azure AD group names

        Returns:
            Agent configuration or None
        """
        # Get area_type from user's groups (weight-based selection)
        area_type = await self.group_mapper.get_area_type_from_groups(user_groups)

        logger.info(f"Looking for agent with area_type='{area_type}'")

        # Query database for agent with matching area_type
        agents = await self.agent_repository.list_agents(enabled_only=True)

        # Find agent matching the area_type
        for agent in agents:
            if agent.area_type == area_type:
                logger.info(f"Found agent: {agent.name} (area_type={agent.area_type})")
                return agent

        # Fallback to general agent if no specific match
        logger.warning(f"No agent found for area_type='{area_type}', looking for 'general'")
        for agent in agents:
            if agent.area_type == 'general':
                logger.info(f"Using fallback agent: {agent.name}")
                return agent

        logger.error("No suitable agent found (not even 'general')")
        return None

    async def get_available_agents_for_user(self, user_groups: List[str]) -> List[Dict]:
        """
        Get all agents the user can access based on their groups.
        Sorted by weight (priority).

        Args:
            user_groups: List of Azure AD group names

        Returns:
            List of accessible agents with their weights
        """
        # Get all area_types user can access (with weights)
        area_info = await self.group_mapper.get_all_area_types_for_user(user_groups)

        logger.info(f"User can access {len(area_info)} area_types")

        # Query database for matching agents
        agents = await self.agent_repository.list_agents(enabled_only=True)

        # Build result with weight information
        accessible_agents = []
        for info in area_info:
            area_type = info['area_type']
            for agent in agents:
                if agent.area_type == area_type:
                    accessible_agents.append({
                        'agent': agent,
                        'weight': info['weight'],
                        'group_name': info['group_name'],
                        'group_description': info.get('description')
                    })
                    break

        # Sort by weight descending
        accessible_agents.sort(key=lambda x: x['weight'], reverse=True)

        logger.info(f"Found {len(accessible_agents)} accessible agents")
        return accessible_agents
