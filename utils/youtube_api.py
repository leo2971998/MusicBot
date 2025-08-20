"""
YouTube Data API wrapper for fast music search.
Provides fast search results using YouTube Data API v3 with fallback to yt-dlp.
"""

import asyncio
import logging
import aiohttp
import time
from typing import List, Dict, Optional
from config import YOUTUBE_API_KEY, YOUTUBE_API_ENABLED

logger = logging.getLogger(__name__)

class YouTubeAPI:
    """YouTube Data API wrapper for fast search"""
    
    def __init__(self):
        self.api_key = YOUTUBE_API_KEY
        self.enabled = YOUTUBE_API_ENABLED
        self.base_url = "https://www.googleapis.com/youtube/v3"
        self.session = None
        
    async def __aenter__(self):
        """Async context manager entry"""
        if not self.session:
            connector = aiohttp.TCPConnector(limit=100, limit_per_host=30)
            timeout = aiohttp.ClientTimeout(total=10)
            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout
            )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()
            self.session = None
    
    async def search_videos(self, query: str, max_results: int = 5) -> List[Dict]:
        """
        Search for videos using YouTube Data API.
        Returns list of video metadata dictionaries.
        """
        if not self.enabled:
            logger.warning("YouTube API not enabled, falling back to yt-dlp")
            return []
        
        try:
            # Prepare search request
            params = {
                'part': 'snippet',
                'q': query,
                'type': 'video',
                'maxResults': max_results,
                'order': 'relevance',
                'key': self.api_key,
                'videoDefinition': 'any',
                'videoDuration': 'any'
            }
            
            # Make API request
            async with self.session.get(
                f"{self.base_url}/search",
                params=params
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return await self._process_search_results(data)
                elif response.status == 403:
                    error_data = await response.json()
                    error_reason = error_data.get('error', {}).get('errors', [{}])[0].get('reason', 'unknown')
                    if error_reason == 'quotaExceeded':
                        logger.warning("YouTube API quota exceeded, falling back to yt-dlp")
                    else:
                        logger.error(f"YouTube API forbidden: {error_reason}")
                    return []
                else:
                    logger.error(f"YouTube API request failed: {response.status}")
                    return []
                    
        except asyncio.TimeoutError:
            logger.warning("YouTube API request timed out, falling back to yt-dlp")
            return []
        except Exception as e:
            logger.error(f"YouTube API error: {e}")
            return []
    
    async def _process_search_results(self, data: Dict) -> List[Dict]:
        """Process YouTube API search results into yt-dlp compatible format"""
        results = []
        items = data.get('items', [])
        
        if not items:
            return results
        
        # Get video details for duration and view count
        video_ids = [item['id']['videoId'] for item in items]
        video_details = await self._get_video_details(video_ids)
        
        for item in items:
            video_id = item['id']['videoId']
            snippet = item['snippet']
            details = video_details.get(video_id, {})
            
            # Convert duration from ISO 8601 to seconds
            duration = self._parse_duration(details.get('duration', 'PT0S'))
            
            # Parse view count
            view_count = int(details.get('viewCount', 0))
            
            result = {
                'id': video_id,
                'title': snippet['title'],
                'uploader': snippet['channelTitle'],
                'duration': duration,
                'view_count': view_count,
                'webpage_url': f"https://www.youtube.com/watch?v={video_id}",
                'thumbnail': snippet.get('thumbnails', {}).get('medium', {}).get('url'),
                'description': snippet.get('description', ''),
                'upload_date': snippet.get('publishedAt', ''),
                'source': 'youtube_api'
            }
            results.append(result)
        
        return results
    
    async def _get_video_details(self, video_ids: List[str]) -> Dict[str, Dict]:
        """Get detailed video information including duration and view count"""
        if not video_ids:
            return {}
        
        try:
            params = {
                'part': 'contentDetails,statistics',
                'id': ','.join(video_ids),
                'key': self.api_key
            }
            
            async with self.session.get(
                f"{self.base_url}/videos",
                params=params
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    details = {}
                    for item in data.get('items', []):
                        video_id = item['id']
                        content_details = item.get('contentDetails', {})
                        statistics = item.get('statistics', {})
                        
                        details[video_id] = {
                            'duration': content_details.get('duration', 'PT0S'),
                            'viewCount': statistics.get('viewCount', '0')
                        }
                    return details
                else:
                    logger.warning(f"Failed to get video details: {response.status}")
                    return {}
        except Exception as e:
            logger.error(f"Error getting video details: {e}")
            return {}
    
    def _parse_duration(self, duration_str: str) -> int:
        """Parse ISO 8601 duration (PT1M30S) to seconds"""
        try:
            # Remove PT prefix
            duration_str = duration_str.replace('PT', '')
            
            total_seconds = 0
            
            # Parse hours
            if 'H' in duration_str:
                hours, duration_str = duration_str.split('H')
                total_seconds += int(hours) * 3600
            
            # Parse minutes
            if 'M' in duration_str:
                minutes, duration_str = duration_str.split('M')
                total_seconds += int(minutes) * 60
            
            # Parse seconds
            if 'S' in duration_str:
                seconds = duration_str.replace('S', '')
                total_seconds += int(seconds)
            
            return total_seconds
        except Exception:
            return 0


# Global YouTube API instance
youtube_api = YouTubeAPI()


async def fast_youtube_search(query: str, max_results: int = 5) -> List[Dict]:
    """
    Fast YouTube search using Data API with fallback to yt-dlp.
    Returns list of video metadata compatible with existing code.
    """
    start_time = time.time()
    
    try:
        async with youtube_api as api:
            results = await api.search_videos(query, max_results)
            
        search_time = time.time() - start_time
        
        if results:
            logger.info(f"YouTube API search completed in {search_time:.2f}s, found {len(results)} results")
            return results
        else:
            logger.info(f"YouTube API search failed after {search_time:.2f}s, falling back to yt-dlp")
            return []
            
    except Exception as e:
        search_time = time.time() - start_time
        logger.error(f"YouTube API search error after {search_time:.2f}s: {e}")
        return []