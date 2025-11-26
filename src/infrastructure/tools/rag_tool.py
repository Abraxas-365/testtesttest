"""RAG (Retrieval-Augmented Generation) tool using Vertex AI RAG Engine with metadata fetching."""

import os
import logging
from typing import Any
import asyncio
import vertexai
from vertexai.preview import rag
from src.domain.models import CorpusConfig
from src.infrastructure.tools.metadata_fetcher import SourceMetadataFetcher

logger = logging.getLogger(__name__)


class VertexRAGTool:
    """
    Vertex AI RAG Engine tool for retrieving information from corpuses.

    This tool uses Google's Vertex AI RAG Engine to perform semantic search
    across configured corpuses and retrieve relevant context with full metadata.
    """

    def __init__(self, corpuses: list[CorpusConfig]):
        """
        Initialize the RAG tool with corpuses.

        Args:
            corpuses: List of corpus configurations to search
        """
        self.corpuses = corpuses
        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        self.location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-east4")
        self.metadata_fetcher = SourceMetadataFetcher()  

        logger.info(f"🧠 RAG Tool initialized: {len(corpuses)} corpuses")
        logger.info(f"🌍 Project: {self.project_id}, Location: {self.location}")

        if self.project_id:
            try:
                vertexai.init(project=self.project_id, location=self.location)
                logger.info(f"✅ Vertex AI initialized: {self.project_id} @ {self.location}")
            except Exception as e:
                logger.error(f"❌ Vertex AI init failed: {e}")

    async def search(self, query: str, top_k: int = 5, similarity_threshold: float = 0.5, fetch_metadata: bool = True) -> dict[str, Any]:
        """
        Search across all configured corpuses for relevant information.

        Args:
            query: The search query
            top_k: Number of top results to return per corpus
            similarity_threshold: Minimum similarity score (0.0 to 1.0)
            fetch_metadata: Whether to fetch metadata for results (default: True)

        Returns:
            Dictionary with search results from all corpuses WITH metadata
        """
        logger.info(f"🔍 RAG Search: '{query}' (top_k={top_k}, fetch_metadata={fetch_metadata})")

        if not self.corpuses:
            logger.error("❌ No corpuses configured")
            return {
                "status": "error",
                "message": "No corpuses configured for this agent",
                "results": []
            }

        if not self.project_id:
            logger.error("❌ GOOGLE_CLOUD_PROJECT not set")
            return {
                "status": "error",
                "message": "GOOGLE_CLOUD_PROJECT environment variable not set",
                "results": []
            }

        all_results = []

        for corpus in self.corpuses:
            if not corpus.enabled:
                logger.warning(f"⏭️ Skipping disabled corpus: {corpus.corpus_name}")
                continue

            if not corpus.vertex_corpus_name:
                logger.warning(f"⏭️ Skipping corpus without vertex_corpus_name: {corpus.corpus_name}")
                continue

            try:
                logger.info(f"📚 Querying corpus: {corpus.corpus_name}")
                
                results = await asyncio.get_event_loop().run_in_executor(
                    None,
                    self._query_corpus,
                    corpus,
                    query,
                    top_k,
                    similarity_threshold
                )

                all_results.extend(results)
                logger.info(f"✅ Got {len(results)} results from {corpus.corpus_name}")

            except Exception as e:
                logger.error(f"❌ Error querying corpus {corpus.corpus_name}: {e}", exc_info=True)
                all_results.append({
                    "corpus_id": corpus.corpus_id,
                    "corpus_name": corpus.corpus_name,
                    "error": str(e),
                    "status": "error"
                })

        all_results.sort(
            key=lambda x: (
                -x.get("relevance_score", 0.0),
                x.get("priority", 999)
            )
        )

        limited_results = all_results[:top_k * 2]

        if fetch_metadata and limited_results:
            logger.info(f"📦 Fetching metadata for {len(limited_results)} results...")
            enriched_results = await self._enrich_with_metadata(limited_results)
        else:
            enriched_results = limited_results

        logger.info(f"✨ Total results: {len(enriched_results)}")

        return {
            "status": "success",
            "query": query,
            "total_results": len(enriched_results),
            "corpuses_searched": len([c for c in self.corpuses if c.enabled]),
            "results": enriched_results
        }

    async def _enrich_with_metadata(self, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Enrich results with metadata from source URIs.
        
        Fetches metadata in parallel for better performance.
        
        Args:
            results: List of RAG results
            
        Returns:
            Results with metadata added
        """
        async def fetch_single_metadata(result):
            """Fetch metadata for a single result."""
            if result.get('source_uri') and 'error' not in result:
                try:
                    metadata = await self.metadata_fetcher.get_metadata(result['source_uri'])
                    result['metadata'] = metadata
                except Exception as e:
                    logger.error(f"Error fetching metadata: {e}")
                    result['metadata'] = {'error': str(e)}
            return result
        
        enriched = await asyncio.gather(*[fetch_single_metadata(r) for r in results])
        
        logger.info(f"✅ Enriched {len(enriched)} results with metadata")
        return list(enriched)

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
            List of search results WITH source URIs
        """
        results = []

        try:
            if corpus.vector_db_type == "vertex_rag":
                logger.info(f"🔮 Calling Vertex AI RAG retrieval_query")
                logger.info(f"  Project: {self.project_id}")
                logger.info(f"  Location: {self.location}")
                logger.info(f"  Corpus: {corpus.vertex_corpus_name}")
                logger.info(f"  Query: {query}")

                rag_retrieval_config = rag.RagRetrievalConfig(
                    top_k=top_k,
                    filter=rag.Filter(
                        vector_distance_threshold=1.0 - similarity_threshold
                    ),
                )

                response = rag.retrieval_query(
                    rag_resources=[
                        rag.RagResource(
                            rag_corpus=corpus.vertex_corpus_name,
                        )
                    ],
                    text=query,
                    rag_retrieval_config=rag_retrieval_config,
                )

                logger.info("✅ RAG API response received")

                if hasattr(response, 'contexts') and response.contexts:
                    if hasattr(response.contexts, 'contexts'):
                        for idx, context in enumerate(response.contexts.contexts):
                            relevance_score = None
                            if hasattr(context, 'distance'):
                                relevance_score = 1.0 - context.distance
                            
                            source_uri = None
                            if hasattr(context, 'source_uri'):
                                source_uri = context.source_uri
                            
                            file_name = None
                            if source_uri:
                                file_name = source_uri.split('/')[-1] if '/' in source_uri else source_uri
                            
                            results.append({
                                "corpus_id": corpus.corpus_id,
                                "corpus_name": corpus.corpus_name,
                                "priority": corpus.priority,
                                "rank": idx + 1,
                                "text": context.text if hasattr(context, 'text') else str(context),
                                "relevance_score": relevance_score,
                                
                                "source_uri": source_uri,
                                "file_name": file_name,
                            })
                        logger.info(f"✅ Processed {len(results)} results with source URIs")
                    else:
                        logger.warning("⚠️ No contexts in response")
                else:
                    logger.warning("⚠️ Response has no contexts attribute")
                    logger.warning(f"   Response type: {type(response)}")

            else:
                logger.warning(f"⚠️ Vector DB type '{corpus.vector_db_type}' not supported")
                results.append({
                    "corpus_id": corpus.corpus_id,
                    "corpus_name": corpus.corpus_name,
                    "priority": corpus.priority,
                    "text": f"RAG support for {corpus.vector_db_type} not yet implemented",
                    "status": "not_implemented"
                })

        except Exception as e:
            logger.error(f"❌ RAG query failed for corpus {corpus.corpus_name}")
            logger.error(f"   Error type: {type(e).__name__}")
            logger.error(f"   Error message: {str(e)}")
            logger.error(f"   Corpus resource: {corpus.vertex_corpus_name}")
            import traceback
            logger.error(traceback.format_exc())
            
            results.append({
                "corpus_id": corpus.corpus_id,
                "corpus_name": corpus.corpus_name,
                "error": f"{type(e).__name__}: {str(e)}",
                "status": "error"
            })

        return results


def create_rag_tool(corpus: CorpusConfig):  
    """
    Factory function to create a RAG tool function for a SINGLE corpus.

    Args:
        corpus: Single corpus configuration

    Returns:
        An async function that can be used as an ADK tool
    """
    tool_instance = VertexRAGTool([corpus])
    
    corpus_name_safe = corpus.display_name.replace(" ", "_").replace("-", "_").lower()
    
    async def rag_search(query: str, top_k: int = 5) -> dict[str, Any]:
        f"""
        Search {corpus.display_name} knowledge base using RAG.
        
        Use this tool to retrieve information specifically from {corpus.display_name}.
        This corpus contains: {corpus.description or 'company documents and policies'}.
        
        IMPORTANT: Always cite the source file when presenting information to users.
        
        Args:
            query: The search query describing what information you need
            top_k: Number of results to return (default: 5)
            
        Returns:
            Dictionary with search results containing:
            - text: The relevant document excerpt
            - file_name: Name of the source file
            - source_uri: Full URI to the source file
            - relevance_score: How relevant this result is (0.0-1.0)
            - metadata: Complete file metadata
        """
        return await tool_instance.search(query, top_k=top_k)
    
    rag_search.__name__ = f"search_{corpus_name_safe}"
    
    return rag_search
