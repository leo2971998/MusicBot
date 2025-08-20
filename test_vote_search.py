#!/usr/bin/env python3
"""
Test script for Vote Skip and Music Search features.
"""

import asyncio
import sys
import os
import logging
from unittest.mock import Mock, MagicMock

# Add the bot directory to path so we can import modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class MockVoiceChannel:
    def __init__(self, members):
        self.members = members
        self.mention = "#test-voice"

class MockMember:
    def __init__(self, user_id, is_bot=False):
        self.id = user_id
        self.bot = is_bot

async def test_vote_skip_functionality():
    """Test vote skip system"""
    logger.info("Testing Vote Skip System...")
    
    from utils.vote_manager import VoteManager
    
    # Test vote threshold calculation
    # Case 1: 1-2 users
    voice_channel_1 = MockVoiceChannel([
        MockMember(1), MockMember(2)  # 2 human users
    ])
    assert VoteManager.get_required_votes(voice_channel_1) == 1, "1-2 users should need 1 vote"
    
    # Case 2: 3-4 users  
    voice_channel_2 = MockVoiceChannel([
        MockMember(1), MockMember(2), MockMember(3), MockMember(4)  # 4 human users
    ])
    assert VoteManager.get_required_votes(voice_channel_2) == 2, "3-4 users should need 2 votes"
    
    # Case 3: 5-6 users
    voice_channel_3 = MockVoiceChannel([
        MockMember(i) for i in range(1, 7)  # 6 human users
    ])
    assert VoteManager.get_required_votes(voice_channel_3) == 3, "5-6 users should need 3 votes"
    
    # Case 4: 7+ users (50% rule)
    voice_channel_4 = MockVoiceChannel([
        MockMember(i) for i in range(1, 11)  # 10 human users
    ])
    assert VoteManager.get_required_votes(voice_channel_4) == 5, "10 users should need 5 votes (50%)"
    
    # Case 5: Mix of bots and humans
    voice_channel_5 = MockVoiceChannel([
        MockMember(1), MockMember(2), MockMember(3),  # 3 humans
        MockMember(101, is_bot=True), MockMember(102, is_bot=True)  # 2 bots
    ])
    assert VoteManager.get_required_votes(voice_channel_5) == 2, "3 humans + bots should need 2 votes"
    
    # Test vote management
    guild_data = {}
    
    # Test adding votes
    assert VoteManager.add_vote(guild_data, 1) == True, "First vote should be added"
    assert VoteManager.add_vote(guild_data, 1) == False, "Duplicate vote should be rejected"
    assert VoteManager.add_vote(guild_data, 2) == True, "Different user vote should be added"
    
    # Test vote threshold checking
    assert VoteManager.check_vote_threshold(guild_data, voice_channel_2) == True, "2/2 votes should reach threshold"
    assert VoteManager.check_vote_threshold(guild_data, voice_channel_4) == False, "2/5 votes should not reach threshold"
    
    # Test vote status
    status = VoteManager.get_vote_status(guild_data, voice_channel_2)
    assert status['current_votes'] == 2, "Should have 2 current votes"
    assert status['required_votes'] == 2, "Should need 2 votes"
    assert status['percentage'] == 100, "Should be 100%"
    assert status['can_skip'] == True, "Should be able to skip"
    
    # Test vote reset
    VoteManager.reset_votes(guild_data, "test_song_id")
    assert len(guild_data['vote_skip']['votes']) == 0, "Votes should be reset"
    assert guild_data['vote_skip']['song_id'] == "test_song_id", "Song ID should be tracked"
    
    logger.info("✅ Vote skip system test passed")

async def test_search_functionality():
    """Test search results functionality"""
    logger.info("Testing Search Results System...")
    
    from ui.search_view import create_search_results_embed
    
    # Mock search results
    mock_results = [
        {
            'title': 'Test Song 1',
            'uploader': 'Test Artist 1',
            'duration': 180,  # 3 minutes
            'view_count': 1500000,
            'webpage_url': 'https://youtube.com/watch?v=test1'
        },
        {
            'title': 'Test Song 2',
            'uploader': 'Test Artist 2', 
            'duration': 240,  # 4 minutes
            'view_count': 850000,
            'webpage_url': 'https://youtube.com/watch?v=test2'
        }
    ]
    
    # Test embed creation
    embed = create_search_results_embed(mock_results, "test query")
    assert embed.title == "🔍 Search Results", "Embed should have correct title"
    assert "test query" in embed.description, "Embed should contain search query"
    assert len(embed.fields) == 2, "Embed should have 2 result fields"
    
    # Test field content
    first_field = embed.fields[0]
    assert "Test Song 1" in first_field.name, "First field should contain song title"
    assert "Test Artist 1" in first_field.value, "First field should contain artist"
    assert "3:00" in first_field.value, "First field should contain formatted duration"
    assert "1.5M views" in first_field.value, "First field should contain formatted view count"
    
    logger.info("✅ Search results system test passed")

async def test_edge_cases():
    """Test edge cases and error handling"""
    logger.info("Testing Edge Cases...")
    
    from utils.vote_manager import VoteManager
    
    # Test with empty voice channel
    empty_channel = MockVoiceChannel([])
    assert VoteManager.get_required_votes(empty_channel) == 1, "Empty channel should default to 1 vote"
    
    # Test with None voice channel
    assert VoteManager.get_required_votes(None) == 1, "None channel should default to 1 vote"
    
    # Test vote management with empty guild data
    empty_guild_data = {}
    status = VoteManager.get_vote_status(empty_guild_data, empty_channel)
    assert status['current_votes'] == 0, "Empty guild data should have 0 votes"
    
    # Test removing non-existent vote
    assert VoteManager.remove_user_vote(empty_guild_data, 999) == False, "Removing non-existent vote should return False"
    
    # Test with very large voice channel
    large_channel = MockVoiceChannel([MockMember(i) for i in range(1, 101)])  # 100 users
    required = VoteManager.get_required_votes(large_channel)
    assert required == 50, "100 users should need 50 votes (50%)"
    
    logger.info("✅ Edge cases test passed")

async def test_integration():
    """Test integration between components"""
    logger.info("Testing Integration...")
    
    from utils.vote_manager import VoteManager
    
    # Simulate realistic scenario
    voice_channel = MockVoiceChannel([
        MockMember(1), MockMember(2), MockMember(3), MockMember(4), MockMember(5)  # 5 users
    ])
    
    guild_data = {}
    required_votes = VoteManager.get_required_votes(voice_channel)  # Should be 3
    
    # Add votes one by one
    for user_id in [1, 2]:
        VoteManager.add_vote(guild_data, user_id)
        status = VoteManager.get_vote_status(guild_data, voice_channel)
        assert not status['can_skip'], f"Should not be able to skip with {status['current_votes']} votes"
    
    # Add final vote
    VoteManager.add_vote(guild_data, 3)
    status = VoteManager.get_vote_status(guild_data, voice_channel)
    assert status['can_skip'], "Should be able to skip with 3/3 votes"
    
    # Test user leaving channel (remove vote)
    new_channel = MockVoiceChannel([MockMember(1), MockMember(2)])  # User 3 left
    VoteManager.remove_user_vote(guild_data, 3)
    status = VoteManager.get_vote_status(guild_data, new_channel)
    # Now need 1 vote for 2 users, have 2 votes, so can still skip
    assert status['can_skip'], "Should still be able to skip after user leaves"
    
    logger.info("✅ Integration test passed")

async def run_all_tests():
    """Run all vote skip and search tests"""
    logger.info("🚀 Starting Vote Skip and Music Search Tests...")
    
    try:
        await test_vote_skip_functionality()
        await test_search_functionality()
        await test_edge_cases()
        await test_integration()
        
        logger.info("✅ All tests passed! Vote Skip and Music Search features are working correctly.")
        
        # Summary of features tested
        logger.info("\n📋 Tested Features:")
        logger.info("• Vote threshold calculation based on voice channel size")
        logger.info("• Vote management (add, remove, reset, duplicate prevention)")
        logger.info("• Threshold checking and percentage calculation")
        logger.info("• Search results display and formatting")
        logger.info("• Edge case handling (empty channels, large channels)")
        logger.info("• Integration scenarios (users joining/leaving)")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)