"""
API routes for Microsoft Teams Tabs integration.
Replaces Azure Bot Framework with direct REST API calls.
"""

import os
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from src.middleware.teams_auth import validate_teams_token, get_user_from_token
from src.application.di import get_container
from src.services.teams_integration import TeamsAgentIntegration

logger = logging.getLogger(__name__)
router = APIRouter()


class TabMessageRequest(BaseModel):
    """Request from Teams Tab"""
    prompt: str
    agent_name: Optional[str] = "search_assistant"
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    mode: Optional[str] = "auto"
    source: Optional[str] = "all"


class TabMessageResponse(BaseModel):
    """Response to Teams Tab"""
    response: str
    agent_name: str
    agent_area: Optional[str] = None
    session_id: Optional[str] = None
    metadata: Optional[dict] = None


@router.post("/tabs/invoke", response_model=TabMessageResponse)
async def process_tab_message(
    request: TabMessageRequest,
    token_data: dict = Depends(validate_teams_token)
):
    """
    Process message from Teams Tab.

    This endpoint receives messages from the React frontend,
    validates authentication via Teams SSO, and routes to the appropriate agent.
    
    **Authentication:** Requires valid Teams SSO token in Authorization header.
    """
    try:
        # Extract user information from validated token
        user_info = get_user_from_token(token_data)
        user_object_id = user_info["user_id"]
        user_name = user_info["name"]
        user_email = user_info["email"]

        logger.info("="*60)
        logger.info("📨 TAB MESSAGE RECEIVED")
        logger.info("="*60)
        logger.info(f"👤 User: {user_name} ({user_email})")
        logger.info(f"🆔 User ID: {user_object_id}")
        logger.info(f"💬 Prompt: {request.prompt[:100]}...")
        logger.info(f"🤖 Agent: {request.agent_name}")
        logger.info(f"📝 Session: {request.session_id}")
        logger.info(f"🎯 Mode: {request.mode}")
        logger.info(f"📂 Source: {request.source}")

        # Get container and services
        container = get_container()
        agent_service = await container.get_agent_service()
        group_mapping_repo = await container.init_group_mapping_repository()

        # Initialize Teams integration (reusing existing logic)
        teams_integration = TeamsAgentIntegration(
            agent_service,
            group_mapping_repo
        )

        # Process message using existing agent routing logic
        result = await teams_integration.process_message(
            user_message=request.prompt,
            aad_user_id=user_object_id,
            user_name=user_name,
            session_id=request.session_id or f"tab-{user_object_id}",
            from_data={"aadObjectId": user_object_id}
        )

        if not result.get("success"):
            logger.error(f"❌ Agent processing failed: {result.get('error')}")
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Failed to process message")
            )

        response_text = result.get("response", "No response from agent")
        agent_name = result.get("agent_name", request.agent_name)
        agent_area = result.get("agent_area", "general")

        logger.info("="*60)
        logger.info("✅ TAB MESSAGE PROCESSED SUCCESSFULLY")
        logger.info("="*60)
        logger.info(f"🤖 Agent: {agent_name} ({agent_area})")
        logger.info(f"📝 Response length: {len(response_text)} chars")

        return TabMessageResponse(
            response=response_text,
            agent_name=agent_name,
            agent_area=agent_area,
            session_id=result.get("session_id"),
            metadata={
                "user_id": user_object_id,
                "user_name": user_name,
                "user_email": user_email,
                "mode": request.mode,
                "source": request.source,
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("="*60)
        logger.error("❌ ERROR PROCESSING TAB MESSAGE")
        logger.error("="*60)
        logger.error(f"Error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error processing message: {str(e)}"
        )


@router.get("/tabs/health")
async def tabs_health():
    """
    Health check endpoint for Teams Tabs integration.
    
    Returns service status and configuration info.
    """
    return {
        "status": "healthy",
        "service": "Teams Tab Backend",
        "version": "2.0.0",
        "authentication": "Teams SSO (JWT)",
        "features": {
            "sso_auth": True,
            "teams_integration": True,
            "agent_routing": True,
            "session_management": True,
            "file_support": False,  # Not implemented for tabs yet
        },
        "endpoints": {
            "invoke": "/api/v1/tabs/invoke",
            "health": "/api/v1/tabs/health",
            "user_profile": "/api/v1/tabs/user/profile"
        }
    }


@router.get("/tabs/user/profile")
async def get_user_profile(token_data: dict = Depends(validate_teams_token)):
    """
    Get authenticated user's profile information from token.
    
    This endpoint demonstrates accessing user info from the validated JWT token.
    
    **Authentication:** Requires valid Teams SSO token in Authorization header.
    """
    user_info = get_user_from_token(token_data)
    
    logger.info(f"📋 Profile requested for: {user_info['email']}")
    
    return {
        "user_id": user_info["user_id"],
        "name": user_info["name"],
        "email": user_info["email"],
        "tenant_id": user_info["tenant_id"],
        "authenticated": True,
        "source": "teams_sso"
    }


@router.post("/tabs/config")
async def get_tab_config(token_data: dict = Depends(validate_teams_token)):
    """
    Get configuration for Teams Tab.
    
    Returns frontend configuration based on authenticated user's permissions.
    """
    user_info = get_user_from_token(token_data)
    
    # You can customize this based on user's group membership, roles, etc.
    return {
        "user": user_info,
        "available_agents": [
            "search_assistant",
            "general_assistant"
        ],
        "features": {
            "file_upload": False,
            "voice_input": False,
            "history": True
        },
        "ui_settings": {
            "theme": "auto",
            "max_message_length": 4000
        }
    }
