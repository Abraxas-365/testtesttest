"""
API routes for Teams Tabs and Web Application.
Supports both Teams SSO (JWT tokens) and Web OAuth2 (session cookies).
"""

import os
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel

from src.middleware.teams_auth import require_auth, optional_auth
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
    tab_request: TabMessageRequest,
    request: Request,
    user: dict = Depends(require_auth)
):
    """
    Process message from Teams Tab or Web Application.

    This endpoint receives messages from the React frontend,
    validates authentication via Teams SSO or web session, and routes to the appropriate agent.

    **Authentication:** Requires valid Teams SSO token OR web session cookie.
    """
    try:
        # Extract user information from authenticated user
        user_object_id = user["user_id"]
        user_name = user["name"]
        user_email = user["email"]

        logger.info("="*60)
        logger.info("📨 TAB MESSAGE RECEIVED")
        logger.info("="*60)
        logger.info(f"👤 User: {user_name} ({user_email})")
        logger.info(f"🆔 User ID: {user_object_id}")
        logger.info(f"💬 Prompt: {tab_request.prompt[:100]}...")
        logger.info(f"🤖 Agent: {tab_request.agent_name}")
        logger.info(f"📝 Session: {tab_request.session_id}")
        logger.info(f"🎯 Mode: {tab_request.mode}")
        logger.info(f"📂 Source: {tab_request.source}")

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
            user_message=tab_request.prompt,
            aad_user_id=user_object_id,
            user_name=user_name,
            session_id=tab_request.session_id or f"tab-{user_object_id}",
            from_data={"aadObjectId": user_object_id}
        )

        if not result.get("success"):
            logger.error(f"❌ Agent processing failed: {result.get('error')}")
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Failed to process message")
            )

        response_text = result.get("response", "No response from agent")
        agent_name = result.get("agent_name", tab_request.agent_name)
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
                "mode": tab_request.mode,
                "source": tab_request.source,
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
    Health check endpoint for Teams Tabs and Web Application.

    Returns service status and configuration info.
    """
    return {
        "status": "healthy",
        "service": "Teams Tab + Web Backend",
        "version": "2.1.0",
        "authentication": "Multi-mode (Teams SSO + Web OAuth2)",
        "features": {
            "teams_sso": True,
            "web_oauth2": True,
            "teams_bot": True,  # Legacy support
            "teams_integration": True,
            "agent_routing": True,
            "session_management": True,
            "file_support": True,
            "multi_document_upload": True,
        },
        "endpoints": {
            "invoke": "/api/v1/tabs/invoke",
            "health": "/api/v1/tabs/health",
            "user_profile": "/api/v1/tabs/user/profile",
            "auth_login": "/api/v1/auth/login-url",
            "auth_callback": "/api/v1/auth/callback",
            "auth_me": "/api/v1/auth/me",
            "auth_status": "/api/v1/auth/status",
            "documents_presigned": "/api/v1/documents/presigned-url",
            "documents_confirm": "/api/v1/documents/confirm-upload",
            "documents_process": "/api/v1/documents/process"
        }
    }


@router.get("/tabs/user/profile")
async def get_user_profile(request: Request, user: dict = Depends(require_auth)):
    """
    Get authenticated user's profile information.

    **Authentication:** Requires valid Teams SSO token OR web session cookie.
    """
    logger.info(f"📋 Profile requested for: {user['email']}")

    return {
        "user_id": user["user_id"],
        "name": user["name"],
        "email": user["email"],
        "tenant_id": user.get("tenant_id"),
        "authenticated": True
    }


@router.post("/tabs/config")
async def get_tab_config(request: Request, user: dict = Depends(require_auth)):
    """
    Get configuration for Teams Tab or Web Application.

    Returns frontend configuration based on authenticated user's permissions.

    **Authentication:** Requires valid Teams SSO token OR web session cookie.
    """
    # You can customize this based on user's group membership, roles, etc.
    return {
        "user": user,
        "available_agents": [
            "search_assistant",
            "general_assistant"
        ],
        "features": {
            "file_upload": True,
            "multi_document_upload": True,
            "voice_input": False,
            "history": True
        },
        "ui_settings": {
            "theme": "auto",
            "max_message_length": 4000,
            "max_file_size_mb": 50,
            "max_files_per_request": 10
        },
        "document_endpoints": {
            "presigned_url": "/api/v1/documents/presigned-url",
            "confirm_upload": "/api/v1/documents/confirm-upload",
            "process": "/api/v1/documents/process",
            "supported_types": "/api/v1/documents/supported-types"
        }
    }
