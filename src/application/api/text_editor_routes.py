"""
AI Text Editor API Routes.

Provides endpoints for:
- Streaming AI text generation with diff suggestions (SSE)
- File upload for attachments
- Non-streaming chat
- Document persistence (CRUD)
"""

import os
import json
import uuid
import logging
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.middleware.teams_auth import require_auth
from src.application.di import get_container
from src.domain.models import (
    DocumentContext,
    AttachmentInfo,
    EditorDocument,
    StreamEvent,
)
from src.domain.services.text_editor_service import TextEditorService
from src.services.storage_service import StorageService
from src.services.diff_generator import DiffGenerator

logger = logging.getLogger(__name__)
router = APIRouter()

# Lazy service initialization
_text_editor_service: Optional[TextEditorService] = None
_storage_service: Optional[StorageService] = None

# Supported upload types for text editor
SUPPORTED_UPLOAD_TYPES = {
    "application/pdf": "PDF Document",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "Word Document",
    "text/plain": "Text File",
    "image/png": "PNG Image",
    "image/jpeg": "JPEG Image",
    "image/gif": "GIF Image",
    "image/webp": "WebP Image",
}

MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB


def get_storage_service() -> StorageService:
    """Get or create storage service singleton."""
    global _storage_service
    if _storage_service is None:
        _storage_service = StorageService()
    return _storage_service


async def get_text_editor_service() -> TextEditorService:
    """Get or create text editor service singleton."""
    global _text_editor_service
    if _text_editor_service is None:
        container = get_container()
        agent_service = await container.get_agent_service()
        storage = get_storage_service()
        _text_editor_service = TextEditorService(
            agent_service=agent_service,
            storage_service=storage,
            diff_generator=DiffGenerator()
        )
    return _text_editor_service


# =============================================================================
# Request/Response Models
# =============================================================================


class DocumentContextRequest(BaseModel):
    """Document context in requests."""
    id: Optional[str] = None
    content: str = ""
    title: Optional[str] = None
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None


class AttachmentInfoRequest(BaseModel):
    """Attachment info in requests."""
    id: str
    url: str
    name: str
    mimeType: str
    size: int
    blobPath: Optional[str] = None


class StreamRequest(BaseModel):
    """Request for streaming AI text generation."""
    message: str = Field(..., description="User's message/prompt")
    attachments: List[AttachmentInfoRequest] = Field(default_factory=list)
    document: Optional[DocumentContextRequest] = None
    sessionId: Optional[str] = Field(None, description="Session ID for conversation continuity")

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "message": "Please rewrite this paragraph to be more concise",
                "document": {
                    "id": "doc-123",
                    "content": "The quick brown fox jumps over the lazy dog.",
                    "title": "My Document"
                },
                "attachments": []
            }]
        }
    }


class ChatRequest(BaseModel):
    """Request for non-streaming chat."""
    message: str = Field(..., description="User's message/prompt")
    attachments: List[AttachmentInfoRequest] = Field(default_factory=list)
    document: Optional[DocumentContextRequest] = None
    sessionId: Optional[str] = Field(None, description="Session ID")


class DiffSuggestionResponse(BaseModel):
    """Diff suggestion in responses."""
    id: str
    type: str
    originalText: str
    newText: str
    startIndex: int
    endIndex: int


class ChatResponse(BaseModel):
    """Response from non-streaming chat."""
    content: str
    diffs: List[DiffSuggestionResponse] = Field(default_factory=list)
    sessionId: Optional[str] = None


class UploadRequest(BaseModel):
    """Request for generating upload URL."""
    filename: str = Field(..., description="Filename with extension")
    contentType: str = Field(..., description="MIME type of the file")


class UploadResponse(BaseModel):
    """Response from file upload."""
    id: str
    url: str
    name: str
    mimeType: str
    size: int
    blobPath: str


class SaveDocumentRequest(BaseModel):
    """Request to save a document."""
    id: Optional[str] = None
    title: str = Field(..., description="Document title")
    content: str = Field(..., description="Document content (markdown)")
    metadata: Optional[dict] = Field(default_factory=dict)


class DocumentResponse(BaseModel):
    """Response with document data."""
    id: str
    title: str
    content: str
    metadata: Optional[dict] = None
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None


class DocumentListResponse(BaseModel):
    """Response with list of documents."""
    documents: List[DocumentResponse]
    total: int
    limit: int
    offset: int


# =============================================================================
# Helper Functions
# =============================================================================


def _request_to_document_context(doc: Optional[DocumentContextRequest]) -> Optional[DocumentContext]:
    """Convert request model to domain model."""
    if not doc:
        return None
    return DocumentContext(
        id=doc.id,
        content=doc.content,
        title=doc.title,
        created_at=doc.createdAt,
        updated_at=doc.updatedAt,
    )


def _request_to_attachment_info(att: AttachmentInfoRequest) -> AttachmentInfo:
    """Convert request model to domain model."""
    return AttachmentInfo(
        id=att.id,
        url=att.url,
        name=att.name,
        mime_type=att.mimeType,
        size=att.size,
        blob_path=att.blobPath,
    )


async def _sse_generator(events):
    """
    Async generator that formats StreamEvents as SSE data.

    SSE Format:
    - data: {"content": "..."} for content chunks
    - data: {"diff": {...}} for diff suggestions
    - data: [DONE] for completion
    """
    try:
        async for event in events:
            yield event.to_sse()
    except Exception as e:
        logger.error(f"SSE generator error: {e}")
        yield f"data: {json.dumps({'error': str(e)})}\n\n"


# =============================================================================
# Stream Endpoint (PRIMARY)
# =============================================================================


@router.post("/ai-editor/stream")
async def stream_ai_editor(
    request: StreamRequest,
    user: dict = Depends(require_auth),
):
    """
    Stream AI text generation with diff suggestions.

    **Authentication:** Requires valid JWT token.

    **Response Format:** Server-Sent Events (SSE)
    - Content chunks: `data: {"content": "..."}`
    - Diff suggestions: `data: {"diff": {"id": "...", "type": "...", ...}}`
    - Completion: `data: [DONE]`

    **Client Usage:**
    ```javascript
    const response = await fetch('/api/v1/ai-editor/stream', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
            message: "Rewrite this paragraph...",
            document: { content: "..." }
        })
    });

    const reader = response.body.getReader();
    // Process SSE stream...
    ```

    **Cancellation:** Client can abort using AbortController.
    """
    try:
        user_id = user["user_id"]
        logger.info(f"Stream request from user {user_id}: {request.message[:50]}...")

        service = await get_text_editor_service()

        # Convert request models to domain models
        document = _request_to_document_context(request.document)
        attachments = [_request_to_attachment_info(a) for a in request.attachments]

        # Create the streaming response
        event_stream = service.stream_response(
            message=request.message,
            user_id=user_id,
            document=document,
            attachments=attachments,
            session_id=request.sessionId,
        )

        return StreamingResponse(
            _sse_generator(event_stream),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
            }
        )

    except Exception as e:
        logger.error(f"Stream endpoint error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Upload Endpoint
# =============================================================================


@router.post("/ai-editor/upload", response_model=UploadResponse)
async def upload_file(
    request: UploadRequest,
    user: dict = Depends(require_auth),
):
    """
    Generate a presigned URL for uploading an attachment.

    **Authentication:** Requires valid JWT token.

    **Supported Types:** PDF, DOCX, TXT, PNG, JPG, GIF, WebP
    **Max Size:** 10MB

    **Usage:**
    1. Call this endpoint to get presigned URL
    2. PUT your file directly to the returned URL
    3. Include the returned info in your stream request attachments
    """
    try:
        user_id = user["user_id"]

        # Validate content type
        if request.contentType not in SUPPORTED_UPLOAD_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported content type: {request.contentType}. "
                       f"Supported: {list(SUPPORTED_UPLOAD_TYPES.keys())}"
            )

        storage = get_storage_service()
        result = storage.generate_presigned_upload_url(
            user_id=user_id,
            filename=request.filename,
            content_type=request.contentType,
            expiration_minutes=15,
        )

        return UploadResponse(
            id=result["document_id"],
            url=result["upload_url"],
            name=request.filename,
            mimeType=request.contentType,
            size=0,  # Size unknown until upload completes
            blobPath=result["blob_path"]
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Chat Endpoint (Non-streaming)
# =============================================================================


@router.post("/ai-editor/chat", response_model=ChatResponse)
async def chat_ai_editor(
    request: ChatRequest,
    user: dict = Depends(require_auth),
):
    """
    Non-streaming AI text editor interaction.

    **Authentication:** Requires valid JWT token.

    Returns the complete response with all diff suggestions.
    Use this for simple interactions or when streaming is not needed.
    """
    try:
        user_id = user["user_id"]
        logger.info(f"Chat request from user {user_id}: {request.message[:50]}...")

        service = await get_text_editor_service()

        # Convert request models
        document = _request_to_document_context(request.document)
        attachments = [_request_to_attachment_info(a) for a in request.attachments]

        # Get non-streaming response
        content, diffs, session_id = await service.get_non_streaming_response(
            message=request.message,
            user_id=user_id,
            document=document,
            attachments=attachments,
            session_id=request.sessionId,
        )

        return ChatResponse(
            content=content,
            diffs=[
                DiffSuggestionResponse(
                    id=d.id,
                    type=d.type.value,
                    originalText=d.original_text,
                    newText=d.new_text,
                    startIndex=d.start_index,
                    endIndex=d.end_index,
                )
                for d in diffs
            ],
            sessionId=session_id,
        )

    except Exception as e:
        logger.error(f"Chat endpoint error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Document CRUD Endpoints
# =============================================================================


@router.post("/ai-editor/documents", response_model=DocumentResponse)
async def save_document(
    request: SaveDocumentRequest,
    user: dict = Depends(require_auth),
):
    """
    Save a document for the text editor.

    **Authentication:** Requires valid JWT token.

    Creates a new document or updates an existing one.
    """
    try:
        user_id = user["user_id"]
        container = get_container()
        repository = await container.get_text_editor_repository()

        # Create document object
        document = EditorDocument(
            document_id=request.id or str(uuid.uuid4()),
            user_id=user_id,
            title=request.title,
            content=request.content,
            metadata=request.metadata or {},
        )

        # Save document
        saved = await repository.save_document(document)

        return DocumentResponse(
            id=saved.document_id,
            title=saved.title,
            content=saved.content,
            metadata=saved.metadata,
            createdAt=saved.created_at.isoformat() if saved.created_at else None,
            updatedAt=saved.updated_at.isoformat() if saved.updated_at else None,
        )

    except Exception as e:
        logger.error(f"Save document error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ai-editor/documents", response_model=DocumentListResponse)
async def list_documents(
    user: dict = Depends(require_auth),
    limit: int = 50,
    offset: int = 0,
):
    """
    List user's documents.

    **Authentication:** Requires valid JWT token.
    """
    try:
        user_id = user["user_id"]
        container = get_container()
        repository = await container.get_text_editor_repository()

        # Get documents
        documents = await repository.list_user_documents(user_id, limit, offset)
        total = await repository.count_user_documents(user_id)

        return DocumentListResponse(
            documents=[
                DocumentResponse(
                    id=doc.document_id,
                    title=doc.title,
                    content=doc.content,
                    metadata=doc.metadata,
                    createdAt=doc.created_at.isoformat() if doc.created_at else None,
                    updatedAt=doc.updated_at.isoformat() if doc.updated_at else None,
                )
                for doc in documents
            ],
            total=total,
            limit=limit,
            offset=offset,
        )

    except Exception as e:
        logger.error(f"List documents error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ai-editor/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: str,
    user: dict = Depends(require_auth),
):
    """
    Get a specific document.

    **Authentication:** Requires valid JWT token.
    """
    try:
        user_id = user["user_id"]
        container = get_container()
        repository = await container.get_text_editor_repository()

        document = await repository.get_document_by_id(document_id, user_id)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        return DocumentResponse(
            id=document.document_id,
            title=document.title,
            content=document.content,
            metadata=document.metadata,
            createdAt=document.created_at.isoformat() if document.created_at else None,
            updatedAt=document.updated_at.isoformat() if document.updated_at else None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get document error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/ai-editor/documents/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: str,
    request: SaveDocumentRequest,
    user: dict = Depends(require_auth),
):
    """
    Update a document.

    **Authentication:** Requires valid JWT token.
    """
    try:
        user_id = user["user_id"]
        container = get_container()
        repository = await container.get_text_editor_repository()

        # Check document exists
        existing = await repository.get_document_by_id(document_id, user_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Document not found")

        # Update document
        document = EditorDocument(
            document_id=document_id,
            user_id=user_id,
            title=request.title,
            content=request.content,
            metadata=request.metadata or {},
        )

        saved = await repository.save_document(document)

        return DocumentResponse(
            id=saved.document_id,
            title=saved.title,
            content=saved.content,
            metadata=saved.metadata,
            createdAt=saved.created_at.isoformat() if saved.created_at else None,
            updatedAt=saved.updated_at.isoformat() if saved.updated_at else None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update document error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/ai-editor/documents/{document_id}")
async def delete_document(
    document_id: str,
    user: dict = Depends(require_auth),
):
    """
    Delete a document.

    **Authentication:** Requires valid JWT token.
    """
    try:
        user_id = user["user_id"]
        container = get_container()
        repository = await container.get_text_editor_repository()

        deleted = await repository.delete_document(document_id, user_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Document not found")

        return {"success": True, "message": "Document deleted"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete document error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
