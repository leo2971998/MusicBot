"""
In-memory search cache for optimized YouTube search performance.
Implements TTL-based caching with query normalization.
"""

import time
import hashlib
import logging
from typing import Dict, List, Optional, Any
from threading import Lock

logger = logging.getLogger(__name__)

class SearchCache:
    """Thread-safe in-memory cache for search results with TTL support"""
    
    def __init__(self, default_ttl: int = 3600):  # 1 hour default TTL
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.lock = Lock()
        self.default_ttl = default_ttl
        
    def _normalize_query(self, query: str) -> str:
        """Normalize query for consistent caching"""
        # Convert to lowercase, strip whitespace, and normalize spacing
        normalized = ' '.join(query.lower().strip().split())
        return normalized
    
    def _generate_key(self, query: str, search_mode: bool = False) -> str:
        """Generate cache key from query and search mode"""
        normalized_query = self._normalize_query(query)
        mode_suffix = "_search" if search_mode else "_single"
        key_string = f"{normalized_query}{mode_suffix}"
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def get(self, query: str, search_mode: bool = False) -> Optional[Any]:
        """Get cached search results if they exist and are not expired"""
        key = self._generate_key(query, search_mode)
        
        with self.lock:
            if key not in self.cache:
                return None
                
            entry = self.cache[key]
            current_time = time.time()
            
            # Check if entry has expired
            if current_time > entry['expires_at']:
                del self.cache[key]
                logger.debug(f"Cache entry expired for query: {query}")
                return None
                
            logger.debug(f"Cache hit for query: {query}")
            return entry['data']
    
    def set(self, query: str, data: Any, search_mode: bool = False, ttl: Optional[int] = None) -> None:
        """Cache search results with TTL"""
        if not data:  # Don't cache empty results
            return
            
        key = self._generate_key(query, search_mode)
        ttl = ttl or self.default_ttl
        expires_at = time.time() + ttl
        
        with self.lock:
            self.cache[key] = {
                'data': data,
                'expires_at': expires_at,
                'created_at': time.time()
            }
            
        logger.debug(f"Cached search results for query: {query} (TTL: {ttl}s)")
    
    def clear_expired(self) -> int:
        """Remove expired entries from cache and return count of removed entries"""
        current_time = time.time()
        expired_keys = []
        
        with self.lock:
            for key, entry in self.cache.items():
                if current_time > entry['expires_at']:
                    expired_keys.append(key)
            
            for key in expired_keys:
                del self.cache[key]
        
        if expired_keys:
            logger.debug(f"Cleared {len(expired_keys)} expired cache entries")
        
        return len(expired_keys)
    
    def clear_all(self) -> None:
        """Clear all cached entries"""
        with self.lock:
            count = len(self.cache)
            self.cache.clear()
            
        if count > 0:
            logger.debug(f"Cleared all {count} cache entries")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        with self.lock:
            current_time = time.time()
            total_entries = len(self.cache)
            expired_entries = sum(
                1 for entry in self.cache.values() 
                if current_time > entry['expires_at']
            )
            active_entries = total_entries - expired_entries
            
            return {
                'total_entries': total_entries,
                'active_entries': active_entries,
                'expired_entries': expired_entries,
                'memory_usage': self._estimate_memory_usage()
            }
    
    def _estimate_memory_usage(self) -> str:
        """Estimate memory usage of cache"""
        # Rough estimation
        total_size = 0
        for entry in self.cache.values():
            # Estimate size of data
            if isinstance(entry['data'], list):
                total_size += len(entry['data']) * 1000  # Rough estimate per entry
            else:
                total_size += 1000  # Single entry estimate
        
        if total_size < 1024:
            return f"{total_size}B"
        elif total_size < 1024 * 1024:
            return f"{total_size / 1024:.1f}KB"
        else:
            return f"{total_size / (1024 * 1024):.1f}MB"

# Global cache instance
search_cache = SearchCache(default_ttl=1800)  # 30 minutes default TTL