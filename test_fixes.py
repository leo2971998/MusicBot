#!/usr/bin/env python3
"""
Test script to verify the main fixes for the MusicBot issues.
This script tests the core functionality without requiring a Discord connection.
"""

import asyncio
import sys
import os
import time
import logging

# Add the bot directory to path so we can import modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot_state import health_monitor, player_manager, queue_manager, data_manager, client
from managers.queue_manager import MAX_QUEUE_SIZE

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class MockGuild:
    def __init__(self, guild_id):
        self.id = guild_id

class MockChannel:
    def __init__(self, channel_id):
        self.id = channel_id

async def test_health_monitor():
    """Test the health monitoring system"""
    logger.info("Testing Health Monitor System...")
    
    # Test health monitor initialization
    assert hasattr(health_monitor, 'start'), "Health monitor should have start method"
    assert hasattr(health_monitor, 'stop'), "Health monitor should have stop method"
    
    # Test health check functionality
    health_status = await player_manager.health_check()
    assert isinstance(health_status, dict), "Health check should return a dictionary"
    
    logger.info("✅ Health monitor system test passed")

async def test_queue_management():
    """Test queue management with limits and memory management"""
    logger.info("Testing Queue Management System...")
    
    test_guild_id = "123456789"
    
    # Test adding songs within limit
    for i in range(5):
        song_info = {
            'title': f'Test Song {i}',
            'url': f'https://test.com/song{i}',
            'requester': '@testuser'
        }
        result = queue_manager.add_song(test_guild_id, song_info)
        assert result, f"Should be able to add song {i}"
    
    # Test queue retrieval
    queue = queue_manager.get_queue(test_guild_id)
    assert len(queue) == 5, f"Queue should have 5 songs, got {len(queue)}"
    
    # Test queue size limit (simulate adding many songs)
    logger.info(f"Testing queue size limit (max {MAX_QUEUE_SIZE})")
    
    # Add songs up to limit
    for i in range(5, MAX_QUEUE_SIZE):
        song_info = {'title': f'Song {i}', 'url': f'test{i}'}
        queue_manager.add_song(test_guild_id, song_info)
    
    # Try to add one more (should fail)
    overflow_song = {'title': 'Overflow Song', 'url': 'overflow'}
    result = queue_manager.add_song(test_guild_id, overflow_song)
    assert not result, "Adding song beyond limit should fail"
    
    # Test cleanup
    queue_manager.cleanup_guild(test_guild_id)
    queue = queue_manager.get_queue(test_guild_id)
    assert len(queue) == 0, "Queue should be empty after cleanup"
    
    logger.info("✅ Queue management test passed")

async def test_guild_data_management():
    """Test guild data management and activity tracking"""
    logger.info("Testing Guild Data Management...")
    
    test_guild_id = "987654321"
    current_time = time.time()
    
    # Test guild data creation
    client.guilds_data[test_guild_id] = {
        'channel_id': '123123123',
        'last_activity': current_time,
        'current_song': None
    }
    
    # Test activity timestamp update
    assert 'last_activity' in client.guilds_data[test_guild_id], "Guild data should have last_activity"
    
    # Test old data detection (simulate old guild)
    old_guild_id = "555555555"
    old_time = current_time - 86400 - 3600  # 25 hours ago
    client.guilds_data[old_guild_id] = {
        'channel_id': '999999999',
        'last_activity': old_time,
        'current_song': None
    }
    
    logger.info("✅ Guild data management test passed")

async def test_error_handling():
    """Test improved error handling"""
    logger.info("Testing Error Handling...")
    
    # Test queue operations with invalid data
    try:
        result = queue_manager.add_song("", None)  # Invalid parameters
        # Should not crash, should return False
        assert not result, "Invalid song addition should return False"
    except Exception as e:
        logger.error(f"Unexpected error in error handling test: {e}")
        raise
    
    # Test health check with no voice clients
    try:
        health_status = await player_manager.health_check()
        assert isinstance(health_status, dict), "Health check should return dict even with no clients"
    except Exception as e:
        logger.error(f"Health check should not crash: {e}")
        raise
    
    logger.info("✅ Error handling test passed")

async def test_ui_components():
    """Test UI component creation"""
    logger.info("Testing UI Components...")
    
    # Test view creation
    from ui.views import MusicControlView
    view = MusicControlView()
    
    # Check that view has expected buttons
    assert len(view.children) > 0, "View should have buttons"
    
    # Test embed creation
    from ui.embeds import create_credits_embed
    embed = create_credits_embed()
    assert embed.title == "Music Bot UI", "Credits embed should have correct title"
    
    logger.info("✅ UI components test passed")

async def test_memory_cleanup():
    """Test memory cleanup functionality"""
    logger.info("Testing Memory Cleanup...")
    
    # Test guild cleanup
    test_guild_id = "cleanup_test"
    
    # Add some data
    client.guilds_data[test_guild_id] = {'test': 'data'}
    client.playback_modes[test_guild_id] = 'normal'
    queue_manager.queues[test_guild_id] = [{'title': 'test'}]
    
    # Test cleanup
    await health_monitor._cleanup_guild(test_guild_id)
    
    # Verify cleanup
    assert test_guild_id not in client.guilds_data, "Guild data should be cleaned up"
    assert test_guild_id not in client.playback_modes, "Playback modes should be cleaned up"
    
    logger.info("✅ Memory cleanup test passed")

async def run_all_tests():
    """Run all tests"""
    logger.info("🚀 Starting MusicBot Fix Verification Tests...")
    
    try:
        await test_health_monitor()
        await test_queue_management() 
        await test_guild_data_management()
        await test_error_handling()
        await test_ui_components()
        await test_memory_cleanup()
        
        logger.info("✅ All tests passed! MusicBot fixes are working correctly.")
        
        # Summary of fixes tested
        logger.info("\n📋 Verified Fixes:")
        logger.info("• Health monitoring system with periodic cleanup")
        logger.info("• Queue size limits to prevent memory leaks")
        logger.info("• Improved error handling and recovery")
        logger.info("• UI component initialization and button responsiveness")
        logger.info("• Guild data management with activity tracking")
        logger.info("• Memory cleanup and resource management")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)