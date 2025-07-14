"""Firecrawl API client with reliability features."""
import asyncio
import logging
import time
from enum import Enum
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import httpx
from firecrawl import FirecrawlApp

from app.config import get_settings


logger = logging.getLogger(__name__)


class CircuitBreakerState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration."""
    failure_threshold: int = 5
    recovery_timeout: int = 60  # seconds
    success_threshold: int = 2  # for half-open state


@dataclass
class RateLimiter:
    """Simple rate limiter for API calls."""
    max_calls: int
    window_seconds: int = 60
    calls: List[float] = field(default_factory=list)
    
    def can_proceed(self) -> bool:
        """Check if we can make another API call."""
        now = time.time()
        # Remove calls outside the window
        self.calls = [call_time for call_time in self.calls 
                     if now - call_time < self.window_seconds]
        
        if len(self.calls) < self.max_calls:
            self.calls.append(now)
            return True
        return False
    
    def wait_time(self) -> float:
        """Get time to wait before next call is allowed."""
        if not self.calls:
            return 0.0
        
        oldest_call = min(self.calls)
        return max(0.0, self.window_seconds - (time.time() - oldest_call))


class CircuitBreaker:
    """Circuit breaker implementation for resilient API calls."""
    
    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
    
    def can_proceed(self) -> bool:
        """Check if the circuit breaker allows the call."""
        if self.state == CircuitBreakerState.CLOSED:
            return True
        
        if self.state == CircuitBreakerState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitBreakerState.HALF_OPEN
                self.success_count = 0
                return True
            return False
        
        # Half-open state
        return True
    
    def record_success(self):
        """Record a successful call."""
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                self.state = CircuitBreakerState.CLOSED
                self.failure_count = 0
        elif self.state == CircuitBreakerState.CLOSED:
            self.failure_count = 0
    
    def record_failure(self):
        """Record a failed call."""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if (self.state == CircuitBreakerState.CLOSED and 
            self.failure_count >= self.config.failure_threshold):
            self.state = CircuitBreakerState.OPEN
        elif self.state == CircuitBreakerState.HALF_OPEN:
            self.state = CircuitBreakerState.OPEN
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if not self.last_failure_time:
            return True
        
        elapsed = (datetime.now() - self.last_failure_time).total_seconds()
        return elapsed >= self.config.recovery_timeout


@dataclass
class FirecrawlResponse:
    """Standardized response from Firecrawl operations."""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    cost: float = 0.0
    response_time: float = 0.0
    source: str = "firecrawl"


class FirecrawlClient:
    """Firecrawl API client with reliability features."""
    
    def __init__(self):
        self.settings = get_settings()
        self.client: Optional[FirecrawlApp] = None
        self.circuit_breaker = CircuitBreaker(CircuitBreakerConfig())
        self.rate_limiter = RateLimiter(
            max_calls=self.settings.firecrawl_rate_limit_per_minute
        )
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize the Firecrawl client if API key is available."""
        if self.settings.firecrawl_api_key and self.settings.use_firecrawl:
            try:
                self.client = FirecrawlApp(api_key=self.settings.firecrawl_api_key)
                logger.info("Firecrawl client initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Firecrawl client: {e}")
                self.client = None
        else:
            logger.warning("Firecrawl client not initialized - missing API key or disabled")
    
    @property
    def is_available(self) -> bool:
        """Check if Firecrawl is available for use."""
        return (
            self.settings.use_firecrawl and 
            self.client is not None and 
            self.circuit_breaker.can_proceed()
        )
    
    async def scrape_url(
        self, 
        url: str, 
        options: Optional[Dict[str, Any]] = None
    ) -> FirecrawlResponse:
        """
        Scrape a single URL with reliability features.
        
        Args:
            url: URL to scrape
            options: Firecrawl scraping options
            
        Returns:
            FirecrawlResponse with scraped data or error
        """
        start_time = time.time()
        
        if not self.is_available:
            return FirecrawlResponse(
                success=False,
                error="Firecrawl not available (disabled, no API key, or circuit breaker open)",
                response_time=time.time() - start_time
            )
        
        # Rate limiting
        if not self.rate_limiter.can_proceed():
            wait_time = self.rate_limiter.wait_time()
            return FirecrawlResponse(
                success=False,
                error=f"Rate limit exceeded. Try again in {wait_time:.1f} seconds",
                response_time=time.time() - start_time
            )
        
        # Default options for ZapAI use case
        default_options = {
            "formats": ["markdown", "html"],
            "includeTags": ["a", "p", "h1", "h2", "h3", "h4", "h5", "h6", "span", "div"],
            "onlyMainContent": True,
            "timeout": self.settings.firecrawl_timeout * 1000,  # Convert to milliseconds
        }
        
        if options:
            default_options.update(options)
        
        # Retry logic
        last_error = None
        for attempt in range(self.settings.firecrawl_max_retries):
            try:
                logger.info(f"Scraping URL: {url} (attempt {attempt + 1})")
                
                # Make the API call
                if not self.client:
                    raise Exception("Firecrawl client not initialized")
                    
                result = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.client.scrape_url(url, params=default_options)
                )
                
                response_time = time.time() - start_time
                
                if result.get("success", False):
                    self.circuit_breaker.record_success()
                    cost = self._calculate_cost(result)
                    
                    logger.info(f"Successfully scraped {url} in {response_time:.2f}s")
                    return FirecrawlResponse(
                        success=True,
                        data=result,
                        cost=cost,
                        response_time=response_time
                    )
                else:
                    error_msg = result.get("error", "Unknown Firecrawl error")
                    logger.warning(f"Firecrawl returned error for {url}: {error_msg}")
                    last_error = error_msg
                    
            except asyncio.TimeoutError:
                last_error = f"Timeout after {self.settings.firecrawl_timeout}s"
                logger.warning(f"Timeout scraping {url}: {last_error}")
                
            except Exception as e:
                last_error = str(e)
                logger.error(f"Error scraping {url}: {last_error}")
            
            # Wait before retry (exponential backoff)
            if attempt < self.settings.firecrawl_max_retries - 1:
                wait_time = 2 ** attempt
                logger.info(f"Retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
        
        # All retries failed
        self.circuit_breaker.record_failure()
        response_time = time.time() - start_time
        
        return FirecrawlResponse(
            success=False,
            error=f"Failed after {self.settings.firecrawl_max_retries} attempts: {last_error}",
            response_time=response_time
        )
    
    async def crawl_website(
        self, 
        url: str, 
        options: Optional[Dict[str, Any]] = None
    ) -> FirecrawlResponse:
        """
        Crawl a website (multiple pages) with reliability features.
        
        Args:
            url: Base URL to crawl
            options: Firecrawl crawling options
            
        Returns:
            FirecrawlResponse with crawled data or error
        """
        start_time = time.time()
        
        if not self.is_available:
            return FirecrawlResponse(
                success=False,
                error="Firecrawl not available (disabled, no API key, or circuit breaker open)",
                response_time=time.time() - start_time
            )
        
        # Rate limiting (crawl uses more quota)
        if not self.rate_limiter.can_proceed():
            wait_time = self.rate_limiter.wait_time()
            return FirecrawlResponse(
                success=False,
                error=f"Rate limit exceeded. Try again in {wait_time:.1f} seconds",
                response_time=time.time() - start_time
            )
        
        # Default options for crawling
        default_options = {
            "crawlerOptions": {
                "limit": 10,  # Reasonable limit for previews
                "maxDepth": 2,
            },
            "pageOptions": {
                "formats": ["markdown"],
                "onlyMainContent": True,
            }
        }
        
        if options:
            default_options.update(options)
        
        try:
            logger.info(f"Starting crawl of: {url}")
            
            # Make the API call
            if not self.client:
                raise Exception("Firecrawl client not initialized")
                
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.client.crawl_url(url, params=default_options)
            )
            
            response_time = time.time() - start_time
            
            if result.get("success", False):
                self.circuit_breaker.record_success()
                cost = self._calculate_cost(result, is_crawl=True)
                
                logger.info(f"Successfully crawled {url} in {response_time:.2f}s")
                return FirecrawlResponse(
                    success=True,
                    data=result,
                    cost=cost,
                    response_time=response_time
                )
            else:
                error_msg = result.get("error", "Unknown Firecrawl crawl error")
                logger.error(f"Firecrawl crawl failed for {url}: {error_msg}")
                self.circuit_breaker.record_failure()
                
                return FirecrawlResponse(
                    success=False,
                    error=error_msg,
                    response_time=response_time
                )
                
        except Exception as e:
            self.circuit_breaker.record_failure()
            error_msg = str(e)
            response_time = time.time() - start_time
            
            logger.error(f"Exception during crawl of {url}: {error_msg}")
            return FirecrawlResponse(
                success=False,
                error=f"Crawl failed: {error_msg}",
                response_time=response_time
            )
    
    def _calculate_cost(self, result: Dict[str, Any], is_crawl: bool = False) -> float:
        """Calculate the cost of a Firecrawl operation."""
        from app.config import API_COSTS
        base_cost = API_COSTS.get("firecrawl_scrape", {}).get("cost_per_request", 0.002)
        
        if is_crawl:
            # Crawl operations typically process multiple pages
            pages_processed = len(result.get("data", []))
            return base_cost * max(1, pages_processed)
        else:
            # Single page scrape
            return base_cost
    
    async def health_check(self) -> bool:
        """Perform a health check on the Firecrawl service."""
        if not self.client:
            return False
        
        try:
            # Try a simple scrape of a lightweight page
            test_url = "https://httpbin.org/status/200"
            result = await self.scrape_url(test_url, {"timeout": 5000})
            return result.success
        except Exception:
            return False
    
    def get_status(self) -> Dict[str, Any]:
        """Get current status of the Firecrawl client."""
        return {
            "available": self.is_available,
            "circuit_breaker_state": self.circuit_breaker.state.value,
            "failure_count": self.circuit_breaker.failure_count,
            "rate_limit_calls": len(self.rate_limiter.calls),
            "rate_limit_max": self.rate_limiter.max_calls,
            "api_key_configured": bool(self.settings.firecrawl_api_key),
            "feature_enabled": self.settings.use_firecrawl,
        }


# Global client instance
_firecrawl_client: Optional[FirecrawlClient] = None


def get_firecrawl_client() -> FirecrawlClient:
    """Get or create the global Firecrawl client instance."""
    global _firecrawl_client
    if _firecrawl_client is None:
        _firecrawl_client = FirecrawlClient()
    return _firecrawl_client


async def scrape_with_fallback(url: str, fallback_scraper=None) -> FirecrawlResponse:
    """
    Scrape URL with Firecrawl and fallback to alternative scraper if needed.
    
    Args:
        url: URL to scrape
        fallback_scraper: Alternative scraping function to use if Firecrawl fails
        
    Returns:
        FirecrawlResponse with data from Firecrawl or fallback
    """
    client = get_firecrawl_client()
    
    # Try Firecrawl first
    result = await client.scrape_url(url)
    
    if result.success:
        return result
    
    # If Firecrawl fails and we have a fallback
    if fallback_scraper:
        logger.info(f"Firecrawl failed for {url}, trying fallback scraper")
        try:
            fallback_data = await fallback_scraper(url)
            return FirecrawlResponse(
                success=True,
                data={"content": fallback_data, "metadata": {"url": url}},
                source="fallback",
                cost=0.0
            )
        except Exception as e:
            logger.error(f"Fallback scraper also failed: {e}")
    
    return result
