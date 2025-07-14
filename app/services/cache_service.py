"""Cache service for search results and data."""
import json
import hashlib
from typing import Any, Optional, Dict, List
from datetime import datetime, timedelta
import redis.asyncio as aioredis
from loguru import logger

from app.config import settings


class CacheService:
    """Handles caching of search results and frequently accessed data."""
    
    def __init__(self):
        self.redis: Optional[aioredis.Redis] = None
        self.default_ttl = settings.cache_ttl_default
        self.search_ttl = settings.cache_ttl_search_results
        self.key_prefix = "zapai:"
    
    async def initialize(self):
        """Initialize Redis connection."""
        try:
            self.redis = aioredis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=settings.redis_max_connections
            )
            
            # Test connection
            await self.redis.ping()
            logger.info("✅ Cache service connected to Redis")
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to Redis: {e}")
            self.redis = None
    
    async def cleanup(self):
        """Cleanup Redis connection."""
        if self.redis:
            await self.redis.close()
            logger.info("Cache service disconnected")
    
    def generate_cache_key(self, query: str, filters: Dict = None) -> str:
        """Generate a cache key for search query and filters."""
        # Create a unique key based on query and filters
        key_data = {
            'query': query.lower().strip(),
            'filters': filters or {}
        }
        
        # Convert to JSON string for consistent hashing
        key_string = json.dumps(key_data, sort_keys=True)
        
        # Generate hash
        key_hash = hashlib.sha256(key_string.encode()).hexdigest()[:16]
        
        return f"{self.key_prefix}search:{key_hash}"
    
    async def get(self, key: str) -> Optional[Any]:
        """Get cached data by key."""
        if not self.redis:
            return None
        
        try:
            cached_data = await self.redis.get(key)
            if cached_data:
                data = json.loads(cached_data)
                logger.debug(f"Cache HIT for key: {key}")
                return data
            else:
                logger.debug(f"Cache MISS for key: {key}")
                return None
                
        except Exception as e:
            logger.error(f"Cache get error for key {key}: {e}")
            return None
    
    async def set(self, key: str, data: Any, ttl: Optional[int] = None) -> bool:
        """Set cached data with optional TTL."""
        if not self.redis:
            return False
        
        try:
            # Serialize data
            serialized_data = json.dumps(data, default=self._json_serializer)
            
            # Set with TTL
            ttl = ttl or self.default_ttl
            await self.redis.setex(key, ttl, serialized_data)
            
            logger.debug(f"Cache SET for key: {key} (TTL: {ttl}s)")
            return True
            
        except Exception as e:
            logger.error(f"Cache set error for key {key}: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete cached data by key."""
        if not self.redis:
            return False
        
        try:
            deleted = await self.redis.delete(key)
            logger.debug(f"Cache DELETE for key: {key}")
            return deleted > 0
            
        except Exception as e:
            logger.error(f"Cache delete error for key {key}: {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        if not self.redis:
            return False
        
        try:
            return await self.redis.exists(key) > 0
        except Exception as e:
            logger.error(f"Cache exists error for key {key}: {e}")
            return False
    
    async def get_ttl(self, key: str) -> int:
        """Get remaining TTL for a key."""
        if not self.redis:
            return -1
        
        try:
            return await self.redis.ttl(key)
        except Exception as e:
            logger.error(f"Cache TTL error for key {key}: {e}")
            return -1
    
    async def extend_ttl(self, key: str, additional_seconds: int) -> bool:
        """Extend TTL for a key."""
        if not self.redis:
            return False
        
        try:
            current_ttl = await self.redis.ttl(key)
            if current_ttl > 0:
                new_ttl = current_ttl + additional_seconds
                await self.redis.expire(key, new_ttl)
                return True
            return False
            
        except Exception as e:
            logger.error(f"Cache extend TTL error for key {key}: {e}")
            return False
    
    # Search-specific methods
    async def cache_search_results(self, query: str, filters: Dict, results: List[Dict]) -> bool:
        """Cache search results with search-specific TTL."""
        cache_key = self.generate_cache_key(query, filters)
        
        cache_data = {
            'query': query,
            'filters': filters,
            'results': results,
            'cached_at': datetime.utcnow().isoformat(),
            'result_count': len(results)
        }
        
        return await self.set(cache_key, cache_data, self.search_ttl)
    
    async def get_cached_search_results(self, query: str, filters: Dict) -> Optional[List[Dict]]:
        """Get cached search results."""
        cache_key = self.generate_cache_key(query, filters)
        cached_data = await self.get(cache_key)
        
        if cached_data:
            return cached_data.get('results', [])
        return None
    
    # Analytics and monitoring
    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        if not self.redis:
            return {'status': 'disconnected'}
        
        try:
            info = await self.redis.info()
            
            stats = {
                'status': 'connected',
                'used_memory': info.get('used_memory_human', 'N/A'),
                'connected_clients': info.get('connected_clients', 0),
                'total_commands_processed': info.get('total_commands_processed', 0),
                'keyspace_hits': info.get('keyspace_hits', 0),
                'keyspace_misses': info.get('keyspace_misses', 0),
                'uptime_in_seconds': info.get('uptime_in_seconds', 0)
            }
            
            # Calculate hit ratio
            hits = stats['keyspace_hits']
            misses = stats['keyspace_misses']
            if hits + misses > 0:
                stats['hit_ratio'] = round(hits / (hits + misses) * 100, 2)
            else:
                stats['hit_ratio'] = 0
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {'status': 'error', 'error': str(e)}
    
    async def clear_expired_keys(self) -> int:
        """Clear expired keys (manual cleanup)."""
        if not self.redis:
            return 0
        
        try:
            # Get all keys with our prefix
            pattern = f"{self.key_prefix}*"
            keys = await self.redis.keys(pattern)
            
            expired_count = 0
            for key in keys:
                ttl = await self.redis.ttl(key)
                if ttl == -2:  # Key has expired
                    expired_count += 1
            
            logger.info(f"Found {expired_count} expired keys")
            return expired_count
            
        except Exception as e:
            logger.error(f"Error clearing expired keys: {e}")
            return 0
    
    async def flush_search_cache(self) -> bool:
        """Flush all search-related cache entries."""
        if not self.redis:
            return False
        
        try:
            pattern = f"{self.key_prefix}search:*"
            keys = await self.redis.keys(pattern)
            
            if keys:
                deleted = await self.redis.delete(*keys)
                logger.info(f"Flushed {deleted} search cache entries")
                return True
            
            return True
            
        except Exception as e:
            logger.error(f"Error flushing search cache: {e}")
            return False
    
    # Utility methods
    def _json_serializer(self, obj):
        """Custom JSON serializer for datetime objects."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
    
    async def batch_get(self, keys: List[str]) -> Dict[str, Any]:
        """Get multiple keys in a single operation."""
        if not self.redis or not keys:
            return {}
        
        try:
            values = await self.redis.mget(*keys)
            result = {}
            
            for i, key in enumerate(keys):
                if values[i]:
                    try:
                        result[key] = json.loads(values[i])
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to decode cached data for key: {key}")
            
            return result
            
        except Exception as e:
            logger.error(f"Batch get error: {e}")
            return {}
    
    async def batch_set(self, key_value_pairs: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        """Set multiple key-value pairs in a single operation."""
        if not self.redis or not key_value_pairs:
            return False
        
        try:
            pipe = self.redis.pipeline()
            ttl = ttl or self.default_ttl
            
            for key, value in key_value_pairs.items():
                serialized_value = json.dumps(value, default=self._json_serializer)
                pipe.setex(key, ttl, serialized_value)
            
            await pipe.execute()
            logger.debug(f"Batch SET for {len(key_value_pairs)} keys")
            return True
            
        except Exception as e:
            logger.error(f"Batch set error: {e}")
            return False 