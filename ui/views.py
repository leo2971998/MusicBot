import asyncio
import logging
import discord
import traceback
from discord import ButtonStyle
from discord.ui import View, Button
from config import PlaybackMode
logger = logging.getLogger(__name__)

class MusicControlView(View):
    """Improved music control view with better error handling"""

    def __init__(self, timeout: float = 300.0):
        super().__init__(timeout=timeout)

    async def on_timeout(self):
        """Handle view timeout"""
        logger.info("Music control view timed out")
        for item in self.children:
            item.disabled = True

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item):
        """Handle interaction errors with detailed logging"""
        logger.error(f"Interaction error in guild {interaction.guild_id} for button '{item.label}': {error}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        logger.error(f"Interaction user: {interaction.user} ({interaction.user.id})")
        logger.error(f"Interaction channel: {interaction.channel} ({interaction.channel.id if interaction.channel else 'None'})")
        logger.error(f"Interaction guild: {interaction.guild} ({interaction.guild.id if interaction.guild else 'None'})")
        logger.error(f"Is response done: {interaction.response.is_done()}")

        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"❌ An error occurred while processing your request: {str(error)}\nPlease check the logs and try again.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"❌ An error occurred while processing your request: {str(error)}\nPlease check the logs and try again.",
                    ephemeral=True
                )
        except Exception as followup_error:
            logger.error(f"Failed to send error message: {followup_error}")
            logger.error(f"Followup error traceback: {traceback.format_exc()}")

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
                logger.error(f"Failed to send followup after InteractionResponded: {followup_error}")
                return False
        except discord.errors.NotFound as e:
            logger.error(f"Interaction not found (possibly expired): {e}")
            return False
        except discord.errors.HTTPException as e:
            logger.error(f"HTTP error in interaction response: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error in interaction response: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False

    @discord.ui.button(label='⏸️ Pause', style=ButtonStyle.primary)
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
        except Exception as e:
            logger.error(f"Error in pause_button: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise  # Re-raise to trigger on_error

    @discord.ui.button(label='▶️ Resume', style=ButtonStyle.primary)
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
        except Exception as e:
            logger.error(f"Error in resume_button: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

    @discord.ui.button(label='⏭️ Skip', style=ButtonStyle.primary)
    async def skip_button(self, interaction: discord.Interaction, button: Button):
        try:
            from bot_state import player_manager
            from ui.embeds import update_stable_message

            guild_id = str(interaction.guild.id)
            logger.debug(f"Skip button clicked in guild {interaction.guild_id} by user {interaction.user}")
            voice_client = player_manager.voice_clients.get(guild_id)
            logger.debug(f"Voice client for guild {guild_id}: {voice_client}")

            if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
                voice_client.stop()
                await self._safe_interaction_response(interaction, '⏭️ Skipped the song.')
                logger.debug(f"Successfully skipped song in guild {guild_id}")
            else:
                await self._safe_interaction_response(interaction, '❌ Nothing is playing.')
                logger.debug(f"No music playing in guild {guild_id}")

            await update_stable_message(guild_id)
            await self._delete_interaction_message_safe(interaction)
        except Exception as e:
            logger.error(f"Error in skip_button: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

    @discord.ui.button(label='⏹️ Stop', style=ButtonStyle.primary)
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
        except Exception as e:
            logger.error(f"Error in stop_button: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

    @discord.ui.button(label='🗑️ Clear Queue', style=ButtonStyle.danger)
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
        except Exception as e:
            logger.error(f"Error in clear_queue_button: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

    @discord.ui.button(label='🔁 Normal', style=ButtonStyle.secondary)
    async def normal_mode_button(self, interaction: discord.Interaction, button: Button):
        try:
            from bot_state import client
            from ui.embeds import update_stable_message

            guild_id = str(interaction.guild.id)
            logger.debug(f"Normal mode button clicked in guild {interaction.guild_id} by user {interaction.user}")
            client.playback_modes[guild_id] = PlaybackMode.NORMAL

            await self._safe_interaction_response(interaction, 'Playback mode set to: **Normal**')
            logger.debug(f"Set playback mode to Normal in guild {guild_id}")
            await update_stable_message(guild_id)
            await self._delete_interaction_message_safe(interaction)
        except Exception as e:
            logger.error(f"Error in normal_mode_button: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

    @discord.ui.button(label='🔂 Repeat', style=ButtonStyle.secondary)
    async def repeat_one_button(self, interaction: discord.Interaction, button: Button):
        try:
            from bot_state import client
            from ui.embeds import update_stable_message

            guild_id = str(interaction.guild.id)
            logger.debug(f"Repeat button clicked in guild {interaction.guild_id} by user {interaction.user}")
            client.playback_modes[guild_id] = PlaybackMode.REPEAT_ONE

            await self._safe_interaction_response(interaction, 'Playback mode set to: **Repeat**')
            logger.debug(f"Set playback mode to Repeat in guild {guild_id}")
            await update_stable_message(guild_id)
            await self._delete_interaction_message_safe(interaction)
        except Exception as e:
            logger.error(f"Error in repeat_one_button: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

    @discord.ui.button(label='🔀 Shuffle', style=ButtonStyle.primary)
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
        except Exception as e:
            logger.error(f"Error in shuffle_button: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

    @discord.ui.button(label='➕ Add Song', style=ButtonStyle.success)
    async def add_song_button(self, interaction: discord.Interaction, button: Button):
        try:
            from ui.modals import AddSongModal
            logger.debug(f"Add song button clicked in guild {interaction.guild_id} by user {interaction.user}")
            modal = AddSongModal()
            await interaction.response.send_modal(modal)
            logger.debug(f"Successfully sent modal for add song in guild {interaction.guild_id}")
        except Exception as e:
            logger.error(f"Error in add_song_button: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

    @discord.ui.button(label='➕ Play Next', style=ButtonStyle.success)
    async def add_next_song_button(self, interaction: discord.Interaction, button: Button):
        try:
            from ui.modals import AddSongModal
            logger.debug(f"Play next button clicked in guild {interaction.guild_id} by user {interaction.user}")
            modal = AddSongModal(play_next=True)
            await interaction.response.send_modal(modal)
            logger.debug(f"Successfully sent modal for play next in guild {interaction.guild_id}")
        except Exception as e:
            logger.error(f"Error in add_next_song_button: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

    @discord.ui.button(label='❌ Remove', style=ButtonStyle.danger)
    async def remove_button(self, interaction: discord.Interaction, button: Button):
        try:
            from ui.modals import RemoveSongModal
            logger.debug(f"Remove button clicked in guild {interaction.guild_id} by user {interaction.user}")
            modal = RemoveSongModal()
            await interaction.response.send_modal(modal)
            logger.debug(f"Successfully sent modal for remove song in guild {interaction.guild_id}")
        except Exception as e:
            logger.error(f"Error in remove_button: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
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
        except Exception as e:
            logger.error(f"Error deleting interaction message in guild {interaction.guild_id}: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
