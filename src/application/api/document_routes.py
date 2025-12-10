"""
Document Upload API Routes.

Provides endpoints for:
- Generating presigned URLs for document uploads
- Confirming upload completion
- Processing documents with the agent
"""

import os
import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field

from src.middleware.teams_auth import require_auth
from src.application.di import get_container
from src.services.storage_service import StorageService
from src.services.document_processor import (
    MultiDocumentProcessor,
    DocumentReference,
    SUPPORTED_MIME_TYPES,
)
from src.services.teams_integration import TeamsAgentIntegration

logger = logging.getLogger(__name__)
router = APIRouter()

# Initialize services lazily
_storage_service: Optional[StorageService] = None
_document_processor: Optional[MultiDocumentProcessor] = None


def get_storage_service() -> StorageService:
    """Get or create storage service singleton."""
    global _storage_service
    if _storage_service is None:
        _storage_service = StorageService()
    return _storage_service


def get_document_processor() -> MultiDocumentProcessor:
    """Get or create document processor singleton."""
    global _document_processor
    if _document_processor is None:
        storage = get_storage_service()
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-east4")
        _document_processor = MultiDocumentProcessor(
            storage_service=storage,
            project_id=project_id,
            location=location,
        )
    return _document_processor


# =============================================================================
# Request/Response Models
# =============================================================================


class PresignedUrlRequest(BaseModel):
    """Request for generating a presigned upload URL."""
    filename: str = Field(..., description="Original filename with extension")
    content_type: str = Field(..., description="MIME type of the file (e.g., 'application/pdf')")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "filename": "report.pdf",
                    "content_type": "application/pdf"
                },
                {
                    "filename": "data.xlsx",
                    "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                }
            ]
        }
    }


class PresignedUrlResponse(BaseModel):
    """Response with presigned upload URL."""
    document_id: str = Field(..., description="Unique document identifier")
    upload_url: str = Field(..., description="Presigned URL for PUT upload")
    filename: str = Field(..., description="Original filename")
    content_type: str = Field(..., description="MIME type")
    blob_path: str = Field(..., description="Path in GCS bucket")
    expires_in_seconds: int = Field(..., description="URL expiration time")


class UploadConfirmRequest(BaseModel):
    """Request to confirm upload completion."""
    document_id: str = Field(..., description="Document ID from presigned URL response")
    blob_path: str = Field(..., description="Blob path from presigned URL response")


class UploadConfirmResponse(BaseModel):
    """Response confirming upload status."""
    success: bool
    document_id: str
    size_bytes: Optional[int] = None
    message: str


class DocumentInfo(BaseModel):
    """Document reference for processing."""
    document_id: str = Field(..., description="Document ID")
    filename: str = Field(..., description="Original filename")
    content_type: str = Field(..., description="MIME type")
    blob_path: str = Field(..., description="GCS blob path")


class ProcessDocumentsRequest(BaseModel):
    """Request to process documents with the agent."""
    documents: List[DocumentInfo] = Field(..., description="List of documents to process")
    prompt: str = Field(..., description="User's question about the documents")
    session_id: Optional[str] = Field(None, description="Session ID for conversation continuity")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "documents": [
                        {
                            "document_id": "abc-123",
                            "filename": "report.pdf",
                            "content_type": "application/pdf",
                            "blob_path": "uploads/user-id/abc-123/report.pdf"
                        }
                    ],
                    "prompt": "Summarize the key findings in this report",
                    "session_id": "session-xyz"
                }
            ]
        }
    }


class ProcessDocumentsResponse(BaseModel):
    """Response from document processing."""
    success: bool
    response: Optional[str] = None
    documents_processed: int = 0
    agent_name: Optional[str] = None
    agent_area: Optional[str] = None
    session_id: Optional[str] = None
    error: Optional[str] = None
    metadata: Optional[dict] = None


class SupportedTypesResponse(BaseModel):
    """Response with supported file types."""
    supported_types: dict = Field(..., description="Map of MIME types to descriptions")


class SignedDownloadUrlResponse(BaseModel):
    """Response with signed download URL."""
    signed_url: str = Field(..., description="Time-limited signed URL for downloading")
    expires_in_seconds: int = Field(..., description="URL expiration time in seconds")


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/documents/supported-types", response_model=SupportedTypesResponse)
async def get_supported_types():
    """
    Get list of supported file types for upload.

    Returns a dictionary mapping MIME types to human-readable descriptions.
    """
    return SupportedTypesResponse(supported_types=SUPPORTED_MIME_TYPES)


@router.get("/documents/signed-url", response_model=SignedDownloadUrlResponse)
async def get_signed_download_url(
    blob_path: str,
    user: dict = Depends(require_auth),
):
    """
    Generate a time-limited signed URL for downloading/viewing a document.

    **Authentication:** Requires valid Teams SSO token or OAuth2 JWT.

    **Security:**
    - Users can only access their own documents
    - URLs expire after 15 minutes
    - Bucket remains private (no public access)

    **Usage:**
    Use this endpoint to get a temporary URL for viewing/downloading
    documents that were previously uploaded. The returned URL can be
    opened directly in the browser.
    """
    try:
        user_id = user["user_id"]

        logger.info(f"🔗 Generating signed download URL for user {user_id}: {blob_path}")

        # Security: Verify the blob_path belongs to this user
        if not blob_path.startswith(f"uploads/{user_id}/"):
            logger.warning(f"⚠️ Access denied: User {user_id} attempted to access {blob_path}")
            raise HTTPException(
                status_code=403,
                detail="Access denied. You can only access your own documents.",
            )

        storage = get_storage_service()

        # Verify document exists
        doc_info = storage.verify_upload(blob_path)
        if not doc_info or not doc_info.get("exists"):
            raise HTTPException(
                status_code=404,
                detail="Document not found",
            )

        # Generate signed URL (15 minutes expiry)
        expiration_minutes = 15
        signed_url = storage.generate_presigned_download_url(
            blob_path=blob_path,
            expiration_minutes=expiration_minutes,
        )

        return SignedDownloadUrlResponse(
            signed_url=signed_url,
            expires_in_seconds=expiration_minutes * 60,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error generating signed download URL: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate download URL: {str(e)}",
        )


@router.post("/documents/presigned-url", response_model=PresignedUrlResponse)
async def generate_presigned_url(
    request_body: PresignedUrlRequest,
    user: dict = Depends(require_auth),
):
    """
    Generate a presigned URL for uploading a document.

    **Authentication:** Requires valid Teams SSO token or OAuth2 JWT.

    **Usage:**
    1. Call this endpoint with filename and content_type
    2. Use the returned `upload_url` to PUT your file directly to GCS
    3. Call `/documents/confirm-upload` to verify the upload succeeded

    **Example upload with curl:**
    ```bash
    curl -X PUT -H "Content-Type: application/pdf" \\
         --data-binary @myfile.pdf \\
         "<upload_url>"
    ```
    """
    try:
        user_id = user["user_id"]

        logger.info(f"📤 Generating presigned URL for {user_id}: {request_body.filename}")

        # Validate content type
        if request_body.content_type not in SUPPORTED_MIME_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported content type: {request_body.content_type}. "
                       f"Supported types: {list(SUPPORTED_MIME_TYPES.keys())}"
            )

        storage = get_storage_service()

        result = storage.generate_presigned_upload_url(
            user_id=user_id,
            filename=request_body.filename,
            content_type=request_body.content_type,
            expiration_minutes=15,
        )

        return PresignedUrlResponse(
            document_id=result["document_id"],
            upload_url=result["upload_url"],
            filename=result["filename"],
            content_type=result["content_type"],
            blob_path=result["blob_path"],
            expires_in_seconds=result["expires_in_seconds"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error generating presigned URL: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate upload URL: {str(e)}")


@router.post("/documents/confirm-upload", response_model=UploadConfirmResponse)
async def confirm_upload(
    request_body: UploadConfirmRequest,
    user: dict = Depends(require_auth),
):
    """
    Confirm that a document upload completed successfully.

    **Authentication:** Requires valid Teams SSO token or OAuth2 JWT.

    Call this after uploading a file to verify it exists in GCS.
    """
    try:
        logger.info(f"✅ Confirming upload: {request_body.document_id}")

        storage = get_storage_service()

        result = storage.verify_upload(request_body.blob_path)

        if not result or not result.get("exists"):
            return UploadConfirmResponse(
                success=False,
                document_id=request_body.document_id,
                message="Document not found. Upload may have failed or URL expired.",
            )

        return UploadConfirmResponse(
            success=True,
            document_id=request_body.document_id,
            size_bytes=result.get("size_bytes"),
            message="Document uploaded successfully",
        )

    except Exception as e:
        logger.error(f"❌ Error confirming upload: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to confirm upload: {str(e)}")


@router.post("/documents/process", response_model=ProcessDocumentsResponse)
async def process_documents(
    request_body: ProcessDocumentsRequest,
    user: dict = Depends(require_auth),
):
    """
    Process uploaded documents with Gemini and the agent.

    **Authentication:** Requires valid Teams SSO token or OAuth2 JWT.

    **Usage:**
    1. First upload documents using presigned URLs
    2. Confirm each upload completed
    3. Call this endpoint with document references and your question
    4. Receive the agent's analysis of the documents

    **Supports multiple documents:** You can include multiple documents
    in a single request for comparative analysis or aggregated queries.

    **Supported file types:** PDF, Word, Excel, PowerPoint, images (JPEG, PNG, GIF, WebP),
    text files, CSV, HTML, Markdown.
    """
    try:
        user_id = user["user_id"]
        user_name = user.get("name", "Unknown")

        logger.info("=" * 60)
        logger.info("📄 DOCUMENT PROCESSING REQUEST")
        logger.info("=" * 60)
        logger.info(f"👤 User: {user_name} ({user_id})")
        logger.info(f"📚 Documents: {len(request_body.documents)}")
        logger.info(f"💬 Prompt: {request_body.prompt[:100]}...")

        # Convert to DocumentReference objects
        doc_refs = [
            DocumentReference(
                document_id=doc.document_id,
                filename=doc.filename,
                content_type=doc.content_type,
                blob_path=doc.blob_path,
            )
            for doc in request_body.documents
        ]

        # Get services
        container = get_container()
        agent_service = await container.get_agent_service()
        group_mapping_repo = await container.init_group_mapping_repository()

        # Get the appropriate agent for this user
        teams_integration = TeamsAgentIntegration(
            agent_service,
            group_mapping_repo,
        )

        # Get user's groups and find the right agent
        user_groups = await teams_integration.get_user_groups(user_id)
        if not user_groups:
            user_groups = ["General-Users"]

        agent_config = await teams_integration.agent_router.get_agent_for_user(user_groups)

        if not agent_config:
            return ProcessDocumentsResponse(
                success=False,
                error="No agent available for your user group",
            )

        # Process documents with Gemini
        processor = get_document_processor()

        # Build system instruction from agent config
        system_instruction = agent_config.instruction if agent_config.instruction else None

        result = await processor.process_documents(
            documents=doc_refs,
            user_query=request_body.prompt,
            system_instruction=system_instruction,
        )

        if not result.success:
            return ProcessDocumentsResponse(
                success=False,
                error=result.error,
                documents_processed=result.documents_processed,
            )

        logger.info("=" * 60)
        logger.info("✅ DOCUMENT PROCESSING COMPLETE")
        logger.info("=" * 60)
        logger.info(f"📚 Processed: {result.documents_processed} document(s)")
        logger.info(f"📝 Response length: {len(result.response)} chars")

        return ProcessDocumentsResponse(
            success=True,
            response=result.response,
            documents_processed=result.documents_processed,
            agent_name=agent_config.name,
            agent_area=agent_config.area_type,
            session_id=request_body.session_id,
            metadata=result.metadata,
        )

    except Exception as e:
        logger.error("=" * 60)
        logger.error("❌ DOCUMENT PROCESSING ERROR")
        logger.error("=" * 60)
        logger.error(f"Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Document processing failed: {str(e)}")


@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: str,
    blob_path: str,
    user: dict = Depends(require_auth),
):
    """
    Delete an uploaded document.

    **Authentication:** Requires valid Teams SSO token or OAuth2 JWT.

    **Note:** Users can only delete their own documents.
    """
    try:
        user_id = user["user_id"]

        # Verify the blob_path belongs to this user
        if f"uploads/{user_id}/" not in blob_path:
            raise HTTPException(
                status_code=403,
                detail="You can only delete your own documents",
            )

        storage = get_storage_service()
        success = storage.delete_document(blob_path)

        if success:
            return {"success": True, "message": "Document deleted"}
        else:
            raise HTTPException(status_code=404, detail="Document not found or already deleted")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error deleting document: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete document: {str(e)}")


@router.get("/documents/list")
async def list_user_documents(
    user: dict = Depends(require_auth),
    max_results: int = 100,
):
    """
    List all documents uploaded by the current user.

    **Authentication:** Requires valid Teams SSO token or OAuth2 JWT.
    """
    try:
        user_id = user["user_id"]

        storage = get_storage_service()
        documents = storage.list_user_documents(user_id, max_results)

        return {
            "user_id": user_id,
            "document_count": len(documents),
            "documents": documents,
        }

    except Exception as e:
        logger.error(f"❌ Error listing documents: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list documents: {str(e)}")
