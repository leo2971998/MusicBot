import asyncio
import logging
import discord
from discord.ui import Modal, TextInput
from typing import List, Dict
import re

logger = logging.getLogger(__name__)

def _is_url(text: str) -> bool:
    """Check if the input text is a URL"""
    url_patterns = [
        r'https?://',
        r'www\.',
        r'youtube\.com',
        r'youtu\.be',
        r'spotify\.com',
        r'soundcloud\.com'
    ]
    text_lower = text.lower().strip()
    return any(re.search(pattern, text_lower) for pattern in url_patterns)

class ModalSearchResultsView(discord.ui.View):
    """Search results view specifically for modal integration with play_next support"""
    
    def __init__(self, search_results: List[Dict], play_next: bool = False, timeout: float = 30.0):
        super().__init__(timeout=timeout)
        self.search_results = search_results
        self.play_next = play_next
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
            self.add_item(ModalSearchResultSelect(options, search_results, play_next))
    
    async def on_timeout(self):
        """Handle timeout - select first result"""
        if not self.selection_made:
            logger.info("Modal search selection timed out, using first result")
            self.selected_index = 0
            self.selection_made = True
            
            # Disable all items
            for item in self.children:
                item.disabled = True
            
            # Clean up channel messages after timeout
            # Note: This is a fallback cleanup in case user doesn't make a selection
            try:
                # We can't access interaction here, but we can try to clean up if we have a stored guild_id
                # For now, we'll rely on the main cleanup in the callback method
                pass
            except Exception as e:
                logger.error(f"Error during timeout cleanup: {e}")

class ModalSearchResultSelect(discord.ui.Select):
    """Dropdown for selecting search results in modal context"""
    
    def __init__(self, options: List[discord.SelectOption], search_results: List[Dict], play_next: bool):
        super().__init__(
            placeholder="Choose a song to add...",
            options=options,
            min_values=1,
            max_values=1
        )
        self.search_results = search_results
        self.play_next = play_next
    
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
            
            # Use the selected result's URL for processing with play_next parameter
            response_message = await process_play_request(
                interaction.user,
                interaction.guild,
                interaction.channel,
                selected_result.get('webpage_url', selected_result.get('url')),
                client,
                queue_manager,
                player_manager,
                data_manager,
                play_next=self.play_next
            )
            
            # Send response
            action_text = "Play Next" if self.play_next else "Add Song"
            await interaction.response.send_message(
                f"🎵 {action_text} - Selected: **{selected_result.get('title', 'Unknown')}**\n{response_message}",
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
            
            # Clean up channel messages after successful selection
            guild_id = str(interaction.guild.id)
            from bot_state import client
            guild_data = client.guilds_data.get(guild_id)
            if guild_data:
                from utils.message_utils import clear_channel_messages
                channel_id = guild_data.get('channel_id')
                stable_message_id = guild_data.get('stable_message_id')
                if channel_id and stable_message_id:
                    channel = client.get_channel(int(channel_id))
                    if channel:
                        # Small delay to ensure message update completes, then cleanup
                        await asyncio.sleep(1)
                        await clear_channel_messages(channel, int(stable_message_id))
                
        except Exception as e:
            logger.error(f"Error in modal search result selection: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while processing your selection.",
                ephemeral=True
            )

class AddSongModal(Modal):
    def __init__(self, play_next: bool = False, preview_mode: bool = True):
        if play_next:
            title = "Play Next"
        else:
            title = "Add Song (Preview)" if preview_mode else "Add Song (Normal)"
        super().__init__(title=title)
        self.play_next = play_next
        self.preview_mode = preview_mode

        self.song_input = TextInput(
            label="Song Name or URL",
            placeholder="Enter song name/keywords for search or paste a URL",
            required=True,
            max_length=500
        )
        self.add_item(self.song_input)

    async def on_submit(self, interaction: discord.Interaction):
        logger.debug(f"AddSongModal submitted in guild {interaction.guild_id}")
        await interaction.response.defer(thinking=True)

        song_name_or_url = self.song_input.value.strip()

        # Import here to avoid circular imports
        from commands.music_commands import process_play_request, _extract_song_data
        from bot_state import client, queue_manager, player_manager, data_manager

        try:
            # Check if input is a URL or search query
            if _is_url(song_name_or_url):
                # Handle as URL - existing behavior
                response_message = await process_play_request(
                    interaction.user,
                    interaction.guild,
                    interaction.channel,
                    song_name_or_url,
                    client,
                    queue_manager,
                    player_manager,
                    data_manager,
                    play_next=self.play_next
                )

                if response_message:
                    await interaction.followup.send(response_message, ephemeral=True)
            else:
                # Handle as search query
                if self.preview_mode:
                    # Preview mode - show search results for user selection
                    search_results = await _extract_song_data(song_name_or_url, search_mode=True)
                    
                    if not search_results or len(search_results) == 0:
                        await interaction.followup.send("❌ No search results found.", ephemeral=True)
                        return

                    # Create search results view and embed
                    from ui.search_view import create_search_results_embed
                    
                    view = ModalSearchResultsView(search_results, self.play_next)
                    embed = create_search_results_embed(search_results, song_name_or_url)
                    
                    # Update embed title to reflect the action
                    action_text = "Play Next" if self.play_next else "Add Song (Preview)"
                    embed.title = f"🔍 Search Results - {action_text}"
                    
                    # Send search results as persistent message
                    await interaction.followup.send(embed=embed, view=view, ephemeral=False)
                else:
                    # Normal mode - auto-select best result
                    best_result = await _extract_song_data(song_name_or_url, search_mode=False)
                    
                    if not best_result:
                        await interaction.followup.send("❌ No search results found.", ephemeral=True)
                        return
                    
                    # Process the best result directly
                    response_message = await process_play_request(
                        interaction.user,
                        interaction.guild,
                        interaction.channel,
                        best_result.get('webpage_url', best_result.get('url')),
                        client,
                        queue_manager,
                        player_manager,
                        data_manager,
                        play_next=self.play_next
                    )
                    
                    action_text = "Play Next" if self.play_next else "Add Song (Normal)"
                    await interaction.followup.send(
                        f"🎵 {action_text} - Auto-selected: **{best_result.get('title', 'Unknown')}**\n{response_message}",
                        ephemeral=True
                    )

        except Exception as e:
            logger.error(f"Error in AddSongModal: {e}")
            await interaction.followup.send("❌ An error occurred while adding the song.", ephemeral=True)

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        logger.error(f"Modal error: {error}")
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ An error occurred while processing your request.",
                    ephemeral=True
                )
        except Exception:
            pass

class RemoveSongModal(Modal):
    def __init__(self):
        super().__init__(title="Remove Song")

        self.song_index = TextInput(
            label="Song Index",
            placeholder="Enter the number of the song to remove",
            required=True,
            max_length=10
        )
        self.add_item(self.song_index)

    async def on_submit(self, interaction: discord.Interaction):
        logger.debug(f"RemoveSongModal submitted in guild {interaction.guild_id}")
        try:
            index = int(self.song_index.value.strip())
            guild_id = str(interaction.guild.id)

            from bot_state import queue_manager
            from ui.embeds import update_stable_message

            removed_song = queue_manager.remove_song(guild_id, index)

            if removed_song:
                await interaction.response.send_message(
                    f'❌ Removed **{removed_song["title"]}** from the queue.',
                    ephemeral=True
                )
                await update_stable_message(guild_id)
            else:
                await interaction.response.send_message(
                    '❌ Invalid song index or queue is empty.',
                    ephemeral=True
                )

        except ValueError:
            await interaction.response.send_message(
                '❌ Please enter a valid number.',
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error in RemoveSongModal: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while removing the song.",
                ephemeral=True
            )

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        logger.error(f"Remove modal error: {error}")
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ An error occurred while processing your request.",
                    ephemeral=True
                )
        except Exception:
            pass