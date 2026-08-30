"""
DataQuality.AI - Main Application Entry Point
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, generate_latest

from app.api.v1.dependencies.tenant_auth import TenantAPIError, tenant_api_error_handler
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logging_config import setup_logging
from app.middleware.correlation import CorrelationIdMiddleware
from app.services.data_sources.errors import DataSourceAPIError, data_source_api_error_handler
from app.services.datasets.errors import DatasetAPIError, dataset_api_error_handler
from app.services.workspaces.errors import WorkspaceAPIError, workspace_api_error_handler

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)


async def http_exception_handler(request, exc: HTTPException) -> JSONResponse:
    """
    FastAPI exception handler for HTTPException.

    Formats error response per TDD §4.9 to match WorkspaceAPIError format.
    Provides uniform error envelope for auth/validation errors.
    """
    # Map HTTP status codes to error codes
    code_map = {
        401: "unauthorized",
        403: "insufficient_permissions",
        404: "not_found",
        422: "validation_error",
    }
    error_code = code_map.get(exc.status_code, "error")

    try:
        request.state.error_code = error_code
    except Exception:
        pass

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": error_code,
                "message": exc.detail if isinstance(exc.detail, str) else str(exc.detail),
                "fields": None,
            }
        },
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Environment: {settings.ENVIRONMENT}")

    # Initialize services
    # TODO: Initialize database connection pool
    # TODO: Initialize vector store
    # TODO: Warm up LLM connection

    # Initialize Spark session if enabled
    try:
        from app.services.execution.spark_session_manager import SparkSessionManager

        deployment_mode = os.getenv("DEPLOYMENT_MODE", "docker-compose")
        enable_cluster = os.getenv("ENABLE_CLUSTER_MODE", "false").lower() == "true"

        if enable_cluster or "spark" in deployment_mode.lower():
            logger.info("Initializing Spark session manager...")
            spark_manager = SparkSessionManager.get_instance()
            session_info = spark_manager.get_session_info()
            if session_info.get("session_active"):
                logger.info(f"Spark session initialized: {session_info}")
            else:
                logger.warning("Spark session not active, will be initialized on first use")
    except Exception as e:
        logger.warning(f"Spark initialization skipped or failed: {e}")

    yield

    # Shutdown
    logger.info(f"Shutting down {settings.APP_NAME}")

    # Close Spark session
    try:
        from app.services.execution.spark_session_manager import SparkSessionManager

        spark_manager = SparkSessionManager.get_instance()
        spark_manager.close_session()
        logger.info("Spark session closed")
    except Exception as e:
        logger.warning(f"Error closing Spark session: {e}")

    # TODO: Close database connections
    # TODO: Close vector store
    # TODO: Cleanup resources


# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Natural Language Data Quality Platform",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# F001 — Correlation ID + Structured Request Logging (TDD §8.2)
# Must be added AFTER CORSMiddleware so the correlation ID header is present
# in all responses, including CORS preflight responses.
app.add_middleware(CorrelationIdMiddleware)

# Register F001 structured error handler
app.add_exception_handler(TenantAPIError, tenant_api_error_handler)  # type: ignore[arg-type]

# Register F002 structured error handler
app.add_exception_handler(WorkspaceAPIError, workspace_api_error_handler)  # type: ignore[arg-type]

# Register F004 structured error handler
app.add_exception_handler(DataSourceAPIError, data_source_api_error_handler)  # type: ignore[arg-type]

# Register F005 structured error handler
app.add_exception_handler(DatasetAPIError, dataset_api_error_handler)  # type: ignore[arg-type]

# Register global HTTPException handler for consistent error format
app.add_exception_handler(HTTPException, http_exception_handler)  # type: ignore[arg-type]


# Health check endpoint
@app.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint"""
    return JSONResponse(
        content={
            "status": "healthy",
            "app": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT,
        }
    )


# Prometheus metrics endpoint
@app.get("/metrics", tags=["observability"], include_in_schema=False)
async def metrics():
    """Prometheus scrape endpoint — exposes all registered metrics."""
    return Response(content=generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)


# Root endpoint
@app.get("/", tags=["root"])
async def root():
    """Root endpoint"""
    return {
        "message": f"Welcome to {settings.APP_NAME}",
        "version": settings.APP_VERSION,
        "docs": "/api/docs",
    }


# Include API router
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": str(exc) if settings.DEBUG else "An unexpected error occurred",
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
    )
