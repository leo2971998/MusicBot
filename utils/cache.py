import time
import logging
from collections import OrderedDict
from typing import Optional, Dict, Any
from threading import Lock

logger = logging.getLogger(__name__)

class SongCache:
    """Thread-safe LRU cache for extracted song data with TTL"""
    
    def __init__(self, max_size: int = 200, ttl_seconds: int = 3600):
        self.max_size = max_size
        self.ttl = ttl_seconds  # 1 hour default (YouTube URLs expire)
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._lock = Lock()
        self._hits = 0
        self._misses = 0
    
    def _make_key(self, query: str) -> str:
        """Normalize query for cache key"""
        return query.strip().lower()
    
    def get(self, query: str) -> Optional[Dict[str, Any]]:
        """Get cached song data if exists and not expired (thread-safe)"""
        key = self._make_key(query)
        
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None
            
            entry = self._cache[key]
            
            # Check TTL
            if time.time() - entry['cached_at'] > self.ttl:
                del self._cache[key]
                self._misses += 1
                logger.debug(f"Cache expired for: {query[:50]}")
                return None
            
            # Move to end (most recently used)
            self._cache.move_to_end(key)
            self._hits += 1
            logger.debug(f"Cache hit for: {query[:50]}")
            return entry['data']
    
    def set(self, query: str, data: Dict[str, Any]):
        """Cache song data (thread-safe)"""
        if not data:  # Don't cache empty data
            return
        
        key = self._make_key(query)
        
        with self._lock:
            # Remove oldest if at capacity
            while len(self._cache) >= self.max_size:
                oldest = next(iter(self._cache))
                del self._cache[oldest]
                logger.debug(f"Evicted oldest cache entry")
            
            self._cache[key] = {
                'data': data,
                'cached_at': time.time()
            }
            logger.debug(f"Cached: {query[:50]}")
    
    def clear(self):
        """Clear all cache (thread-safe)"""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0
        logger.info("Cache cleared")
    
    def stats(self) -> Dict[str, Any]:
        """Get cache statistics (thread-safe)"""
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0
            
            return {
                'size': len(self._cache),
                'max_size': self.max_size,
                'hits': self._hits,
                'misses': self._misses,
                'hit_rate': f"{hit_rate:.1f}%",
                'total_requests': total_requests
            }
    
    def get_entry_age(self, query: str) -> Optional[float]:
        """Get age of cache entry in seconds (thread-safe)"""
        key = self._make_key(query)
        
        with self._lock:
            if key not in self._cache:
                return None
            
            entry = self._cache[key]
            return time.time() - entry['cached_at']
    
    def remove(self, query: str) -> bool:
        """Remove specific entry from cache (thread-safe)"""
        key = self._make_key(query)
        
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                logger.debug(f"Removed from cache: {query[:50]}")
                return True
        return False
    
    def cleanup_expired(self) -> int:
        """Remove all expired entries and return count (thread-safe)"""
        with self._lock:
            current_time = time.time()
            expired_keys = [
                key for key, entry in self._cache.items()
                if current_time - entry['cached_at'] > self.ttl
            ]
            
            for key in expired_keys:
                del self._cache[key]
        
        if expired_keys:
            logger.info(f"Cleaned up {len(expired_keys)} expired cache entries")
        
        return len(expired_keys)

# Global instance
song_cache = SongCache()

