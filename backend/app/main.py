"""
Aion Backend - FastAPI Application Entry Point

This is the main entry point for the Aion backend server.
It sets up the FastAPI application with:
- CORS middleware for cross-origin requests from clients
- Rate limiting middleware
- Security headers middleware
- HTTPS enforcement (production)
- API routers for all endpoints
- Health check endpoint
- OpenAPI documentation
"""
from contextlib import asynccontextmanager
from typing import AsyncGenerator
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.utils.request import get_real_ip
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.v1.router import api_router
from app.config import settings

logger = logging.getLogger(__name__)


# =============================================================================
# Security Middleware
# =============================================================================

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""
    
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"
        
        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        
        # Enable XSS filter
        response.headers["X-XSS-Protection"] = "1; mode=block"
        
        # Referrer policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # Permissions policy (disable sensitive features)
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(self), camera=()"
        
        # Content Security Policy (relaxed for API)
        if not request.url.path.startswith("/docs") and not request.url.path.startswith("/redoc"):
            response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        
        # HSTS (only in production with HTTPS)
        if settings.production and settings.require_https:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        return response


class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    """Redirect HTTP to HTTPS in production."""
    
    async def dispatch(self, request: Request, call_next):
        if settings.production and settings.require_https:
            # Check if request is HTTP (not HTTPS)
            forwarded_proto = request.headers.get("X-Forwarded-Proto", "")
            if request.url.scheme == "http" and forwarded_proto != "https":
                url = request.url.replace(scheme="https")
                return RedirectResponse(url, status_code=301)
        
        return await call_next(request)

# Rate limiter configuration
limiter = Limiter(key_func=get_real_ip, default_limits=["100/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """
    Application lifespan handler.
    
    Runs setup code before the app starts accepting requests,
    and cleanup code after the app shuts down.
    """
    # Startup
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    logger.info(f"Database: {settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}")
    logger.info(f"Vector DB: {settings.qdrant_url}")
    logger.info(f"Ollama: {settings.ollama_url}")
    
    # Start mDNS service discovery
    try:
        from app.services.discovery_service import get_discovery_service
        discovery_service = get_discovery_service(port=8000)
        await discovery_service.start()
        logger.info("mDNS service discovery started")
    except Exception as e:
        logger.warning(f"mDNS service discovery not available: {e}")
    yield
    
    # Shutdown
    logger.info(f"Shutting down {settings.app_name}")
    
    # Stop mDNS service discovery
    try:
        from app.services.discovery_service import get_discovery_service
        discovery_service = get_discovery_service()
        await discovery_service.stop()
        logger.info("mDNS service discovery stopped")
    except Exception as e:
        logger.warning(f"Error stopping mDNS service discovery: {e}")


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="""
# Aion - Personal Life Management System

A privacy-centric, AI-powered personal operating system.

## Features

- 📦 **Hierarchical Blocks** - Organize everything in nested blocks
- 🗃️ **Notion-like Databases** - Custom fields and views per block
- 🤖 **Local AI** - Semantic search and intelligent automation
- 📊 **Analytics** - Auto-generated insights and visualizations
- 🔒 **Privacy First** - All data stays on your local machine

## API Architecture

- `/api/v1/blocks` - Block management (CRUD, hierarchy)
- `/api/v1/ai` - AI interactions (chat, search, automation)
- `/api/v1/search` - Semantic and full-text search

All endpoints return JSON and accept JSON request bodies.
    """,
    openapi_url=f"{settings.api_v1_prefix}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Add security headers middleware (first, so it applies to all responses)
app.add_middleware(SecurityHeadersMiddleware)

# Add HTTPS redirect middleware (production only)
if settings.production and settings.require_https:
    app.add_middleware(HTTPSRedirectMiddleware)

# Configure CORS
# Build CORS origins list with optional tunnel domain
cors_origins = list(settings.cors_origins)
if settings.tunnel_domain:
    cors_origins.append(f"https://{settings.tunnel_domain}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Device-ID", "X-Request-ID"],
    expose_headers=["X-Request-ID", "X-Rate-Limit-Remaining"],
)

# Configure rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Include API routers
app.include_router(api_router, prefix=settings.api_v1_prefix)


# ============================================================================
# Neural Graph Endpoint (Direct - bypasses router)
# ============================================================================

@app.get("/api/v1/ai/graph", tags=["ai"])
async def get_neural_graph_direct(limit: int = 50):
    """
    Get semantic graph data for visualization.
    Added directly to main.py to bypass potential router caching issues.
    """
    from app.services.vector_service import get_vector_service
    vector_service = get_vector_service()
    
    if not await vector_service.is_available():
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Vector service not available")
    
    return await vector_service.get_semantic_graph(limit=limit)


@app.get("/api/v1/ai/graph-direct", tags=["ai"])
async def get_neural_graph_direct_unique(limit: int = 50):
    """
    Unique path to avoid router conflicts.
    """
    from app.services.vector_service import get_vector_service
    vector_service = get_vector_service()
    if not await vector_service.is_available():
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Vector service not available")
    return await vector_service.get_semantic_graph(limit=limit)


# ============================================================================
# Health Check Endpoints
# ============================================================================

@app.get("/", tags=["root"])
async def root():
    """Root endpoint - API information."""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "api": settings.api_v1_prefix,
    }


@app.get("/health", tags=["health"])
async def health_check():
    """
    Health check endpoint.
    
    Returns the status of the API and its dependencies.
    """
    from app.db.session import engine
    from app.services.vector_service import get_vector_service
    from app.services.ai_service import get_ai_service
    from sqlalchemy import text
    
    # Check database
    db_status = "unhealthy"
    db_error = None
    try:
        if engine:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            db_status = "healthy"
    except Exception as e:
        db_error = str(e)
    
    # Check Qdrant
    qdrant_status = "unhealthy"
    qdrant_error = None
    try:
        vector_service = get_vector_service()
        if await vector_service.is_available():
            qdrant_status = "healthy"
        else:
            qdrant_error = "Not available"
    except Exception as e:
        qdrant_error = str(e)
    
    # Check Ollama
    ollama_status = "unhealthy"
    ollama_error = None
    ollama_models = []
    try:
        ai_service = get_ai_service()
        if await ai_service.is_available():
            ollama_status = "healthy"
            ollama_models = await ai_service.list_models()
        else:
            ollama_error = "Not available"
    except Exception as e:
        ollama_error = str(e)
    
    # Determine overall status
    all_healthy = (db_status == "healthy" and qdrant_status == "healthy" and ollama_status == "healthy")
    overall_status = "healthy" if all_healthy else "degraded"
    
    return {
        "status": overall_status,
        "version": settings.app_version,
        "components": {
            "api": "healthy",
            "database": {
                "status": db_status,
                "error": db_error,
            },
            "vector_db": {
                "status": qdrant_status,
                "error": qdrant_error,
            },
            "ollama": {
                "status": ollama_status,
                "error": ollama_error,
                "models": [m.get("name", m) if isinstance(m, dict) else m for m in ollama_models[:5]],
            },
        },
    }


@app.get("/health/ready", tags=["health"])
async def readiness_check():
    """
    Readiness check - indicates if the service is ready to accept requests.
    """
    from app.db.session import engine
    from app.services.vector_service import get_vector_service
    from app.services.ai_service import get_ai_service
    from sqlalchemy import text
    
    ready = True
    checks = {}
    
    # Check database
    try:
        if engine:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            checks["database"] = True
        else:
            checks["database"] = False
            ready = False
    except Exception:
        checks["database"] = False
        ready = False
    
    # Check Qdrant
    try:
        vector_service = get_vector_service()
        checks["vector_db"] = await vector_service.is_available()
        if not checks["vector_db"]:
            ready = False
    except Exception:
        checks["vector_db"] = False
        ready = False
    
    # Check Ollama
    try:
        ai_service = get_ai_service()
        checks["ollama"] = await ai_service.is_available()
        if not checks["ollama"]:
            ready = False
    except Exception:
        checks["ollama"] = False
        ready = False
    
    return {"ready": ready, "checks": checks}


@app.get("/health/live", tags=["health"])
async def liveness_check():
    """
    Liveness check - indicates if the service is running.
    """
    return {"alive": True}
