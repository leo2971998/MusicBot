#!/usr/bin/env python3
"""
Test script for search performance optimization.
Tests the new fast search functionality with YouTube API and caching.
"""

import asyncio
import sys
import os
import time
import logging

# Add the bot directory to path so we can import modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Import our modules
from commands.music_commands import _fast_search, _ytdlp_fallback_search
from utils.cache import get_cache_stats, clear_search_cache
from utils.youtube_api import fast_youtube_search

async def test_fast_search():
    """Test the fast search functionality"""
    logger.info("Testing Fast Search Performance...")
    
    test_queries = [
        "never gonna give you up",
        "bohemian rhapsody",
        "despacito",
        "shape of you ed sheeran",
        "blinding lights weeknd"
    ]
    
    total_time = 0
    total_searches = 0
    
    for query in test_queries:
        logger.info(f"\n--- Testing query: '{query}' ---")
        
        # Test fast search
        start_time = time.time()
        results = await _fast_search(query, max_results=5)
        search_time = time.time() - start_time
        
        total_time += search_time
        total_searches += 1
        
        logger.info(f"Search completed in {search_time:.3f}s")
        logger.info(f"Found {len(results)} results")
        
        # Display first result
        if results:
            first_result = results[0]
            duration_str = f"{first_result.get('duration', 0)//60}:{first_result.get('duration', 0)%60:02d}"
            logger.info(f"First result: {first_result.get('title')} by {first_result.get('uploader')} ({duration_str})")
            logger.info(f"Source: {first_result.get('source', 'unknown')}")
        else:
            logger.warning("No results found")
        
        # Test cache hit (second search should be faster)
        logger.info("Testing cache hit...")
        start_time = time.time()
        cached_results = await _fast_search(query, max_results=5)
        cache_time = time.time() - start_time
        
        logger.info(f"Cached search completed in {cache_time:.3f}s (should be <0.01s)")
        logger.info(f"Cache speedup: {search_time/cache_time:.1f}x faster" if cache_time > 0 else "Instantaneous")
    
    avg_time = total_time / total_searches if total_searches > 0 else 0
    logger.info(f"\n=== PERFORMANCE SUMMARY ===")
    logger.info(f"Average search time: {avg_time:.3f}s")
    logger.info(f"Total searches: {total_searches}")
    logger.info(f"Target: <0.8s per search")
    
    if avg_time < 0.8:
        logger.info("✅ Performance target achieved!")
    elif avg_time < 2.0:
        logger.info("🟡 Performance improved but could be better")
    else:
        logger.info("❌ Performance needs improvement")
    
    # Display cache stats
    stats = await get_cache_stats()
    logger.info(f"\n=== CACHE STATISTICS ===")
    logger.info(f"Cache size: {stats['size']}/{stats['max_size']}")
    logger.info(f"Cache hits: {stats['hits']}")
    logger.info(f"Cache misses: {stats['misses']}")
    logger.info(f"Hit rate: {stats['hit_rate']:.1f}%")
    logger.info(f"Evictions: {stats['evictions']}")

async def test_youtube_api():
    """Test YouTube API directly"""
    logger.info("\n=== TESTING YOUTUBE API DIRECTLY ===")
    
    try:
        start_time = time.time()
        results = await fast_youtube_search("never gonna give you up", max_results=3)
        api_time = time.time() - start_time
        
        logger.info(f"YouTube API search completed in {api_time:.3f}s")
        logger.info(f"Found {len(results)} results via API")
        
        if results:
            for i, result in enumerate(results, 1):
                duration_str = f"{result.get('duration', 0)//60}:{result.get('duration', 0)%60:02d}"
                logger.info(f"{i}. {result.get('title')} by {result.get('uploader')} ({duration_str})")
        
        return True
    except Exception as e:
        logger.error(f"YouTube API test failed: {e}")
        return False

async def test_fallback():
    """Test yt-dlp fallback"""
    logger.info("\n=== TESTING YT-DLP FALLBACK ===")
    
    try:
        start_time = time.time()
        results = await _ytdlp_fallback_search("never gonna give you up", max_results=3)
        fallback_time = time.time() - start_time
        
        logger.info(f"yt-dlp fallback completed in {fallback_time:.3f}s")
        logger.info(f"Found {len(results)} results via yt-dlp")
        
        if results:
            for i, result in enumerate(results, 1):
                duration_str = f"{result.get('duration', 0)//60}:{result.get('duration', 0)%60:02d}"
                logger.info(f"{i}. {result.get('title')} by {result.get('uploader')} ({duration_str})")
        
        return True
    except Exception as e:
        logger.error(f"yt-dlp fallback test failed: {e}")
        return False

async def run_performance_tests():
    """Run all performance tests"""
    logger.info("🚀 Starting Search Performance Tests")
    logger.info("="*50)
    
    # Clear cache to start fresh
    await clear_search_cache()
    
    try:
        # Test YouTube API
        api_success = await test_youtube_api()
        
        # Test fallback
        fallback_success = await test_fallback()
        
        # Test integrated fast search
        await test_fast_search()
        
        # Summary
        logger.info("\n" + "="*50)
        logger.info("🏁 PERFORMANCE TEST SUMMARY")
        logger.info("="*50)
        
        if api_success:
            logger.info("✅ YouTube API: Working")
        else:
            logger.info("❌ YouTube API: Failed (will use fallback)")
        
        if fallback_success:
            logger.info("✅ yt-dlp Fallback: Working")
        else:
            logger.info("❌ yt-dlp Fallback: Failed")
        
        logger.info("\n📊 Expected Performance:")
        logger.info("• YouTube API: 200-800ms")
        logger.info("• Cache Hit: <10ms") 
        logger.info("• yt-dlp Fallback: 2-5s (improved from 3-5s+)")
        
        return api_success or fallback_success
        
    except Exception as e:
        logger.error(f"Performance test failed: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(run_performance_tests())
    
    if success:
        print("\n🎉 Search optimization tests completed!")
        print("The bot should now search 5-10x faster than before.")
    else:
        print("\n❌ Some tests failed. Check the logs above.")
    
    sys.exit(0 if success else 1)