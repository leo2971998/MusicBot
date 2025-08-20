"""
Search result caching system for improved performance.
Implements in-memory caching with TTL and size limits.
"""

import asyncio
import hashlib
import time
import logging
from typing import Dict, List, Optional, Any
from config import SEARCH_CACHE_TTL, SEARCH_CACHE_MAX_SIZE

logger = logging.getLogger(__name__)


class CacheEntry:
    """Cache entry with TTL support"""
    
    def __init__(self, data: Any, ttl: int):
        self.data = data
        self.created_at = time.time()
        self.ttl = ttl
        self.access_count = 1
        self.last_accessed = self.created_at
    
    def is_expired(self) -> bool:
        """Check if cache entry is expired"""
        return time.time() - self.created_at > self.ttl
    
    def access(self):
        """Record cache access for LRU tracking"""
        self.access_count += 1
        self.last_accessed = time.time()


class SearchCache:
    """In-memory search result cache with TTL and LRU eviction"""
    
    def __init__(self, max_size: int = SEARCH_CACHE_MAX_SIZE, ttl: int = SEARCH_CACHE_TTL):
        self.max_size = max_size
        self.ttl = ttl
        self.cache: Dict[str, CacheEntry] = {}
        self.lock = asyncio.Lock()
        self.hits = 0
        self.misses = 0
        self.evictions = 0
    
    def _normalize_query(self, query: str) -> str:
        """Normalize query for consistent caching"""
        # Convert to lowercase and strip whitespace
        normalized = query.lower().strip()
        # Remove extra spaces
        normalized = ' '.join(normalized.split())
        return normalized
    
    def _hash_query(self, query: str) -> str:
        """Create hash key for query"""
        normalized = self._normalize_query(query)
        return hashlib.md5(normalized.encode('utf-8')).hexdigest()
    
    async def get(self, query: str) -> Optional[List[Dict]]:
        """Get cached search results for query"""
        async with self.lock:
            key = self._hash_query(query)
            entry = self.cache.get(key)
            
            if entry is None:
                self.misses += 1
                return None
            
            if entry.is_expired():
                del self.cache[key]
                self.misses += 1
                logger.debug(f"Cache entry expired for query: {query}")
                return None
            
            entry.access()
            self.hits += 1
            logger.debug(f"Cache hit for query: {query}")
            return entry.data.copy()  # Return copy to prevent modification
    
    async def set(self, query: str, results: List[Dict]) -> None:
        """Cache search results for query"""
        async with self.lock:
            key = self._hash_query(query)
            
            # Check if we need to evict entries
            if len(self.cache) >= self.max_size and key not in self.cache:
                await self._evict_lru()
            
            # Store the entry
            self.cache[key] = CacheEntry(results.copy(), self.ttl)
            logger.debug(f"Cached {len(results)} results for query: {query}")
    
    async def _evict_lru(self) -> None:
        """Evict least recently used entry"""
        if not self.cache:
            return
        
        # Find LRU entry
        lru_key = min(
            self.cache.keys(),
            key=lambda k: self.cache[k].last_accessed
        )
        
        del self.cache[lru_key]
        self.evictions += 1
        logger.debug(f"Evicted LRU cache entry: {lru_key}")
    
    async def cleanup_expired(self) -> int:
        """Remove expired entries and return count removed"""
        async with self.lock:
            expired_keys = [
                key for key, entry in self.cache.items()
                if entry.is_expired()
            ]
            
            for key in expired_keys:
                del self.cache[key]
            
            if expired_keys:
                logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")
            
            return len(expired_keys)
    
    async def clear(self) -> None:
        """Clear all cache entries"""
        async with self.lock:
            count = len(self.cache)
            self.cache.clear()
            self.hits = 0
            self.misses = 0
            self.evictions = 0
            logger.info(f"Cleared {count} cache entries")
    
    async def stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        async with self.lock:
            total_requests = self.hits + self.misses
            hit_rate = (self.hits / total_requests * 100) if total_requests > 0 else 0
            
            return {
                'size': len(self.cache),
                'max_size': self.max_size,
                'hits': self.hits,
                'misses': self.misses,
                'evictions': self.evictions,
                'hit_rate': hit_rate,
                'ttl': self.ttl
            }


# Global search cache instance
search_cache = SearchCache()


async def get_cached_search(query: str) -> Optional[List[Dict]]:
    """Get cached search results"""
    return await search_cache.get(query)


async def cache_search_results(query: str, results: List[Dict]) -> None:
    """Cache search results"""
    await search_cache.set(query, results)


async def cleanup_search_cache() -> int:
    """Cleanup expired cache entries"""
    return await search_cache.cleanup_expired()


async def get_cache_stats() -> Dict[str, Any]:
    """Get cache statistics"""
    return await search_cache.stats()


async def clear_search_cache() -> None:
    """Clear search cache"""
    await search_cache.clear()