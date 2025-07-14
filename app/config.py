"""Configuration management for ZapAI."""
import os
from typing import Optional, List
from pydantic_settings import BaseSettings
from pydantic import Field, root_validator


class Settings(BaseSettings):
    """Application settings."""
    
    # Application
    app_name: str = "ZapAI"
    version: str = "1.0.0"
    debug: bool = Field(default=False)
    environment: str = Field(default="development")
    secret_key: str = Field(default="dev-secret-key-change-in-production")
    api_version: str = Field(default="v1")
    
    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./zapai.db"
    redis_url: str = Field(default="redis://localhost:6379/0")
    
    # API Keys (optional for development)
    google_api_key: Optional[str] = Field(default=None)
    google_cse_id: Optional[str] = Field(default=None)
    bing_api_key: Optional[str] = Field(default=None)
    openai_api_key: Optional[str] = Field(default=None)
    anthropic_api_key: Optional[str] = Field(default=None)
    
    # Rate Limiting
    rate_limit_per_minute: int = Field(default=60)
    rate_limit_per_hour: int = Field(default=300)
    rate_limit_per_day: int = Field(default=1000)
    
    # MCP Configuration
    mcp_timeout: int = Field(default=30)
    mcp_max_retries: int = Field(default=3)
    
    # AI Processing
    max_tokens_per_request: int = Field(default=4000)
    ai_processing_timeout: int = Field(default=60)
    enable_ai_fallback: bool = Field(default=True)
    ai_enabled: bool = Field(default=True)
    ai_model_name: str = Field(default="gpt-4")
    ai_max_tokens: int = Field(default=1000)
    
    # Firecrawl Configuration
    firecrawl_api_key: Optional[str] = Field(default=None)
    use_firecrawl: bool = Field(default=True)
    firecrawl_timeout: int = Field(default=30)
    
    # Stripe Configuration
    stripe_api_key: Optional[str] = Field(default=None)
    stripe_webhook_secret: Optional[str] = Field(default=None)
    stripe_price_per_search: float = Field(default=2.99)  # $2.99 per search enrichment
    stripe_currency: str = Field(default="usd")
    stripe_success_url: str = Field(default="http://localhost:8000/payment/success")
    stripe_cancel_url: str = Field(default="http://localhost:8000/payment/cancel")
    firecrawl_max_retries: int = Field(default=3)
    firecrawl_rate_limit_per_minute: int = Field(default=50)
    
    # Celery/Background Workers Configuration
    celery_broker_url: str = Field(default="redis://localhost:6379/0")
    celery_result_backend: str = Field(default="redis://localhost:6379/0")
    celery_task_serializer: str = Field(default="json")
    celery_result_serializer: str = Field(default="json")
    celery_accept_content: List[str] = Field(default=["json"])
    celery_timezone: str = Field(default="UTC")
    
    # Apollo.io Configuration
    apollo_api_key: Optional[str] = Field(default=None)
    apollo_base_url: str = Field(default="https://api.apollo.io/v1")
    apollo_max_contacts_per_request: int = Field(default=10)
    apollo_timeout: int = Field(default=30)
    apollo_max_retries: int = Field(default=3)
    apollo_rate_limit_per_minute: int = Field(default=100)
    
    # Scraping
    max_pages_per_search: int = Field(default=4)
    scraping_timeout: int = Field(default=30)
    max_concurrent_scrapes: int = Field(default=5)
    
    # Caching
    cache_ttl_search_results: int = Field(default=3600)
    cache_ttl_scraped_content: int = Field(default=604800)
    cache_ttl_contact_data: int = Field(default=2592000)
    cache_ttl_default: int = Field(default=1800)
    redis_max_connections: int = Field(default=20)
    
    # Ngrok
    ngrok_auth_token: Optional[str] = Field(default=None)
    ngrok_domain: Optional[str] = Field(default=None)
    
    # Logging
    log_level: str = Field(default="INFO")
    log_file: str = Field(default="logs/zapai.log")
    
    model_config = {
        "env_file": ".env",
        "case_sensitive": False
    }


# API Cost Configuration
class APICosts:
    """API cost configuration."""
    google_search_per_request: float = 0.005
    bing_search_per_request: float = 0.007
    openai_gpt4_per_1k_tokens: float = 0.03
    openai_gpt35_per_1k_tokens: float = 0.002
    playwright_per_page: float = 0.001
    redis_per_operation: float = 0.0001
    apollo_per_contact: float = 0.10  # $0.10 per contact enrichment
    firecrawl_per_scrape: float = 0.02  # $0.02 per page scrape

# Global settings instance with API costs
class SettingsWithCosts(Settings):
    """Settings with API costs."""
    api_costs: APICosts = APICosts()

settings = SettingsWithCosts()

def get_settings() -> SettingsWithCosts:
    """Get application settings."""
    return settings

API_COSTS = {
    "google_search": {
        "free_tier": 100,  # queries per day
        "cost_per_query": 0.005,  # $5 per 1000 queries
    },
    "bing_search": {
        "free_tier": 1000,  # queries per month
        "cost_per_query": 0.007,  # $7 per 1000 queries
    },
    "openai_gpt4": {
        "cost_per_input_token": 0.00003,  # $0.03 per 1K tokens
        "cost_per_output_token": 0.00006,  # $0.06 per 1K tokens
    },
    "anthropic_claude": {
        "cost_per_input_token": 0.00025,  # $0.25 per 1K tokens
        "cost_per_output_token": 0.00125,  # $1.25 per 1K tokens
    },
    "firecrawl_scrape": {
        "cost_per_request": 0.002,  # $2 per 1000 requests
        "free_tier": 500,  # requests per month
    }
}

# MCP Server Endpoints - Essential servers only for ZapAI functionality
MCP_SERVERS = {
    "puppeteer_scraper": "npx @hisma/server-puppeteer",
}

# Search Engine Configurations
SEARCH_ENGINES = {
    "google": {
        "enabled": True,
        "max_results": 10,
        "timeout": 10,
        "retry_count": 3,
    },
    "bing": {
        "enabled": True,
        "max_results": 10,
        "timeout": 10,
        "retry_count": 3,
    },
    "duckduckgo": {
        "enabled": True,
        "max_results": 10,
        "timeout": 15,
        "retry_count": 2,
    }
}
