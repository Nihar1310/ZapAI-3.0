"""Rate limiting service for API usage control."""
import asyncio
from typing import Dict, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
import redis.asyncio as aioredis
from loguru import logger

from app.config import settings


@dataclass
class RateLimit:
    """Rate limit configuration."""
    requests: int
    window_seconds: int
    burst_requests: int = None


class RateLimiter:
    """Redis-based rate limiter for API requests."""
    
    def __init__(self):
        self.redis: Optional[aioredis.Redis] = None
        self.key_prefix = "ratelimit:"
        
        # Default rate limits by user tier
        self.rate_limits = {
            'free': RateLimit(requests=100, window_seconds=3600, burst_requests=10),    # 100/hour, 10 burst
            'basic': RateLimit(requests=1000, window_seconds=3600, burst_requests=50),  # 1000/hour, 50 burst
            'premium': RateLimit(requests=10000, window_seconds=3600, burst_requests=200), # 10k/hour, 200 burst
            'enterprise': RateLimit(requests=100000, window_seconds=3600, burst_requests=1000) # 100k/hour, 1k burst
        }
        
        # Service-specific limits
        self.service_limits = {
            'search': RateLimit(requests=50, window_seconds=60),  # 50 searches per minute
            'scraping': RateLimit(requests=200, window_seconds=300), # 200 pages per 5 minutes
            'ai_processing': RateLimit(requests=100, window_seconds=300) # 100 AI calls per 5 minutes
        }
    
    async def initialize(self):
        """Initialize Redis connection."""
        try:
            self.redis = aioredis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
            
            await self.redis.ping()
            logger.info("✅ Rate limiter connected to Redis")
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to Redis for rate limiting: {e}")
            self.redis = None
    
    async def cleanup(self):
        """Cleanup Redis connection."""
        if self.redis:
            await self.redis.close()
            logger.info("Rate limiter disconnected")
    
    async def check_rate_limit(
        self, 
        identifier: str, 
        limit_type: str = 'free',
        service: Optional[str] = None
    ) -> Dict[str, Any]:
        """Check if request is within rate limits."""
        if not self.redis:
            return {'allowed': True, 'reason': 'Rate limiter offline'}
        
        try:
            # Determine which limits to apply
            user_limit = self.rate_limits.get(limit_type, self.rate_limits['free'])
            service_limit = self.service_limits.get(service) if service else None
            
            # Check user limits
            user_check = await self._check_limit(
                f"user:{identifier}",
                user_limit.requests,
                user_limit.window_seconds
            )
            
            if not user_check['allowed']:
                return user_check
            
            # Check burst limits
            if user_limit.burst_requests:
                burst_check = await self._check_limit(
                    f"burst:{identifier}",
                    user_limit.burst_requests,
                    60  # 1 minute burst window
                )
                
                if not burst_check['allowed']:
                    return {
                        'allowed': False,
                        'reason': 'Burst rate limit exceeded',
                        'retry_after': burst_check['retry_after'],
                        'limit_type': 'burst'
                    }
            
            # Check service-specific limits
            if service_limit:
                service_check = await self._check_limit(
                    f"service:{service}:{identifier}",
                    service_limit.requests,
                    service_limit.window_seconds
                )
                
                if not service_check['allowed']:
                    return {
                        'allowed': False,
                        'reason': f'{service} service rate limit exceeded',
                        'retry_after': service_check['retry_after'],
                        'limit_type': 'service'
                    }
            
            return {'allowed': True}
            
        except Exception as e:
            logger.error(f"Rate limit check error: {e}")
            return {'allowed': True, 'reason': 'Rate limiter error'}
    
    async def _check_limit(
        self, 
        key: str, 
        max_requests: int, 
        window_seconds: int
    ) -> Dict[str, Any]:
        """Check rate limit using sliding window algorithm."""
        redis_key = f"{self.key_prefix}{key}"
        current_time = datetime.utcnow().timestamp()
        window_start = current_time - window_seconds
        
        # Use Redis pipeline for atomic operations
        pipe = self.redis.pipeline()
        
        # Remove old entries
        pipe.zremrangebyscore(redis_key, 0, window_start)
        
        # Count current requests in window
        pipe.zcard(redis_key)
        
        # Add current request
        pipe.zadd(redis_key, {str(current_time): current_time})
        
        # Set expiry
        pipe.expire(redis_key, window_seconds + 1)
        
        # Execute pipeline
        results = await pipe.execute()
        
        current_requests = results[1]  # Count after cleanup
        
        if current_requests >= max_requests:
            # Find oldest request to calculate retry_after
            oldest_entries = await self.redis.zrange(redis_key, 0, 0, withscores=True)
            if oldest_entries:
                oldest_time = oldest_entries[0][1]
                retry_after = int(oldest_time + window_seconds - current_time)
            else:
                retry_after = window_seconds
            
            return {
                'allowed': False,
                'current_requests': current_requests,
                'max_requests': max_requests,
                'window_seconds': window_seconds,
                'retry_after': max(retry_after, 1),
                'reason': 'Rate limit exceeded'
            }
        
        return {
            'allowed': True,
            'current_requests': current_requests + 1,
            'max_requests': max_requests,
            'remaining_requests': max_requests - current_requests - 1
        }
    
    async def increment_counter(
        self, 
        identifier: str, 
        limit_type: str = 'free',
        service: Optional[str] = None
    ) -> bool:
        """Increment rate limit counters (call after successful request)."""
        if not self.redis:
            return True
        
        try:
            # This is automatically handled in _check_limit when we add the request
            # But we can track successful completions separately if needed
            completion_key = f"{self.key_prefix}completed:{identifier}"
            current_time = datetime.utcnow().timestamp()
            
            await self.redis.zadd(completion_key, {str(current_time): current_time})
            await self.redis.expire(completion_key, 3600)  # 1 hour retention
            
            return True
            
        except Exception as e:
            logger.error(f"Error incrementing rate limit counter: {e}")
            return False
    
    async def get_user_limits(self, identifier: str, limit_type: str = 'free') -> Dict[str, Any]:
        """Get current rate limit status for user."""
        if not self.redis:
            return {'status': 'offline'}
        
        try:
            user_limit = self.rate_limits.get(limit_type, self.rate_limits['free'])
            current_time = datetime.utcnow().timestamp()
            
            # Get current usage
            user_key = f"{self.key_prefix}user:{identifier}"
            window_start = current_time - user_limit.window_seconds
            
            # Clean and count
            await self.redis.zremrangebyscore(user_key, 0, window_start)
            current_requests = await self.redis.zcard(user_key)
            
            # Get burst usage if applicable
            burst_requests = 0
            if user_limit.burst_requests:
                burst_key = f"{self.key_prefix}burst:{identifier}"
                burst_window_start = current_time - 60
                await self.redis.zremrangebyscore(burst_key, 0, burst_window_start)
                burst_requests = await self.redis.zcard(burst_key)
            
            return {
                'status': 'active',
                'limit_type': limit_type,
                'hourly_limit': user_limit.requests,
                'hourly_used': current_requests,
                'hourly_remaining': max(0, user_limit.requests - current_requests),
                'burst_limit': user_limit.burst_requests or 0,
                'burst_used': burst_requests,
                'burst_remaining': max(0, (user_limit.burst_requests or 0) - burst_requests),
                'window_seconds': user_limit.window_seconds
            }
            
        except Exception as e:
            logger.error(f"Error getting user limits: {e}")
            return {'status': 'error', 'error': str(e)}
    
    async def reset_user_limits(self, identifier: str) -> bool:
        """Reset rate limits for a user (admin function)."""
        if not self.redis:
            return False
        
        try:
            pattern = f"{self.key_prefix}*:{identifier}"
            keys = await self.redis.keys(pattern)
            
            if keys:
                await self.redis.delete(*keys)
                logger.info(f"Reset rate limits for user: {identifier}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error resetting user limits: {e}")
            return False
    
    async def get_service_stats(self, service: str, hours: int = 24) -> Dict[str, Any]:
        """Get service usage statistics."""
        if not self.redis:
            return {'status': 'offline'}
        
        try:
            current_time = datetime.utcnow().timestamp()
            window_start = current_time - (hours * 3600)
            
            pattern = f"{self.key_prefix}service:{service}:*"
            keys = await self.redis.keys(pattern)
            
            total_requests = 0
            unique_users = set()
            
            for key in keys:
                # Extract user identifier from key
                user_id = key.split(':')[-1]
                unique_users.add(user_id)
                
                # Count requests in window
                await self.redis.zremrangebyscore(key, 0, window_start)
                requests = await self.redis.zcard(key)
                total_requests += requests
            
            return {
                'status': 'active',
                'service': service,
                'period_hours': hours,
                'total_requests': total_requests,
                'unique_users': len(unique_users),
                'avg_requests_per_user': round(total_requests / len(unique_users), 2) if unique_users else 0
            }
            
        except Exception as e:
            logger.error(f"Error getting service stats: {e}")
            return {'status': 'error', 'error': str(e)}
    
    def get_rate_limit_config(self) -> Dict[str, Any]:
        """Get current rate limit configuration."""
        return {
            'user_tiers': {
                tier: {
                    'requests_per_hour': limit.requests,
                    'burst_requests': limit.burst_requests,
                    'window_seconds': limit.window_seconds
                }
                for tier, limit in self.rate_limits.items()
            },
            'service_limits': {
                service: {
                    'requests': limit.requests,
                    'window_seconds': limit.window_seconds
                }
                for service, limit in self.service_limits.items()
            }
        } 