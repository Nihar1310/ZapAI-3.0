"""Analytics and monitoring models."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Float, JSON, Boolean
from sqlalchemy.dialects.postgresql import UUID
import uuid

from app.database import Base


class CostMetrics(Base):
    """Cost tracking metrics."""
    __tablename__ = "cost_metrics"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Cost details
    service_name = Column(String(100), nullable=False, index=True)
    cost_type = Column(String(50), nullable=False)  # per_request, per_token, per_page
    cost_amount = Column(Float, nullable=False)
    
    # Usage metrics
    requests_count = Column(Integer, default=0)
    tokens_used = Column(Integer, default=0)
    total_cost = Column(Float, default=0.0)
    
    # Context
    user_id = Column(UUID(as_uuid=True), nullable=True)
    query_id = Column(UUID(as_uuid=True), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    date = Column(DateTime, default=datetime.utcnow, index=True)
    
    def __repr__(self):
        return f"<CostMetrics(service='{self.service_name}', cost={self.total_cost})>"


class SystemMetrics(Base):
    """System performance metrics."""
    __tablename__ = "system_metrics"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Metric details
    metric_name = Column(String(100), nullable=False, index=True)
    metric_type = Column(String(50), nullable=False)  # counter, gauge, histogram
    value = Column(Float, nullable=False)
    
    # Additional data
    labels = Column(JSON, nullable=True)  # {service: 'google', status: 'success'}
    description = Column(String(500), nullable=True)
    
    # Timestamps
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    
    def __repr__(self):
        return f"<SystemMetrics(name='{self.metric_name}', value={self.value})>"


class SearchAnalytics(Base):
    """Search analytics and insights."""
    __tablename__ = "search_analytics"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Time period
    date = Column(DateTime, nullable=False, index=True)
    hour = Column(Integer, nullable=True)  # 0-23 for hourly analytics
    
    # Search metrics
    total_searches = Column(Integer, default=0)
    successful_searches = Column(Integer, default=0)
    failed_searches = Column(Integer, default=0)
    
    # Engine performance
    google_requests = Column(Integer, default=0)
    bing_requests = Column(Integer, default=0)
    duckduckgo_requests = Column(Integer, default=0)
    
    # Scraping metrics
    pages_scraped = Column(Integer, default=0)
    scraping_success_rate = Column(Float, default=0.0)
    
    # AI processing
    ai_requests = Column(Integer, default=0)
    ai_tokens_used = Column(Integer, default=0)
    ai_processing_time = Column(Float, default=0.0)
    
    # Cost metrics
    total_cost = Column(Float, default=0.0)
    cost_per_search = Column(Float, default=0.0)
    
    # Performance metrics
    avg_response_time = Column(Float, default=0.0)
    avg_results_per_search = Column(Float, default=0.0)
    
    # Contact extraction
    contacts_extracted = Column(Integer, default=0)
    emails_found = Column(Integer, default=0)
    phones_found = Column(Integer, default=0)
    
    def __repr__(self):
        return f"<SearchAnalytics(date={self.date}, searches={self.total_searches})>"


class ErrorLog(Base):
    """Error logging and monitoring."""
    __tablename__ = "error_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Error details
    error_type = Column(String(100), nullable=False, index=True)
    error_message = Column(String(1000), nullable=False)
    error_code = Column(String(50), nullable=True)
    
    # Context
    service = Column(String(100), nullable=True, index=True)  # google, bing, openai, etc.
    endpoint = Column(String(200), nullable=True)
    user_id = Column(UUID(as_uuid=True), nullable=True)
    
    # Request details
    request_data = Column(JSON, nullable=True)
    stack_trace = Column(String(5000), nullable=True)
    
    # Severity and status
    severity = Column(String(20), default="error")  # debug, info, warning, error, critical
    resolved = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    resolved_at = Column(DateTime, nullable=True)
    
    def __repr__(self):
        return f"<ErrorLog(type='{self.error_type}', service='{self.service}')>"


class PerformanceMetrics(Base):
    """Performance monitoring metrics."""
    __tablename__ = "performance_metrics"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Endpoint details
    endpoint = Column(String(200), nullable=False, index=True)
    method = Column(String(10), nullable=False)
    
    # Performance metrics
    response_time = Column(Float, nullable=False)
    status_code = Column(Integer, nullable=False)
    
    # Resource usage
    memory_usage = Column(Float, nullable=True)  # MB
    cpu_usage = Column(Float, nullable=True)  # Percentage
    
    # Request details
    request_size = Column(Integer, nullable=True)  # bytes
    response_size = Column(Integer, nullable=True)  # bytes
    
    # User context
    user_id = Column(UUID(as_uuid=True), nullable=True)
    ip_address = Column(String(45), nullable=True)
    
    # Timestamps
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    
    def __repr__(self):
        return f"<PerformanceMetrics(endpoint='{self.endpoint}', time={self.response_time})>"
