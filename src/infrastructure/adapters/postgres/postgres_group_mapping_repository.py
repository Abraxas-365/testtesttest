"""PostgreSQL implementation of GroupMappingRepository."""

from typing import List, Optional
from asyncpg import Pool

from src.domain.ports.group_mapping_repository import GroupMappingRepository
from src.domain.models.azure_ad_models import AzureADGroupMapping


class PostgresGroupMappingRepository(GroupMappingRepository):
    """PostgreSQL adapter for Azure AD group mappings."""

    def __init__(self, pool: Pool):
        """
        Initialize repository.

        Args:
            pool: AsyncPG connection pool
        """
        self.pool = pool

    async def get_all_mappings(self, enabled_only: bool = True) -> List[AzureADGroupMapping]:
        """Get all group mappings."""
        query = """
            SELECT mapping_id, group_name, area_type, weight, description, enabled, created_at, updated_at
            FROM azure_ad_group_mappings
            WHERE enabled = TRUE OR $1 = FALSE
            ORDER BY weight DESC, group_name ASC
        """

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, enabled_only)

            return [
                AzureADGroupMapping(
                    mapping_id=row['mapping_id'],
                    group_name=row['group_name'],
                    area_type=row['area_type'],
                    weight=row['weight'],
                    description=row['description'],
                    enabled=row['enabled'],
                    created_at=row['created_at'],
                    updated_at=row['updated_at']
                )
                for row in rows
            ]

    async def get_mapping_by_group_name(self, group_name: str) -> Optional[AzureADGroupMapping]:
        """Get mapping for specific group."""
        query = """
            SELECT mapping_id, group_name, area_type, weight, description, enabled, created_at, updated_at
            FROM azure_ad_group_mappings
            WHERE group_name = $1 AND enabled = TRUE
        """

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, group_name)

            if not row:
                return None

            return AzureADGroupMapping(
                mapping_id=row['mapping_id'],
                group_name=row['group_name'],
                area_type=row['area_type'],
                weight=row['weight'],
                description=row['description'],
                enabled=row['enabled'],
                created_at=row['created_at'],
                updated_at=row['updated_at']
            )

    async def get_mappings_by_group_names(self, group_names: List[str]) -> List[AzureADGroupMapping]:
        """Get mappings for multiple groups."""
        if not group_names:
            return []

        query = """
            SELECT mapping_id, group_name, area_type, weight, description, enabled, created_at, updated_at
            FROM azure_ad_group_mappings
            WHERE group_name = ANY($1) AND enabled = TRUE
            ORDER BY weight DESC, group_name ASC
        """

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, group_names)

            return [
                AzureADGroupMapping(
                    mapping_id=row['mapping_id'],
                    group_name=row['group_name'],
                    area_type=row['area_type'],
                    weight=row['weight'],
                    description=row['description'],
                    enabled=row['enabled'],
                    created_at=row['created_at'],
                    updated_at=row['updated_at']
                )
                for row in rows
            ]

    async def create_mapping(
        self,
        group_name: str,
        area_type: str,
        weight: int,
        description: Optional[str] = None,
        enabled: bool = True
    ) -> AzureADGroupMapping:
        """Create new group mapping."""
        query = """
            INSERT INTO azure_ad_group_mappings (group_name, area_type, weight, description, enabled)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING mapping_id, group_name, area_type, weight, description, enabled, created_at, updated_at
        """

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, group_name, area_type, weight, description, enabled)

            return AzureADGroupMapping(
                mapping_id=row['mapping_id'],
                group_name=row['group_name'],
                area_type=row['area_type'],
                weight=row['weight'],
                description=row['description'],
                enabled=row['enabled'],
                created_at=row['created_at'],
                updated_at=row['updated_at']
            )

    async def update_mapping(
        self,
        mapping_id: int,
        area_type: Optional[str] = None,
        weight: Optional[int] = None,
        description: Optional[str] = None,
        enabled: Optional[bool] = None
    ) -> Optional[AzureADGroupMapping]:
        """Update existing mapping."""
        # Build dynamic UPDATE query
        updates = []
        params = []
        param_count = 1

        if area_type is not None:
            updates.append(f"area_type = ${param_count}")
            params.append(area_type)
            param_count += 1

        if weight is not None:
            updates.append(f"weight = ${param_count}")
            params.append(weight)
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
            # Nothing to update
            return await self.get_mapping_by_id(mapping_id)

        params.append(mapping_id)

        query = f"""
            UPDATE azure_ad_group_mappings
            SET {', '.join(updates)}
            WHERE mapping_id = ${param_count}
            RETURNING mapping_id, group_name, area_type, weight, description, enabled, created_at, updated_at
        """

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, *params)

            if not row:
                return None

            return AzureADGroupMapping(
                mapping_id=row['mapping_id'],
                group_name=row['group_name'],
                area_type=row['area_type'],
                weight=row['weight'],
                description=row['description'],
                enabled=row['enabled'],
                created_at=row['created_at'],
                updated_at=row['updated_at']
            )

    async def delete_mapping(self, mapping_id: int) -> bool:
        """Delete mapping."""
        query = "DELETE FROM azure_ad_group_mappings WHERE mapping_id = $1"

        async with self.pool.acquire() as conn:
            result = await conn.execute(query, mapping_id)
            return result == "DELETE 1"

    async def get_mapping_by_id(self, mapping_id: int) -> Optional[AzureADGroupMapping]:
        """Get mapping by ID."""
        query = """
            SELECT mapping_id, group_name, area_type, weight, description, enabled, created_at, updated_at
            FROM azure_ad_group_mappings
            WHERE mapping_id = $1
        """

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, mapping_id)

            if not row:
                return None

            return AzureADGroupMapping(
                mapping_id=row['mapping_id'],
                group_name=row['group_name'],
                area_type=row['area_type'],
                weight=row['weight'],
                description=row['description'],
                enabled=row['enabled'],
                created_at=row['created_at'],
                updated_at=row['updated_at']
            )
