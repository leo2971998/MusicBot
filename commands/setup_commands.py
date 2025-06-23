import discord
from discord import app_commands
from discord.ext import commands
import logging
from config import MUSIC_CHANNEL_NAME

logger = logging.getLogger(__name__)

def setup_admin_commands(client, data_manager):
    """Setup admin/setup commands"""

    @client.tree.command(name="setup", description="Set up the music channel and bot UI")
    @app_commands.describe(channel_name="Name of the music channel (optional)")
    async def setup(interaction: discord.Interaction, channel_name: str = MUSIC_CHANNEL_NAME):
        """Setup command to initialize the bot in a guild"""
        try:
            # Check permissions
            if not interaction.user.guild_permissions.manage_channels:
                await interaction.response.send_message(
                    "❌ You need 'Manage Channels' permission to use this command.",
                    ephemeral=True
                )
                return

            guild_id = str(interaction.guild.id)

            # Find or create the music channel
            channel = discord.utils.get(interaction.guild.channels, name=channel_name)
            if not channel:
                overwrites = {
                    interaction.guild.default_role: discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True
                    )
                }
                channel = await interaction.guild.create_text_channel(channel_name, overwrites=overwrites)
                logger.info(f"Created music channel '{channel_name}' in guild {guild_id}")

            # Create stable message
            stable_message = await channel.send('🎶 **Music Bot UI Initialized** 🎶')

            # Save guild data INCLUDING the stable message reference
            client.guilds_data[guild_id] = {
                'channel_id': channel.id,
                'stable_message_id': stable_message.id,
                'current_song': None,
                'stable_message': stable_message  # ← ADD THIS LINE HERE
            }

            # Save to file
            await data_manager.save_guilds_data(client)

            await interaction.response.send_message(
                f'✅ Music commands channel setup complete in {channel.mention}!',
                ephemeral=True
            )

            # NOW update the stable message (after guild data is complete)
            from ui.embeds import update_stable_message
            from utils.message_utils import clear_channel_messages

            await update_stable_message(guild_id)
            await clear_channel_messages(channel, stable_message.id)

        except Exception as e:
            logger.error(f"Error in setup command for guild {interaction.guild.id}: {e}")

            # Try to respond if we haven't already
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ An error occurred during setup. Please try again.",
                        ephemeral=True
                    )
            except:
                pass

    @client.tree.command(name="reset", description="Reset the bot configuration for this server")
    async def reset(interaction: discord.Interaction):
        """Reset command to clear bot data for a guild"""
        try:
            # Check permissions
            if not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message(
                    "❌ You need Administrator permission to use this command.",
                    ephemeral=True
                )
                return

            guild_id = str(interaction.guild.id)

            # Clean up voice client if connected
            from bot import player_manager, queue_manager
            await player_manager.disconnect_voice_client(guild_id)

            # Clear queue
            queue_manager.cleanup_guild(guild_id)

            # Remove guild data
            client.guilds_data.pop(guild_id, None)
            client.playback_modes.pop(guild_id, None)

            # Save changes
            await data_manager.save_guilds_data(client)

            await interaction.response.send_message(
                "✅ Bot configuration has been reset for this server.",
                ephemeral=True
            )

            logger.info(f"Reset bot configuration for guild {guild_id}")

        except Exception as e:
            logger.error(f"Error in reset command for guild {interaction.guild.id}: {e}")
            await interaction.response.send_message(
                "❌ An error occurred during reset. Please try again.",
                ephemeral=True
            )