"""
Multi-document Gemini processor.

Processes multiple uploaded documents using Gemini's multimodal capabilities
and returns a unified response based on the user's query.
"""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from google import genai
from google.genai import types

from src.services.storage_service import StorageService

logger = logging.getLogger(__name__)


# Supported MIME types for Gemini processing
SUPPORTED_MIME_TYPES = {
    # Documents
    "application/pdf": "PDF Document",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "Word Document",
    "application/msword": "Word Document (Legacy)",
    "text/plain": "Text File",
    "text/csv": "CSV File",
    "text/html": "HTML File",
    "text/markdown": "Markdown File",
    # Images
    "image/jpeg": "JPEG Image",
    "image/png": "PNG Image",
    "image/gif": "GIF Image",
    "image/webp": "WebP Image",
    # Spreadsheets
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "Excel Spreadsheet",
    "application/vnd.ms-excel": "Excel Spreadsheet (Legacy)",
    # Presentations
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "PowerPoint",
    "application/vnd.ms-powerpoint": "PowerPoint (Legacy)",
}


@dataclass
class DocumentReference:
    """Reference to an uploaded document for processing."""
    document_id: str
    filename: str
    content_type: str
    blob_path: str


@dataclass
class ProcessingResult:
    """Result of multi-document processing."""
    success: bool
    response: Optional[str] = None
    documents_processed: int = 0
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class MultiDocumentProcessor:
    """
    Processes multiple documents using Gemini.

    Supports various document types including PDFs, images, Word docs,
    spreadsheets, and more. Documents are fetched from GCS and sent
    to Gemini for analysis.
    """

    def __init__(
        self,
        storage_service: StorageService,
        project_id: str,
        location: str = "us-east4",
        model_name: str = "gemini-2.5-flash",
    ):
        """
        Initialize the multi-document processor.

        Args:
            storage_service: GCS storage service for document retrieval
            project_id: GCP project ID
            location: GCP region for Vertex AI
            model_name: Gemini model to use
        """
        self.storage_service = storage_service
        self.project_id = project_id
        self.location = location
        self.model_name = model_name

        self.gemini_client = genai.Client(
            vertexai=True,
            project=project_id,
            location=location,
        )

        logger.info(f"✅ MultiDocumentProcessor initialized with model: {model_name}")

    def _sanitize_text(self, text: str, max_length: int = 100000) -> str:
        """
        Sanitize text for safe storage and display.

        Args:
            text: Raw text
            max_length: Maximum character length

        Returns:
            Sanitized text
        """
        if not text:
            return ""

        # Remove null bytes
        text = text.replace('\x00', '')

        # Remove control characters except newlines/tabs
        text = ''.join(
            char for char in text
            if char in ('\n', '\t', '\r') or ord(char) >= 32
        )

        # Normalize whitespace
        lines = text.split('\n')
        normalized_lines = [' '.join(line.split()) for line in lines]
        text = '\n'.join(line for line in normalized_lines if line)

        # Truncate if needed
        if len(text) > max_length:
            text = text[:max_length] + "\n\n[... Content truncated due to length ...]"
            logger.warning(f"⚠️ Text truncated to {max_length} chars")

        return text

    def is_supported_type(self, content_type: str) -> bool:
        """Check if a content type is supported for processing."""
        return content_type in SUPPORTED_MIME_TYPES

    def get_supported_types(self) -> Dict[str, str]:
        """Get dictionary of supported MIME types and descriptions."""
        return SUPPORTED_MIME_TYPES.copy()

    async def process_documents(
        self,
        documents: List[DocumentReference],
        user_query: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.3,
        max_output_tokens: int = 8192,
    ) -> ProcessingResult:
        """
        Process multiple documents with Gemini and answer the user's query.

        Args:
            documents: List of document references to process
            user_query: User's question about the documents
            system_instruction: Optional system prompt for context
            temperature: Model temperature (0.0-1.0)
            max_output_tokens: Maximum response length

        Returns:
            ProcessingResult with Gemini's response
        """
        if not documents:
            return ProcessingResult(
                success=False,
                error="No documents provided for processing",
            )

        try:
            logger.info(f"📄 Processing {len(documents)} document(s) with query: {user_query[:100]}...")

            # Build content parts for Gemini
            content_parts = []

            # Add system context if provided
            if system_instruction:
                content_parts.append(
                    types.Part(text=f"System Context: {system_instruction}\n\n")  # ✅ CORRECT SYNTAX
                )

            # Add document context header
            doc_list = "\n".join([
                f"- {doc.filename} ({SUPPORTED_MIME_TYPES.get(doc.content_type, doc.content_type)})"
                for doc in documents
            ])
            content_parts.append(
                types.Part(text=f"The following {len(documents)} document(s) have been provided for analysis:\n{doc_list}\n\n")  # ✅ CORRECT SYNTAX
            )

            # Fetch and add each document
            processed_count = 0
            failed_docs = []

            for doc in documents:
                try:
                    # Validate content type
                    if not self.is_supported_type(doc.content_type):
                        logger.warning(f"⚠️ Unsupported content type: {doc.content_type} for {doc.filename}")
                        failed_docs.append(f"{doc.filename} (unsupported type)")
                        continue

                    # Fetch document bytes from GCS
                    doc_bytes = await self.storage_service.get_document_bytes(doc.blob_path)

                    # Add document part with inline_data
                    content_parts.append(
                        types.Part(
                            inline_data=types.Blob(
                                mime_type=doc.content_type,
                                data=doc_bytes
                            )
                        )  # ✅ CORRECT SYNTAX FOR BINARY DATA
                    )

                    # Add filename label for context
                    content_parts.append(
                        types.Part(text=f"\n[Above: {doc.filename}]\n\n")  # ✅ CORRECT SYNTAX
                    )

                    processed_count += 1
                    logger.info(f"✅ Added document: {doc.filename} ({len(doc_bytes)} bytes)")

                except Exception as doc_error:
                    logger.error(f"❌ Failed to process {doc.filename}: {doc_error}")
                    failed_docs.append(f"{doc.filename} ({str(doc_error)})")

            if processed_count == 0:
                return ProcessingResult(
                    success=False,
                    error=f"Failed to process any documents. Errors: {', '.join(failed_docs)}",
                    documents_processed=0,
                )

            # Add the user's query
            content_parts.append(
                types.Part(text=f"\n\nUser Question: {user_query}")  # ✅ CORRECT SYNTAX
            )

            # Call Gemini
            logger.info(f"🤖 Sending {processed_count} document(s) to Gemini {self.model_name}")

            response = self.gemini_client.models.generate_content(
                model=self.model_name,
                contents=content_parts,
                config=types.GenerateContentConfig(
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                ),
            )

            response_text = self._sanitize_text(response.text)

            logger.info(f"✅ Gemini processed {processed_count} document(s), response: {len(response_text)} chars")

            return ProcessingResult(
                success=True,
                response=response_text,
                documents_processed=processed_count,
                metadata={
                    "model": self.model_name,
                    "total_documents": len(documents),
                    "processed_documents": processed_count,
                    "failed_documents": failed_docs if failed_docs else None,
                },
            )

        except Exception as e:
            logger.error(f"❌ Document processing failed: {e}", exc_info=True)
            return ProcessingResult(
                success=False,
                error=str(e),
                documents_processed=0,
            )

    async def process_single_document(
        self,
        document: DocumentReference,
        user_query: str,
        temperature: float = 0.3,
    ) -> ProcessingResult:
        """
        Process a single document with Gemini.

        Convenience method for single document processing.

        Args:
            document: Document reference to process
            user_query: User's question about the document
            temperature: Model temperature

        Returns:
            ProcessingResult with Gemini's response
        """
        return await self.process_documents(
            documents=[document],
            user_query=user_query,
            temperature=temperature,
        )
