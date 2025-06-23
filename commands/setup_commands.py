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

            # Check bot permissions
            bot_member = interaction.guild.me
            if not bot_member.guild_permissions.manage_channels:
                await interaction.response.send_message(
                    "❌ I need 'Manage Channels' permission to create channels.",
                    ephemeral=True
                )
                return

            if not bot_member.guild_permissions.send_messages:
                await interaction.response.send_message(
                    "❌ I need 'Send Messages' permission to function properly.",
                    ephemeral=True
                )
                return

            # Find or create the music channel
            channel = discord.utils.get(interaction.guild.channels, name=channel_name)
            if not channel:
                try:
                    overwrites = {
                        interaction.guild.default_role: discord.PermissionOverwrite(
                            view_channel=True,
                            send_messages=True,
                            read_message_history=True
                        )
                    }
                    channel = await interaction.guild.create_text_channel(channel_name, overwrites=overwrites)
                    logger.info(f"Created music channel '{channel_name}' in guild {guild_id}")
                except discord.Forbidden:
                    await interaction.response.send_message(
                        "❌ I don't have permission to create channels. Please create a channel manually and try again.",
                        ephemeral=True
                    )
                    return
                except Exception as e:
                    logger.error(f"Error creating channel in guild {guild_id}: {e}")
                    await interaction.response.send_message(
                        f"❌ Failed to create channel: {str(e)}",
                        ephemeral=True
                    )
                    return

            # Check if bot can send messages in the channel
            if not channel.permissions_for(bot_member).send_messages:
                await interaction.response.send_message(
                    f"❌ I don't have permission to send messages in {channel.mention}.",
                    ephemeral=True
                )
                return

            # Create stable message
            try:
                stable_message = await channel.send('🎶 **Music Bot UI Initialized** 🎶')
            except discord.Forbidden:
                await interaction.response.send_message(
                    f"❌ I don't have permission to send messages in {channel.mention}.",
                    ephemeral=True
                )
                return
            except Exception as e:
                logger.error(f"Error creating stable message in guild {guild_id}: {e}")
                await interaction.response.send_message(
                    f"❌ Failed to create UI message: {str(e)}",
                    ephemeral=True
                )
                return

            # Save guild data
            client.guilds_data[guild_id] = {
                'channel_id': channel.id,
                'stable_message_id': stable_message.id,
                'current_song': None
            }

            # Save to file
            try:
                await data_manager.save_guilds_data(client)
            except Exception as e:
                logger.error(f"Error saving guild data for guild {guild_id}: {e}")
                # Continue anyway, data is in memory

            # Store stable message reference
            client.guilds_data[guild_id]['stable_message'] = stable_message

            await interaction.response.send_message(
                f'✅ Music commands channel setup complete in {channel.mention}!',
                ephemeral=True
            )

            # Update the stable message and clear any other messages
            try:
                from ui.embeds import update_stable_message
                from utils.message_utils import clear_channel_messages

                await update_stable_message(guild_id)
                await clear_channel_messages(channel, stable_message.id)
                logger.info(f"Successfully initialized UI for guild {guild_id}")
            except Exception as e:
                logger.error(f"Error updating stable message for guild {guild_id}: {e}")
                # UI was created but update failed - not critical

        except Exception as e:
            logger.error(f"Critical error in setup command for guild {interaction.guild.id}: {e}")

            # Try to respond if we haven't already
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        f"❌ An error occurred during setup: {str(e)}",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        f"❌ An error occurred during setup: {str(e)}",
                        ephemeral=True
                    )
            except Exception as response_error:
                logger.error(f"Error sending error response: {response_error}")

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
            try:
                from bot import player_manager, queue_manager
                await player_manager.disconnect_voice_client(guild_id)

                # Clear queue
                queue_manager.cleanup_guild(guild_id)
            except Exception as e:
                logger.error(f"Error cleaning up voice/queue for guild {guild_id}: {e}")

            # Remove guild data
            client.guilds_data.pop(guild_id, None)
            client.playback_modes.pop(guild_id, None)

            # Save changes
            try:
                await data_manager.save_guilds_data(client)
            except Exception as e:
                logger.error(f"Error saving data after reset for guild {guild_id}: {e}")

            await interaction.response.send_message(
                "✅ Bot configuration has been reset for this server.",
                ephemeral=True
            )

            logger.info(f"Reset bot configuration for guild {guild_id}")

        except Exception as e:
            logger.error(f"Error in reset command for guild {interaction.guild.id}: {e}")

            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        f"❌ An error occurred during reset: {str(e)}",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        f"❌ An error occurred during reset: {str(e)}",
                        ephemeral=True
                    )
            except Exception as response_error:
                logger.error(f"Error sending reset error response: {response_error}")