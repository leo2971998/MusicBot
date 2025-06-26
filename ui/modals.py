import asyncio
import logging
import discord
from discord.ui import Modal, TextInput

logger = logging.getLogger(__name__)

class AddSongModal(Modal):
    def __init__(self, play_next: bool = False):
        title = "Play Next" if play_next else "Add Song"
        super().__init__(title=title)
        self.play_next = play_next

        self.song_input = TextInput(
            label="Song Name or URL",
            placeholder="Enter the song name or URL",
            required=True,
            max_length=500
        )
        self.add_item(self.song_input)

    async def on_submit(self, interaction: discord.Interaction):
        logger.debug(f"AddSongModal submitted in guild {interaction.guild_id}")
        await interaction.response.defer(thinking=True)

        song_name_or_url = self.song_input.value.strip()

        # Import here to avoid circular imports
        from commands.music_commands import process_play_request
        from bot_state import client, queue_manager, player_manager, data_manager

        try:
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

            # Clean up channel messages
            guild_id = str(interaction.guild.id)
            guild_data = client.guilds_data.get(guild_id)
            if guild_data:
                from utils.message_utils import clear_channel_messages
                channel_id = guild_data.get('channel_id')
                stable_message_id = guild_data.get('stable_message_id')
                if channel_id and stable_message_id:
                    channel = client.get_channel(int(channel_id))
                    if channel:
                        await asyncio.sleep(5)
                        await clear_channel_messages(channel, int(stable_message_id))

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