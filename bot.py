import asyncio
import logging
import os

import discord

from config import TOKEN, LOG_LEVEL, LOG_FORMAT, PlaybackMode
from bot_state import client, data_manager, player_manager, queue_manager

# Setup logging
logging.basicConfig(level=getattr(logging, LOG_LEVEL), format=LOG_FORMAT)
logger = logging.getLogger(__name__)

# Bot setup uses shared client from bot_state

@client.event
async def on_ready():
    logger.info(f'{client.user} has connected to Discord!')
    await data_manager.load_guilds_data(client)
    await restore_guild_states()

    # Sync slash commands
    try:
        synced = await client.tree.sync()
        logger.info(f'Synced {len(synced)} slash commands')
    except Exception as e:
        logger.error(f'Failed to sync commands: {e}')

async def restore_guild_states():
    guilds_to_remove = []
    for guild_id, guild_data in list(client.guilds_data.items()):
        try:
            # Validate that guild_id is numeric
            if not guild_id.isdigit():
                logger.warning(f"Invalid guild_id format: {guild_id}, removing from data")
                guilds_to_remove.append(guild_id)
                continue

            guild = client.get_guild(int(guild_id))

            if not guild:
                guilds_to_remove.append(guild_id)
                continue

            channel_id = guild_data.get('channel_id')
            if not channel_id:
                guilds_to_remove.append(guild_id)
                continue

            channel = guild.get_channel(int(channel_id))
            if not channel:
                guilds_to_remove.append(guild_id)
                continue

            await restore_stable_message(guild_id, guild_data, channel)
        except Exception as e:
            logger.error(f"Error processing guild {guild_id}: {e}")
            guilds_to_remove.append(guild_id)

    for gid in guilds_to_remove:
        client.guilds_data.pop(gid, None)
        client.playback_modes.pop(gid, None)
        queue_manager.cleanup_guild(gid)

    if guilds_to_remove:
        await data_manager.save_guilds_data(client)
        logger.info(f'Cleaned up {len(guilds_to_remove)} invalid guilds')

async def restore_stable_message(guild_id: str, guild_data: dict, channel: discord.TextChannel) -> bool:
    try:
        stable_message_id = guild_data.get('stable_message_id')
        stable_message = None
        if stable_message_id:
            try:
                stable_message = await channel.fetch_message(int(stable_message_id))
            except discord.NotFound:
                pass
        if not stable_message:
            stable_message = await channel.send('🎶 **Music Bot UI Initialized** 🎶')
            guild_data['stable_message_id'] = stable_message.id
        guild_data['stable_message'] = stable_message

        # **FIX: Update the stable message with embeds and view**
        from ui.embeds import update_stable_message
        await update_stable_message(guild_id)

        return True
    except Exception as e:
        logger.error(f'Failed to restore stable message in guild {guild_id}: {e}')
        return False

@client.event
async def on_message(message):
    """Handle messages in music channels"""
    if message.author == client.user:
        return

    if not message.guild:
        return

    guild_id = str(message.guild.id)
    guild_data = client.guilds_data.get(guild_id)

    if guild_data:
        channel_id = guild_data.get('channel_id')
        if channel_id and message.channel.id == int(channel_id):
            # Delete user message in music channel
            try:
                await message.delete()
            except discord.Forbidden:
                logger.warning(f"Permission error: Cannot delete message {message.id}")
            except discord.HTTPException as e:
                logger.warning(f"Failed to delete message {message.id}: {e}")

            # Process as play request
            from commands.music_commands import process_play_request
            response_message = await process_play_request(
                message.author,
                message.guild,
                message.channel,
                message.content,
                client,
                queue_manager,
                player_manager,
                data_manager
            )

            if response_message:
                sent_msg = await message.channel.send(response_message)
                # Delete response after 5 seconds
                await asyncio.sleep(5)
                try:
                    await sent_msg.delete()
                except:
                    pass
        else:
            await client.process_commands(message)
    else:
        await client.process_commands(message)

def load_extensions():
    from commands import music_commands, setup_commands
    music_commands.setup_music_commands(client, queue_manager, player_manager, data_manager)
    setup_commands.setup_admin_commands(client, data_manager)

def main():
    load_extensions()
    token = TOKEN or os.getenv('DISCORD_TOKEN')
    if not token:
        raise RuntimeError('DISCORD_TOKEN is not set')
    client.run(token)

if __name__ == '__main__':
    main()