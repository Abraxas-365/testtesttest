"""
Teams Integration Service.

Handles integration between Microsoft Teams bot and GCP agents.
Routes messages based on Azure AD group membership.
"""
import os
import logging
from typing import Optional, List, Dict
from msgraph import GraphServiceClient
from azure.identity import ClientSecretCredential

from src.services.azure_ad_router import AgentRouter, AzureADGroupMapper
from src.domain.services.agent_service import AgentService
from src.domain.ports.group_mapping_repository import GroupMappingRepository

logger = logging.getLogger(__name__)


class TeamsAgentIntegration:
    """
    Integration service for Microsoft Teams bot with GCP agents.

    This service:
    1. Receives message from Teams user
    2. Gets user's Azure AD groups via Microsoft Graph
    3. Maps groups to agent area_type
    4. Routes message to appropriate GCP agent
    5. Returns agent response to Teams
    """

    def __init__(
        self,
        agent_service: AgentService,
        group_mapping_repository: GroupMappingRepository,
        graph_tenant_id: Optional[str] = None,
        graph_client_id: Optional[str] = None,
        graph_client_secret: Optional[str] = None
    ):
        """
        Initialize Teams integration service.

        Args:
            agent_service: GCP agent service instance
            group_mapping_repository: Repository for Azure AD group mappings
            graph_tenant_id: Azure AD tenant ID
            graph_client_id: App client ID
            graph_client_secret: App client secret
        """
        self.agent_service = agent_service
        self.agent_router = AgentRouter(agent_service.repository, group_mapping_repository)

        # Initialize Microsoft Graph client
        tenant_id = graph_tenant_id or os.getenv('GRAPH_TENANT_ID')
        client_id = graph_client_id or os.getenv('GRAPH_CLIENT_ID')
        client_secret = graph_client_secret or os.getenv('GRAPH_CLIENT_SECRET')

        if tenant_id and client_id and client_secret:
            credential = ClientSecretCredential(
                tenant_id=tenant_id,
                client_id=client_id,
                client_secret=client_secret
            )
            self.graph_client = GraphServiceClient(
                credentials=credential,
                scopes=['https://graph.microsoft.com/.default']
            )
        else:
            logger.warning("Microsoft Graph credentials not configured")
            self.graph_client = None

    async def get_user_groups(self, aad_user_id: str) -> List[str]:
        """
        Get user's Azure AD group memberships.

        Args:
            aad_user_id: Azure AD user object ID

        Returns:
            List of group display names
        """
        if not self.graph_client:
            logger.error("Graph client not initialized")
            return []

        try:
            # Get user's transitive group memberships
            result = await self.graph_client.users.by_user_id(aad_user_id).transitive_member_of.get()

            if not result or not result.value:
                logger.info(f"No groups found for user {aad_user_id}")
                return []

            # Extract group display names
            group_names = [
                item.display_name for item in result.value
                if hasattr(item, 'display_name') and item.odata_type == '#microsoft.graph.group'
            ]

            logger.info(f"User {aad_user_id} groups: {group_names}")
            return group_names

        except Exception as e:
            logger.error(f"Error getting user groups: {e}")
            return []

    async def process_message(
        self,
        user_message: str,
        aad_user_id: str,
        user_name: str,
        session_id: Optional[str] = None,
        persist_session: bool = False
    ) -> Dict[str, any]:
        """
        Process a message from Teams user.

        Args:
            user_message: Message text from user
            aad_user_id: Azure AD user object ID
            user_name: User's display name
            session_id: Optional session ID for conversation continuity
            persist_session: Whether to persist session in database

        Returns:
            Dictionary with response and metadata
        """
        try:
            # Step 1: Get user's Azure AD groups
            user_groups = await self.get_user_groups(aad_user_id)

            if not user_groups:
                logger.warning(f"No groups found for user {user_name}, using general agent")
                user_groups = ['General-Users']  # Fallback

            # Step 2: Route to appropriate agent based on groups
            agent_config = await self.agent_router.get_agent_for_user(user_groups)

            if not agent_config:
                return {
                    'success': False,
                    'error': 'No suitable agent found',
                    'response': 'Sorry, I cannot process your request at this time.'
                }

            logger.info(f"Routing user '{user_name}' to agent '{agent_config.name}' (area: {agent_config.area_type})")

            # Step 3: Invoke the appropriate GCP agent
            response = await self.agent_service.invoke_agent(
                agent_id=agent_config.agent_id,
                prompt=user_message,
                user_id=aad_user_id,
                session_id=session_id,
                persist_session=persist_session
            )

            # Step 4: Return response with metadata
            return {
                'success': True,
                'response': response,
                'agent_name': agent_config.name,
                'agent_area': agent_config.area_type,
                'user_groups': user_groups,
                'session_id': session_id
            }

        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'response': 'Sorry, an error occurred while processing your message.'
            }

    async def get_user_agent_info(self, aad_user_id: str) -> Dict:
        """
        Get information about which agent(s) a user can access.

        Args:
            aad_user_id: Azure AD user object ID

        Returns:
            Dictionary with agent information
        """
        try:
            # Get user's groups
            user_groups = await self.get_user_groups(aad_user_id)

            # Get primary agent
            primary_agent = await self.agent_router.get_agent_for_user(user_groups)

            # Get all accessible agents
            accessible_agents = await self.agent_router.get_available_agents_for_user(user_groups)

            return {
                'user_groups': user_groups,
                'primary_agent': {
                    'name': primary_agent.name,
                    'description': primary_agent.description,
                    'area': primary_agent.area_type
                } if primary_agent else None,
                'accessible_agents': [
                    {
                        'name': agent.name,
                        'description': agent.description,
                        'area': agent.area_type
                    }
                    for agent in accessible_agents
                ]
            }

        except Exception as e:
            logger.error(f"Error getting user agent info: {e}")
            return {'error': str(e)}
