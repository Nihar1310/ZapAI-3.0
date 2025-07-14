"""Search-related database models."""
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, Float, Boolean, ForeignKey, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSONB
import uuid
from sqlalchemy.sql import func
import enum

from app.database import Base


class SearchStatus(enum.Enum):
    preview = "preview"
    paid = "paid"
    enriching = "enriching"
    ready = "ready"
    failed = "failed"

class SearchQuery(Base):
    """Search query model."""
    __tablename__ = "search_queries"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    query_text = Column(String(500), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    filters = Column(JSON, nullable=True)  # Location, contact types, etc.
    max_pages = Column(Integer, default=4)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    status = Column(Enum(SearchStatus), nullable=False, default=SearchStatus.preview)
    firecrawl_raw = Column(JSONB)
    
    # Processing status
    processing_time = Column(Float, nullable=True)  # seconds
    total_results = Column(Integer, default=0)
    pages_processed = Column(Integer, default=0)
    
    # Cost tracking
    total_cost = Column(Float, default=0.0)
    cost_breakdown = Column(JSON, nullable=True)
    
    # Relationships
    results = relationship("SearchResult", back_populates="query", cascade="all, delete-orphan")
    user = relationship("User", back_populates="search_queries")
    
    def __repr__(self):
        return f"<SearchQuery(id={self.id}, query='{self.query_text[:50]}...')>"


class SearchResult(Base):
    """Individual search result model."""
    __tablename__ = "search_results"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    query_id = Column(UUID(as_uuid=True), ForeignKey("search_queries.id"), nullable=False)
    
    # Basic result info
    url = Column(Text, nullable=False, index=True)
    title = Column(Text, nullable=True)
    snippet = Column(Text, nullable=True)
    
    # Source information
    source_engines = Column(ARRAY(String), nullable=True)  # ['google', 'bing']
    rank_google = Column(Integer, nullable=True)
    rank_bing = Column(Integer, nullable=True)
    rank_duckduckgo = Column(Integer, nullable=True)
    
    # Scraped content
    scraped_content = Column(Text, nullable=True)
    scraped_at = Column(DateTime, nullable=True)
    scraping_success = Column(Boolean, default=False)
    scraping_error = Column(Text, nullable=True)
    
    # AI processing
    ai_processed = Column(Boolean, default=False)
    ai_processed_at = Column(DateTime, nullable=True)
    ai_processing_cost = Column(Float, default=0.0)
    
    # Quality metrics
    confidence_score = Column(Float, default=0.0)  # 0.0 to 1.0
    relevance_score = Column(Float, default=0.0)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    query = relationship("SearchQuery", back_populates="results")
    contact_data = relationship("ContactData", back_populates="result", cascade="all, delete-orphan")
    location_data = relationship("LocationData", back_populates="result", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<SearchResult(id={self.id}, url='{self.url[:50]}...')>"


class ContactData(Base):
    """Extracted contact information."""
    __tablename__ = "contact_data"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    result_id = Column(UUID(as_uuid=True), ForeignKey("search_results.id"), nullable=False)
    
    # Contact information
    emails = Column(ARRAY(String), nullable=True)
    phone_numbers = Column(ARRAY(String), nullable=True)
    names = Column(ARRAY(String), nullable=True)
    
    # Additional extracted data
    job_titles = Column(ARRAY(String), nullable=True)
    companies = Column(ARRAY(String), nullable=True)
    social_profiles = Column(JSON, nullable=True)  # {platform: url}
    
    # Extraction metadata
    extraction_method = Column(String(50), nullable=True)  # 'regex', 'ai', 'hybrid'
    extraction_confidence = Column(Float, default=0.0)
    extracted_at = Column(DateTime, default=datetime.utcnow)
    
    # Validation status
    emails_validated = Column(Boolean, default=False)
    phones_validated = Column(Boolean, default=False)
    
    # Relationships
    result = relationship("SearchResult", back_populates="contact_data")
    
    def __repr__(self):
        return f"<ContactData(id={self.id}, result_id={self.result_id})>"


class LocationData(Base):
    """Geographic location information."""
    __tablename__ = "location_data"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    result_id = Column(UUID(as_uuid=True), ForeignKey("search_results.id"), nullable=False)
    
    # Location details
    country = Column(String(100), nullable=True, index=True)
    state = Column(String(100), nullable=True, index=True)
    city = Column(String(100), nullable=True, index=True)
    region = Column(String(100), nullable=True)
    postal_code = Column(String(20), nullable=True)
    
    # Coordinates
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    
    # Address information
    full_address = Column(Text, nullable=True)
    street_address = Column(String(200), nullable=True)
    
    # Metadata
    extraction_confidence = Column(Float, default=0.0)
    extracted_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    result = relationship("SearchResult", back_populates="location_data")
    
    def __repr__(self):
        return f"<LocationData(id={self.id}, city='{self.city}', country='{self.country}')>"


class SearchCache(Base):
    """Cache for search results."""
    __tablename__ = "search_cache"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cache_key = Column(String(255), nullable=False, unique=True, index=True)
    query_hash = Column(String(64), nullable=False, index=True)
    
    # Cached data
    cached_data = Column(JSON, nullable=False)
    
    # Cache metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False, index=True)
    hit_count = Column(Integer, default=0)
    last_accessed = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<SearchCache(key='{self.cache_key}', expires={self.expires_at})>"
