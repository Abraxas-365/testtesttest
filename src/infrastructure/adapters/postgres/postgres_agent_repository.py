"""PostgreSQL adapter implementation of AgentRepository port."""

import json
from typing import Optional
import asyncpg
from asyncpg import Pool

from src.domain.models import AgentConfig, ToolConfig, ModelConfig, CorpusConfig
from src.domain.ports import AgentRepository


class PostgresAgentRepository(AgentRepository):
    """
    PostgreSQL implementation of the AgentRepository port.

    This adapter connects to a PostgreSQL database and implements
    all methods defined in the AgentRepository interface.
    """

    def __init__(self, pool: Pool):
        """
        Initialize the PostgreSQL repository.

        Args:
            pool: AsyncPG connection pool
        """
        self.pool = pool

    @classmethod
    async def create(
        cls,
        host: str,
        port: int,
        database: str,
        user: str,
        password: str,
        min_size: int = 10,
        max_size: int = 20,
    ) -> "PostgresAgentRepository":
        """
        Create a new PostgreSQL repository with a connection pool.

        Args:
            host: Database host
            port: Database port
            database: Database name
            user: Database user
            password: Database password
            min_size: Minimum pool size
            max_size: Maximum pool size

        Returns:
            PostgresAgentRepository instance
        """
        pool = await asyncpg.create_pool(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
            min_size=min_size,
            max_size=max_size,
        )
        return cls(pool)

    async def close(self):
        """Close the connection pool."""
        await self.pool.close()

    async def get_agent_by_id(self, agent_id: str) -> Optional[AgentConfig]:
        """Get agent configuration by ID."""
        query = """
            SELECT
                a.agent_id,
                a.name,
                a.instruction,
                a.description,
                a.enabled,
                a.metadata,
                a.agent_type,
                a.area_type,
                a.model_name,
                a.temperature,
                a.max_tokens,
                a.top_p,
                a.top_k,
                COALESCE(
                    json_agg(
                        json_build_object(
                            'tool_id', t.tool_id,
                            'tool_name', t.tool_name,
                            'tool_type', t.tool_type,
                            'function_name', t.function_name,
                            'parameters', t.parameters,
                            'description', t.description,
                            'enabled', t.enabled
                        )
                    ) FILTER (WHERE t.tool_id IS NOT NULL),
                    '[]'
                ) as tools,
                COALESCE(
                    json_agg(
                        json_build_object(
                            'corpus_id', c.corpus_id,
                            'corpus_name', c.corpus_name,
                            'display_name', c.display_name,
                            'description', c.description,
                            'vertex_corpus_name', c.vertex_corpus_name,
                            'embedding_model', c.embedding_model,
                            'vector_db_type', c.vector_db_type,
                            'vector_db_config', c.vector_db_config,
                            'document_count', c.document_count,
                            'chunk_size', c.chunk_size,
                            'chunk_overlap', c.chunk_overlap,
                            'priority', ac.priority,
                            'metadata', c.metadata,
                            'enabled', c.enabled
                        )
                    ) FILTER (WHERE c.corpus_id IS NOT NULL),
                    '[]'
                ) as corpuses,
                COALESCE(
                    array_agg(DISTINCT sa.sub_agent_id) FILTER (WHERE sa.sub_agent_id IS NOT NULL),
                    ARRAY[]::text[]
                ) as sub_agent_ids
            FROM agents a
            LEFT JOIN agent_tools at ON a.agent_id = at.agent_id
            LEFT JOIN tools t ON at.tool_id = t.tool_id
            LEFT JOIN agent_corpuses ac ON a.agent_id = ac.agent_id
            LEFT JOIN corpuses c ON ac.corpus_id = c.corpus_id
            LEFT JOIN agent_sub_agents sa ON a.agent_id = sa.parent_agent_id
            WHERE a.agent_id = $1
            GROUP BY a.agent_id
        """

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, agent_id)
            if not row:
                return None
            return self._row_to_agent_config(row)

    async def get_agent_by_name(self, name: str) -> Optional[AgentConfig]:
        """Get agent configuration by name."""
        query = """
            SELECT
                a.agent_id,
                a.name,
                a.instruction,
                a.description,
                a.enabled,
                a.metadata,
                a.agent_type,
                a.area_type,
                a.model_name,
                a.temperature,
                a.max_tokens,
                a.top_p,
                a.top_k,
                COALESCE(
                    json_agg(
                        json_build_object(
                            'tool_id', t.tool_id,
                            'tool_name', t.tool_name,
                            'tool_type', t.tool_type,
                            'function_name', t.function_name,
                            'parameters', t.parameters,
                            'description', t.description,
                            'enabled', t.enabled
                        )
                    ) FILTER (WHERE t.tool_id IS NOT NULL),
                    '[]'
                ) as tools,
                COALESCE(
                    json_agg(
                        json_build_object(
                            'corpus_id', c.corpus_id,
                            'corpus_name', c.corpus_name,
                            'display_name', c.display_name,
                            'description', c.description,
                            'vertex_corpus_name', c.vertex_corpus_name,
                            'embedding_model', c.embedding_model,
                            'vector_db_type', c.vector_db_type,
                            'vector_db_config', c.vector_db_config,
                            'document_count', c.document_count,
                            'chunk_size', c.chunk_size,
                            'chunk_overlap', c.chunk_overlap,
                            'priority', ac.priority,
                            'metadata', c.metadata,
                            'enabled', c.enabled
                        )
                    ) FILTER (WHERE c.corpus_id IS NOT NULL),
                    '[]'
                ) as corpuses,
                COALESCE(
                    array_agg(DISTINCT sa.sub_agent_id) FILTER (WHERE sa.sub_agent_id IS NOT NULL),
                    ARRAY[]::text[]
                ) as sub_agent_ids
            FROM agents a
            LEFT JOIN agent_tools at ON a.agent_id = at.agent_id
            LEFT JOIN tools t ON at.tool_id = t.tool_id
            LEFT JOIN agent_corpuses ac ON a.agent_id = ac.agent_id
            LEFT JOIN corpuses c ON ac.corpus_id = c.corpus_id
            LEFT JOIN agent_sub_agents sa ON a.agent_id = sa.parent_agent_id
            WHERE a.name = $1
            GROUP BY a.agent_id
        """

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, name)
            if not row:
                return None
            return self._row_to_agent_config(row)

    async def list_agents(self, enabled_only: bool = True) -> list[AgentConfig]:
        """List all agent configurations."""
        query = """
            SELECT
                a.agent_id,
                a.name,
                a.instruction,
                a.description,
                a.enabled,
                a.metadata,
                a.agent_type,
                a.area_type,
                a.model_name,
                a.temperature,
                a.max_tokens,
                a.top_p,
                a.top_k,
                COALESCE(
                    json_agg(
                        json_build_object(
                            'tool_id', t.tool_id,
                            'tool_name', t.tool_name,
                            'tool_type', t.tool_type,
                            'function_name', t.function_name,
                            'parameters', t.parameters,
                            'description', t.description,
                            'enabled', t.enabled
                        )
                    ) FILTER (WHERE t.tool_id IS NOT NULL),
                    '[]'
                ) as tools,
                COALESCE(
                    json_agg(
                        json_build_object(
                            'corpus_id', c.corpus_id,
                            'corpus_name', c.corpus_name,
                            'display_name', c.display_name,
                            'description', c.description,
                            'vertex_corpus_name', c.vertex_corpus_name,
                            'embedding_model', c.embedding_model,
                            'vector_db_type', c.vector_db_type,
                            'vector_db_config', c.vector_db_config,
                            'document_count', c.document_count,
                            'chunk_size', c.chunk_size,
                            'chunk_overlap', c.chunk_overlap,
                            'priority', ac.priority,
                            'metadata', c.metadata,
                            'enabled', c.enabled
                        )
                    ) FILTER (WHERE c.corpus_id IS NOT NULL),
                    '[]'
                ) as corpuses,
                COALESCE(
                    array_agg(DISTINCT sa.sub_agent_id) FILTER (WHERE sa.sub_agent_id IS NOT NULL),
                    ARRAY[]::text[]
                ) as sub_agent_ids
            FROM agents a
            LEFT JOIN agent_tools at ON a.agent_id = at.agent_id
            LEFT JOIN tools t ON at.tool_id = t.tool_id
            LEFT JOIN agent_corpuses ac ON a.agent_id = ac.agent_id
            LEFT JOIN corpuses c ON ac.corpus_id = c.corpus_id
            LEFT JOIN agent_sub_agents sa ON a.agent_id = sa.parent_agent_id
        """

        if enabled_only:
            query += " WHERE a.enabled = true"

        query += " GROUP BY a.agent_id ORDER BY a.name"

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query)
            return [self._row_to_agent_config(row) for row in rows]

    async def get_tools_for_agent(self, agent_id: str) -> list[ToolConfig]:
        """Get all tools for a specific agent."""
        query = """
            SELECT
                t.tool_id,
                t.tool_name,
                t.tool_type,
                t.function_name,
                t.parameters,
                t.description,
                t.enabled
            FROM tools t
            INNER JOIN agent_tools at ON t.tool_id = at.tool_id
            WHERE at.agent_id = $1 AND t.enabled = true
            ORDER BY t.tool_name
        """

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, agent_id)
            return [self._row_to_tool_config(row) for row in rows]

    async def get_tool_by_id(self, tool_id: str) -> Optional[ToolConfig]:
        """Get tool configuration by ID."""
        query = """
            SELECT
                tool_id,
                tool_name,
                tool_type,
                function_name,
                parameters,
                description,
                enabled
            FROM tools
            WHERE tool_id = $1
        """

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, tool_id)
            if not row:
                return None
            return self._row_to_tool_config(row)

    async def save_agent(self, agent: AgentConfig) -> AgentConfig:
        """Save or update an agent configuration."""
        query = """
            INSERT INTO agents (
                agent_id, name, instruction, description, enabled, metadata,
                agent_type, area_type,
                model_name, temperature, max_tokens, top_p, top_k
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            ON CONFLICT (agent_id) DO UPDATE SET
                name = EXCLUDED.name,
                instruction = EXCLUDED.instruction,
                description = EXCLUDED.description,
                enabled = EXCLUDED.enabled,
                metadata = EXCLUDED.metadata,
                agent_type = EXCLUDED.agent_type,
                area_type = EXCLUDED.area_type,
                model_name = EXCLUDED.model_name,
                temperature = EXCLUDED.temperature,
                max_tokens = EXCLUDED.max_tokens,
                top_p = EXCLUDED.top_p,
                top_k = EXCLUDED.top_k,
                updated_at = NOW()
            RETURNING *
        """

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    query,
                    agent.agent_id,
                    agent.name,
                    agent.instruction,
                    agent.description,
                    agent.enabled,
                    json.dumps(agent.metadata),
                    agent.agent_type,
                    agent.area_type,
                    agent.model.model_name,
                    agent.model.temperature,
                    agent.model.max_tokens,
                    agent.model.top_p,
                    agent.model.top_k,
                )

                await conn.execute(
                    "DELETE FROM agent_tools WHERE agent_id = $1", agent.agent_id
                )

                if agent.tools:
                    await conn.executemany(
                        "INSERT INTO agent_tools (agent_id, tool_id) VALUES ($1, $2)",
                        [(agent.agent_id, tool.tool_id) for tool in agent.tools],
                    )

                await conn.execute(
                    "DELETE FROM agent_corpuses WHERE agent_id = $1",
                    agent.agent_id,
                )

                if agent.corpuses:
                    await conn.executemany(
                        "INSERT INTO agent_corpuses (agent_id, corpus_id, priority) VALUES ($1, $2, $3)",
                        [(agent.agent_id, corpus.corpus_id, corpus.priority) for corpus in agent.corpuses],
                    )

                await conn.execute(
                    "DELETE FROM agent_sub_agents WHERE parent_agent_id = $1",
                    agent.agent_id,
                )

                if agent.sub_agent_ids:
                    await conn.executemany(
                        "INSERT INTO agent_sub_agents (parent_agent_id, sub_agent_id) VALUES ($1, $2)",
                        [(agent.agent_id, sub_id) for sub_id in agent.sub_agent_ids],
                    )

        return agent

    async def delete_agent(self, agent_id: str) -> bool:
        """Delete an agent configuration."""
        query = "DELETE FROM agents WHERE agent_id = $1"

        async with self.pool.acquire() as conn:
            result = await conn.execute(query, agent_id)
            return result == "DELETE 1"

    def _row_to_agent_config(self, row) -> AgentConfig:
        """Convert a database row to AgentConfig."""
        model_config = ModelConfig(
            model_name=row["model_name"],
            temperature=row["temperature"],
            max_tokens=row["max_tokens"],
            top_p=row["top_p"],
            top_k=row["top_k"],
        )

        tools = []
        if row["tools"]:
            tools_data = row["tools"] if isinstance(row["tools"], list) else json.loads(row["tools"])
            tools = [
                ToolConfig(
                    tool_id=t["tool_id"],
                    tool_name=t["tool_name"],
                    tool_type=t["tool_type"],
                    function_name=t.get("function_name"),
                    parameters=t.get("parameters", {}),
                    description=t.get("description"),
                    enabled=t.get("enabled", True),
                )
                for t in tools_data
            ]

        corpuses = []
        if row.get("corpuses"):
            corpuses_data = row["corpuses"] if isinstance(row["corpuses"], list) else json.loads(row["corpuses"])
            corpuses = [
                CorpusConfig(
                    corpus_id=c["corpus_id"],
                    corpus_name=c["corpus_name"],
                    display_name=c["display_name"],
                    description=c.get("description"),
                    vertex_corpus_name=c.get("vertex_corpus_name"),
                    embedding_model=c.get("embedding_model", "text-embedding-005"),
                    vector_db_type=c.get("vector_db_type", "vertex_rag"),
                    vector_db_config=c.get("vector_db_config", {}),
                    document_count=c.get("document_count", 0),
                    chunk_size=c.get("chunk_size", 1000),
                    chunk_overlap=c.get("chunk_overlap", 200),
                    priority=c.get("priority", 1),
                    metadata=c.get("metadata", {}),
                    enabled=c.get("enabled", True),
                )
                for c in corpuses_data
            ]

        metadata = row["metadata"]
        if isinstance(metadata, str):
            metadata = json.loads(metadata)

        return AgentConfig(
            agent_id=row["agent_id"],
            name=row["name"],
            model=model_config,
            instruction=row["instruction"],
            description=row["description"],
            agent_type=row.get("agent_type", "assistant"),
            area_type=row.get("area_type", "general"),
            tools=tools,
            corpuses=corpuses,
            sub_agent_ids=row["sub_agent_ids"] or [],
            enabled=row["enabled"],
            metadata=metadata or {},
        )

    def _row_to_tool_config(self, row) -> ToolConfig:
        """Convert a database row to ToolConfig."""
        parameters = row["parameters"]
        if isinstance(parameters, str):
            parameters = json.loads(parameters)

        return ToolConfig(
            tool_id=row["tool_id"],
            tool_name=row["tool_name"],
            tool_type=row["tool_type"],
            function_name=row.get("function_name"),
            parameters=parameters or {},
            description=row.get("description"),
            enabled=row.get("enabled", True),
        )
