#!/usr/bin/env python3
"""
Visual demonstration of the Vote Skip and Music Search features
"""

import asyncio
from ui.views import MusicControlView
from ui.embeds import create_credits_embed, create_now_playing_embed, create_queue_embed
from ui.search_view import create_search_results_embed, SearchResultsView
from utils.vote_manager import VoteManager
import discord

class MockVoiceChannel:
    def __init__(self, members):
        self.members = members
        self.mention = "#test-voice"

class MockMember:
    def __init__(self, user_id, is_bot=False):
        self.id = user_id
        self.bot = is_bot

async def demo_vote_skip_ui():
    """Demonstrate the vote skip feature"""
    print("\n" + "="*60)
    print("🗳️  VOTE SKIP FEATURE DEMONSTRATION")
    print("="*60)
    
    # Simulate voice channel with 5 users
    voice_channel = MockVoiceChannel([
        MockMember(1), MockMember(2), MockMember(3), MockMember(4), MockMember(5)
    ])
    
    # Simulate guild data with current song
    guild_data = {
        'current_song': {
            'title': 'Never Gonna Give You Up',
            'requester': '@TestUser1',
            'webpage_url': 'https://youtube.com/watch?v=dQw4w9WgXcQ',
            'thumbnail': 'https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg',
            'source': 'youtube'
        },
        'song_duration': 213
    }
    
    required_votes = VoteManager.get_required_votes(voice_channel)
    print(f"👥 Voice Channel: 5 users")
    print(f"🎯 Required votes to skip: {required_votes}")
    print()
    
    # Demonstrate vote progression
    scenarios = [
        ([], "No votes yet"),
        ([1], "User 1 votes to skip"),
        ([1, 2], "User 2 also votes to skip"),
        ([1, 2, 3], "User 3 votes - threshold reached!")
    ]
    
    for votes, description in scenarios:
        # Reset votes and add current votes
        VoteManager.reset_votes(guild_data)
        for user_id in votes:
            VoteManager.add_vote(guild_data, user_id)
        
        status = VoteManager.get_vote_status(guild_data, voice_channel)
        progress_bar = "▓" * status['current_votes'] + "░" * (status['required_votes'] - status['current_votes'])
        
        print(f"📊 {description}")
        print(f"   Votes: {status['current_votes']}/{status['required_votes']} ({status['percentage']}%)")
        print(f"   Progress: `{progress_bar}`")
        if status['can_skip']:
            print("   ✅ Can skip song!")
        else:
            print("   ❌ More votes needed")
        print()

async def demo_search_results_ui():
    """Demonstrate the search results feature"""
    print("\n" + "="*60)
    print("🔍  MUSIC SEARCH WITH PREVIEW DEMONSTRATION")
    print("="*60)
    
    # Mock search results
    search_results = [
        {
            'title': 'Never Gonna Give You Up',
            'uploader': 'Rick Astley',
            'duration': 213,
            'view_count': 1500000000,
            'webpage_url': 'https://youtube.com/watch?v=dQw4w9WgXcQ'
        },
        {
            'title': 'Never Gonna Give You Up (Remastered)',
            'uploader': 'Official Rick Astley',
            'duration': 215,
            'view_count': 50000000,
            'webpage_url': 'https://youtube.com/watch?v=example1'
        },
        {
            'title': 'Rick Astley - Never Gonna Give You Up (Live)',
            'uploader': 'Rick Astley Live',
            'duration': 240,
            'view_count': 25000000,
            'webpage_url': 'https://youtube.com/watch?v=example2'
        }
    ]
    
    print("Search Query: 'Never Gonna Give You Up'")
    print("Results found: 3")
    print()
    
    for i, result in enumerate(search_results, 1):
        duration_str = f"{result['duration']//60}:{result['duration']%60:02d}"
        
        if result['view_count'] >= 1000000000:
            view_str = f"{result['view_count']/1000000000:.1f}B views"
        elif result['view_count'] >= 1000000:
            view_str = f"{result['view_count']/1000000:.1f}M views"
        else:
            view_str = f"{result['view_count']/1000:.1f}K views"
        
        print(f"{i}. 🎵 {result['title']}")
        print(f"   👤 {result['uploader']}")
        print(f"   ⏱️  {duration_str}")
        print(f"   👀 {view_str}")
        print()
    
    print("💡 Users can select from dropdown or wait 30 seconds for auto-selection")

async def demo_ui_integration():
    """Show how the new features integrate with existing UI"""
    print("\n" + "="*60)
    print("🎛️  UI INTEGRATION DEMONSTRATION")
    print("="*60)
    
    # Show button changes
    view = MusicControlView()
    
    print("Updated Control Buttons:")
    for item in view.children:
        if hasattr(item, 'label'):
            if 'Vote Skip' in item.label:
                print(f"• {item.label} - Smart voting system (was '⏭️ Skip')")
            else:
                print(f"• {item.label} - {item.style.name} button")
    
    print()
    print("New Slash Commands:")
    print("• /search <query> - Search with preview and selection")
    print("• /play <query> - Direct play (existing, now supports better search)")
    print("• /playnext <query> - Play next in queue")
    
    print()
    print("Vote Status Display:")
    print("• Real-time vote progress in Now Playing embed")
    print("• Visual progress bar with percentage")
    print("• Automatic threshold calculation based on voice channel size")

async def demo_vote_scenarios():
    """Demonstrate different voting scenarios"""
    print("\n" + "="*60)
    print("📊  VOTE THRESHOLD SCENARIOS")
    print("="*60)
    
    scenarios = [
        (2, "Small group (1-2 users)"),
        (4, "Medium group (3-4 users)"),
        (6, "Large group (5-6 users)"),
        (10, "Very large group (7+ users - 50% rule)")
    ]
    
    for user_count, description in scenarios:
        members = [MockMember(i) for i in range(1, user_count + 1)]
        channel = MockVoiceChannel(members)
        required = VoteManager.get_required_votes(channel)
        percentage = (required / user_count) * 100
        
        print(f"👥 {description}")
        print(f"   Users in channel: {user_count}")
        print(f"   Votes needed: {required} ({percentage:.0f}%)")
        print()

async def create_demo():
    """Create a complete demonstration"""
    print("🎶 MusicBot Vote Skip & Search Feature Demo")
    print("=" * 60)
    
    await demo_vote_skip_ui()
    await demo_search_results_ui()
    await demo_ui_integration()
    await demo_vote_scenarios()
    
    print("\n" + "="*60)
    print("✅ FEATURE SUMMARY")
    print("="*60)
    print("Vote Skip Features:")
    print("• Smart threshold calculation based on voice channel size")
    print("• Real-time vote progress display with visual progress bar")
    print("• Duplicate vote prevention")
    print("• Automatic vote reset when new song starts")
    print("• Voice channel validation (users must be in same channel)")
    print()
    print("Search with Preview Features:")
    print("• Top 5 search results with metadata (title, artist, duration, views)")
    print("• Interactive dropdown selection")
    print("• 30-second timeout with auto-selection of first result")
    print("• Seamless integration with existing play functionality")
    print("• Rich embeds with formatted information")
    print()
    print("Technical Implementation:")
    print("• Minimal changes to existing codebase")
    print("• Thread-safe vote management using guild data structure")
    print("• Backward compatibility maintained")
    print("• Comprehensive error handling and edge case management")

if __name__ == "__main__":
    asyncio.run(create_demo())