"""Main application entry point for Cloud Run."""

import os
import logging
from contextlib import asynccontextmanager

# Configure Vertex AI environment variables BEFORE any ADK imports
# ADK reads these variables during initialization, so they must be set first
if not os.getenv("GOOGLE_GENAI_USE_VERTEXAI"):
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"

# Set project and location from Cloud Run's environment
# These are typically already set in Cloud Run, but we ensure they exist
if not os.getenv("GOOGLE_CLOUD_PROJECT"):
    logger_msg = "WARNING: GOOGLE_CLOUD_PROJECT not set. ADK agents will fail."
    print(logger_msg)

if not os.getenv("GOOGLE_CLOUD_LOCATION"):
    # Default to us-central1 if not specified
    os.environ["GOOGLE_CLOUD_LOCATION"] = "us-central1"
    print(f"INFO: GOOGLE_CLOUD_LOCATION not set, defaulting to us-central1")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.application.api import router
from src.application.api.teams_routes import router as teams_router
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
    """
    Application lifespan manager.

    Handles startup and shutdown events.
    """
    # Startup
    logger.info("Starting application...")
    try:
        container = get_container()
        await container.init_repository()
        logger.info("Application started successfully")
    except Exception as e:
        logger.error(f"Error during startup: {e}")
        raise

    yield

    # Shutdown
    logger.info("Shutting down application...")
    try:
        await close_container()
        logger.info("Application shut down successfully")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")


# Create FastAPI application
app = FastAPI(
    title="ADK Agent Service",
    description="Google ADK Agent Service with PostgreSQL configuration",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router, prefix="/api/v1")
app.include_router(teams_router, prefix="/api/v1", tags=["teams"])
app.include_router(group_mapping_router, prefix="/api/v1", tags=["group-mappings"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "ADK Agent Service",
        "version": "1.0.0",
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8080"))
    host = os.getenv("HOST", "0.0.0.0")

    logger.info(f"Starting server on {host}:{port}")

    uvicorn.run(
        "src.main:app",
        host=host,
        port=port,
        reload=os.getenv("ENVIRONMENT") == "development",
        log_level="info",
    )
