"""User and authentication models."""
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Float, JSON, Text
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid

from app.database import Base


class User(Base):
    """User model."""
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, index=True, nullable=False)
    username = Column(String(100), unique=True, index=True, nullable=True)
    
    # Authentication
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    
    # Subscription and limits
    subscription_tier = Column(String(50), default="free")  # free, pro, enterprise
    api_key = Column(String(255), unique=True, index=True, nullable=True)
    
    # Rate limiting
    rate_limit_per_minute = Column(Integer, default=10)
    rate_limit_per_hour = Column(Integer, default=100)
    rate_limit_per_day = Column(Integer, default=1000)
    
    # Usage tracking
    total_queries = Column(Integer, default=0)
    total_cost = Column(Float, default=0.0)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
    
    # Relationships
    search_queries = relationship("SearchQuery", back_populates="user")
    api_usage = relationship("ApiUsage", back_populates="user")
    
    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}')>"


class ApiUsage(Base):
    """API usage tracking."""
    __tablename__ = "api_usage"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=True)  # Can be null for anonymous usage
    
    # Service usage
    service_name = Column(String(100), nullable=False, index=True)  # google, bing, openai, etc.
    endpoint = Column(String(200), nullable=True)
    
    # Usage metrics
    requests_count = Column(Integer, default=1)
    tokens_used = Column(Integer, default=0)
    cost = Column(Float, default=0.0)
    
    # Request details
    request_data = Column(JSON, nullable=True)
    response_status = Column(String(50), nullable=True)
    processing_time = Column(Float, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    date = Column(DateTime, default=datetime.utcnow, index=True)  # For daily aggregation
    
    # Relationships
    user = relationship("User", back_populates="api_usage")
    
    def __repr__(self):
        return f"<ApiUsage(service='{self.service_name}', cost={self.cost})>"


class UserSession(Base):
    """User session management."""
    __tablename__ = "user_sessions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    session_token = Column(String(255), unique=True, index=True, nullable=False)
    
    # Session details
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    
    # Session status
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    last_activity = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<UserSession(user_id={self.user_id}, active={self.is_active})>"
