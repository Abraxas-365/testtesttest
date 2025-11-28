"""Multi-Mode Authentication Middleware for Teams Bot, Teams Tabs, and Web"""

import os
import logging
from typing import Optional, Dict
from fastapi import HTTPException, Security, Depends, Request, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from jwt import PyJWKClient
from datetime import datetime, timedelta
import secrets

logger = logging.getLogger(__name__)
security = HTTPBearer()

# Simple in-memory session store (use Redis in production)
SESSION_STORE: Dict[str, Dict] = {}


def get_azure_config() -> Dict[str, str]:
    """Get Azure AD configuration from environment variables."""
    tenant_id = os.getenv("AZURE_TENANT_ID")
    client_id = os.getenv("AZURE_CLIENT_ID")
    
    if not tenant_id or not client_id:
        logger.error("❌ AZURE_TENANT_ID or AZURE_CLIENT_ID not set")
        raise HTTPException(
            status_code=500,
            detail="Azure AD configuration missing. Please set AZURE_TENANT_ID and AZURE_CLIENT_ID environment variables."
        )
    
    return {
        "tenant_id": tenant_id,
        "client_id": client_id,
        "jwks_uri": f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys",
        "issuer": f"https://login.microsoftonline.com/{tenant_id}/v2.0"
    }


async def validate_teams_token(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> dict:
    """
    Validate JWT token from Teams SSO.

    Args:
        credentials: HTTP Authorization header credentials

    Returns:
        dict: Decoded token payload containing user information

    Raises:
        HTTPException: If token is invalid or expired
    """
    token = credentials.credentials

    try:
        # Get Azure AD configuration
        config = get_azure_config()
        
        # Get signing keys from Microsoft
        jwks_client = PyJWKClient(config["jwks_uri"], cache_keys=True)
        signing_key = jwks_client.get_signing_key_from_jwt(token)

        # Decode and validate token
        decoded_token = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=config["client_id"],  # Your app's client ID
            issuer=config["issuer"],
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_aud": True,
                "verify_iss": True,
            }
        )

        logger.info(f"✅ Token validated for user: {decoded_token.get('preferred_username')}")

        return decoded_token

    except jwt.ExpiredSignatureError:
        logger.error("❌ Token expired")
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidAudienceError:
        logger.error("❌ Invalid token audience")
        raise HTTPException(status_code=401, detail="Invalid token audience")
    except jwt.InvalidIssuerError:
        logger.error("❌ Invalid token issuer")
        raise HTTPException(status_code=401, detail="Invalid token issuer")
    except jwt.InvalidTokenError as e:
        logger.error(f"❌ Invalid token: {str(e)}")
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
    except Exception as e:
        logger.error(f"❌ Token validation error: {str(e)}")
        raise HTTPException(status_code=401, detail="Authentication failed")


def get_user_from_token(token_data: dict) -> dict:
    """
    Extract user information from decoded token.

    Args:
        token_data: Decoded JWT token

    Returns:
        dict: User information
    """
    return {
        "user_id": token_data.get("oid"),  # Azure AD Object ID
        "name": token_data.get("name"),
        "email": token_data.get("preferred_username") or token_data.get("upn"),
        "tenant_id": token_data.get("tid"),
    }


# ============================================================================
# SESSION MANAGEMENT (for Web OAuth2 flow)
# ============================================================================

def create_session(user_data: dict) -> str:
    """Create a new session and return session ID."""
    session_id = secrets.token_urlsafe(32)
    SESSION_STORE[session_id] = {
        "user_data": user_data,
        "created_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(hours=24)
    }
    logger.info(f"✅ Session created for user: {user_data.get('email')}")
    return session_id


def get_session(session_id: str) -> Optional[dict]:
    """Get session data by session ID."""
    session = SESSION_STORE.get(session_id)
    if not session:
        return None

    # Check if session expired
    if datetime.utcnow() > session["expires_at"]:
        del SESSION_STORE[session_id]
        return None

    return session["user_data"]


def delete_session(session_id: str):
    """Delete a session."""
    if session_id in SESSION_STORE:
        del SESSION_STORE[session_id]


# ============================================================================
# MULTI-MODE AUTHENTICATION (Teams SSO + Web Session + Optional)
# ============================================================================

async def get_user_from_request(request: Request) -> Optional[dict]:
    """
    Try to get user from multiple sources (in order of priority):
    1. Bearer token (Teams SSO)
    2. Session cookie (Web OAuth2)

    Returns None if no valid authentication found.
    """
    # Try Teams SSO token first
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        try:
            token = auth_header.replace("Bearer ", "")
            config = get_azure_config()
            jwks_client = PyJWKClient(config["jwks_uri"], cache_keys=True)
            signing_key = jwks_client.get_signing_key_from_jwt(token)

            decoded_token = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=config["client_id"],
                issuer=config["issuer"],
                options={
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_aud": True,
                    "verify_iss": True,
                }
            )
            logger.info(f"✅ Authenticated via Teams SSO: {decoded_token.get('preferred_username')}")
            return get_user_from_token(decoded_token)
        except Exception as e:
            logger.debug(f"Bearer token validation failed: {str(e)}")

    # Try session cookie
    session_id = request.cookies.get("session_id")
    if session_id:
        user_data = get_session(session_id)
        if user_data:
            logger.info(f"✅ Authenticated via session: {user_data.get('email')}")
            return user_data

    return None


async def require_auth(request: Request) -> dict:
    """
    Require authentication from any source.
    Raises HTTPException if not authenticated.
    """
    user = await get_user_from_request(request)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please provide a valid Bearer token or login session."
        )
    return user


async def optional_auth(request: Request) -> Optional[dict]:
    """
    Optional authentication - returns None if not authenticated.
    Does not raise exceptions.
    """
    return await get_user_from_request(request)
