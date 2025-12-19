import asyncio
import logging
import discord
from discord import ButtonStyle, Embed
from discord.ui import View, Button, Select
from config import PlaybackMode
logger = logging.getLogger(__name__)

class PlaybackModeSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label='Normal', emoji='🔁', value='normal', description='Play through queue once'),
            discord.SelectOption(label='Repeat Song', emoji='🔂', value='repeat_one', description='Repeat current song'),
            discord.SelectOption(label='Repeat Queue', emoji='🔄', value='repeat_all', description='Loop entire queue'),
        ]
        super().__init__(placeholder='🎵 Playback Mode', options=options, row=3)

    async def callback(self, interaction: discord.Interaction):
        from bot_state import client, queue_manager
        from ui.embeds import update_stable_message
        
        guild_id = str(interaction.guild.id)
        mode_map = {
            'normal': PlaybackMode.NORMAL,
            'repeat_one': PlaybackMode.REPEAT_ONE,
            'repeat_all': PlaybackMode.REPEAT_ALL,
        }
        
        selected_mode = self.values[0]
        client.playback_modes[guild_id] = mode_map[selected_mode]
        
        # Save playlist snapshot when switching to repeat all mode
        if selected_mode == 'repeat_all':
            current_song = client.guilds_data[guild_id].get('current_song')
            # Save current queue + current song for looping
            if current_song or queue_manager.get_queue_length(guild_id) > 0:
                # Create a snapshot of the complete playlist (current song + queue)
                playlist = []
                if current_song:
                    playlist.append(current_song)
                playlist.extend(queue_manager.get_queue(guild_id))
                queue_manager.repeat_all_playlists[guild_id] = playlist
                logger.info(f"Saved {len(playlist)} songs for repeat all mode in guild {guild_id}")
        
        mode_labels = {
            'normal': 'Normal',
            'repeat_one': 'Repeat Song',
            'repeat_all': 'Repeat Queue',
        }
        
        await interaction.response.send_message(
            f'🎵 Playback mode: **{mode_labels[self.values[0]]}**', 
            ephemeral=True
        )
        logger.debug(f"Set playback mode to {self.values[0]} in guild {guild_id}")
        await update_stable_message(guild_id)

class QueuePaginationView(View):
    """Pagination view for browsing large queues"""
    def __init__(self, guild_id: str, current_page: int = 1):
        super().__init__(timeout=60)
        self.guild_id = guild_id
        self.current_page = current_page

    @discord.ui.button(label='◀️ Prev', style=ButtonStyle.secondary)
    async def prev_page(self, interaction: discord.Interaction, button: Button):
        """Go to previous page"""
        try:
            from bot_state import queue_manager
            
            self.current_page = max(1, self.current_page - 1)
            
            # Get queue page to check if we have content
            songs, total_pages, _ = queue_manager.get_queue_page(self.guild_id, self.current_page)
            
            if not songs and total_pages == 0:
                await interaction.response.send_message('❌ Queue is empty', ephemeral=True)
                return
            
            # Create paginated embed
            embed = self._create_queue_embed_paginated(self.current_page)
            
            # Update buttons state
            self._update_button_states(total_pages)
            
            await interaction.response.edit_message(embed=embed, view=self)
            logger.debug(f"Queue pagination: moved to page {self.current_page} in guild {self.guild_id}")
        except Exception as e:
            logger.error(f"Error in prev_page: {e}")
            await interaction.response.send_message('❌ Error navigating queue', ephemeral=True)

    @discord.ui.button(label='Next ▶️', style=ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: Button):
        """Go to next page"""
        try:
            from bot_state import queue_manager
            
            _, total_pages, _ = queue_manager.get_queue_page(self.guild_id, self.current_page)
            
            if total_pages == 0:
                await interaction.response.send_message('❌ Queue is empty', ephemeral=True)
                return
            
            self.current_page = min(total_pages, self.current_page + 1)
            
            # Create paginated embed
            embed = self._create_queue_embed_paginated(self.current_page)
            
            # Update buttons state
            self._update_button_states(total_pages)
            
            await interaction.response.edit_message(embed=embed, view=self)
            logger.debug(f"Queue pagination: moved to page {self.current_page} in guild {self.guild_id}")
        except Exception as e:
            logger.error(f"Error in next_page: {e}")
            await interaction.response.send_message('❌ Error navigating queue', ephemeral=True)

    def _update_button_states(self, total_pages: int):
        """Update button enabled/disabled states based on current page"""
        for item in self.children:
            if isinstance(item, Button):
                if item.label == '◀️ Prev':
                    item.disabled = (self.current_page <= 1)
                elif item.label == 'Next ▶️':
                    item.disabled = (self.current_page >= total_pages)

    def _create_queue_embed_paginated(self, page: int = 1) -> Embed:
        """Create paginated queue embed"""
        try:
            from bot_state import queue_manager
            
            songs, total_pages, current_page = queue_manager.get_queue_page(self.guild_id, page, per_page=10)
            
            def get_source_icon(song):
                return "🎧" if song.get('source') == 'spotify' else "📺"
            
            if songs:
                # Calculate starting position for this page
                start_pos = (current_page - 1) * 10
                
                queue_description = '\n'.join(
                    f"{start_pos + idx + 1}. {get_source_icon(song)} **[{song['title']}]({song.get('spotify_url', song.get('webpage_url'))})** — *{song.get('requester', 'Unknown')}*"
                    for idx, song in enumerate(songs)
                )
            else:
                queue_description = 'No songs in the queue.'
            
            embed = Embed(
                title=f'📜 Queue (Page {current_page}/{total_pages if total_pages > 0 else 1})',
                description=queue_description,
                color=0x1db954
            )
            
            total_songs = queue_manager.get_queue_length(self.guild_id)
            embed.set_footer(text=f"Total songs in queue: {total_songs} | Page {current_page} of {total_pages if total_pages > 0 else 1}")
            
            return embed
        except Exception as e:
            logger.error(f"Error creating paginated queue embed: {e}")
            return Embed(
                title='📜 Queue',
                description='Error loading queue.',
                color=0xff0000
            )

class MusicControlView(View):
    """Improved music control view with better error handling"""

    def __init__(self, timeout: float = None):
        super().__init__(timeout=timeout)
        self.add_item(PlaybackModeSelect())

    async def on_timeout(self):
        """Handle view timeout"""
        logger.info("Music control view timed out")
        for item in self.children:
            item.disabled = True

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item):
        """Handle interaction errors with detailed logging and recovery"""
        logger.exception(
            "Interaction error in guild %s for button '%s'",
            interaction.guild_id,
            item.label,
        )
        logger.error(f"Interaction user: {interaction.user} ({interaction.user.id})")
        logger.error(f"Interaction channel: {interaction.channel} ({interaction.channel.id if interaction.channel else 'None'})")
        logger.error(f"Interaction guild: {interaction.guild} ({interaction.guild.id if interaction.guild else 'None'})")
        logger.error(f"Is response done: {interaction.response.is_done()}")

        # Attempt to recover from interaction error
        error_message = f"❌ An error occurred while processing your request: {str(error)}"
        
        # Add helpful troubleshooting info for common errors
        if "Guild data not found" in str(error):
            error_message += "\n\n💡 Try running `/setup` to reinitialize the music bot in this channel."
        elif "voice channel" in str(error).lower():
            error_message += "\n\n💡 Make sure you're connected to a voice channel and the bot has permission to join."
        elif "permission" in str(error).lower():
            error_message += "\n\n💡 The bot may be missing required permissions. Please check Discord permissions."

        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(error_message, ephemeral=True)
            else:
                await interaction.followup.send(error_message, ephemeral=True)
        except Exception as followup_error:
            logger.exception("Failed to send error message")
            
        # Attempt to update the stable message to refresh the UI
        try:
            from ui.embeds import update_stable_message
            if interaction.guild:
                guild_id = str(interaction.guild.id)
                await update_stable_message(guild_id)
                logger.debug(f"Refreshed stable message after error in guild {guild_id}")
        except Exception as refresh_error:
            logger.warning(f"Could not refresh stable message after error: {refresh_error}")

    async def _safe_interaction_response(self, interaction: discord.Interaction,
                                         message: str, ephemeral: bool = False):
        """Safely send interaction response with enhanced logging"""
        try:
            logger.debug(f"Attempting to send interaction response: {message[:50]}...")
            logger.debug(f"Response already done: {interaction.response.is_done()}")
            
            if not interaction.response.is_done():
                await interaction.response.send_message(message, ephemeral=ephemeral)
                logger.debug("Successfully sent interaction response")
            else:
                await interaction.followup.send(message, ephemeral=ephemeral)
                logger.debug("Successfully sent followup message")
            return True
        except discord.errors.InteractionResponded as e:
            logger.warning(f"Interaction already responded: {e}")
            try:
                await interaction.followup.send(message, ephemeral=ephemeral)
                logger.debug("Successfully sent followup after InteractionResponded error")
                return True
            except Exception as followup_error:
                logger.exception("Failed to send followup after InteractionResponded")
                return False
        except discord.errors.NotFound:
            logger.exception("Interaction not found (possibly expired)")
            return False
        except discord.errors.HTTPException:
            logger.exception("HTTP error in interaction response")
            return False
        except Exception:
            logger.exception("Unexpected error in interaction response")
            return False

    # Row 0: Playback controls (emoji-only for cleaner look)
    @discord.ui.button(label='⏸️', style=ButtonStyle.primary, row=0)
    async def pause_button(self, interaction: discord.Interaction, button: Button):
        try:
            # Import here to avoid circular imports
            from bot_state import player_manager, data_manager
            from ui.embeds import update_stable_message

            logger.debug(f"Pause button clicked in guild {interaction.guild_id} by user {interaction.user}")

            guild_id = str(interaction.guild.id)
            voice_client = player_manager.voice_clients.get(guild_id)
            logger.debug(f"Voice client for guild {guild_id}: {voice_client}")

            if voice_client and voice_client.is_playing():
                voice_client.pause()
                await self._safe_interaction_response(interaction, '⏸️ Paused the music.')
                logger.debug(f"Successfully paused music in guild {guild_id}")
            else:
                await self._safe_interaction_response(interaction, '❌ Nothing is playing.')
                logger.debug(f"No music playing in guild {guild_id}")

            await update_stable_message(guild_id)
            await self._delete_interaction_message_safe(interaction)
        except Exception:
            logger.exception("Error in pause_button")
            raise  # Re-raise to trigger on_error

    @discord.ui.button(label='▶️', style=ButtonStyle.primary, row=0)
    async def resume_button(self, interaction: discord.Interaction, button: Button):
        try:
            from bot_state import player_manager
            from ui.embeds import update_stable_message

            logger.debug(f"Resume button clicked in guild {interaction.guild_id} by user {interaction.user}")

            guild_id = str(interaction.guild.id)
            voice_client = player_manager.voice_clients.get(guild_id)
            logger.debug(f"Voice client for guild {guild_id}: {voice_client}")

            if voice_client and voice_client.is_paused():
                voice_client.resume()
                await self._safe_interaction_response(interaction, '▶️ Resumed the music.')
                logger.debug(f"Successfully resumed music in guild {guild_id}")
            else:
                await self._safe_interaction_response(interaction, '❌ Nothing is paused.')
                logger.debug(f"No music paused in guild {guild_id}")

            await update_stable_message(guild_id)
            await self._delete_interaction_message_safe(interaction)
        except Exception:
            logger.exception("Error in resume_button")
            raise

    @discord.ui.button(label='⏭️', style=ButtonStyle.primary, row=0)
    async def skip_button(self, interaction: discord.Interaction, button: Button):
        try:
            from bot_state import player_manager, client
            from ui.embeds import update_stable_message
            from utils.vote_manager import VoteManager

            guild_id = str(interaction.guild.id)
            user_id = interaction.user.id
            logger.debug(f"Skip button clicked in guild {interaction.guild_id} by user {interaction.user}")
            
            voice_client = player_manager.voice_clients.get(guild_id)
            if not voice_client or not (voice_client.is_playing() or voice_client.is_paused()):
                await self._safe_interaction_response(interaction, '❌ Nothing is playing.')
                return

            # Check if user is in voice channel
            if not interaction.user.voice or not interaction.user.voice.channel:
                await self._safe_interaction_response(interaction, '❌ You must be in the voice channel to skip.')
                return

            # Check if user is in the same voice channel as bot
            if interaction.user.voice.channel != voice_client.channel:
                await self._safe_interaction_response(interaction, f'❌ You must be in {voice_client.channel.mention} to skip.')
                return

            guild_data = client.guilds_data.get(guild_id, {})
            
            # Check if user is the song requestor
            if VoteManager.is_song_requestor(guild_data, user_id):
                # Skip immediately for requestor
                voice_client.stop()
                VoteManager.reset_votes(guild_data)  # Reset votes for next song
                await self._safe_interaction_response(interaction, '⏭️ Song skipped by requestor.')
                logger.info(f"Song skipped by requestor (user {user_id}) in guild {guild_id}")
            else:
                # Use vote system for non-requestors
                # Try to add vote
                if not VoteManager.add_vote(guild_data, user_id):
                    await self._safe_interaction_response(interaction, '❌ You have already voted to skip this song.')
                    return

                # Check if threshold is reached
                if VoteManager.check_vote_threshold(guild_data, voice_client.channel):
                    # Skip the song
                    voice_client.stop()
                    VoteManager.reset_votes(guild_data)  # Reset votes for next song
                    await self._safe_interaction_response(interaction, '⏭️ Vote threshold reached! Skipping song.')
                    logger.info(f"Song skipped by vote in guild {guild_id}")
                else:
                    # Show vote progress
                    vote_status = VoteManager.get_vote_status(guild_data, voice_client.channel)
                    progress_bar = "▓" * vote_status['current_votes'] + "░" * (vote_status['required_votes'] - vote_status['current_votes'])
                    await self._safe_interaction_response(
                        interaction, 
                        f'🗳️ Vote added! **{vote_status["current_votes"]}/{vote_status["required_votes"]}** votes needed to skip.\n'
                        f'`{progress_bar}` {vote_status["percentage"]}%'
                    )

            await update_stable_message(guild_id)
            await self._delete_interaction_message_safe(interaction)
        except Exception:
            logger.exception("Error in skip_button")
            raise

    @discord.ui.button(label='⏹️', style=ButtonStyle.danger, row=0)
    async def stop_button(self, interaction: discord.Interaction, button: Button):
        try:
            from bot_state import player_manager, client, queue_manager
            from ui.embeds import update_stable_message

            guild_id = str(interaction.guild.id)
            logger.debug(f"Stop button clicked in guild {interaction.guild_id} by user {interaction.user}")

            await player_manager.disconnect_voice_client(guild_id)
            client.guilds_data[guild_id]['current_song'] = None
            client.playback_modes[guild_id] = PlaybackMode.NORMAL

            await self._safe_interaction_response(interaction, '⏹️ Stopped the music and left the voice channel.')
            logger.debug(f"Successfully stopped music in guild {guild_id}")
            await update_stable_message(guild_id)
            await self._delete_interaction_message_safe(interaction)
        except Exception:
            logger.exception("Error in stop_button")
            raise

    # Row 1: Queue management
    @discord.ui.button(label='🔀', style=ButtonStyle.secondary, row=1)
    async def shuffle_button(self, interaction: discord.Interaction, button: Button):
        try:
            from bot_state import queue_manager
            from ui.embeds import update_stable_message

            guild_id = str(interaction.guild.id)
            logger.debug(f"Shuffle button clicked in guild {interaction.guild_id} by user {interaction.user}")

            if queue_manager.shuffle_queue(guild_id):
                await self._safe_interaction_response(interaction, '🔀 Queue shuffled.')
                logger.debug(f"Successfully shuffled queue in guild {guild_id}")
            else:
                await self._safe_interaction_response(interaction, '❌ The queue is empty.')
                logger.debug(f"Queue is empty in guild {guild_id}")

            await update_stable_message(guild_id)
            await self._delete_interaction_message_safe(interaction)
        except Exception:
            logger.exception("Error in shuffle_button")
            raise

    @discord.ui.button(label='🗑️ Clear', style=ButtonStyle.danger, row=1)
    async def clear_queue_button(self, interaction: discord.Interaction, button: Button):
        try:
            from bot_state import queue_manager
            from ui.embeds import update_stable_message

            guild_id = str(interaction.guild.id)
            logger.debug(f"Clear queue button clicked in guild {interaction.guild_id} by user {interaction.user}")
            count = queue_manager.clear_queue(guild_id)
            logger.debug(f"Cleared {count} songs from queue in guild {guild_id}")

            if count > 0:
                await self._safe_interaction_response(interaction, f'🗑️ Cleared {count} songs from the queue.')
            else:
                await self._safe_interaction_response(interaction, '❌ The queue is already empty.')

            await update_stable_message(guild_id)
            await self._delete_interaction_message_safe(interaction)
        except Exception:
            logger.exception("Error in clear_queue_button")
            raise

    @discord.ui.button(label='↕️ Move', style=ButtonStyle.secondary, row=1)
    async def move_button(self, interaction: discord.Interaction, button: Button):
        try:
            from ui.modals import MoveSongModal
            logger.debug(f"Move button clicked in guild {interaction.guild_id} by user {interaction.user}")
            modal = MoveSongModal()
            await interaction.response.send_modal(modal)
            logger.debug(f"Successfully sent modal for move song in guild {interaction.guild_id}")
        except Exception:
            logger.exception("Error in move_button")
            raise

    @discord.ui.button(label='❌ Remove', style=ButtonStyle.danger, row=1)
    async def remove_button(self, interaction: discord.Interaction, button: Button):
        try:
            from ui.modals import RemoveRangeModal
            logger.debug(f"Remove button clicked in guild {interaction.guild_id} by user {interaction.user}")
            modal = RemoveRangeModal()
            await interaction.response.send_modal(modal)
            logger.debug(f"Successfully sent modal for remove song in guild {interaction.guild_id}")
        except Exception:
            logger.exception("Error in remove_button")
            raise

    # Row 2: Add songs
    @discord.ui.button(label='🎵 Add Song', style=ButtonStyle.success, row=2)
    async def add_song_button(self, interaction: discord.Interaction, button: Button):
        try:
            from ui.modals import AddSongModal
            logger.debug(f"Add song button clicked in guild {interaction.guild_id} by user {interaction.user}")
            modal = AddSongModal(preview_mode=True)
            await interaction.response.send_modal(modal)
            logger.debug(f"Successfully sent modal for add song in guild {interaction.guild_id}")
        except Exception:
            logger.exception("Error in add_song_button")
            raise

    @discord.ui.button(label='➕ Play Next', style=ButtonStyle.success, row=2)
    async def add_next_song_button(self, interaction: discord.Interaction, button: Button):
        try:
            from ui.modals import AddSongModal
            logger.debug(f"Play next button clicked in guild {interaction.guild_id} by user {interaction.user}")
            modal = AddSongModal(play_next=True)
            await interaction.response.send_modal(modal)
            logger.debug(f"Successfully sent modal for play next in guild {interaction.guild_id}")
        except Exception:
            logger.exception("Error in add_next_song_button")
            raise

    @discord.ui.button(label='📋 View Queue', style=ButtonStyle.primary, row=2)
    async def view_queue_button(self, interaction: discord.Interaction, button: Button):
        try:
            from bot_state import queue_manager
            logger.debug(f"View queue button clicked in guild {interaction.guild_id} by user {interaction.user}")
            
            guild_id = str(interaction.guild.id)
            queue_length = queue_manager.get_queue_length(guild_id)
            
            if queue_length == 0:
                await interaction.response.send_message('📋 The queue is empty.', ephemeral=True)
                return
            
            # Create paginated view and embed
            view = QueuePaginationView(guild_id, current_page=1)
            embed = view._create_queue_embed_paginated(page=1)
            
            # Update button states
            from bot_state import queue_manager
            _, total_pages, _ = queue_manager.get_queue_page(guild_id, 1)
            view._update_button_states(total_pages)
            
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            logger.debug(f"Successfully sent paginated queue view in guild {interaction.guild_id}")
        except Exception:
            logger.exception("Error in view_queue_button")
            raise

    async def _delete_interaction_message_safe(self, interaction: discord.Interaction, delay: float = 5.0):
        """Safely delete interaction message with enhanced logging"""
        try:
            logger.debug(f"Scheduling deletion of interaction message in guild {interaction.guild_id} after {delay}s")
            await asyncio.sleep(delay)
            message = await interaction.original_response()
            await message.delete()
            logger.debug(f"Successfully deleted interaction message in guild {interaction.guild_id}")
        except discord.errors.NotFound:
            logger.debug(f"Interaction message already deleted in guild {interaction.guild_id}")
        except discord.errors.Forbidden:
            logger.warning(f"No permission to delete interaction message in guild {interaction.guild_id}")
        except Exception:
            logger.exception(
                "Error deleting interaction message in guild %s",
                interaction.guild_id,
            )
