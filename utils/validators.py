import discord
from discord import app_commands
import logging

logger = logging.getLogger(__name__)

def is_setup():
    """Decorator to check if bot is set up in guild"""
    async def predicate(interaction: discord.Interaction):
        try:
            # Import here to avoid circular imports
            from bot_state import client

            guild_id = str(interaction.guild_id)
            guild_data = client.guilds_data.get(guild_id)

            if not guild_data or not guild_data.get('channel_id'):
                await interaction.response.send_message(
                    "❌ Please run /setup to initialize the music channel first.",
                    ephemeral=True
                )
                return False
            return True

        except Exception as e:
            logger.error(f"Error in is_setup check: {e}")
            await interaction.response.send_message(
                "❌ An error occurred. Please try again.",
                ephemeral=True
            )
            return False

    return app_commands.check(predicate)