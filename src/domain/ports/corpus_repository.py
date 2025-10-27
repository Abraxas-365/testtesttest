"""Repository port (interface) for corpus management."""

from abc import ABC, abstractmethod
from typing import Optional
from src.domain.models import CorpusConfig


class CorpusRepository(ABC):
    """
    Port (interface) for corpus repository.

    This defines the contract that any adapter must implement
    to provide corpus management.
    """

    @abstractmethod
    async def get_corpus_by_id(self, corpus_id: str) -> Optional[CorpusConfig]:
        """
        Retrieve a corpus configuration by ID.

        Args:
            corpus_id: The unique identifier of the corpus

        Returns:
            CorpusConfig if found, None otherwise
        """
        pass

    @abstractmethod
    async def get_corpus_by_name(self, corpus_name: str) -> Optional[CorpusConfig]:
        """
        Retrieve a corpus configuration by name.

        Args:
            corpus_name: The name of the corpus

        Returns:
            CorpusConfig if found, None otherwise
        """
        pass

    @abstractmethod
    async def list_corpuses(self, enabled_only: bool = True) -> list[CorpusConfig]:
        """
        List all corpus configurations.

        Args:
            enabled_only: If True, return only enabled corpuses

        Returns:
            List of CorpusConfig objects
        """
        pass

    @abstractmethod
    async def get_corpuses_for_agent(self, agent_id: str) -> list[CorpusConfig]:
        """
        Get all corpuses assigned to a specific agent.

        Args:
            agent_id: The unique identifier of the agent

        Returns:
            List of CorpusConfig objects ordered by priority
        """
        pass

    @abstractmethod
    async def save_corpus(self, corpus: CorpusConfig) -> CorpusConfig:
        """
        Save or update a corpus configuration.

        Args:
            corpus: The corpus configuration to save

        Returns:
            The saved CorpusConfig
        """
        pass

    @abstractmethod
    async def delete_corpus(self, corpus_id: str) -> bool:
        """
        Delete a corpus configuration.

        Args:
            corpus_id: The unique identifier of the corpus

        Returns:
            True if deleted, False if not found
        """
        pass

    @abstractmethod
    async def assign_corpus_to_agent(
        self, agent_id: str, corpus_id: str, priority: int = 1
    ) -> bool:
        """
        Assign a corpus to an agent.

        Args:
            agent_id: The unique identifier of the agent
            corpus_id: The unique identifier of the corpus
            priority: Priority level (lower = higher priority)

        Returns:
            True if assigned successfully
        """
        pass

    @abstractmethod
    async def unassign_corpus_from_agent(
        self, agent_id: str, corpus_id: str
    ) -> bool:
        """
        Remove a corpus assignment from an agent.

        Args:
            agent_id: The unique identifier of the agent
            corpus_id: The unique identifier of the corpus

        Returns:
            True if unassigned successfully
        """
        pass
