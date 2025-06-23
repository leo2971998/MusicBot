import asyncio
import logging
import discord
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
        """Handle interaction errors"""
        logger.error(f"Interaction error in guild {interaction.guild_id}: {error}")

        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ An error occurred while processing your request. Please try again.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "❌ An error occurred while processing your request. Please try again.",
                    ephemeral=True
                )
        except Exception as followup_error:
            logger.error(f"Failed to send error message: {followup_error}")

    async def _safe_interaction_response(self, interaction: discord.Interaction,
                                         message: str, ephemeral: bool = False):
        """Safely send interaction response"""
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(message, ephemeral=ephemeral)
            else:
                await interaction.followup.send(message, ephemeral=ephemeral)
            return True
        except Exception as e:
            logger.error(f"Error in interaction response: {e}")
            return False

    @discord.ui.button(label='⏸️ Pause', style=ButtonStyle.primary)
    async def pause_button(self, interaction: discord.Interaction, button: Button):
        # Import here to avoid circular imports
        from bot_state import player_manager, data_manager
        from ui.embeds import update_stable_message

        guild_id = str(interaction.guild.id)
        voice_client = player_manager.voice_clients.get(guild_id)

        if voice_client and voice_client.is_playing():
            voice_client.pause()
            await self._safe_interaction_response(interaction, '⏸️ Paused the music.')
        else:
            await self._safe_interaction_response(interaction, '❌ Nothing is playing.')

        await update_stable_message(guild_id)
        await self._delete_interaction_message_safe(interaction)

    @discord.ui.button(label='▶️ Resume', style=ButtonStyle.primary)
    async def resume_button(self, interaction: discord.Interaction, button: Button):
        from bot_state import player_manager
        from ui.embeds import update_stable_message

        guild_id = str(interaction.guild.id)
        voice_client = player_manager.voice_clients.get(guild_id)

        if voice_client and voice_client.is_paused():
            voice_client.resume()
            await self._safe_interaction_response(interaction, '▶️ Resumed the music.')
        else:
            await self._safe_interaction_response(interaction, '❌ Nothing is paused.')

        await update_stable_message(guild_id)
        await self._delete_interaction_message_safe(interaction)

    @discord.ui.button(label='⏭️ Skip', style=ButtonStyle.primary)
    async def skip_button(self, interaction: discord.Interaction, button: Button):
        from bot_state import player_manager
        from ui.embeds import update_stable_message

        guild_id = str(interaction.guild.id)
        voice_client = player_manager.voice_clients.get(guild_id)

        if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
            voice_client.stop()
            await self._safe_interaction_response(interaction, '⏭️ Skipped the song.')
        else:
            await self._safe_interaction_response(interaction, '❌ Nothing is playing.')

        await update_stable_message(guild_id)
        await self._delete_interaction_message_safe(interaction)

    @discord.ui.button(label='⏹️ Stop', style=ButtonStyle.primary)
    async def stop_button(self, interaction: discord.Interaction, button: Button):
        from bot_state import player_manager, client, queue_manager
        from ui.embeds import update_stable_message

        guild_id = str(interaction.guild.id)

        await player_manager.disconnect_voice_client(guild_id)
        client.guilds_data[guild_id]['current_song'] = None
        client.playback_modes[guild_id] = PlaybackMode.NORMAL

        await self._safe_interaction_response(interaction, '⏹️ Stopped the music and left the voice channel.')
        await update_stable_message(guild_id)
        await self._delete_interaction_message_safe(interaction)

    @discord.ui.button(label='🗑️ Clear Queue', style=ButtonStyle.danger)
    async def clear_queue_button(self, interaction: discord.Interaction, button: Button):
        from bot_state import queue_manager
        from ui.embeds import update_stable_message

        guild_id = str(interaction.guild.id)
        count = queue_manager.clear_queue(guild_id)

        if count > 0:
            await self._safe_interaction_response(interaction, f'🗑️ Cleared {count} songs from the queue.')
        else:
            await self._safe_interaction_response(interaction, '❌ The queue is already empty.')

        await update_stable_message(guild_id)
        await self._delete_interaction_message_safe(interaction)

    @discord.ui.button(label='🔁 Normal', style=ButtonStyle.secondary)
    async def normal_mode_button(self, interaction: discord.Interaction, button: Button):
        from bot_state import client
        from ui.embeds import update_stable_message

        guild_id = str(interaction.guild.id)
        client.playback_modes[guild_id] = PlaybackMode.NORMAL

        await self._safe_interaction_response(interaction, 'Playback mode set to: **Normal**')
        await update_stable_message(guild_id)
        await self._delete_interaction_message_safe(interaction)

    @discord.ui.button(label='🔂 Repeat', style=ButtonStyle.secondary)
    async def repeat_one_button(self, interaction: discord.Interaction, button: Button):
        from bot_state import client
        from ui.embeds import update_stable_message

        guild_id = str(interaction.guild.id)
        client.playback_modes[guild_id] = PlaybackMode.REPEAT_ONE

        await self._safe_interaction_response(interaction, 'Playback mode set to: **Repeat**')
        await update_stable_message(guild_id)
        await self._delete_interaction_message_safe(interaction)

    @discord.ui.button(label='🔀 Shuffle', style=ButtonStyle.primary)
    async def shuffle_button(self, interaction: discord.Interaction, button: Button):
        from bot_state import queue_manager
        from ui.embeds import update_stable_message

        guild_id = str(interaction.guild.id)

        if queue_manager.shuffle_queue(guild_id):
            await self._safe_interaction_response(interaction, '🔀 Queue shuffled.')
        else:
            await self._safe_interaction_response(interaction, '❌ The queue is empty.')

        await update_stable_message(guild_id)
        await self._delete_interaction_message_safe(interaction)

    @discord.ui.button(label='➕ Add Song', style=ButtonStyle.success)
    async def add_song_button(self, interaction: discord.Interaction, button: Button):
        from ui.modals import AddSongModal
        modal = AddSongModal()
        await interaction.response.send_modal(modal)

    @discord.ui.button(label='➕ Play Next', style=ButtonStyle.success)
    async def add_next_song_button(self, interaction: discord.Interaction, button: Button):
        from ui.modals import AddSongModal
        modal = AddSongModal(play_next=True)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label='❌ Remove', style=ButtonStyle.danger)
    async def remove_button(self, interaction: discord.Interaction, button: Button):
        from ui.modals import RemoveSongModal
        modal = RemoveSongModal()
        await interaction.response.send_modal(modal)

    async def _delete_interaction_message_safe(self, interaction: discord.Interaction, delay: float = 5.0):
        """Safely delete interaction message"""
        try:
            await asyncio.sleep(delay)
            message = await interaction.original_response()
            await message.delete()
        except Exception as e:
            logger.error(f"Error deleting interaction message: {e}")