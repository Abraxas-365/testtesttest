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
from src.application.api.teams_routes import router as teams_router
from src.application.api.tabs_routes import router as tabs_router
from src.application.api.auth_routes import router as auth_router
from src.application.api.group_mapping_routes import router as group_mapping_router
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
    description="Google ADK Agent Service with PDF/DOCX support",
    version="1.0.1",
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
# Legacy bot routes (can be deprecated once tabs are fully migrated)
app.include_router(teams_router, prefix="/api/v1", tags=["teams-bot"])
# New Teams Tabs + Web routes (replacement for bot framework)
app.include_router(tabs_router, prefix="/api/v1", tags=["teams-tabs", "web"])
# OAuth2 authentication routes for web application
app.include_router(auth_router, prefix="/api/v1", tags=["auth"])
app.include_router(group_mapping_router, prefix="/api/v1", tags=["group-mappings"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "GrupoDC Agent Service",
        "version": "1.0.1",
        "features": ["PDF support", "DOCX support", "Gemini 2.5 Flash"],
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    """Health check."""
    return {
        "status": "healthy",
        "version": "2.0.0",
        "mode": "multi (bot + tabs + web)",
        "authentication": {
            "teams_bot": True,
            "teams_sso": True,
            "web_oauth2": True
        },
        "file_support": {
            "pdf": True,
            "docx": True,
            "method": "gemini_native"
        },
        "endpoints": {
            "bot": "/api/v1/teams/message",
            "tabs": "/api/v1/tabs/invoke",
            "tabs_health": "/api/v1/tabs/health",
            "auth_login": "/api/v1/auth/login-url",
            "auth_callback": "/api/v1/auth/callback",
            "auth_me": "/api/v1/auth/me",
            "auth_status": "/api/v1/auth/status"
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
