#!/usr/bin/env python3
"""
Test script for dual song-adding functionality
"""
import asyncio
import discord
from discord.ui import Button
from ui.modals import AddSongModal  
from ui.views import MusicControlView


async def test_modal_functionality():
    """Test modal titles and parameters"""
    print("Testing Modal Functionality:")
    print("=" * 50)
    
    # Test different modal modes
    preview_modal = AddSongModal(preview_mode=True)
    normal_modal = AddSongModal(preview_mode=False)
    play_next_modal = AddSongModal(play_next=True)
    play_next_preview_modal = AddSongModal(play_next=True, preview_mode=True)
    
    print(f"Preview mode: '{preview_modal.title}'")
    print(f"Normal mode: '{normal_modal.title}'")
    print(f"Play next mode: '{play_next_modal.title}'") 
    print(f"Play next preview mode: '{play_next_preview_modal.title}'")
    
    # Check modal attributes
    print(f"\nModal attributes:")
    print(f"Preview modal - preview_mode: {preview_modal.preview_mode}, play_next: {preview_modal.play_next}")
    print(f"Normal modal - preview_mode: {normal_modal.preview_mode}, play_next: {normal_modal.play_next}")
    print(f"Play next modal - preview_mode: {play_next_modal.preview_mode}, play_next: {play_next_modal.play_next}")


def test_button_layout():
    """Test button layout in MusicControlView"""
    print("\nTesting Button Layout:")
    print("=" * 50)
    
    view = MusicControlView()
    
    add_song_buttons = []
    for i, child in enumerate(view.children):
        if hasattr(child, 'label') and 'Add Song' in child.label:
            add_song_buttons.append((i+1, child.label, child.style))
    
    print(f"Total buttons: {len(view.children)}")
    print(f"Add Song buttons found: {len(add_song_buttons)}")
    
    for pos, label, style in add_song_buttons:
        print(f"  {pos}. '{label}' - Style: {style}")
    
    # Check if we have both preview and normal buttons
    labels = [label for _, label, _ in add_song_buttons]
    has_preview = any('Preview' in label for label in labels)
    has_normal = any('Normal' in label for label in labels)
    
    print(f"\nButton validation:")
    print(f"Has Preview button: {has_preview}")
    print(f"Has Normal button: {has_normal}")
    print(f"Expected dual functionality: {has_preview and has_normal}")


async def main():
    """Main test function"""
    print("Testing Dual Song-Adding Functionality")
    print("=" * 70)
    
    await test_modal_functionality()
    test_button_layout()
    
    print("\n" + "=" * 70)
    print("Test completed!")


if __name__ == "__main__":
    asyncio.run(main())