"""Repository port (interface) for text editor documents."""

from abc import ABC, abstractmethod
from typing import Optional, List
from src.domain.models import EditorDocument


class TextEditorRepository(ABC):
    """
    Port (interface) for text editor document repository.

    This defines the contract that any adapter (like PostgreSQL) must implement
    to provide document persistence for the AI Text Editor.
    """

    @abstractmethod
    async def get_document_by_id(
        self, document_id: str, user_id: str
    ) -> Optional[EditorDocument]:
        """
        Retrieve a document by ID for a specific user.

        Args:
            document_id: The unique identifier of the document
            user_id: The user ID (for authorization)

        Returns:
            EditorDocument if found and owned by user, None otherwise
        """
        pass

    @abstractmethod
    async def list_user_documents(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> List[EditorDocument]:
        """
        List all documents for a user with pagination.

        Args:
            user_id: The user ID to list documents for
            limit: Maximum number of documents to return
            offset: Number of documents to skip

        Returns:
            List of EditorDocument objects, sorted by updated_at descending
        """
        pass

    @abstractmethod
    async def save_document(self, document: EditorDocument) -> EditorDocument:
        """
        Save or update a document.

        If document_id exists, updates the document.
        Otherwise, creates a new document.

        Args:
            document: The document to save

        Returns:
            The saved EditorDocument with updated timestamps
        """
        pass

    @abstractmethod
    async def delete_document(self, document_id: str, user_id: str) -> bool:
        """
        Delete a document.

        Args:
            document_id: The unique identifier of the document
            user_id: The user ID (for authorization)

        Returns:
            True if deleted, False if not found or not owned by user
        """
        pass

    @abstractmethod
    async def count_user_documents(self, user_id: str) -> int:
        """
        Count total documents for a user.

        Args:
            user_id: The user ID to count documents for

        Returns:
            Total number of documents
        """
        pass
