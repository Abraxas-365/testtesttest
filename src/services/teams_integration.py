"""
Teams Integration Service.

Handles integration between Microsoft Teams bot and GCP agents.
Routes messages based on Azure AD group membership.
Sessions are ALWAYS persisted to database.

Special commands:
- "borrar session" / "clear session" / "reset" -> Clears conversation history
"""
import os
import logging
from typing import Optional, List, Dict
from msgraph import GraphServiceClient
from msgraph.generated.models.o_data_errors.o_data_error import ODataError
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
    
    All conversations are automatically persisted to database.
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

        tenant_id = graph_tenant_id or os.getenv('GRAPH_TENANT_ID')
        client_id = graph_client_id or os.getenv('GRAPH_CLIENT_ID')
        client_secret = graph_client_secret or os.getenv('GRAPH_CLIENT_SECRET')

        if tenant_id and client_id and client_secret:
            try:
                credential = ClientSecretCredential(
                    tenant_id=tenant_id,
                    client_id=client_id,
                    client_secret=client_secret
                )
                self.graph_client = GraphServiceClient(
                    credentials=credential,
                    scopes=['https://graph.microsoft.com/.default']
                )
                logger.info("✅ Microsoft Graph client initialized successfully")
            except Exception as e:
                logger.error(f"❌ Error initializing Graph client: {e}")
                self.graph_client = None
        else:
            logger.warning("⚠️ Microsoft Graph credentials not configured")
            self.graph_client = None

    def extract_aad_object_id(self, teams_user_id: str, from_data: dict = None) -> Optional[str]:
        """
        Extract Azure AD Object ID from Teams user data.
        
        Teams provides TWO user IDs:
        1. from.id = "29:xxx" (Teams channel user ID - doesn't work with Graph API)
        2. from.aadObjectId = "guid" (Azure AD object ID - works with Graph API)
        
        Args:
            teams_user_id: The Teams channel user ID (from.id)
            from_data: The complete 'from' object from Teams Activity
            
        Returns:
            Azure AD object ID or None
        """
        if from_data:
            aad_id = from_data.get('aadObjectId')
            if aad_id:
                logger.info(f"✅ Found Azure AD Object ID: {aad_id}")
                return aad_id
        
        if teams_user_id and not teams_user_id.startswith('29:'):
            import re
            if re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', teams_user_id, re.I):
                logger.info(f"✅ Using provided ID as Azure AD Object ID: {teams_user_id}")
                return teams_user_id
        
        logger.warning(f"⚠️ Could not extract Azure AD Object ID from Teams user: {teams_user_id}")
        return None

    async def get_user_groups(self, aad_user_id: str) -> List[str]:
        """
        Get user's Azure AD group memberships.

        Args:
            aad_user_id: Azure AD user object ID (NOT Teams channel ID!)

        Returns:
            List of group display names (or ['General-Users'] as fallback)
        """
        if not self.graph_client:
            logger.error("❌ Graph client not initialized")
            return ['General-Users']
        
        if not aad_user_id or aad_user_id.startswith('29:'):
            logger.error(f"❌ Invalid Azure AD Object ID: {aad_user_id}. Cannot query Microsoft Graph.")
            return ['General-Users']

        try:
            logger.info(f"🔍 Querying Microsoft Graph for user: {aad_user_id}")
            
            result = await self.graph_client.users.by_user_id(aad_user_id).transitive_member_of.get()

            if not result or not result.value:
                logger.info(f"ℹ️ No groups found for user {aad_user_id}")
                return ['General-Users']

            group_names = [
                item.display_name for item in result.value
                if hasattr(item, 'display_name') and hasattr(item, 'odata_type') and item.odata_type == '#microsoft.graph.group'
            ]

            if not group_names:
                logger.warning(f"⚠️ User {aad_user_id} has no group memberships")
                return ['General-Users']

            logger.info(f"✅ User {aad_user_id} belongs to {len(group_names)} groups: {group_names}")
            return group_names

        except ODataError as ode:
            if ode.error and ode.error.code == 'Request_ResourceNotFound':
                logger.error(f"❌ User NOT FOUND in Azure AD: {aad_user_id}")
                logger.error(f"   This user may be:")
                logger.error(f"   1. An external/guest user")
                logger.error(f"   2. Deleted from Azure AD")
                logger.error(f"   3. The aadObjectId is incorrect")
                logger.error(f"   🔄 Using fallback: General-Users group")
                return ['General-Users']
            else:
                logger.error(f"❌ Microsoft Graph ODataError: {ode.error.code if ode.error else 'Unknown'}")
                logger.error(f"   Message: {ode.error.message if ode.error and ode.error.message else 'None'}")
                return ['General-Users']

        except Exception as e:
            logger.error(f"❌ Error getting user groups from Microsoft Graph: {e}", exc_info=True)
            logger.error(f"   User ID attempted: {aad_user_id}")
            logger.error(f"   Error type: {type(e).__name__}")
            
            if hasattr(e, 'response_status_code'):
                logger.error(f"   Response status: {e.response_status_code}")
            if hasattr(e, 'message'):
                logger.error(f"   Error message: {e.message}")
            
            logger.info(f"🔄 Using fallback: General-Users group")
            return ['General-Users']

    async def clear_session_history(
        self,
        user_id: str,
        session_id: str,
        agent_id: str
    ) -> bool:
        """
        Clear all conversation history for a session.
        SIMPLE VERSION: Just delete events using asyncpg.
        
        Args:
            user_id: User identifier
            session_id: Session identifier  
            agent_id: Agent identifier
            
        Returns:
            True if deleted successfully
        """
        try:
            app_name = f"agent_{agent_id}"
            
            logger.info(f"🗑️ Clearing session history for {session_id[:20]}...")
            logger.info(f"   App: {app_name}")
            logger.info(f"   User: {user_id}")
            
            from src.application.di import get_container
            container = get_container()
            repo = await container.init_repository()
            pool = repo.pool
            
            if not pool:
                logger.error("❌ Database pool not available")
                return False
            
            async with pool.acquire() as conn:
                async with conn.transaction():
                    delete_result = await conn.execute(
                        """
                        DELETE FROM events 
                        WHERE app_name = $1 
                          AND user_id = $2 
                          AND session_id = $3
                        """,
                        app_name, user_id, session_id
                    )
                    
                    deleted_count = 0
                    if delete_result and delete_result.startswith('DELETE'):
                        try:
                            deleted_count = int(delete_result.split()[1])
                        except (IndexError, ValueError):
                            deleted_count = 0
                    
                    logger.info(f"🗑️ Deleted {deleted_count} events from session")
                    
                    update_result = await conn.execute(
                        """
                        UPDATE sessions 
                        SET state = '{}'::jsonb,
                            update_time = NOW()
                        WHERE app_name = $1 
                          AND user_id = $2 
                          AND id = $3
                        """,
                        app_name, user_id, session_id
                    )
                    
                    logger.info(f"✅ Session state reset: {update_result}")
            
            logger.info("✅ Session history cleared successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error clearing session: {e}", exc_info=True)
            return False

    async def process_message(
        self,
        user_message: str,
        aad_user_id: str,
        user_name: str,
        session_id: Optional[str] = None,
        from_data: Optional[dict] = None
    ) -> Dict[str, any]:
        """
        Process a message from Teams user.
        
        Sessions are ALWAYS persisted to database for conversation continuity.
        
        Special commands:
        - "borrar session" / "clear session" / "reset" -> Clears conversation history

        Args:
            user_message: Message text from user
            aad_user_id: User ID from Teams (could be channel ID or AAD ID)
            user_name: User's display name
            session_id: Optional session ID for conversation continuity
            from_data: Complete 'from' object from Teams Activity (contains aadObjectId)

        Returns:
            Dictionary with response and metadata
        """
        try:
            logger.info(f"💬 Processing message from {user_name}: {user_message}")
            
            real_aad_id = self.extract_aad_object_id(aad_user_id, from_data)
            
            message_lower = user_message.lower().strip()
            clear_commands = [
                "borrar session",
                "borrar sesion", 
                "clear session",
                "reset session",
                "limpiar sesion",
                "limpiar session",
                "reset",
                "borrar historial",
                "clear history",
                "nueva sesion",
                "nueva session",
                "new session",
                "reiniciar"
            ]
            
            if any(cmd in message_lower for cmd in clear_commands):
                logger.info("🗑️ Clear session command detected")
                
                user_groups = []
                if real_aad_id:
                    user_groups = await self.get_user_groups(real_aad_id)
                
                if not user_groups:
                    user_groups = ['General-Users']
                
                agent_config = await self.agent_router.get_agent_for_user(user_groups)
                
                if not agent_config:
                    return {
                        'success': False,
                        'error': 'No agent found',
                        'response': 'No pude procesar tu solicitud.'
                    }
                
                if session_id:
                    success = await self.clear_session_history(
                        user_id=real_aad_id or aad_user_id,
                        session_id=session_id,
                        agent_id=agent_config.agent_id
                    )
                    
                    if success:
                        return {
                            'success': True,
                            'response': (
                                "✅ **Sesión reiniciada exitosamente**\n\n"
                                "He borrado el historial de conversación. "
                                "Empezamos desde cero.\n\n"
                                "¿En qué puedo ayudarte?"
                            ),
                            'agent_name': agent_config.name,
                            'agent_id': agent_config.agent_id,
                            'agent_area': agent_config.area_type,
                            'action': 'session_cleared'
                        }
                    else:
                        return {
                            'success': False,
                            'response': (
                                "⚠️ Hubo un problema al borrar la sesión.\n\n"
                                "Intenta de nuevo o contacta al administrador."
                            ),
                            'agent_name': agent_config.name,
                            'action': 'session_clear_failed'
                        }
                else:
                    return {
                        'success': True,
                        'response': (
                            "ℹ️ **No hay sesión activa para borrar**\n\n"
                            "Esta es una conversación nueva.\n\n"
                            "¿En qué puedo ayudarte hoy?"
                        ),
                        'action': 'no_session_to_clear'
                    }
            
            
            user_groups = []
            if real_aad_id:
                logger.info(f"🔍 Looking up groups for AAD ID: {real_aad_id}")
                user_groups = await self.get_user_groups(real_aad_id)
            else:
                logger.warning(f"⚠️ Could not extract Azure AD ID for user {user_name}, skipping group lookup")
                user_groups = ['General-Users']

            if not user_groups:
                logger.warning(f"⚠️ No groups found for user {user_name}, using general agent")
                user_groups = ['General-Users']

            logger.info(f"👥 User groups: {user_groups}")

            agent_config = await self.agent_router.get_agent_for_user(user_groups)

            if not agent_config:
                logger.error("❌ No suitable agent found for user")
                return {
                    'success': False,
                    'error': 'No suitable agent found',
                    'response': 'Sorry, I cannot process your request at this time. Please contact your administrator.'
                }

            logger.info(f"🎯 Routing user '{user_name}' to agent '{agent_config.name}' (area: {agent_config.area_type})")

            try:
                response = await self.agent_service.invoke_agent(
                    agent_id=agent_config.agent_id,
                    prompt=user_message,
                    user_id=real_aad_id or aad_user_id,
                    session_id=session_id
                )
            except Exception as agent_error:
                logger.error(f"❌ Error invoking agent {agent_config.agent_id}: {agent_error}", exc_info=True)
                return {
                    'success': False,
                    'error': f'Agent error: {str(agent_error)}',
                    'response': 'Sorry, there was an error processing your message. Please try again.'
                }

            return {
                'success': True,
                'response': response,
                'agent_name': agent_config.name,
                'agent_id': agent_config.agent_id,
                'agent_area': agent_config.area_type,
                'user_groups': user_groups,
                'session_id': session_id,
                'aad_object_id': real_aad_id
            }

        except Exception as e:
            logger.error(f"❌ Error processing message: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'response': 'Sorry, an error occurred while processing your message. Please try again or contact support.'
            }

    async def get_user_agent_info(self, aad_user_id: str, from_data: Optional[dict] = None) -> Dict:
        """
        Get information about which agent(s) a user can access.

        Args:
            aad_user_id: User ID from Teams
            from_data: Complete 'from' object from Teams Activity

        Returns:
            Dictionary with agent information
        """
        try:
            real_aad_id = self.extract_aad_object_id(aad_user_id, from_data)
            
            user_groups = []
            if real_aad_id:
                user_groups = await self.get_user_groups(real_aad_id)
            
            if not user_groups:
                user_groups = ['General-Users']

            primary_agent = await self.agent_router.get_agent_for_user(user_groups)

            accessible_agents = await self.agent_router.get_available_agents_for_user(user_groups)

            return {
                'user_groups': user_groups,
                'aad_object_id': real_aad_id,
                'primary_agent': {
                    'agent_id': primary_agent.agent_id,
                    'name': primary_agent.name,
                    'description': primary_agent.description,
                    'area': primary_agent.area_type
                } if primary_agent else None,
                'accessible_agents': [
                    {
                        'agent_id': info['agent'].agent_id,
                        'name': info['agent'].name,
                        'description': info['agent'].description,
                        'area': info['agent'].area_type,
                        'weight': info['weight']
                    }
                    for info in accessible_agents
                ]
            }

        except Exception as e:
            logger.error(f"❌ Error getting user agent info: {e}", exc_info=True)
            return {'error': str(e)}
