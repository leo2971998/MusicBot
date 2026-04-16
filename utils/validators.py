import logging

import discord
from discord import app_commands

from utils.guild_setup import ensure_guild_music_panel

logger = logging.getLogger(__name__)


def is_setup():
    """Decorator to check if bot is set up in guild."""

    async def predicate(interaction: discord.Interaction):
        try:
            from bot_state import client

            if not interaction.guild:
                await interaction.response.send_message(
                    "❌ This command can only be used in a server.",
                    ephemeral=True,
                )
                return False

            guild_id = str(interaction.guild_id)
            guild_data = client.guilds_data.get(guild_id)
            channel = None

            if guild_data and guild_data.get('channel_id'):
                try:
                    channel = interaction.guild.get_channel(int(guild_data['channel_id']))
                except (TypeError, ValueError):
                    channel = None

            if channel is None:
                guild_data, channel, _ = await ensure_guild_music_panel(
                    interaction.guild,
                    create_channel=False,
                )

            if not guild_data or not channel:
                await interaction.response.send_message(
                    "❌ Please run /setup to initialize the music channel first.",
                    ephemeral=True,
                )
                return False

            return True

        except Exception as e:
            logger.error(f"Error in is_setup check: {e}")
            await interaction.response.send_message(
                "❌ An error occurred. Please try again.",
                ephemeral=True,
            )
            return False

    return app_commands.check(predicate)
