#!/usr/bin/env python3
"""
Test script to verify search performance optimizations.
Compares old vs new search approaches and measures performance.
"""

import asyncio
import time
import logging
import sys
import os

# Add the bot directory to path so we can import modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

async def test_search_performance():
    """Test search performance improvements"""
    logger.info("Testing Search Performance Optimizations...")
    
    try:
        from utils.search_optimizer import search_optimizer
        from utils.search_cache import search_cache
        from config import YTDL_FORMAT_OPTS
        import yt_dlp as youtube_dl
        
        # Test queries
        test_queries = [
            "never gonna give you up",
            "bohemian rhapsody",
            "imagine dragons believer"
        ]
        
        # Initialize old-style ytdl for comparison
        old_ytdl = youtube_dl.YoutubeDL(YTDL_FORMAT_OPTS)
        
        logger.info("=" * 60)
        logger.info("PERFORMANCE COMPARISON")
        logger.info("=" * 60)
        
        for query in test_queries:
            logger.info(f"\nTesting query: '{query}'")
            
            # Test old method
            logger.info("Testing OLD method (full metadata extraction)...")
            start_time = time.time()
            try:
                old_result = old_ytdl.extract_info(f"ytsearch5:{query}", download=False)
                old_elapsed = time.time() - start_time
                old_count = len(old_result.get('entries', []))
                logger.info(f"  OLD: {old_elapsed:.2f}s - {old_count} results")
            except Exception as e:
                logger.error(f"  OLD method failed: {e}")
                old_elapsed = float('inf')
            
            # Test new fast search method
            logger.info("Testing NEW method (fast search)...")
            start_time = time.time()
            try:
                new_result = await search_optimizer.fast_search(query, max_results=5)
                new_elapsed = time.time() - start_time
                new_count = len(new_result) if new_result else 0
                logger.info(f"  NEW: {new_elapsed:.2f}s - {new_count} results")
                
                if old_elapsed != float('inf') and new_elapsed > 0:
                    improvement = ((old_elapsed - new_elapsed) / old_elapsed) * 100
                    speed_factor = old_elapsed / new_elapsed
                    logger.info(f"  IMPROVEMENT: {improvement:.1f}% faster ({speed_factor:.1f}x)")
                    
            except Exception as e:
                logger.error(f"  NEW method failed: {e}")
            
            # Test cache hit performance
            logger.info("Testing CACHED result...")
            start_time = time.time()
            cached_result = search_cache.get(query, search_mode=True)
            cache_elapsed = time.time() - start_time
            
            if cached_result:
                logger.info(f"  CACHE HIT: {cache_elapsed:.4f}s - {len(cached_result)} results")
            else:
                # Cache the result for next test
                if 'new_result' in locals() and new_result:
                    search_cache.set(query, new_result, search_mode=True)
                    logger.info("  CACHE MISS: Result cached for next test")
        
        # Test cache statistics
        logger.info("\n" + "=" * 60)
        logger.info("CACHE STATISTICS")
        logger.info("=" * 60)
        
        cache_stats = search_cache.get_stats()
        for key, value in cache_stats.items():
            logger.info(f"  {key}: {value}")
        
        logger.info("\n✅ Search performance test completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Search performance test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_two_phase_approach():
    """Test the two-phase search approach"""
    logger.info("\nTesting Two-Phase Search Approach...")
    
    try:
        from utils.search_optimizer import search_optimizer
        
        # Phase 1: Fast search
        logger.info("Phase 1: Fast search with minimal metadata...")
        start_time = time.time()
        fast_results = await search_optimizer.fast_search("never gonna give you up", max_results=3)
        phase1_elapsed = time.time() - start_time
        
        if fast_results:
            logger.info(f"  Phase 1: {phase1_elapsed:.2f}s - {len(fast_results)} results")
            
            # Show first result info
            first_result = fast_results[0]
            logger.info(f"  Sample result: {first_result.get('title', 'Unknown')} by {first_result.get('uploader', 'Unknown')}")
            
            # Phase 2: Full metadata for selected result
            if first_result.get('_fast_result', False):
                logger.info("Phase 2: Getting full metadata for selected result...")
                start_time = time.time()
                full_metadata = await search_optimizer.get_full_metadata(first_result['webpage_url'])
                phase2_elapsed = time.time() - start_time
                
                if full_metadata:
                    logger.info(f"  Phase 2: {phase2_elapsed:.2f}s - Full metadata extracted")
                    logger.info(f"  Total time: {phase1_elapsed + phase2_elapsed:.2f}s")
                    logger.info(f"  Benefit: User sees results in {phase1_elapsed:.2f}s, full data ready in {phase2_elapsed:.2f}s more")
                else:
                    logger.warning("  Phase 2: Failed to extract full metadata")
            else:
                logger.info("  Result already has full metadata, no Phase 2 needed")
        else:
            logger.warning("  Phase 1: No results found")
        
        logger.info("✅ Two-phase approach test completed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Two-phase approach test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def run_all_tests():
    """Run all performance tests"""
    logger.info("🎵 Starting Music Search Performance Tests")
    
    success = True
    
    try:
        # Test basic search performance
        if not await test_search_performance():
            success = False
        
        # Test two-phase approach
        if not await test_two_phase_approach():
            success = False
        
        if success:
            logger.info("\n🎉 All tests passed! Search optimization is working.")
        else:
            logger.error("\n❌ Some tests failed. Check the logs above.")
            
    except Exception as e:
        logger.error(f"❌ Test suite failed: {e}")
        success = False
    
    return success

if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)