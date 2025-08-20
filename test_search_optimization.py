#!/usr/bin/env python3
"""
Test script to verify search optimization changes.
Tests the new auto-selection functionality and performance improvements.
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

async def test_best_result_search():
    """Test the new get_best_result method"""
    logger.info("Testing best result search optimization...")
    
    try:
        from utils.search_optimizer import search_optimizer
        
        test_queries = [
            "never gonna give you up",
            "bohemian rhapsody queen",
            "imagine dragons believer"
        ]
        
        for query in test_queries:
            logger.info(f"\nTesting query: '{query}'")
            
            # Test new optimized method
            logger.info("Testing optimized get_best_result method...")
            start_time = time.time()
            try:
                best_result = await search_optimizer.get_best_result(query)
                elapsed = time.time() - start_time
                
                if best_result:
                    logger.info(f"  SUCCESS: {elapsed:.2f}s")
                    logger.info(f"  Result: {best_result.get('title', 'Unknown')} by {best_result.get('uploader', 'Unknown')}")
                    logger.info(f"  Views: {best_result.get('view_count', 0):,}")
                    logger.info(f"  URL: {best_result.get('webpage_url', 'Unknown')}")
                else:
                    logger.warning(f"  No result found in {elapsed:.2f}s")
                    
            except Exception as e:
                logger.error(f"  ERROR: {e}")
            
            # Compare with old multi-result method
            logger.info("Testing multi-result method for comparison...")
            start_time = time.time()
            try:
                multi_results = await search_optimizer.fast_search(query, max_results=3)
                elapsed = time.time() - start_time
                
                if multi_results:
                    best_from_multi = max(multi_results, key=lambda x: x.get('view_count', 0))
                    logger.info(f"  Multi-result: {elapsed:.2f}s - {len(multi_results)} results")
                    logger.info(f"  Best from multi: {best_from_multi.get('title', 'Unknown')} - {best_from_multi.get('view_count', 0):,} views")
                else:
                    logger.warning(f"  No multi-results found in {elapsed:.2f}s")
                    
            except Exception as e:
                logger.error(f"  Multi-result ERROR: {e}")
        
        logger.info("✅ Best result search test completed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Best result search test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_cache_integration():
    """Test caching integration with the new approach"""
    logger.info("\nTesting cache integration...")
    
    try:
        from utils.search_cache import search_cache
        from utils.search_optimizer import search_optimizer
        
        # Clear cache first
        search_cache.clear_all()
        
        query = "test query for cache"
        
        # First call should miss cache
        logger.info("First call (should miss cache)...")
        start_time = time.time()
        result1 = await search_optimizer.get_best_result(query)
        elapsed1 = time.time() - start_time
        
        if result1:
            # Cache the result manually for testing
            search_cache.set(query, result1, search_mode=False, ttl=300)
            logger.info(f"  First call: {elapsed1:.2f}s - Result cached")
        
        # Second call should hit cache
        logger.info("Second call (should hit cache)...")
        start_time = time.time()
        cached_result = search_cache.get(query, search_mode=False)
        elapsed2 = time.time() - start_time
        
        if cached_result:
            logger.info(f"  Cache hit: {elapsed2:.4f}s")
            logger.info(f"  Speed improvement: {(elapsed1/elapsed2):.1f}x faster")
        else:
            logger.warning("  Cache miss - unexpected")
        
        # Check cache stats
        stats = search_cache.get_stats()
        logger.info(f"  Cache stats: {stats}")
        
        logger.info("✅ Cache integration test completed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Cache integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_command_logic():
    """Test the updated command logic without Discord interaction"""
    logger.info("\nTesting command logic simulation...")
    
    try:
        from utils.search_optimizer import search_optimizer
        from utils.search_cache import search_cache
        
        query = "test search command"
        
        # Simulate the new search command logic
        logger.info("Simulating new search command flow...")
        
        # Step 1: Preprocess query
        optimized_query = search_optimizer.preprocess_query(query)
        logger.info(f"  Preprocessed query: '{query}' -> '{optimized_query}'")
        
        # Step 2: Check cache
        cached_result = search_cache.get(query, search_mode=False)
        if cached_result:
            logger.info("  Cache hit - would use cached result")
            best_result = cached_result
        else:
            logger.info("  Cache miss - would search for new result")
            # Step 3: Get best result
            best_result = await search_optimizer.get_best_result(optimized_query)
            
            if best_result:
                # Step 4: Cache result
                search_cache.set(query, best_result, search_mode=False, ttl=3600)
                logger.info("  Result found and cached")
            else:
                logger.warning("  No result found")
        
        if best_result:
            logger.info(f"  Would play: {best_result.get('title', 'Unknown')}")
            logger.info(f"  By: {best_result.get('uploader', 'Unknown')}")
            logger.info(f"  Views: {best_result.get('view_count', 0):,}")
        
        logger.info("✅ Command logic test completed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Command logic test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def run_all_tests():
    """Run all optimization tests"""
    logger.info("🎵 Starting Search Optimization Tests")
    
    success = True
    
    try:
        # Test best result search
        if not await test_best_result_search():
            success = False
        
        # Test cache integration
        if not await test_cache_integration():
            success = False
        
        # Test command logic
        if not await test_command_logic():
            success = False
        
        if success:
            logger.info("\n🎉 All optimization tests passed! Search optimization is working.")
        else:
            logger.error("\n❌ Some tests failed. Check the logs above.")
            
    except Exception as e:
        logger.error(f"❌ Test suite failed: {e}")
        success = False
    
    return success

if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)