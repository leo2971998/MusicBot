#!/usr/bin/env python3
"""
Test script for dual song-adding search modes
Tests the _extract_song_data function with preview vs normal modes
"""
import asyncio
import logging
from unittest.mock import Mock, patch
from commands.music_commands import _extract_song_data

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


async def test_search_modes():
    """Test search functionality in both preview and normal modes"""
    print("Testing Search Modes:")
    print("=" * 50)
    
    # Test query
    test_query = "test song search"
    
    try:
        # Test preview mode (search_mode=True)
        print(f"Testing preview mode with query: '{test_query}'")
        preview_results = await _extract_song_data(test_query, search_mode=True)
        
        if preview_results:
            if isinstance(preview_results, list):
                print(f"✅ Preview mode returned {len(preview_results)} results")
                for i, result in enumerate(preview_results[:3]):  # Show first 3
                    title = result.get('title', 'Unknown')[:50]
                    views = result.get('view_count', 0)
                    print(f"  {i+1}. {title} ({views:,} views)")
            else:
                print(f"✅ Preview mode returned single result: {preview_results.get('title', 'Unknown')}")
        else:
            print("❌ Preview mode returned no results")
        
        # Test normal mode (search_mode=False)
        print(f"\nTesting normal mode with query: '{test_query}'")
        normal_result = await _extract_song_data(test_query, search_mode=False)
        
        if normal_result:
            title = normal_result.get('title', 'Unknown')[:50]
            views = normal_result.get('view_count', 0)
            uploader = normal_result.get('uploader', 'Unknown')
            print(f"✅ Normal mode auto-selected: {title}")
            print(f"   Uploader: {uploader}")
            print(f"   Views: {views:,}")
            print(f"   Has URL: {'url' in normal_result or 'webpage_url' in normal_result}")
        else:
            print("❌ Normal mode returned no result")
            
    except Exception as e:
        print(f"❌ Error during search testing: {e}")
        logger.exception("Search test error")


async def test_url_handling():
    """Test URL handling (should work the same in both modes)"""
    print("\nTesting URL Handling:")
    print("=" * 50)
    
    # Test with a mock YouTube URL
    test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    
    try:
        print(f"Testing URL: {test_url}")
        
        # Both modes should handle URLs the same way
        preview_result = await _extract_song_data(test_url, search_mode=True)
        normal_result = await _extract_song_data(test_url, search_mode=False)
        
        if preview_result and normal_result:
            print("✅ Both modes handle URLs correctly")
            print(f"   Preview result title: {preview_result.get('title', 'Unknown')[:50]}")
            print(f"   Normal result title: {normal_result.get('title', 'Unknown')[:50]}")
        else:
            print("❌ URL handling failed in one or both modes")
            print(f"   Preview result: {bool(preview_result)}")
            print(f"   Normal result: {bool(normal_result)}")
            
    except Exception as e:
        print(f"❌ Error during URL testing: {e}")
        logger.exception("URL test error")


def test_mock_modal_flow():
    """Test the modal flow with mocked interactions"""
    print("\nTesting Modal Flow (Mocked):")
    print("=" * 50)
    
    from ui.modals import AddSongModal
    
    # Test modal creation
    preview_modal = AddSongModal(preview_mode=True)
    normal_modal = AddSongModal(preview_mode=False)
    
    print(f"✅ Preview modal created with title: '{preview_modal.title}'")
    print(f"✅ Normal modal created with title: '{normal_modal.title}'")
    
    # Verify modal attributes
    assert preview_modal.preview_mode == True
    assert normal_modal.preview_mode == False
    assert preview_modal.play_next == False
    assert normal_modal.play_next == False
    
    print("✅ Modal attributes are correct")
    
    # Test play_next combinations
    play_next_preview = AddSongModal(play_next=True, preview_mode=True)
    play_next_normal = AddSongModal(play_next=True, preview_mode=False)
    
    print(f"✅ Play Next Preview modal: '{play_next_preview.title}'")
    print(f"✅ Play Next Normal modal: '{play_next_normal.title}'")


async def main():
    """Main test function"""
    print("Testing Dual Song-Adding Search Modes")
    print("=" * 70)
    
    # Test search functionality
    await test_search_modes()
    
    # Test URL handling
    await test_url_handling()
    
    # Test modal flow
    test_mock_modal_flow()
    
    print("\n" + "=" * 70)
    print("Search modes test completed!")
    print("\nExpected behavior:")
    print("- Preview mode: Returns multiple results for user selection")
    print("- Normal mode: Returns single best result (auto-selected)")
    print("- Both modes: Handle URLs identically")
    print("- Modals: Correctly configured with appropriate titles and modes")


if __name__ == "__main__":
    asyncio.run(main())