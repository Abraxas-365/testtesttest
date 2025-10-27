"""PostgreSQL adapter implementation of CorpusRepository port."""

import json
from typing import Optional
from asyncpg import Pool

from src.domain.models import CorpusConfig
from src.domain.ports import CorpusRepository


class PostgresCorpusRepository(CorpusRepository):
    """
    PostgreSQL implementation of the CorpusRepository port.

    This adapter connects to a PostgreSQL database and implements
    all methods defined in the CorpusRepository interface.
    """

    def __init__(self, pool: Pool):
        """
        Initialize the PostgreSQL corpus repository.

        Args:
            pool: AsyncPG connection pool
        """
        self.pool = pool

    async def get_corpus_by_id(self, corpus_id: str) -> Optional[CorpusConfig]:
        """Get corpus configuration by ID."""
        query = """
            SELECT
                corpus_id,
                corpus_name,
                display_name,
                description,
                vertex_corpus_name,
                embedding_model,
                vector_db_type,
                vector_db_config,
                document_count,
                chunk_size,
                chunk_overlap,
                metadata,
                enabled
            FROM corpuses
            WHERE corpus_id = $1
        """

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, corpus_id)
            if not row:
                return None
            return self._row_to_corpus_config(row)

    async def get_corpus_by_name(self, corpus_name: str) -> Optional[CorpusConfig]:
        """Get corpus configuration by name."""
        query = """
            SELECT
                corpus_id,
                corpus_name,
                display_name,
                description,
                vertex_corpus_name,
                embedding_model,
                vector_db_type,
                vector_db_config,
                document_count,
                chunk_size,
                chunk_overlap,
                metadata,
                enabled
            FROM corpuses
            WHERE corpus_name = $1
        """

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, corpus_name)
            if not row:
                return None
            return self._row_to_corpus_config(row)

    async def list_corpuses(self, enabled_only: bool = True) -> list[CorpusConfig]:
        """List all corpus configurations."""
        query = """
            SELECT
                corpus_id,
                corpus_name,
                display_name,
                description,
                vertex_corpus_name,
                embedding_model,
                vector_db_type,
                vector_db_config,
                document_count,
                chunk_size,
                chunk_overlap,
                metadata,
                enabled
            FROM corpuses
        """

        if enabled_only:
            query += " WHERE enabled = true"

        query += " ORDER BY corpus_name"

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query)
            return [self._row_to_corpus_config(row) for row in rows]

    async def get_corpuses_for_agent(self, agent_id: str) -> list[CorpusConfig]:
        """Get all corpuses for a specific agent."""
        query = """
            SELECT
                c.corpus_id,
                c.corpus_name,
                c.display_name,
                c.description,
                c.vertex_corpus_name,
                c.embedding_model,
                c.vector_db_type,
                c.vector_db_config,
                c.document_count,
                c.chunk_size,
                c.chunk_overlap,
                c.metadata,
                c.enabled,
                ac.priority
            FROM corpuses c
            INNER JOIN agent_corpuses ac ON c.corpus_id = ac.corpus_id
            WHERE ac.agent_id = $1 AND c.enabled = true
            ORDER BY ac.priority ASC, c.corpus_name
        """

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, agent_id)
            return [self._row_to_corpus_config(row) for row in rows]

    async def save_corpus(self, corpus: CorpusConfig) -> CorpusConfig:
        """Save or update a corpus configuration."""
        query = """
            INSERT INTO corpuses (
                corpus_id, corpus_name, display_name, description,
                vertex_corpus_name, embedding_model, vector_db_type,
                vector_db_config, document_count, chunk_size, chunk_overlap,
                metadata, enabled
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            ON CONFLICT (corpus_id) DO UPDATE SET
                corpus_name = EXCLUDED.corpus_name,
                display_name = EXCLUDED.display_name,
                description = EXCLUDED.description,
                vertex_corpus_name = EXCLUDED.vertex_corpus_name,
                embedding_model = EXCLUDED.embedding_model,
                vector_db_type = EXCLUDED.vector_db_type,
                vector_db_config = EXCLUDED.vector_db_config,
                document_count = EXCLUDED.document_count,
                chunk_size = EXCLUDED.chunk_size,
                chunk_overlap = EXCLUDED.chunk_overlap,
                metadata = EXCLUDED.metadata,
                enabled = EXCLUDED.enabled,
                updated_at = NOW()
            RETURNING *
        """

        async with self.pool.acquire() as conn:
            await conn.execute(
                query,
                corpus.corpus_id,
                corpus.corpus_name,
                corpus.display_name,
                corpus.description,
                corpus.vertex_corpus_name,
                corpus.embedding_model,
                corpus.vector_db_type,
                json.dumps(corpus.vector_db_config),
                corpus.document_count,
                corpus.chunk_size,
                corpus.chunk_overlap,
                json.dumps(corpus.metadata),
                corpus.enabled,
            )

        return corpus

    async def delete_corpus(self, corpus_id: str) -> bool:
        """Delete a corpus configuration."""
        query = "DELETE FROM corpuses WHERE corpus_id = $1"

        async with self.pool.acquire() as conn:
            result = await conn.execute(query, corpus_id)
            return result == "DELETE 1"

    async def assign_corpus_to_agent(
        self, agent_id: str, corpus_id: str, priority: int = 1
    ) -> bool:
        """Assign a corpus to an agent."""
        query = """
            INSERT INTO agent_corpuses (agent_id, corpus_id, priority)
            VALUES ($1, $2, $3)
            ON CONFLICT (agent_id, corpus_id) DO UPDATE SET
                priority = EXCLUDED.priority
        """

        async with self.pool.acquire() as conn:
            await conn.execute(query, agent_id, corpus_id, priority)
            return True

    async def unassign_corpus_from_agent(
        self, agent_id: str, corpus_id: str
    ) -> bool:
        """Remove a corpus assignment from an agent."""
        query = "DELETE FROM agent_corpuses WHERE agent_id = $1 AND corpus_id = $2"

        async with self.pool.acquire() as conn:
            result = await conn.execute(query, agent_id, corpus_id)
            return result == "DELETE 1"

    def _row_to_corpus_config(self, row) -> CorpusConfig:
        """Convert a database row to CorpusConfig."""
        vector_db_config = row["vector_db_config"]
        if isinstance(vector_db_config, str):
            vector_db_config = json.loads(vector_db_config)

        metadata = row["metadata"]
        if isinstance(metadata, str):
            metadata = json.loads(metadata)

        return CorpusConfig(
            corpus_id=row["corpus_id"],
            corpus_name=row["corpus_name"],
            display_name=row["display_name"],
            description=row.get("description"),
            vertex_corpus_name=row.get("vertex_corpus_name"),
            embedding_model=row.get("embedding_model", "text-embedding-005"),
            vector_db_type=row.get("vector_db_type", "vertex_rag"),
            vector_db_config=vector_db_config or {},
            document_count=row.get("document_count", 0),
            chunk_size=row.get("chunk_size", 1000),
            chunk_overlap=row.get("chunk_overlap", 200),
            priority=row.get("priority", 1),
            metadata=metadata or {},
            enabled=row.get("enabled", True),
        )
