import logging

import discord
from discord import app_commands

from config import MUSIC_CHANNEL_NAME
from utils.guild_setup import ensure_guild_music_panel

logger = logging.getLogger(__name__)


def setup_admin_commands(client, data_manager):
    """Setup admin/setup commands."""

    @client.tree.command(name="setup", description="Set up the music channel and bot UI")
    @app_commands.describe(channel_name="Name of the music channel (optional)")
    async def setup(interaction: discord.Interaction, channel_name: str = MUSIC_CHANNEL_NAME):
        """Set up or repair the bot panel for a guild."""
        try:
            if not interaction.user.guild_permissions.manage_channels:
                await interaction.response.send_message(
                    "❌ You need 'Manage Channels' permission to use this command.",
                    ephemeral=True,
                )
                return

            guild_data, channel, _ = await ensure_guild_music_panel(
                interaction.guild,
                channel_name=channel_name,
                create_channel=True,
            )

            if not guild_data or not channel:
                await interaction.response.send_message(
                    "❌ I couldn't prepare the music channel. Please check my permissions and try again.",
                    ephemeral=True,
                )
                return

            await interaction.response.send_message(
                f"✅ Music commands channel ready in {channel.mention}.",
                ephemeral=True,
            )

            from utils.message_utils import clear_channel_messages

            stable_message_id = guild_data.get('stable_message_id')
            if stable_message_id:
                await clear_channel_messages(channel, stable_message_id)

        except Exception as e:
            logger.error(f"Error in setup command for guild {interaction.guild.id}: {e}")

            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ An error occurred during setup. Please try again.",
                        ephemeral=True,
                    )
            except Exception:
                pass

    @client.tree.command(name="reset", description="Reset the bot configuration for this server")
    async def reset(interaction: discord.Interaction):
        """Reset command to clear bot data for a guild."""
        try:
            if not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message(
                    "❌ You need Administrator permission to use this command.",
                    ephemeral=True,
                )
                return

            guild_id = str(interaction.guild.id)

            from bot_state import player_manager, queue_manager

            await player_manager.disconnect_voice_client(guild_id)
            queue_manager.cleanup_guild(guild_id)

            client.guilds_data.pop(guild_id, None)
            client.playback_modes.pop(guild_id, None)

            await data_manager.save_guilds_data(client)

            await interaction.response.send_message(
                "✅ Bot configuration has been reset for this server.",
                ephemeral=True,
            )

            logger.info(f"Reset bot configuration for guild {guild_id}")

        except Exception as e:
            logger.error(f"Error in reset command for guild {interaction.guild.id}: {e}")
            await interaction.response.send_message(
                "❌ An error occurred during reset. Please try again.",
                ephemeral=True,
            )
