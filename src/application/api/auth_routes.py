"""OAuth2 Authentication Routes for Web Application (JWT-based)"""

import os
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Response, Request
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel
import httpx
from urllib.parse import urlencode

from src.middleware.teams_auth import (
    get_azure_config,
    create_access_token,
    get_user_from_request,
    require_auth,
    optional_auth
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================================================
# MODELS
# ============================================================================

class LoginUrlResponse(BaseModel):
    login_url: str
    state: str


class UserInfoResponse(BaseModel):
    user_id: str
    name: str
    email: str
    tenant_id: Optional[str] = None
    authenticated: bool = True


# ============================================================================
# OAUTH2 ENDPOINTS
# ============================================================================

@router.get("/auth/login-url", response_model=LoginUrlResponse)
async def get_login_url(redirect_uri: Optional[str] = None):
    """
    Get Microsoft OAuth2 login URL for web application.

    This endpoint generates the URL that the frontend should redirect to
    for Microsoft authentication.

    Args:
        redirect_uri: Optional redirect URI (defaults to AZURE_REDIRECT_URI env var)

    Returns:
        LoginUrlResponse with login_url and state
    """
    try:
        config = get_azure_config()
        tenant_id = config["tenant_id"]
        client_id = config["client_id"]

        # Get redirect URI from parameter or environment
        if not redirect_uri:
            redirect_uri = os.getenv("AZURE_REDIRECT_URI")
            if not redirect_uri:
                raise HTTPException(
                    status_code=500,
                    detail="AZURE_REDIRECT_URI not configured"
                )

        # Generate state for CSRF protection
        import secrets
        state = secrets.token_urlsafe(32)

        # Build authorization URL
        auth_params = {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "response_mode": "query",
            "scope": "openid profile email User.Read",
            "state": state,
        }

        auth_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize?{urlencode(auth_params)}"

        logger.info(f"✅ Generated login URL for redirect_uri: {redirect_uri}")

        return LoginUrlResponse(login_url=auth_url, state=state)

    except Exception as e:
        logger.error(f"❌ Error generating login URL: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to generate login URL: {str(e)}")


@router.get("/auth/callback")
async def auth_callback(
    code: str,
    state: str,
    error: Optional[str] = None,
    error_description: Optional[str] = None
):
    """
    OAuth2 callback endpoint that handles the redirect from Microsoft.

    This endpoint:
    1. Receives the authorization code from Microsoft
    2. Exchanges it for an access token
    3. Gets user information from ID token
    4. Creates a JWT access token
    5. Redirects to frontend with JWT in URL fragment

    Args:
        code: Authorization code from Microsoft
        state: CSRF state token
        error: Optional error from Microsoft
        error_description: Optional error description

    Returns:
        Redirect to frontend with JWT token in URL fragment (#token=xxx)
    """
    # Check for errors from Microsoft
    if error:
        logger.error(f"❌ OAuth2 error: {error} - {error_description}")
        # Redirect to frontend with error
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
        return RedirectResponse(
            url=f"{frontend_url}/auth/error?error={error}&description={error_description}"
        )

    try:
        config = get_azure_config()
        tenant_id = config["tenant_id"]
        client_id = config["client_id"]
        client_secret = os.getenv("AZURE_CLIENT_SECRET")

        if not client_secret:
            raise HTTPException(
                status_code=500,
                detail="AZURE_CLIENT_SECRET not configured"
            )

        redirect_uri = os.getenv("AZURE_REDIRECT_URI")
        if not redirect_uri:
            raise HTTPException(
                status_code=500,
                detail="AZURE_REDIRECT_URI not configured"
            )

        # Exchange authorization code for access token
        token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
        token_data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "scope": "openid profile email User.Read",
        }

        async with httpx.AsyncClient() as client:
            token_response = await client.post(token_url, data=token_data)

            if token_response.status_code != 200:
                logger.error(f"❌ Token exchange failed: {token_response.text}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Token exchange failed: {token_response.text}"
                )

            tokens = token_response.json()
            access_token = tokens.get("access_token")
            id_token = tokens.get("id_token")

            # Decode ID token to get user info
            import jwt
            decoded_id_token = jwt.decode(
                id_token,
                options={"verify_signature": False}  # Already validated by Microsoft
            )

            # Create user data
            user_data = {
                "user_id": decoded_id_token.get("oid"),
                "name": decoded_id_token.get("name"),
                "email": decoded_id_token.get("preferred_username") or decoded_id_token.get("email"),
                "tenant_id": decoded_id_token.get("tid"),
            }

            # Create JWT access token
            access_token_jwt = create_access_token(user_data)

            # Redirect to frontend with JWT in URL fragment (hash)
            # Using fragment (#) is more secure than query params (?)
            # because fragments are not sent to the server on redirect
            frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
            redirect_url = f"{frontend_url}/auth/success#token={access_token_jwt}"

            logger.info(f"✅ User logged in successfully: {user_data.get('email')}")

            return RedirectResponse(url=redirect_url)

    except Exception as e:
        logger.error(f"❌ Authentication callback error: {str(e)}")
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
        return RedirectResponse(
            url=f"{frontend_url}/auth/error?error=server_error&description={str(e)}"
        )


@router.post("/auth/logout")
async def logout():
    """
    Logout endpoint for JWT-based authentication.

    Note: With JWT tokens, logout is handled client-side by deleting the token
    from localStorage/sessionStorage. This endpoint exists for consistency
    but doesn't need to do anything on the server side.

    The client should:
    1. Delete the JWT token from storage
    2. Clear any cached user data
    3. Redirect to login page

    Returns:
        Success message
    """
    logger.info(f"✅ Logout request received (JWT-based, no server-side action needed)")

    return {
        "message": "Logged out successfully",
        "note": "Please delete the JWT token from client storage"
    }


@router.get("/auth/me", response_model=UserInfoResponse)
async def get_current_user(request: Request):
    """
    Get current authenticated user information.

    Works with both Teams SSO tokens and web sessions.

    Returns:
        UserInfoResponse with user information
    """
    user = await require_auth(request)

    return UserInfoResponse(
        user_id=user["user_id"],
        name=user["name"],
        email=user["email"],
        tenant_id=user.get("tenant_id"),
        authenticated=True
    )


@router.get("/auth/status")
async def auth_status(request: Request):
    """
    Check authentication status without requiring authentication.

    Returns:
        Authentication status and user info if authenticated
    """
    user = await optional_auth(request)

    if user:
        return {
            "authenticated": True,
            "user": {
                "user_id": user["user_id"],
                "name": user["name"],
                "email": user["email"],
                "tenant_id": user.get("tenant_id"),
            }
        }
    else:
        return {
            "authenticated": False,
            "user": None
        }
