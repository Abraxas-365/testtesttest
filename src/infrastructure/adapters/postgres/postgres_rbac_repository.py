"""PostgreSQL implementation of RBACRepository."""

import json
import logging
from typing import List, Optional
from asyncpg import Pool

from src.domain.ports.rbac_repository import RBACRepository
from src.domain.models.rbac_models import (
    Role, SuperadminEntry, EntraGroupRoleMapping
)

logger = logging.getLogger(__name__)


class PostgresRBACRepository(RBACRepository):
    """PostgreSQL adapter for RBAC operations."""

    def __init__(self, pool: Pool):
        """
        Initialize repository.

        Args:
            pool: AsyncPG connection pool
        """
        self.pool = pool

    # ============================================
    # SUPERADMIN WHITELIST
    # ============================================

    async def is_superadmin(self, email: str) -> bool:
        """Check if email is in the superadmin whitelist."""
        query = """
            SELECT EXISTS(
                SELECT 1 FROM superadmin_whitelist
                WHERE LOWER(email) = LOWER($1) AND enabled = TRUE
            )
        """
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, email)

    async def list_superadmins(self) -> List[SuperadminEntry]:
        """List all enabled superadmin entries."""
        query = """
            SELECT whitelist_id, email, added_by_email, added_at, notes, enabled
            FROM superadmin_whitelist
            WHERE enabled = TRUE
            ORDER BY added_at DESC
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query)
            return [self._row_to_superadmin(row) for row in rows]

    async def add_superadmin(
        self,
        email: str,
        added_by_email: str,
        notes: Optional[str] = None
    ) -> SuperadminEntry:
        """Add email to superadmin whitelist."""
        query = """
            INSERT INTO superadmin_whitelist (email, added_by_email, notes)
            VALUES (LOWER($1), $2, $3)
            RETURNING whitelist_id, email, added_by_email, added_at, notes, enabled
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, email, added_by_email, notes)
            return self._row_to_superadmin(row)

    async def remove_superadmin(self, email: str) -> bool:
        """Remove email from superadmin whitelist (soft delete)."""
        query = """
            UPDATE superadmin_whitelist
            SET enabled = FALSE
            WHERE LOWER(email) = LOWER($1) AND enabled = TRUE
        """
        async with self.pool.acquire() as conn:
            result = await conn.execute(query, email)
            return result == "UPDATE 1"

    def _row_to_superadmin(self, row) -> SuperadminEntry:
        """Convert database row to SuperadminEntry."""
        return SuperadminEntry(
            whitelist_id=row['whitelist_id'],
            email=row['email'],
            added_by_email=row['added_by_email'],
            added_at=row['added_at'],
            notes=row['notes'],
            enabled=row['enabled']
        )

    # ============================================
    # ROLES
    # ============================================

    async def get_role(self, role_name: str) -> Optional[Role]:
        """Get role by name."""
        query = """
            SELECT role_id, role_name, display_name, description, weight,
                   permissions, enabled, created_at, updated_at
            FROM rbac_roles
            WHERE role_name = $1 AND enabled = TRUE
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, role_name)
            if not row:
                return None
            return self._row_to_role(row)

    async def get_all_roles(self) -> List[Role]:
        """Get all enabled roles."""
        query = """
            SELECT role_id, role_name, display_name, description, weight,
                   permissions, enabled, created_at, updated_at
            FROM rbac_roles
            WHERE enabled = TRUE
            ORDER BY weight DESC
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query)
            return [self._row_to_role(row) for row in rows]

    async def get_default_role(self) -> Role:
        """Get the default role for users with no group mappings."""
        role = await self.get_role("viewer")
        if not role:
            raise RuntimeError("Default 'viewer' role not found in database")
        return role

    def _row_to_role(self, row) -> Role:
        """Convert database row to Role."""
        permissions = row['permissions']
        if isinstance(permissions, str):
            permissions = json.loads(permissions)
        return Role(
            role_id=row['role_id'],
            role_name=row['role_name'],
            display_name=row['display_name'],
            description=row['description'],
            weight=row['weight'],
            permissions=permissions,
            enabled=row['enabled'],
            created_at=row['created_at'],
            updated_at=row['updated_at']
        )

    # ============================================
    # ENTRA GROUP -> ROLE MAPPINGS
    # ============================================

    async def get_role_for_groups(self, group_names: List[str]) -> Optional[Role]:
        """Get the highest-priority role for given groups."""
        if not group_names:
            return None

        query = """
            SELECT r.role_id, r.role_name, r.display_name, r.description,
                   r.weight, r.permissions, r.enabled, r.created_at, r.updated_at
            FROM entra_group_role_mappings m
            JOIN rbac_roles r ON m.role_name = r.role_name
            WHERE m.group_name = ANY($1)
              AND m.enabled = TRUE
              AND r.enabled = TRUE
            ORDER BY r.weight DESC
            LIMIT 1
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, group_names)
            if not row:
                return None
            return self._row_to_role(row)

    async def list_group_role_mappings(
        self, enabled_only: bool = True
    ) -> List[EntraGroupRoleMapping]:
        """List all group to role mappings."""
        query = """
            SELECT mapping_id, group_id, group_name, role_name, description,
                   enabled, created_by_email, created_at, updated_at
            FROM entra_group_role_mappings
            WHERE enabled = TRUE OR $1 = FALSE
            ORDER BY group_name ASC
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, enabled_only)
            return [self._row_to_mapping(row) for row in rows]

    async def get_group_role_mapping(
        self, group_name: str
    ) -> Optional[EntraGroupRoleMapping]:
        """Get mapping for specific group."""
        query = """
            SELECT mapping_id, group_id, group_name, role_name, description,
                   enabled, created_by_email, created_at, updated_at
            FROM entra_group_role_mappings
            WHERE group_name = $1
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, group_name)
            if not row:
                return None
            return self._row_to_mapping(row)

    async def get_group_role_mapping_by_id(
        self, mapping_id: int
    ) -> Optional[EntraGroupRoleMapping]:
        """Get mapping by ID."""
        query = """
            SELECT mapping_id, group_id, group_name, role_name, description,
                   enabled, created_by_email, created_at, updated_at
            FROM entra_group_role_mappings
            WHERE mapping_id = $1
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, mapping_id)
            if not row:
                return None
            return self._row_to_mapping(row)

    async def create_group_role_mapping(
        self,
        group_name: str,
        role_name: str,
        created_by_email: str,
        group_id: Optional[str] = None,
        description: Optional[str] = None
    ) -> EntraGroupRoleMapping:
        """Create new group to role mapping."""
        query = """
            INSERT INTO entra_group_role_mappings
            (group_id, group_name, role_name, description, created_by_email)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING mapping_id, group_id, group_name, role_name, description,
                      enabled, created_by_email, created_at, updated_at
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                query, group_id, group_name, role_name, description, created_by_email
            )
            return self._row_to_mapping(row)

    async def update_group_role_mapping(
        self,
        mapping_id: int,
        role_name: Optional[str] = None,
        description: Optional[str] = None,
        enabled: Optional[bool] = None
    ) -> Optional[EntraGroupRoleMapping]:
        """Update existing mapping."""
        updates = []
        params = []
        param_count = 1

        if role_name is not None:
            updates.append(f"role_name = ${param_count}")
            params.append(role_name)
            param_count += 1

        if description is not None:
            updates.append(f"description = ${param_count}")
            params.append(description)
            param_count += 1

        if enabled is not None:
            updates.append(f"enabled = ${param_count}")
            params.append(enabled)
            param_count += 1

        if not updates:
            return await self.get_group_role_mapping_by_id(mapping_id)

        params.append(mapping_id)

        query = f"""
            UPDATE entra_group_role_mappings
            SET {', '.join(updates)}
            WHERE mapping_id = ${param_count}
            RETURNING mapping_id, group_id, group_name, role_name, description,
                      enabled, created_by_email, created_at, updated_at
        """

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, *params)
            if not row:
                return None
            return self._row_to_mapping(row)

    async def delete_group_role_mapping(self, mapping_id: int) -> bool:
        """Delete group to role mapping."""
        query = "DELETE FROM entra_group_role_mappings WHERE mapping_id = $1"
        async with self.pool.acquire() as conn:
            result = await conn.execute(query, mapping_id)
            return result == "DELETE 1"

    def _row_to_mapping(self, row) -> EntraGroupRoleMapping:
        """Convert database row to EntraGroupRoleMapping."""
        return EntraGroupRoleMapping(
            mapping_id=row['mapping_id'],
            group_id=row['group_id'],
            group_name=row['group_name'],
            role_name=row['role_name'],
            description=row['description'],
            enabled=row['enabled'],
            created_by_email=row['created_by_email'],
            created_at=row['created_at'],
            updated_at=row['updated_at']
        )

    # ============================================
    # AUDIT LOG
    # ============================================

    async def log_audit_event(
        self,
        action: str,
        performed_by_email: str,
        target_resource: str,
        target_id: Optional[str] = None,
        old_value: Optional[dict] = None,
        new_value: Optional[dict] = None,
        ip_address: Optional[str] = None
    ) -> None:
        """Log an RBAC audit event."""
        query = """
            INSERT INTO rbac_audit_log
            (action, performed_by_email, target_resource, target_id,
             old_value, new_value, ip_address)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
        """
        async with self.pool.acquire() as conn:
            await conn.execute(
                query,
                action,
                performed_by_email,
                target_resource,
                target_id,
                json.dumps(old_value) if old_value else None,
                json.dumps(new_value) if new_value else None,
                ip_address
            )
            logger.info(
                f"RBAC Audit: {action} by {performed_by_email} on "
                f"{target_resource}:{target_id or 'N/A'}"
            )
