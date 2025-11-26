"""Teams SSO Token Validation Middleware"""

import os
import logging
from typing import Optional, Dict
from fastapi import HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from jwt import PyJWKClient

logger = logging.getLogger(__name__)
security = HTTPBearer()


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


# Optional: Create a dependency that can be used without enforcing authentication
async def validate_teams_token_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security, auto_error=False)
) -> Optional[dict]:
    """
    Validate Teams token but don't raise error if missing.
    Useful for endpoints that support both authenticated and unauthenticated access.
    """
    if not credentials:
        return None
    
    try:
        return await validate_teams_token(credentials)
    except HTTPException:
        return None
