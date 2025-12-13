"""RBAC Middleware - FastAPI dependencies for permission checking."""

import logging
from typing import List, Optional

from fastapi import HTTPException, Depends, Request

from src.middleware.teams_auth import get_user_from_request
from src.application.di import get_container
from src.domain.models.rbac_models import UserRBAC
from src.domain.services.rbac_service import RBACService

logger = logging.getLogger(__name__)


async def get_user_rbac(request: Request) -> UserRBAC:
    """
    FastAPI dependency that resolves the current user's RBAC context.

    This combines:
    1. JWT authentication (existing)
    2. Superadmin check
    3. Entra ID groups -> Role mapping

    Usage:
        @router.get("/protected")
        async def protected_endpoint(user: UserRBAC = Depends(get_user_rbac)):
            ...

    Returns:
        UserRBAC context with resolved role and permissions

    Raises:
        HTTPException 401 if not authenticated
    """
    # Get basic user info from existing auth
    user = await get_user_from_request(request)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Authentication required"
        )

    user_id = user.get("user_id", "")
    email = user.get("email", "")
    tenant_id = user.get("tenant_id")

    # Get Entra ID groups for this user
    container = get_container()
    entra_groups: List[str] = []

    try:
        # Try to get user's Entra groups from Microsoft Graph
        agent_service = await container.get_agent_service()
        group_mapping_repo = await container.init_group_mapping_repository()

        from src.services.teams_integration import TeamsAgentIntegration
        teams_integration = TeamsAgentIntegration(
            agent_service,
            group_mapping_repo
        )

        # Get groups from Graph API (uses user_id which should be AAD Object ID)
        entra_groups = await teams_integration.get_user_groups(user_id)
        logger.debug(f"User {email} belongs to groups: {entra_groups}")

    except Exception as e:
        logger.warning(f"Could not fetch Entra groups for {email}: {e}")
        entra_groups = []

    # Resolve RBAC using service
    rbac_repo = await container.init_rbac_repository()
    rbac_service = RBACService(rbac_repo)

    user_rbac = await rbac_service.resolve_user_rbac(
        user_id=user_id,
        email=email,
        tenant_id=tenant_id,
        entra_groups=entra_groups
    )

    # Store in request state for later use
    request.state.user_rbac = user_rbac

    return user_rbac


def require_permission(permission: str):
    """
    FastAPI dependency factory that requires a specific permission.

    Usage:
        @router.get("/agents")
        async def list_agents(
            user: UserRBAC = Depends(require_permission("agents:list"))
        ):
            ...

    Args:
        permission: Permission string to require (e.g., "agents:list")

    Returns:
        FastAPI dependency that validates the permission
    """
    async def permission_checker(
        user_rbac: UserRBAC = Depends(get_user_rbac)
    ) -> UserRBAC:
        if not user_rbac.has_permission(permission):
            logger.warning(
                f"Permission denied: {user_rbac.email} lacks '{permission}' "
                f"(role: {user_rbac.role.role_name})"
            )
            raise HTTPException(
                status_code=403,
                detail=f"Permission denied. Required: {permission}"
            )
        return user_rbac

    return permission_checker


def require_any_permission(permissions: List[str]):
    """
    FastAPI dependency that requires at least one of the specified permissions.

    Usage:
        @router.get("/resource")
        async def get_resource(
            user: UserRBAC = Depends(require_any_permission(["agents:view", "agents:list"]))
        ):
            ...

    Args:
        permissions: List of permission strings (user needs at least one)

    Returns:
        FastAPI dependency that validates permissions
    """
    async def permission_checker(
        user_rbac: UserRBAC = Depends(get_user_rbac)
    ) -> UserRBAC:
        if not user_rbac.has_any_permission(permissions):
            logger.warning(
                f"Permission denied: {user_rbac.email} lacks any of {permissions}"
            )
            raise HTTPException(
                status_code=403,
                detail=f"Permission denied. Required one of: {permissions}"
            )
        return user_rbac

    return permission_checker


def require_superadmin():
    """
    FastAPI dependency that requires superadmin status.

    Usage:
        @router.post("/admin-only")
        async def admin_endpoint(
            user: UserRBAC = Depends(require_superadmin())
        ):
            ...

    Returns:
        FastAPI dependency that validates superadmin status
    """
    async def superadmin_checker(
        user_rbac: UserRBAC = Depends(get_user_rbac)
    ) -> UserRBAC:
        if not user_rbac.is_superadmin:
            logger.warning(
                f"Superadmin required: {user_rbac.email} is not a superadmin"
            )
            raise HTTPException(
                status_code=403,
                detail="Superadmin access required"
            )
        return user_rbac

    return superadmin_checker


# Role weights for hierarchy comparison
ROLE_WEIGHTS = {
    "viewer": 100,
    "editor": 500,
    "admin": 900,
    "superadmin": 1000
}


def require_role(role_name: str):
    """
    FastAPI dependency that requires a specific role or higher.

    Roles are hierarchical by weight:
    - superadmin (1000) > admin (900) > editor (500) > viewer (100)

    Usage:
        @router.post("/editor-endpoint")
        async def editor_endpoint(
            user: UserRBAC = Depends(require_role("editor"))
        ):
            ...

    Args:
        role_name: Minimum required role name

    Returns:
        FastAPI dependency that validates role level
    """
    async def role_checker(
        user_rbac: UserRBAC = Depends(get_user_rbac)
    ) -> UserRBAC:
        required_weight = ROLE_WEIGHTS.get(role_name, 0)
        user_weight = user_rbac.role.weight

        if user_weight < required_weight:
            logger.warning(
                f"Role check failed: {user_rbac.email} has role '{user_rbac.role.role_name}' "
                f"(weight {user_weight}), but '{role_name}' (weight {required_weight}) required"
            )
            raise HTTPException(
                status_code=403,
                detail=f"Role '{role_name}' or higher required"
            )
        return user_rbac

    return role_checker


async def optional_user_rbac(request: Request) -> Optional[UserRBAC]:
    """
    FastAPI dependency for optional RBAC context.

    Returns UserRBAC if authenticated, None otherwise.
    Does not raise exceptions.

    Usage:
        @router.get("/public-or-private")
        async def mixed_endpoint(
            user: Optional[UserRBAC] = Depends(optional_user_rbac)
        ):
            if user:
                # Authenticated user
            else:
                # Anonymous access
    """
    try:
        return await get_user_rbac(request)
    except HTTPException:
        return None
    except Exception as e:
        logger.debug(f"Optional auth failed: {e}")
        return None


def get_client_ip(request: Request) -> Optional[str]:
    """
    Extract client IP from request headers.

    Checks X-Forwarded-For for proxied requests.

    Args:
        request: FastAPI request object

    Returns:
        Client IP address or None
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None
