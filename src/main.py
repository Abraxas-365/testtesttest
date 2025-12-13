"""Main application entry point for Cloud Run."""

import os
import logging
from contextlib import asynccontextmanager

# Configure Vertex AI environment variables BEFORE any imports
if not os.getenv("GOOGLE_GENAI_USE_VERTEXAI"):
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"

if not os.getenv("GOOGLE_CLOUD_PROJECT"):
    logger_msg = "WARNING: GOOGLE_CLOUD_PROJECT not set. ADK agents will fail."
    print(logger_msg)

if not os.getenv("GOOGLE_CLOUD_LOCATION"):
    os.environ["GOOGLE_CLOUD_LOCATION"] = "us-east4"
    print(f"INFO: GOOGLE_CLOUD_LOCATION not set, defaulting to us-east4")

if not os.getenv("GOOGLE_API_KEY"):
    # For Vertex AI, we don't need API key, but SDK checks for it
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.application.api import router
from src.application.api.chat_routes import router as chat_router
from src.application.api.auth_routes import router as auth_router
from src.application.api.group_mapping_routes import router as group_mapping_router
from src.application.api.document_routes import router as document_router
from src.application.api.text_editor_routes import router as text_editor_router
from src.application.api.policy_routes import router as policy_router
from src.application.api.rbac_routes import router as rbac_router
from src.application.di import get_container, close_container


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("🚀 Starting application...")
    try:
        container = get_container()
        await container.init_repository()
        logger.info("✅ Application started successfully")
        logger.info("📄 File processing: Gemini Native (PDF/DOCX)")
    except Exception as e:
        logger.error(f"❌ Error during startup: {e}")
        raise

    yield

    # Shutdown
    logger.info("🛑 Shutting down application...")
    try:
        await close_container()
        logger.info("✅ Application shut down successfully")
    except Exception as e:
        logger.error(f"❌ Error during shutdown: {e}")


# Create FastAPI application
app = FastAPI(
    title="GrupoDC Agent Service",
    description="Google ADK Agent Service with Chat API, PDF/DOCX support",
    version="3.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
# Updated for Teams Tabs support with specific domain allowlist
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        # Teams domains
        "https://teams.microsoft.com",
        "https://*.teams.microsoft.com",
        "https://*.teams.office.com",
        "https://outlook.office.com",
        "https://*.outlook.office.com",
        # Local development
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:8080",
        # Add your deployed frontend URL here
        # "https://your-frontend-app.com",
        # Allow all for development (comment out in production)
        "*",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router, prefix="/api/v1")

# ============================================
# Chat API (RESTful chat session management)
# ============================================
app.include_router(chat_router, prefix="/api/v1", tags=["chat"])

# ============================================
# Other API routes
# ============================================
# OAuth2 authentication routes for web application
app.include_router(auth_router, prefix="/api/v1", tags=["auth"])
app.include_router(group_mapping_router, prefix="/api/v1", tags=["group-mappings"])
# Document upload and processing routes
app.include_router(document_router, prefix="/api/v1", tags=["documents"])
# AI Text Editor routes
app.include_router(text_editor_router, prefix="/api/v1", tags=["ai-editor"])
# Policy creation and management routes
app.include_router(policy_router, prefix="/api/v1", tags=["policies"])
# RBAC (Role-Based Access Control) routes
app.include_router(rbac_router, prefix="/api/v1", tags=["rbac"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "GrupoDC Agent Service",
        "version": "3.0.0",
        "features": ["Chat API", "PDF support", "DOCX support", "Gemini 2.5 Flash"],
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    """Health check."""
    return {
        "status": "healthy",
        "version": "3.0.0",
        "mode": "chat_api",
        "authentication": {
            "jwt_required": True,
            "methods": ["teams_sso", "web_oauth2"]
        },
        "file_support": {
            "pdf": True,
            "docx": True,
            "images": True,
            "excel": True,
            "method": "gemini_native",
            "multi_document": True,
            "presigned_upload": True
        },
        "endpoints": {
            # Chat API
            "chat": "/api/v1/chat",
            "chat_session": "/api/v1/chat/sessions/{session_id}",
            "list_sessions": "/api/v1/chat/sessions",
            "get_session": "/api/v1/chat/sessions/{session_id}",
            "delete_session": "/api/v1/chat/sessions/{session_id}",

            # Authentication
            "auth_login": "/api/v1/auth/login-url",
            "auth_callback": "/api/v1/auth/callback",
            "auth_me": "/api/v1/auth/me",
            "auth_status": "/api/v1/auth/status",

            # Documents
            "documents_presigned": "/api/v1/documents/presigned-url",
            "documents_confirm": "/api/v1/documents/confirm-upload",
            "documents_process": "/api/v1/documents/process",
            "documents_supported_types": "/api/v1/documents/supported-types",

            # AI Editor
            "ai_editor_stream": "/api/v1/ai-editor/stream",
            "ai_editor_upload": "/api/v1/ai-editor/upload",
            "ai_editor_chat": "/api/v1/ai-editor/chat",
            "ai_editor_documents": "/api/v1/ai-editor/documents",

            # RBAC (Role-Based Access Control)
            "rbac_me": "/api/v1/rbac/me",
            "rbac_roles": "/api/v1/rbac/roles",
            "rbac_superadmins": "/api/v1/rbac/superadmins",
            "rbac_group_mappings": "/api/v1/rbac/group-mappings"
        }
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8080"))
    host = os.getenv("HOST", "0.0.0.0")

    logger.info(f"🚀 Starting server on {host}:{port}")

    uvicorn.run(
        "src.main:app",
        host=host,
        port=port,
        reload=os.getenv("ENVIRONMENT") == "development",
        log_level="info",
    )
