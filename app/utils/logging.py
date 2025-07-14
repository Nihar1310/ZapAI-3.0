"""Logging configuration."""
import sys
from loguru import logger

from app.config import settings


def setup_logging():
    """Setup application logging."""
    # Remove default handler
    logger.remove()
    
    # Add console handler
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    )
    
    # Add file handler if configured
    if settings.log_file:
        logger.add(
            settings.log_file,
            level=settings.log_level,
            rotation="1 day",
            retention="30 days",
            compression="zip"
        ) 