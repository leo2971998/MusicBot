"""
Search performance optimization utilities.
Handles two-phase search approach and query optimization.
"""

import asyncio
import logging
import time
from typing import List, Dict, Optional, Any
import yt_dlp as youtube_dl
from config import FAST_SEARCH_OPTS, FULL_METADATA_OPTS

logger = logging.getLogger(__name__)

class SearchOptimizer:
    """Handles optimized YouTube search with two-phase approach"""
    
    def __init__(self):
        # Initialize optimized yt-dlp instances
        self.fast_ytdl = youtube_dl.YoutubeDL(FAST_SEARCH_OPTS)
        self.full_ytdl = youtube_dl.YoutubeDL(FULL_METADATA_OPTS)
    
    async def fast_search(self, query: str, max_results: int = 5) -> Optional[List[Dict[str, Any]]]:
        """
        Phase 1: Fast search with minimal metadata extraction
        Returns basic info quickly for user selection
        """
        try:
            start_time = time.time()
            search_query = f"ytsearch{max_results}:{query}"
            
            loop = asyncio.get_running_loop()
            search_results = await loop.run_in_executor(
                None, lambda: self.fast_ytdl.extract_info(search_query, download=False)
            )
            
            elapsed = time.time() - start_time
            logger.debug(f"Fast search completed in {elapsed:.2f}s for query: {query}")
            
            if not search_results or not search_results.get('entries'):
                logger.debug(f"No search results found for query: {query}")
                return None
            
            # Process and enhance basic results
            processed_results = []
            for entry in search_results['entries'][:max_results]:
                if entry:  # Skip None entries
                    processed_entry = self._process_fast_result(entry)
                    if processed_entry:
                        processed_results.append(processed_entry)
            
            logger.debug(f"Processed {len(processed_results)} fast search results")
            return processed_results
            
        except Exception as e:
            logger.error(f"Error in fast search for query '{query}': {e}")
            return None
    
    async def get_full_metadata(self, video_url: str) -> Optional[Dict[str, Any]]:
        """
        Phase 2: Extract full metadata for selected video
        Called when user selects a specific result
        """
        try:
            start_time = time.time()
            
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None, lambda: self.full_ytdl.extract_info(video_url, download=False)
            )
            
            elapsed = time.time() - start_time
            logger.debug(f"Full metadata extraction completed in {elapsed:.2f}s for URL: {video_url}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error extracting full metadata for URL '{video_url}': {e}")
            return None
    
    def _process_fast_result(self, entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process and enhance fast search result with estimated metadata"""
        try:
            if not entry or not entry.get('id'):
                return None
            
            # Extract basic information available from flat extraction
            video_id = entry.get('id', '')
            title = entry.get('title', 'Unknown Title')
            uploader = entry.get('uploader', 'Unknown Artist')
            
            # Generate YouTube URL if not present
            webpage_url = entry.get('url') or entry.get('webpage_url')
            if not webpage_url and video_id:
                webpage_url = f"https://www.youtube.com/watch?v={video_id}"
            
            # Create enhanced result with available data
            enhanced_result = {
                'id': video_id,
                'title': title,
                'uploader': uploader,
                'webpage_url': webpage_url,
                'url': webpage_url,
                'duration': entry.get('duration', 0),
                'view_count': entry.get('view_count', 0),
                'description': entry.get('description', ''),
                'upload_date': entry.get('upload_date', ''),
                'thumbnail': entry.get('thumbnail', ''),
                # Mark as fast result for later full metadata extraction
                '_fast_result': True,
                '_original_entry': entry
            }
            
            return enhanced_result
            
        except Exception as e:
            logger.error(f"Error processing fast result: {e}")
            return None
    
    def preprocess_query(self, query: str) -> str:
        """Optimize search query for better results"""
        # Remove common filler words that don't help search
        filler_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from'}
        
        # Split query into words
        words = query.lower().split()
        
        # Keep important words, remove fillers (but keep if query becomes too short)
        filtered_words = [word for word in words if word not in filler_words or len(words) <= 3]
        
        # Rejoin words
        optimized_query = ' '.join(filtered_words) if filtered_words else query
        
        # Limit query length to avoid overly long searches
        if len(optimized_query) > 100:
            optimized_query = optimized_query[:100].strip()
        
        return optimized_query
    
    async def search_with_fallback(self, query: str, max_results: int = 5) -> Optional[List[Dict[str, Any]]]:
        """
        Search with fallback to ensure results
        Try fast search first, fallback to regular search if needed
        """
        # Try fast search first
        results = await self.fast_search(query, max_results)
        
        if results and len(results) >= 1:
            return results
        
        # Fallback to regular search if fast search fails or returns no results
        logger.debug(f"Fast search failed for '{query}', falling back to regular search")
        
        try:
            start_time = time.time()
            search_query = f"ytsearch{max_results}:{query}"
            
            loop = asyncio.get_running_loop()
            search_results = await loop.run_in_executor(
                None, lambda: self.full_ytdl.extract_info(search_query, download=False)
            )
            
            elapsed = time.time() - start_time
            logger.debug(f"Fallback search completed in {elapsed:.2f}s")
            
            if search_results and search_results.get('entries'):
                return search_results['entries'][:max_results]
            
        except Exception as e:
            logger.error(f"Error in fallback search for query '{query}': {e}")
        
        return None

# Global optimizer instance
search_optimizer = SearchOptimizer()