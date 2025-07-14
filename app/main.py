"""Main FastAPI application for ZapAI."""
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
import uvicorn
from loguru import logger
import time
import sys

from app.config import get_settings, settings
from app.database import init_db
from app.api.v1.router import api_router
from app.services.mcp_manager import MCPManager
from app.services.cache_service import CacheService
from app.services.rate_limiter import RateLimiter
from app.utils.logging import setup_logging

# Global service instances
mcp_manager = MCPManager()
cache_service = CacheService()
rate_limiter = RateLimiter()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("🚀 Starting ZapAI application...")
    
    try:
        # Initialize database
        await init_db()
        logger.info("✅ Database initialized")
        
        # Initialize services
        await mcp_manager.initialize()
        await cache_service.initialize()
        await rate_limiter.initialize()
        
        logger.info("✅ All services initialized successfully")
        
        yield
        
    except Exception as e:
        logger.error(f"❌ Startup failed: {e}")
        raise
    
    finally:
        # Shutdown
        logger.info("🛑 Shutting down ZapAI application...")
        
        # Cleanup services
        await mcp_manager.cleanup()
        await cache_service.cleanup()
        await rate_limiter.cleanup()
        
        logger.info("✅ Application shutdown complete")


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description="AI-Powered Search Engine with Multi-Engine Aggregation",
    docs_url=f"/api/{settings.api_version}/docs",
    redoc_url=f"/api/{settings.api_version}/redoc",
    openapi_url=f"/api/{settings.api_version}/openapi.json",
    lifespan=lifespan,
)

# Setup logging
setup_logging()

# Add middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.debug else ["https://localhost", "http://localhost"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"] if settings.debug else ["localhost", "127.0.0.1"]
)


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Add processing time to response headers."""
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Rate limiting middleware."""
    # Skip rate limiting for health check and docs
    if request.url.path in ["/health", "/api/v1/docs", "/api/v1/redoc"]:
        return await call_next(request)
    
    # Get client IP
    client_ip = getattr(request.client, 'host', '127.0.0.1') if request.client else '127.0.0.1'
    
    # Check rate limit (disabled for now)
    # rate_limiter = request.app.state.rate_limiter
    # if not await rate_limiter.check_rate_limit(client_ip):
    #     return JSONResponse(
    #         status_code=429,
    #         content={
    #             "error": "Rate limit exceeded",
    #             "message": "Too many requests. Please try again later."
    #         }
    #     )
    
    return await call_next(request)


# Include API routes
app.include_router(api_router, prefix=f"/api/{settings.api_version}")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Welcome to ZapAI - AI-Powered Search Engine",
        "version": settings.version,
        "docs": f"/api/{settings.api_version}/docs",
        "status": "operational"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    health_status = {
        "status": "healthy",
        "version": settings.version,
        "environment": settings.environment,
        "services": {
            "mcp_manager": "connected" if mcp_manager.servers_status else "disconnected",
            "cache_service": "connected" if cache_service.redis else "disconnected",
            "rate_limiter": "connected" if rate_limiter.redis else "disconnected"
        }
    }
    
    # Check service health
    if cache_service.redis:
        try:
            cache_stats = await cache_service.get_cache_stats()
            health_status["services"]["cache_service"] = cache_stats.get("status", "unknown")
        except Exception:
            health_status["services"]["cache_service"] = "error"
    
    # Overall status
    all_healthy = all(
        status != "disconnected" and status != "error" 
        for status in health_status["services"].values()
    )
    
    if not all_healthy:
        health_status["status"] = "degraded"
    
    return health_status


@app.get("/api/{settings.api_version}/status")
async def service_status():
    """Detailed service status."""
    return {
        "mcp_servers": mcp_manager.get_server_status(),
        "cache": await cache_service.get_cache_stats() if cache_service.redis else {"status": "offline"},
        "rate_limiter": {"status": "online" if rate_limiter.redis else "offline"}
    }


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Custom HTTP exception handler."""
    logger.error(f"HTTP {exc.status_code}: {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code,
            "path": request.url.path
        }
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": "An unexpected error occurred",
            "path": request.url.path
        }
    )


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
