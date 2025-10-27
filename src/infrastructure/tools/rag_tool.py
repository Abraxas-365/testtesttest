"""RAG (Retrieval-Augmented Generation) tool using Vertex AI RAG Engine."""

import os
from typing import Any, Optional
import vertexai
from vertexai import rag
from src.domain.models import CorpusConfig


class VertexRAGTool:
    """
    Vertex AI RAG Engine tool for retrieving information from corpuses.

    This tool uses Google's Vertex AI RAG Engine to perform semantic search
    across configured corpuses and retrieve relevant context for the LLM.
    """

    def __init__(self, corpuses: list[CorpusConfig]):
        """
        Initialize the RAG tool with corpuses.

        Args:
            corpuses: List of corpus configurations to search
        """
        self.corpuses = corpuses
        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        self.location = os.getenv("GOOGLE_CLOUD_REGION", "us-central1")

        # Initialize Vertex AI
        if self.project_id:
            vertexai.init(project=self.project_id, location=self.location)

    def __call__(self, query: str, top_k: int = 5, similarity_threshold: float = 0.5) -> dict[str, Any]:
        """
        Search across all configured corpuses for relevant information.

        Args:
            query: The search query
            top_k: Number of top results to return per corpus
            similarity_threshold: Minimum similarity score (0.0 to 1.0)

        Returns:
            Dictionary with search results from all corpuses
        """
        if not self.corpuses:
            return {
                "status": "error",
                "message": "No corpuses configured for this agent",
                "results": []
            }

        if not self.project_id:
            return {
                "status": "error",
                "message": "GOOGLE_CLOUD_PROJECT environment variable not set",
                "results": []
            }

        all_results = []

        for corpus in self.corpuses:
            if not corpus.enabled or not corpus.vertex_corpus_name:
                continue

            try:
                # Query the corpus using Vertex AI RAG Engine
                results = self._query_corpus(
                    corpus=corpus,
                    query=query,
                    top_k=top_k,
                    similarity_threshold=similarity_threshold
                )

                all_results.extend(results)

            except Exception as e:
                print(f"Error querying corpus {corpus.corpus_name}: {e}")
                all_results.append({
                    "corpus_id": corpus.corpus_id,
                    "corpus_name": corpus.corpus_name,
                    "error": str(e),
                    "status": "error"
                })

        # Sort by relevance score (if available) and priority
        all_results.sort(
            key=lambda x: (
                -x.get("relevance_score", 0.0),
                x.get("priority", 999)
            )
        )

        return {
            "status": "success",
            "query": query,
            "total_results": len(all_results),
            "corpuses_searched": len(self.corpuses),
            "results": all_results[:top_k * 2]  # Return up to 2x top_k results
        }

    def _query_corpus(
        self,
        corpus: CorpusConfig,
        query: str,
        top_k: int,
        similarity_threshold: float
    ) -> list[dict[str, Any]]:
        """
        Query a single corpus using Vertex AI RAG Engine.

        Args:
            corpus: The corpus configuration
            query: The search query
            top_k: Number of results to return
            similarity_threshold: Minimum similarity score

        Returns:
            List of search results
        """
        results = []

        try:
            if corpus.vector_db_type == "vertex_rag":
                # Use Vertex AI RAG Engine
                response = rag.retrieval_query(
                    rag_resources=[
                        rag.RagResource(
                            rag_corpus=corpus.vertex_corpus_name,
                        )
                    ],
                    text=query,
                    similarity_top_k=top_k,
                    vector_distance_threshold=1.0 - similarity_threshold,
                )

                # Process response
                if hasattr(response, 'contexts') and response.contexts:
                    for idx, context in enumerate(response.contexts.contexts):
                        results.append({
                            "corpus_id": corpus.corpus_id,
                            "corpus_name": corpus.corpus_name,
                            "priority": corpus.priority,
                            "rank": idx + 1,
                            "text": context.text if hasattr(context, 'text') else str(context),
                            "relevance_score": context.score if hasattr(context, 'score') else None,
                            "source": context.source_uri if hasattr(context, 'source_uri') else None,
                        })

            else:
                # For other vector DB types, return a placeholder
                results.append({
                    "corpus_id": corpus.corpus_id,
                    "corpus_name": corpus.corpus_name,
                    "priority": corpus.priority,
                    "text": f"RAG support for {corpus.vector_db_type} not yet implemented",
                    "status": "not_implemented"
                })

        except Exception as e:
            results.append({
                "corpus_id": corpus.corpus_id,
                "corpus_name": corpus.corpus_name,
                "error": str(e),
                "status": "error"
            })

        return results


def create_rag_tool(corpuses: list[CorpusConfig]) -> VertexRAGTool:
    """
    Factory function to create a RAG tool.

    Args:
        corpuses: List of corpus configurations

    Returns:
        Configured VertexRAGTool instance
    """
    return VertexRAGTool(corpuses)


# Simple function wrapper for ADK compatibility
def vertex_rag_retrieval(query: str, corpuses: list = None, top_k: int = 5) -> dict[str, Any]:
    """
    Retrieve information from RAG corpuses.

    This function is designed to be registered as a tool in the ADK agent.
    Note: The corpuses parameter should be injected by the tool registry.

    Args:
        query: The search query
        corpuses: List of corpus configurations (injected)
        top_k: Number of results to return

    Returns:
        Dictionary with search results
    """
    if not corpuses:
        return {
            "status": "error",
            "message": "No corpuses configured",
            "results": []
        }

    tool = VertexRAGTool(corpuses)
    return tool(query, top_k=top_k)
