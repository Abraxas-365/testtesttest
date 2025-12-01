# Document Upload & Processing API

This document describes the API endpoints for uploading documents via presigned URLs and processing them with Gemini.

## Overview

The document upload system uses a 3-step flow:

1. **Get Presigned URL** - Request a secure upload URL for your document
2. **Upload Document** - PUT the file directly to Google Cloud Storage
3. **Process Documents** - Send document references to Gemini for analysis

This approach allows large files to be uploaded directly to cloud storage without going through the backend, improving performance and scalability.

---

## Environment Variables

Add these to your `.env` file:

```bash
# Required for document uploads
GCS_BUCKET_NAME=your-project-documents  # Defaults to {GOOGLE_CLOUD_PROJECT}-documents
GOOGLE_CLOUD_PROJECT=your-gcp-project
GOOGLE_CLOUD_LOCATION=us-east4
```

### GCS Bucket Setup

Create a bucket with appropriate CORS settings:

```bash
# Create bucket
gsutil mb -l us-east4 gs://your-project-documents

# Set CORS for browser uploads
cat > cors.json << 'EOF'
[
  {
    "origin": ["*"],
    "method": ["PUT", "GET", "DELETE"],
    "responseHeader": ["Content-Type", "Content-Length"],
    "maxAgeSeconds": 3600
  }
]
EOF

gsutil cors set cors.json gs://your-project-documents
```

---

## API Endpoints

### 1. Get Supported File Types

Returns the list of supported MIME types for document upload.

**Endpoint:** `GET /api/v1/documents/supported-types`

**Authentication:** None required

**Response:**
```json
{
  "supported_types": {
    "application/pdf": "PDF Document",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "Word Document",
    "application/msword": "Word Document (Legacy)",
    "text/plain": "Text File",
    "text/csv": "CSV File",
    "text/html": "HTML File",
    "text/markdown": "Markdown File",
    "image/jpeg": "JPEG Image",
    "image/png": "PNG Image",
    "image/gif": "GIF Image",
    "image/webp": "WebP Image",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "Excel Spreadsheet",
    "application/vnd.ms-excel": "Excel Spreadsheet (Legacy)",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "PowerPoint",
    "application/vnd.ms-powerpoint": "PowerPoint (Legacy)"
  }
}
```

---

### 2. Generate Presigned Upload URL

Generates a presigned URL for uploading a document directly to GCS.

**Endpoint:** `POST /api/v1/documents/presigned-url`

**Authentication:** Required (Teams SSO or OAuth2 JWT)

**Headers:**
```
Authorization: Bearer <token>
Content-Type: application/json
```

**Request Body:**
```json
{
  "filename": "report.pdf",
  "content_type": "application/pdf"
}
```

**Response:**
```json
{
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "upload_url": "https://storage.googleapis.com/bucket/path?X-Goog-Signature=...",
  "filename": "report.pdf",
  "content_type": "application/pdf",
  "blob_path": "uploads/user-id/550e8400-e29b-41d4-a716-446655440000/report.pdf",
  "expires_in_seconds": 900
}
```

**Error Responses:**
- `400` - Unsupported content type
- `401` - Authentication required
- `500` - Server error

---

### 3. Upload File to GCS

Use the presigned URL from step 2 to upload the file directly to GCS.

**Method:** `PUT`

**URL:** The `upload_url` from the presigned URL response

**Headers:**
```
Content-Type: <same content_type used in presigned URL request>
```

**Body:** Raw file bytes

**Example with curl:**
```bash
curl -X PUT \
  -H "Content-Type: application/pdf" \
  --data-binary @myfile.pdf \
  "https://storage.googleapis.com/bucket/path?X-Goog-Signature=..."
```

**Example with JavaScript:**
```javascript
async function uploadFile(file, presignedData) {
  const response = await fetch(presignedData.upload_url, {
    method: 'PUT',
    headers: {
      'Content-Type': presignedData.content_type,
    },
    body: file,
  });

  if (!response.ok) {
    throw new Error(`Upload failed: ${response.status}`);
  }

  return presignedData;
}
```

---

### 4. Confirm Upload (Optional)

Verify that a document was successfully uploaded.

**Endpoint:** `POST /api/v1/documents/confirm-upload`

**Authentication:** Required (Teams SSO or OAuth2 JWT)

**Request Body:**
```json
{
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "blob_path": "uploads/user-id/550e8400-e29b-41d4-a716-446655440000/report.pdf"
}
```

**Response:**
```json
{
  "success": true,
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "size_bytes": 1048576,
  "message": "Document uploaded successfully"
}
```

---

### 5. Process Documents

Process one or more uploaded documents with Gemini.

**Endpoint:** `POST /api/v1/documents/process`

**Authentication:** Required (Teams SSO or OAuth2 JWT)

**Request Body:**
```json
{
  "documents": [
    {
      "document_id": "550e8400-e29b-41d4-a716-446655440000",
      "filename": "report.pdf",
      "content_type": "application/pdf",
      "blob_path": "uploads/user-id/550e8400-e29b-41d4-a716-446655440000/report.pdf"
    },
    {
      "document_id": "660e8400-e29b-41d4-a716-446655440001",
      "filename": "data.xlsx",
      "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "blob_path": "uploads/user-id/660e8400-e29b-41d4-a716-446655440001/data.xlsx"
    }
  ],
  "prompt": "Compare the findings in the PDF report with the data in the spreadsheet. Are there any discrepancies?",
  "session_id": "optional-session-id"
}
```

**Response:**
```json
{
  "success": true,
  "response": "Based on my analysis of both documents...",
  "documents_processed": 2,
  "agent_name": "search_assistant",
  "agent_area": "general",
  "session_id": "optional-session-id",
  "metadata": {
    "model": "gemini-2.5-flash",
    "total_documents": 2,
    "processed_documents": 2,
    "failed_documents": null
  }
}
```

**Error Response:**
```json
{
  "success": false,
  "response": null,
  "documents_processed": 0,
  "error": "Failed to process any documents. Errors: report.pdf (file not found)",
  "metadata": null
}
```

---

### 6. List User Documents

List all documents uploaded by the current user.

**Endpoint:** `GET /api/v1/documents/list`

**Authentication:** Required (Teams SSO or OAuth2 JWT)

**Query Parameters:**
- `max_results` (optional): Maximum number of results (default: 100)

**Response:**
```json
{
  "user_id": "user-azure-ad-id",
  "document_count": 3,
  "documents": [
    {
      "blob_path": "uploads/user-id/doc-1/report.pdf",
      "size_bytes": 1048576,
      "content_type": "application/pdf",
      "created": "2024-01-15T10:30:00Z"
    }
  ]
}
```

---

### 7. Delete Document

Delete an uploaded document.

**Endpoint:** `DELETE /api/v1/documents/{document_id}?blob_path=<blob_path>`

**Authentication:** Required (Teams SSO or OAuth2 JWT)

**Query Parameters:**
- `blob_path` (required): The blob path of the document to delete

**Response:**
```json
{
  "success": true,
  "message": "Document deleted"
}
```

---

## Complete Upload & Process Flow

### JavaScript/TypeScript Example

```typescript
interface PresignedUrlResponse {
  document_id: string;
  upload_url: string;
  filename: string;
  content_type: string;
  blob_path: string;
  expires_in_seconds: number;
}

interface DocumentInfo {
  document_id: string;
  filename: string;
  content_type: string;
  blob_path: string;
}

async function uploadAndProcessDocuments(
  files: File[],
  prompt: string,
  authToken: string
): Promise<string> {
  const baseUrl = 'https://your-api.com/api/v1';
  const uploadedDocs: DocumentInfo[] = [];

  // Step 1 & 2: Get presigned URLs and upload each file
  for (const file of files) {
    // Get presigned URL
    const presignedResponse = await fetch(`${baseUrl}/documents/presigned-url`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${authToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        filename: file.name,
        content_type: file.type,
      }),
    });

    if (!presignedResponse.ok) {
      throw new Error(`Failed to get presigned URL for ${file.name}`);
    }

    const presignedData: PresignedUrlResponse = await presignedResponse.json();

    // Upload file directly to GCS
    const uploadResponse = await fetch(presignedData.upload_url, {
      method: 'PUT',
      headers: {
        'Content-Type': presignedData.content_type,
      },
      body: file,
    });

    if (!uploadResponse.ok) {
      throw new Error(`Failed to upload ${file.name}`);
    }

    // Store document info for processing
    uploadedDocs.push({
      document_id: presignedData.document_id,
      filename: presignedData.filename,
      content_type: presignedData.content_type,
      blob_path: presignedData.blob_path,
    });
  }

  // Step 3: Process all documents with Gemini
  const processResponse = await fetch(`${baseUrl}/documents/process`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${authToken}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      documents: uploadedDocs,
      prompt: prompt,
    }),
  });

  if (!processResponse.ok) {
    throw new Error('Failed to process documents');
  }

  const result = await processResponse.json();

  if (!result.success) {
    throw new Error(result.error || 'Processing failed');
  }

  return result.response;
}

// Usage
const files = [/* File objects from input */];
const response = await uploadAndProcessDocuments(
  files,
  'Summarize the key points from these documents',
  'your-auth-token'
);
console.log(response);
```

### Python Example

```python
import httpx
import asyncio

async def upload_and_process_documents(
    files: list[tuple[str, bytes, str]],  # (filename, content, content_type)
    prompt: str,
    auth_token: str,
    base_url: str = "https://your-api.com/api/v1"
) -> str:
    headers = {"Authorization": f"Bearer {auth_token}"}
    uploaded_docs = []

    async with httpx.AsyncClient() as client:
        # Step 1 & 2: Upload each file
        for filename, content, content_type in files:
            # Get presigned URL
            presigned_resp = await client.post(
                f"{base_url}/documents/presigned-url",
                headers=headers,
                json={"filename": filename, "content_type": content_type}
            )
            presigned_resp.raise_for_status()
            presigned_data = presigned_resp.json()

            # Upload to GCS
            upload_resp = await client.put(
                presigned_data["upload_url"],
                content=content,
                headers={"Content-Type": content_type}
            )
            upload_resp.raise_for_status()

            uploaded_docs.append({
                "document_id": presigned_data["document_id"],
                "filename": presigned_data["filename"],
                "content_type": presigned_data["content_type"],
                "blob_path": presigned_data["blob_path"],
            })

        # Step 3: Process documents
        process_resp = await client.post(
            f"{base_url}/documents/process",
            headers=headers,
            json={"documents": uploaded_docs, "prompt": prompt}
        )
        process_resp.raise_for_status()
        result = process_resp.json()

        if not result["success"]:
            raise Exception(result.get("error", "Processing failed"))

        return result["response"]


# Usage
async def main():
    files = [
        ("report.pdf", open("report.pdf", "rb").read(), "application/pdf"),
        ("data.xlsx", open("data.xlsx", "rb").read(),
         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ]

    response = await upload_and_process_documents(
        files=files,
        prompt="Compare these documents and highlight key differences",
        auth_token="your-token"
    )
    print(response)

asyncio.run(main())
```

---

## Error Handling

| Status Code | Description |
|-------------|-------------|
| `400` | Bad request - invalid content type or missing required fields |
| `401` | Unauthorized - missing or invalid authentication token |
| `403` | Forbidden - trying to access another user's documents |
| `404` | Document not found |
| `500` | Server error - check logs for details |

---

## Best Practices

1. **Validate file types client-side** before requesting presigned URLs
2. **Use the confirm-upload endpoint** to verify uploads before processing
3. **Handle upload failures gracefully** - presigned URLs expire after 15 minutes
4. **Batch related documents** in a single process request for better context
5. **Clean up unused documents** using the delete endpoint
6. **Set appropriate CORS** on your GCS bucket for browser uploads

---

## Supported File Types

| Category | Extensions | MIME Types |
|----------|------------|------------|
| Documents | .pdf | application/pdf |
| | .docx | application/vnd.openxmlformats-officedocument.wordprocessingml.document |
| | .doc | application/msword |
| | .txt | text/plain |
| | .md | text/markdown |
| | .html | text/html |
| | .csv | text/csv |
| Spreadsheets | .xlsx | application/vnd.openxmlformats-officedocument.spreadsheetml.sheet |
| | .xls | application/vnd.ms-excel |
| Presentations | .pptx | application/vnd.openxmlformats-officedocument.presentationml.presentation |
| | .ppt | application/vnd.ms-powerpoint |
| Images | .jpg, .jpeg | image/jpeg |
| | .png | image/png |
| | .gif | image/gif |
| | .webp | image/webp |
