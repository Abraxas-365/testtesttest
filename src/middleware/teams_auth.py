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

# JWT Configuration
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24


def get_jwt_secret_key() -> str:
    """Get JWT secret key from environment variables."""
    secret_key = os.getenv("JWT_SECRET_KEY")

    if not secret_key:
        logger.warning("⚠️ JWT_SECRET_KEY not set, using fallback (NOT SECURE FOR PRODUCTION)")
        # Fallback for development only - MUST be set in production
        secret_key = "dev-secret-key-CHANGE-IN-PRODUCTION-" + os.getenv("GOOGLE_CLOUD_PROJECT", "dev")

    return secret_key


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
# JWT TOKEN MANAGEMENT (for Web OAuth2 flow)
# ============================================================================

def create_access_token(user_data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token for authenticated user.

    Args:
        user_data: User information to encode in token
        expires_delta: Optional custom expiration time

    Returns:
        str: Encoded JWT token
    """
    to_encode = user_data.copy()

    # Set expiration
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)

    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "iss": "grupodc-agent-backend",  # Issuer
        "type": "access_token"
    })

    # Encode JWT
    secret_key = get_jwt_secret_key()
    encoded_jwt = jwt.encode(to_encode, secret_key, algorithm=JWT_ALGORITHM)

    logger.info(f"✅ JWT created for user: {user_data.get('email')} (expires: {expire})")

    return encoded_jwt


def decode_access_token(token: str) -> dict:
    """
    Decode and validate a JWT access token.

    Args:
        token: JWT token string

    Returns:
        dict: Decoded token payload

    Raises:
        HTTPException: If token is invalid or expired
    """
    try:
        secret_key = get_jwt_secret_key()

        # Decode and validate JWT
        payload = jwt.decode(
            token,
            secret_key,
            algorithms=[JWT_ALGORITHM],
            options={
                "verify_signature": True,
                "verify_exp": True,
                "require_exp": True,
                "require_iat": True
            }
        )

        # Verify issuer
        if payload.get("iss") != "grupodc-agent-backend":
            raise HTTPException(status_code=401, detail="Invalid token issuer")

        # Verify token type
        if payload.get("type") != "access_token":
            raise HTTPException(status_code=401, detail="Invalid token type")

        logger.debug(f"✅ JWT validated for user: {payload.get('email')}")

        return payload

    except jwt.ExpiredSignatureError:
        logger.error("❌ JWT expired")
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as e:
        logger.error(f"❌ Invalid JWT: {str(e)}")
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
    except Exception as e:
        logger.error(f"❌ JWT validation error: {str(e)}")
        raise HTTPException(status_code=401, detail="Authentication failed")


# ============================================================================
# MULTI-MODE AUTHENTICATION (Teams SSO JWT + Web OAuth2 JWT)
# ============================================================================

async def get_user_from_request(request: Request) -> Optional[dict]:
    """
    Try to get user from multiple JWT token sources (in order of priority):
    1. Teams SSO JWT (signed by Microsoft with RS256)
    2. Web OAuth2 JWT (signed by backend with HS256)

    Returns None if no valid authentication found.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None

    token = auth_header.replace("Bearer ", "")

    # Try Teams SSO token (Microsoft JWT with RS256)
    try:
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

    except Exception as teams_error:
        logger.debug(f"Not a Teams SSO token: {str(teams_error)}")

        # Try Web OAuth2 JWT (our own JWT with HS256)
        try:
            decoded_token = decode_access_token(token)
            logger.info(f"✅ Authenticated via Web OAuth2 JWT: {decoded_token.get('email')}")

            # Return user data in standard format
            return {
                "user_id": decoded_token.get("user_id"),
                "name": decoded_token.get("name"),
                "email": decoded_token.get("email"),
                "tenant_id": decoded_token.get("tenant_id"),
            }

        except Exception as jwt_error:
            logger.debug(f"Not a valid OAuth2 JWT: {str(jwt_error)}")

    return None


async def require_auth(request: Request) -> dict:
    """
    Require authentication from any JWT token source.
    Raises HTTPException if not authenticated.
    """
    user = await get_user_from_request(request)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please provide a valid JWT token in Authorization header."
        )
    return user


async def optional_auth(request: Request) -> Optional[dict]:
    """
    Optional authentication - returns None if not authenticated.
    Does not raise exceptions.
    """
    return await get_user_from_request(request)
