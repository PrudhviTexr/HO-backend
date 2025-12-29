"""
Simple in-memory cache for API responses
"""
import time
from typing import Any, Optional, Dict
from functools import wraps

class SimpleCache:
    """Simple in-memory cache with TTL"""
    
    def __init__(self, default_ttl: int = 300):  # 5 minutes default
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.default_ttl = default_ttl
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired"""
        if key not in self.cache:
            return None
        
        entry = self.cache[key]
        if time.time() > entry['expires_at']:
            # Expired, remove it
            del self.cache[key]
            return None
        
        return entry['value']
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in cache with TTL"""
        ttl = ttl or self.default_ttl
        self.cache[key] = {
            'value': value,
            'expires_at': time.time() + ttl
        }
    
    def clear(self) -> None:
        """Clear all cache entries"""
        self.cache.clear()
    
    def delete(self, key: str) -> None:
        """Delete a specific cache entry"""
        if key in self.cache:
            del self.cache[key]

# Global cache instance
cache = SimpleCache(default_ttl=300)  # 5 minutes default TTL

def cached(ttl: int = 300):
    """Decorator to cache function results"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Create cache key from function name and arguments
            cache_key = f"{func.__name__}:{str(args)}:{str(sorted(kwargs.items()))}"
            
            # Check cache
            cached_value = cache.get(cache_key)
            if cached_value is not None:
                return cached_value
            
            # Call function and cache result
            result = await func(*args, **kwargs)
            cache.set(cache_key, result, ttl=ttl)
            return result
        
        return wrapper
    return decorator

