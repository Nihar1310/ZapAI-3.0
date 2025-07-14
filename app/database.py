"""Database configuration and connection management."""
import asyncio
from typing import AsyncGenerator
from sqlalchemy import create_engine, MetaData, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.ext.declarative import declarative_base
from loguru import logger

from .config import settings

# SQLAlchemy setup
def get_database_url():
    """Get the database URL from settings."""
    url = settings.DATABASE_URL
    if url and url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url

# Database engine
engine = create_async_engine(
    get_database_url(),
    echo=False,
    pool_pre_ping=True,
)

Base = declarative_base()
metadata = MetaData()

# Redis setup
redis_client = None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get database session."""
    async with AsyncSession(engine) as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            raise e
        finally:
            await session.close()


async def get_redis():
    """Get Redis client."""
    global redis_client
    if redis_client is None:
        try:
            import redis.asyncio as redis
            redis_client = redis.from_url(settings.redis_url)
            # Test connection
            await redis_client.ping()
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}. Running without Redis cache.")
            redis_client = None
    return redis_client


async def init_db():
    """Initialize database tables."""
    try:
        logger.info("Initializing database...")
        # For demo purposes, just log success
        logger.info("✅ Database initialized (demo mode)")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        logger.warning("Continuing without database initialization...")


async def close_db():
    """Close database connections."""
    try:
        await engine.dispose()
        if redis_client:
            await redis_client.close()
        logger.info("✅ Database connections closed")
    except Exception as e:
        logger.warning(f"Error closing database: {e}")


# Database utilities
class DatabaseManager:
    """Database management utilities."""
    
    @staticmethod
    async def health_check() -> dict:
        """Check database health."""
        try:
            async with AsyncSession(engine) as session:
                await session.execute(text("SELECT 1"))
                db_status = "healthy"
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            db_status = "unhealthy"
        
        try:
            redis_conn = await get_redis()
            if redis_conn:
                await redis_conn.ping()
                redis_status = "healthy"
            else:
                redis_status = "offline"
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            redis_status = "unhealthy"
        
        return {
            "database": db_status,
            "redis": redis_status,
            "overall": "healthy" if db_status == "healthy" else "degraded"
        }
    
    @staticmethod
    async def get_stats() -> dict:
        """Get database statistics."""
        return {
            "status": "connected",
            "type": "demo",
            "message": "Database stats not implemented in demo mode"
        }
