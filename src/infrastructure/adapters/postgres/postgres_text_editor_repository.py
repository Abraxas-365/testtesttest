"""PostgreSQL adapter implementation of TextEditorRepository port."""

import logging
import uuid as uuid_module
from typing import Optional, List, Union
from datetime import datetime
import asyncpg
from asyncpg import Pool

from src.domain.models import EditorDocument
from src.domain.ports import TextEditorRepository

logger = logging.getLogger(__name__)


def _to_uuid(value: Union[str, uuid_module.UUID, None]) -> Optional[uuid_module.UUID]:
    """Convert a value to UUID if it's a valid UUID string."""
    if value is None:
        return None
    if isinstance(value, uuid_module.UUID):
        return value
    try:
        return uuid_module.UUID(str(value))
    except (ValueError, AttributeError):
        return None


class PostgresTextEditorRepository(TextEditorRepository):
    """
    PostgreSQL implementation of the TextEditorRepository port.

    This adapter connects to a PostgreSQL database and implements
    all methods defined in the TextEditorRepository interface.
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
        min_size: int = 5,
        max_size: int = 10,
    ) -> "PostgresTextEditorRepository":
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
            PostgresTextEditorRepository instance
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

    async def get_document_by_id(
        self, document_id: str, user_id: str
    ) -> Optional[EditorDocument]:
        """Get document by ID for a specific user."""
        # Convert document_id to UUID
        doc_uuid = _to_uuid(document_id)
        if doc_uuid is None:
            logger.warning(f"Invalid document_id format: {document_id}")
            return None

        query = """
            SELECT
                document_id,
                user_id,
                title,
                content,
                metadata,
                created_at,
                updated_at
            FROM editor_documents
            WHERE document_id = $1 AND user_id = $2
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, doc_uuid, user_id)
            if row:
                return self._row_to_document(row)
            return None

    async def list_user_documents(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> List[EditorDocument]:
        """List all documents for a user with pagination."""
        query = """
            SELECT
                document_id,
                user_id,
                title,
                content,
                metadata,
                created_at,
                updated_at
            FROM editor_documents
            WHERE user_id = $1
            ORDER BY updated_at DESC
            LIMIT $2 OFFSET $3
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, user_id, limit, offset)
            return [self._row_to_document(row) for row in rows]

    async def save_document(self, document: EditorDocument) -> EditorDocument:
        """Save or update a document."""
        # Check if document exists
        existing = await self._document_exists(document.document_id)

        if existing:
            return await self._update_document(document)
        else:
            return await self._create_document(document)

    async def _document_exists(self, document_id: str) -> bool:
        """Check if a document exists."""
        doc_uuid = _to_uuid(document_id)
        if doc_uuid is None:
            return False

        query = "SELECT 1 FROM editor_documents WHERE document_id = $1"
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(query, doc_uuid)
            return result is not None

    async def _create_document(self, document: EditorDocument) -> EditorDocument:
        """Create a new document."""
        import json

        # Generate document_id if not provided or empty, or convert to UUID
        doc_id = document.document_id
        if not doc_id or doc_id == "":
            doc_uuid = uuid_module.uuid4()
        else:
            doc_uuid = _to_uuid(doc_id)
            if doc_uuid is None:
                # Generate a new UUID if the provided one is invalid
                doc_uuid = uuid_module.uuid4()
                logger.warning(f"Invalid document_id provided: {doc_id}, generated new UUID: {doc_uuid}")

        query = """
            INSERT INTO editor_documents (
                document_id, user_id, title, content, metadata
            )
            VALUES ($1, $2, $3, $4, $5)
            RETURNING document_id, user_id, title, content, metadata, created_at, updated_at
        """
        metadata_json = json.dumps(document.metadata) if document.metadata else "{}"

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                doc_uuid,
                document.user_id,
                document.title,
                document.content,
                metadata_json,
            )
            logger.info(f"Created document {row['document_id']} for user {document.user_id}")
            return self._row_to_document(row)

    async def _update_document(self, document: EditorDocument) -> EditorDocument:
        """Update an existing document."""
        import json

        doc_uuid = _to_uuid(document.document_id)
        if doc_uuid is None:
            raise ValueError(f"Invalid document_id format: {document.document_id}")

        query = """
            UPDATE editor_documents
            SET title = $1, content = $2, metadata = $3
            WHERE document_id = $4 AND user_id = $5
            RETURNING document_id, user_id, title, content, metadata, created_at, updated_at
        """
        metadata_json = json.dumps(document.metadata) if document.metadata else "{}"

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                document.title,
                document.content,
                metadata_json,
                doc_uuid,
                document.user_id,
            )
            if row:
                logger.info(f"Updated document {document.document_id}")
                return self._row_to_document(row)
            else:
                raise ValueError(
                    f"Document {document.document_id} not found or not owned by user"
                )

    async def delete_document(self, document_id: str, user_id: str) -> bool:
        """Delete a document."""
        doc_uuid = _to_uuid(document_id)
        if doc_uuid is None:
            logger.warning(f"Invalid document_id format for deletion: {document_id}")
            return False

        query = """
            DELETE FROM editor_documents
            WHERE document_id = $1 AND user_id = $2
            RETURNING document_id
        """
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(query, doc_uuid, user_id)
            if result:
                logger.info(f"Deleted document {document_id}")
                return True
            return False

    async def count_user_documents(self, user_id: str) -> int:
        """Count total documents for a user."""
        query = "SELECT COUNT(*) FROM editor_documents WHERE user_id = $1"
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, user_id)

    def _row_to_document(self, row: asyncpg.Record) -> EditorDocument:
        """Convert a database row to an EditorDocument."""
        import json

        metadata = row["metadata"]
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        elif metadata is None:
            metadata = {}

        return EditorDocument(
            document_id=str(row["document_id"]),
            user_id=row["user_id"],
            title=row["title"],
            content=row["content"],
            metadata=metadata,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
