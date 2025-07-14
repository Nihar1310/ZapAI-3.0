"""Authentication utilities."""
from typing import Optional
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.database import get_db
from app.models.user import User

security = HTTPBearer(auto_error=False)


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    """Get current user from token (optional - returns None if no token)."""
    if not credentials:
        return None
    
    try:
        # In a real app, you would decode JWT token here
        # For now, we'll just return a mock user for development
        return None
        
    except Exception as e:
        logger.error(f"Auth error: {e}")
        return None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """Get current user from token (required)."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    
    try:
        # In a real app, you would decode JWT token here
        # For now, we'll raise an error for development
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication not implemented"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Auth error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication"
        )


async def get_current_user_id(
    user: User = Depends(get_current_user)
) -> int:
    """Get current user ID from authenticated user."""
    return user.id 