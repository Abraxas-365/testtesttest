"""
Google Cloud Storage Service for document uploads.

Provides presigned URL generation for secure client-side uploads
and document retrieval for processing.
"""

import os
import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from google.cloud import storage
from google.cloud.storage import Blob

logger = logging.getLogger(__name__)


@dataclass
class UploadedDocument:
    """Represents an uploaded document."""
    document_id: str
    filename: str
    content_type: str
    gcs_uri: str
    size_bytes: Optional[int] = None
    uploaded_at: Optional[datetime] = None


class StorageService:
    """
    Google Cloud Storage service for document management.

    Handles:
    - Presigned URL generation for uploads
    - Document retrieval for Gemini processing
    - Document lifecycle management
    """

    def __init__(
        self,
        bucket_name: Optional[str] = None,
        project_id: Optional[str] = None,
    ):
        """
        Initialize storage service.

        Args:
            bucket_name: GCS bucket name (defaults to env var GCS_BUCKET_NAME)
            project_id: GCP project ID (defaults to env var GOOGLE_CLOUD_PROJECT)
        """
        self.project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT")
        self.bucket_name = bucket_name or os.getenv("GCS_BUCKET_NAME", f"{self.project_id}-documents")

        self.client = storage.Client(project=self.project_id)
        self.bucket = self.client.bucket(self.bucket_name)

        logger.info(f"✅ StorageService initialized with bucket: {self.bucket_name}")

    def _generate_document_id(self) -> str:
        """Generate a unique document ID."""
        return str(uuid.uuid4())

    def _get_blob_path(self, user_id: str, document_id: str, filename: str) -> str:
        """
        Generate the blob path for a document.

        Path format: uploads/{user_id}/{document_id}/{filename}
        """
        safe_filename = "".join(c if c.isalnum() or c in ".-_" else "_" for c in filename)
        return f"uploads/{user_id}/{document_id}/{safe_filename}"

    def generate_presigned_upload_url(
        self,
        user_id: str,
        filename: str,
        content_type: str,
        expiration_minutes: int = 15,
    ) -> Dict[str, Any]:
        """
        Generate a presigned URL for uploading a document.

        Args:
            user_id: User identifier for organizing uploads
            filename: Original filename
            content_type: MIME type of the file
            expiration_minutes: URL expiration time in minutes

        Returns:
            Dictionary with upload URL and document metadata
        """
        document_id = self._generate_document_id()
        blob_path = self._get_blob_path(user_id, document_id, filename)

        blob = self.bucket.blob(blob_path)

        # Generate signed URL for PUT request
        expiration = timedelta(minutes=expiration_minutes)

        upload_url = blob.generate_signed_url(
            version="v4",
            expiration=expiration,
            method="PUT",
            content_type=content_type,
        )

        logger.info(f"📤 Generated presigned upload URL for document {document_id}")

        return {
            "document_id": document_id,
            "upload_url": upload_url,
            "filename": filename,
            "content_type": content_type,
            "gcs_uri": f"gs://{self.bucket_name}/{blob_path}",
            "blob_path": blob_path,
            "expires_in_seconds": expiration_minutes * 60,
        }

    def generate_presigned_download_url(
        self,
        blob_path: str,
        expiration_minutes: int = 60,
    ) -> str:
        """
        Generate a presigned URL for downloading a document.

        Args:
            blob_path: Path to the blob in GCS
            expiration_minutes: URL expiration time in minutes

        Returns:
            Signed download URL
        """
        blob = self.bucket.blob(blob_path)

        expiration = timedelta(minutes=expiration_minutes)

        download_url = blob.generate_signed_url(
            version="v4",
            expiration=expiration,
            method="GET",
        )

        return download_url

    async def get_document_bytes(self, blob_path: str) -> bytes:
        """
        Download document bytes from GCS.

        Args:
            blob_path: Path to the blob in GCS

        Returns:
            Document content as bytes
        """
        blob = self.bucket.blob(blob_path)
        content = blob.download_as_bytes()

        logger.info(f"📥 Downloaded {len(content)} bytes from {blob_path}")
        return content

    def verify_upload(self, blob_path: str) -> Optional[Dict[str, Any]]:
        """
        Verify that a document was successfully uploaded.

        Args:
            blob_path: Path to the blob in GCS

        Returns:
            Document metadata if exists, None otherwise
        """
        blob = self.bucket.blob(blob_path)

        if not blob.exists():
            logger.warning(f"⚠️ Document not found at {blob_path}")
            return None

        blob.reload()

        return {
            "exists": True,
            "size_bytes": blob.size,
            "content_type": blob.content_type,
            "created": blob.time_created.isoformat() if blob.time_created else None,
            "md5_hash": blob.md5_hash,
        }

    def delete_document(self, blob_path: str) -> bool:
        """
        Delete a document from GCS.

        Args:
            blob_path: Path to the blob in GCS

        Returns:
            True if deleted successfully
        """
        try:
            blob = self.bucket.blob(blob_path)
            blob.delete()
            logger.info(f"🗑️ Deleted document at {blob_path}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to delete {blob_path}: {e}")
            return False

    def list_user_documents(
        self,
        user_id: str,
        max_results: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        List all documents for a user.

        Args:
            user_id: User identifier
            max_results: Maximum number of results

        Returns:
            List of document metadata
        """
        prefix = f"uploads/{user_id}/"
        blobs = self.client.list_blobs(
            self.bucket_name,
            prefix=prefix,
            max_results=max_results,
        )

        documents = []
        for blob in blobs:
            documents.append({
                "blob_path": blob.name,
                "size_bytes": blob.size,
                "content_type": blob.content_type,
                "created": blob.time_created.isoformat() if blob.time_created else None,
            })

        return documents
