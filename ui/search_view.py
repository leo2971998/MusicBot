"""
Search results view for music bot.
Displays search results with interactive selection.
"""

import asyncio
import logging
import discord
from discord import ButtonStyle
from discord.ui import View, Button, Select
from typing import List, Dict, Optional, Callable

logger = logging.getLogger(__name__)

class SearchResultsView(View):
    """Interactive view for selecting from search results"""
    
    def __init__(self, search_results: List[Dict], timeout: float = 30.0):
        super().__init__(timeout=timeout)
        self.search_results = search_results
        self.selected_index = None
        self.selection_made = False
        
        # Create dropdown for search results
        options = []
        for i, result in enumerate(search_results[:5]):  # Limit to top 5 results
            title = result.get('title', 'Unknown Title')
            # Truncate title if too long for dropdown
            if len(title) > 90:
                title = title[:87] + "..."
            
            duration = result.get('duration', 0)
            duration_str = f"{duration//60}:{duration%60:02d}" if duration else "Unknown"
            
            options.append(discord.SelectOption(
                label=title,
                description=f"Duration: {duration_str} | {result.get('uploader', 'Unknown Artist')}",
                value=str(i)
            ))
        
        if options:
            self.add_item(SearchResultSelect(options, search_results))
    
    async def on_timeout(self):
        """Handle timeout - select first result"""
        if not self.selection_made:
            logger.info("Search selection timed out, using first result")
            self.selected_index = 0
            self.selection_made = True
            
            # Disable all items
            for item in self.children:
                item.disabled = True

class SearchResultSelect(Select):
    """Dropdown for selecting search results"""
    
    def __init__(self, options: List[discord.SelectOption], search_results: List[Dict]):
        super().__init__(
            placeholder="Choose a song to play...",
            options=options,
            min_values=1,
            max_values=1
        )
        self.search_results = search_results
    
    async def callback(self, interaction: discord.Interaction):
        """Handle search result selection"""
        try:
            selected_index = int(self.values[0])
            selected_result = self.search_results[selected_index]
            
            # Mark selection as made
            self.view.selected_index = selected_index
            self.view.selection_made = True
            
            # Process the selected song
            from commands.music_commands import process_play_request
            from bot_state import client, queue_manager, player_manager, data_manager
            
            # Use the selected result's URL for processing
            response_message = await process_play_request(
                interaction.user,
                interaction.guild,
                interaction.channel,
                selected_result.get('webpage_url', selected_result.get('url')),
                client,
                queue_manager,
                player_manager,
                data_manager
            )
            
            # Send response
            await interaction.response.send_message(
                f"🎵 Selected: **{selected_result.get('title', 'Unknown')}**\n{response_message}",
                ephemeral=True
            )
            
            # Disable the view
            for item in self.view.children:
                item.disabled = True
            
            # Update the original message to show selection was made
            try:
                await interaction.edit_original_response(view=self.view)
            except discord.NotFound:
                pass  # Message might have been deleted
                
        except Exception as e:
            logger.error(f"Error in search result selection: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while processing your selection.",
                ephemeral=True
            )

def create_search_results_embed(search_results: List[Dict], query: str) -> discord.Embed:
    """Create embed displaying search results"""
    embed = discord.Embed(
        title="🔍 Search Results",
        description=f"Search query: **{query}**\n\nSelect a song from the dropdown below:",
        color=0x3498db
    )
    
    # Add top 5 results to embed
    for i, result in enumerate(search_results[:5], 1):
        title = result.get('title', 'Unknown Title')
        uploader = result.get('uploader', 'Unknown Artist')
        duration = result.get('duration', 0)
        view_count = result.get('view_count', 0)
        
        # Format duration
        if duration:
            duration_str = f"{duration//60}:{duration%60:02d}"
        else:
            duration_str = "Unknown"
        
        # Format view count
        if view_count:
            if view_count >= 1000000:
                view_str = f"{view_count/1000000:.1f}M views"
            elif view_count >= 1000:
                view_str = f"{view_count/1000:.1f}K views"
            else:
                view_str = f"{view_count} views"
        else:
            view_str = "Unknown views"
        
        embed.add_field(
            name=f"{i}. {title}",
            value=f"👤 {uploader}\n⏱️ {duration_str}\n👀 {view_str}",
            inline=False
        )
    
    embed.set_footer(text="Select from dropdown or wait 30 seconds for auto-selection of first result")
    return embed