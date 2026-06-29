"""
PR Chatbot — Main Application Entry Point

Starts the FastAPI server with all routes and initializes
the database and schema registry on startup.
"""
import logging
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.models.database import init_db, engine
from app.api.routes import router
from app.auth.routes import router as auth_router
from app.services.schema_registry import schema_registry
from app.agents.reviewer_agent import reviewer_agent


# ── Logging Setup ─────────────────────────────────────────────

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger("pr_chatbot")


# ── Request Logging Middleware ────────────────────────────────

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log method, path, status code, and duration for every request."""

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "%s %s → %d (%.0fms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response


# ── App Lifecycle ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup
    logger.info("=" * 60)
    logger.info("PR Chatbot starting up...")
    logger.info(f"LLM Provider: {settings.llm_provider}")
    logger.info(f"Database: {settings.database_url}")
    logger.info(f"CORS Origins: {settings.cors_origins}")
    logger.info("=" * 60)

    # Initialize database
    await init_db()
    logger.info("Database initialized.")

    # Load schema registry
    schema_registry.load()
    supported = schema_registry.get_supported_types()
    primary = schema_registry.get_primary_types()
    logger.info(f"Schema registry loaded. Supported types: {supported}")
    logger.info(f"Primary types (with templates): {primary}")

    # Load reviewer agent validation rules
    reviewer_agent.load()
    review_types = reviewer_agent.get_supported_types()
    logger.info(f"Reviewer agent loaded. Review rules for: {review_types}")

    yield

    # Shutdown
    logger.info("PR Chatbot shutting down.")


# ── FastAPI App ───────────────────────────────────────────────

app = FastAPI(
    title="PR Chatbot",
    description=(
        "Chat-based infrastructure YAML configuration generator. "
        "Supports S3, Glue DB, and IAM resource types."
    ),
    version="0.2.0",
    lifespan=lifespan,
)


# ── Global Exception Handler ─────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch unhandled exceptions and return a clean 500 response."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# ── Middleware ────────────────────────────────────────────────

# Request logging (added first so it wraps everything)
app.add_middleware(RequestLoggingMiddleware)

# CORS — uses configured origins (default: localhost dev ports)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Mount routes
app.include_router(router, prefix="/api")
app.include_router(auth_router)

# Serve React build output (../frontend/dist)
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"

if FRONTEND_DIR.exists():
    # Serve static assets (JS, CSS, images) from dist/assets
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR / "assets")), name="assets")


# ── Health Check ──────────────────────────────────────────────

@app.get("/health")
async def health_check():
    """Health check with DB connectivity test."""
    db_ok = False
    try:
        from sqlalchemy import text
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        logger.warning("Health check: DB connectivity failed")

    return JSONResponse(content={
        "status": "healthy" if db_ok else "degraded",
        "version": app.version,
        "database": "connected" if db_ok else "unavailable",
    })


# ── SPA Fallback ─────────────────────────────────────────────

@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    """Serve the React SPA. All non-API routes return index.html."""
    file_path = FRONTEND_DIR / full_path
    if file_path.is_file():
        return FileResponse(str(file_path))
    index_file = FRONTEND_DIR / "index.html"
    if index_file.is_file():
        return FileResponse(str(index_file))
    return JSONResponse(
        status_code=404,
        content={"detail": "Frontend build not found"},
    )


# ── Main ──────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
