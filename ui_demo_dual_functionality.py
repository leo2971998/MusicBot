#!/usr/bin/env python3
"""
Demo script to visualize the dual song-adding functionality UI
Shows how the buttons are arranged and what each mode does
"""
from ui.views import MusicControlView
from ui.modals import AddSongModal
from discord import ButtonStyle


def visualize_button_layout():
    """Visualize the button layout in a text-based format"""
    print("MusicBot Control Panel - Button Layout")
    print("=" * 60)
    
    # Manually define the button layout based on our implementation
    buttons = [
        ("⏸️ Pause", "🔵"),
        ("▶️ Resume", "🔵"),
        ("🗳️ Vote Skip", "🔵"),
        ("⏹️ Stop", "🔵"),
        ("🗑️ Clear Queue", "🔴"),
        ("🔁 Normal", "⚪"),
        ("🔂 Repeat", "⚪"),
        ("🔀 Shuffle", "🔵"),
        ("🔍 Add Song (Preview)", "🟢"),
        ("🎵 Add Song (Normal)", "🟢"),
        ("➕ Play Next", "🟢"),
        ("❌ Remove", "🔴"),
    ]
    
    # Group buttons by rows (Discord UI typically shows 5 buttons per row)
    buttons_per_row = 5
    
    # Display buttons in rows
    for i in range(0, len(buttons), buttons_per_row):
        row_buttons = buttons[i:i+buttons_per_row]
        
        # Print button labels
        labels = [f"{btn[1]} {btn[0]}" for btn in row_buttons]
        print(" | ".join(f"{label:^20}" for label in labels))
        
        if i + buttons_per_row < len(buttons):
            print("-" * 60)
    
    print("=" * 60)


def explain_dual_functionality():
    """Explain the difference between the two add song modes"""
    print("\nDual Song-Adding Functionality Explanation")
    print("=" * 60)
    
    print("🔍 Add Song (Preview) Mode:")
    print("  • Shows multiple search results (up to 5)")
    print("  • User can browse and choose specific version")
    print("  • Perfect for finding covers, live versions, remixes")
    print("  • Displays metadata: duration, artist, view count")
    print("  • Interactive dropdown selection")
    print("  • Auto-selects first result if user doesn't choose")
    
    print("\n🎵 Add Song (Normal) Mode:")
    print("  • Auto-selects most viewed result instantly")
    print("  • No preview interface - direct add")
    print("  • Fast one-click experience")
    print("  • Usually gets official/popular version")
    print("  • Optimized for speed and convenience")
    print("  • Shows what was auto-selected in confirmation")
    
    print("\n➕ Play Next Mode:")
    print("  • Works with both Preview and Normal modes")
    print("  • Adds songs to front of queue (play next)")
    print("  • Same search behavior as regular add")
    print("  • Uses current preview_mode default (True)")


def show_modal_variations():
    """Show the different modal titles and configurations"""
    print("\nModal Variations")
    print("=" * 60)
    
    # Show modal configurations without instantiating them
    modal_configs = [
        ("Add Song (Preview)", "preview_mode=True, play_next=False", "Add Song (Preview)"),
        ("Add Song (Normal)", "preview_mode=False, play_next=False", "Add Song (Normal)"),
        ("Play Next (Preview)", "play_next=True, preview_mode=True", "Play Next"),
        ("Play Next (Normal)", "play_next=True, preview_mode=False", "Play Next"),
    ]
    
    for description, config, title in modal_configs:
        print(f"{description:20} | Title: '{title}'")
        print(f"{'':20} | Config: {config}")
        print("-" * 60)


def show_user_workflow():
    """Show the expected user workflow for each mode"""
    print("\nUser Workflow Examples")
    print("=" * 60)
    
    print("🔍 PREVIEW MODE WORKFLOW:")
    print("1. User clicks '🔍 Add Song (Preview)' button")
    print("2. Modal opens with 'Add Song (Preview)' title")
    print("3. User types: 'bohemian rhapsody'")
    print("4. System shows 5 search results:")
    print("   • Queen - Bohemian Rhapsody (Official)")
    print("   • Queen - Bohemian Rhapsody (Live Aid)")
    print("   • Pentatonix - Bohemian Rhapsody (Cover)")
    print("   • Queen - Bohemian Rhapsody (Remastered)")
    print("   • Bohemian Rhapsody (Karaoke Version)")
    print("5. User selects 'Live Aid' version")
    print("6. Song is added to queue")
    
    print("\n🎵 NORMAL MODE WORKFLOW:")
    print("1. User clicks '🎵 Add Song (Normal)' button")
    print("2. Modal opens with 'Add Song (Normal)' title")
    print("3. User types: 'bohemian rhapsody'")
    print("4. System auto-selects most viewed result")
    print("5. Immediately adds: 'Queen - Bohemian Rhapsody (Official)'")
    print("6. Confirmation: 'Auto-selected: Queen - Bohemian Rhapsody'")
    print("7. Song is added to queue")
    
    print("\nTime Comparison:")
    print("Preview Mode: 5-10 seconds (browsing + selection)")
    print("Normal Mode:  1-2 seconds (instant auto-selection)")


def main():
    """Main demo function"""
    print("🎵 MusicBot Dual Song-Adding Functionality Demo")
    print("=" * 70)
    
    visualize_button_layout()
    explain_dual_functionality()
    show_modal_variations()
    show_user_workflow()
    
    print("\n" + "=" * 70)
    print("✅ Implementation provides clear user choice:")
    print("   🔍 Preview = Browsing multiple options (discovery)")
    print("   🎵 Normal = Fast auto-selection (speed)")
    print("=" * 70)


if __name__ == "__main__":
    main()