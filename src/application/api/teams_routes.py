"""
API routes for Microsoft Teams integration.

These routes handle Teams bot webhook callbacks and route messages to GCP agents.
"""
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Optional
import logging

from src.application.di import get_container
from src.services.teams_integration import TeamsAgentIntegration

logger = logging.getLogger(__name__)

router = APIRouter()


class TeamsMessageRequest(BaseModel):
    """Teams message request model."""
    user_message: str
    aad_user_id: str
    user_name: str
    session_id: Optional[str] = None
    persist_session: bool = True  # Enable session persistence by default


class TeamsMessageResponse(BaseModel):
    """Teams message response model."""
    success: bool
    response: str
    agent_name: Optional[str] = None
    agent_area: Optional[str] = None
    user_groups: Optional[list] = None
    session_id: Optional[str] = None
    error: Optional[str] = None


@router.post("/teams/message", response_model=TeamsMessageResponse)
async def process_teams_message(request: TeamsMessageRequest):
    """
    Process a message from Microsoft Teams bot.

    This endpoint:
    1. Receives message from Teams bot
    2. Gets user's Azure AD groups
    3. Routes to appropriate agent based on groups
    4. Returns agent response

    Example Request:
    ```json
    {
        "user_message": "I need help with a contract review",
        "aad_user_id": "12345-67890-abcdef",
        "user_name": "John Doe",
        "session_id": "teams-session-123",
        "persist_session": true
    }
    ```
    """
    try:
        # Get container and services
        container = get_container()
        agent_service = await container.get_agent_service()
        group_mapping_repo = await container.init_group_mapping_repository()

        # Initialize Teams integration
        teams_integration = TeamsAgentIntegration(agent_service, group_mapping_repo)

        # Process the message
        result = await teams_integration.process_message(
            user_message=request.user_message,
            aad_user_id=request.aad_user_id,
            user_name=request.user_name,
            session_id=request.session_id,
            persist_session=request.persist_session
        )

        return TeamsMessageResponse(**result)

    except Exception as e:
        logger.error(f"Error in teams/message endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/teams/user/{aad_user_id}/agents")
async def get_user_agents(aad_user_id: str):
    """
    Get agent information for a specific user.

    Shows which agent(s) the user can access based on their Azure AD groups.

    Args:
        aad_user_id: Azure AD user object ID

    Returns:
        User's accessible agents and primary agent
    """
    try:
        container = get_container()
        agent_service = await container.get_agent_service()
        group_mapping_repo = await container.init_group_mapping_repository()

        teams_integration = TeamsAgentIntegration(agent_service, group_mapping_repo)

        result = await teams_integration.get_user_agent_info(aad_user_id)

        return result

    except Exception as e:
        logger.error(f"Error in get_user_agents endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/teams/health")
async def teams_health():
    """Health check for Teams integration."""
    return {
        "status": "healthy",
        "service": "Teams Integration",
        "features": [
            "Azure AD group-based routing",
            "Session persistence",
            "Multi-agent support"
        ]
    }
