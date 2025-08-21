import asyncio
import logging
import os
import time
import signal

import discord

from config import TOKEN, LOG_LEVEL, LOG_FORMAT, PlaybackMode
from bot_state import client, data_manager, player_manager, queue_manager, health_monitor

# Setup logging
logging.basicConfig(level=getattr(logging, LOG_LEVEL), format=LOG_FORMAT)
logger = logging.getLogger(__name__)

# Bot setup uses shared client from bot_state

@client.event
async def on_ready():
    logger.info(f'{client.user} has connected to Discord!')
    logger.debug('Loading guild data and restoring states')
    await data_manager.load_guilds_data(client)
    await restore_guild_states()

    # Sync slash commands
    try:
        synced = await client.tree.sync()
        logger.info(f'Synced {len(synced)} slash commands')
        logger.debug(f'Synced commands: {[cmd.name for cmd in synced]}')
    except Exception as e:
        logger.error(f'Failed to sync commands: {e}')
    
    # Start health monitoring system
    try:
        await health_monitor.start()
        logger.info('Health monitoring system started')
    except Exception as e:
        logger.error(f'Failed to start health monitoring: {e}')


@client.event
async def on_voice_state_update(member, before, after):
    """Handle voice state changes for vote management"""
    try:
        # Only process if it's a user leaving a voice channel where the bot is present
        if before.channel and not after.channel:  # User left a voice channel
            guild_id = str(member.guild.id)
            guild_data = client.guilds_data.get(guild_id)
            
            # Check if bot is in the channel the user left and if there are active votes
            voice_client = player_manager.voice_clients.get(guild_id)
            if (voice_client and voice_client.channel == before.channel and 
                guild_data and 'vote_skip' in guild_data):
                
                # Remove the user's vote if they had one
                from utils.vote_manager import VoteManager
                if VoteManager.remove_user_vote(guild_data, member.id):
                    logger.info(f"Removed vote from user {member.id} who left voice channel in guild {guild_id}")
                    
                    # Update the UI to reflect the vote change
                    from ui.embeds import update_stable_message
                    await update_stable_message(guild_id)
                    
    except Exception as e:
        logger.error(f"Error handling voice state update: {e}")

@client.event
async def on_disconnect():
    """Handle bot disconnect gracefully"""
    logger.warning('Bot disconnected, stopping health monitor')
    try:
        await health_monitor.stop()
    except Exception as e:
        logger.error(f'Error stopping health monitor: {e}')

async def restore_guild_states():
    logger.debug('Restoring guild states')
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
        logger.debug(f'Restoring stable message in guild {guild_id}')
        stable_message_id = guild_data.get('stable_message_id')
        stable_message = None
        
        # Initialize last activity timestamp
        guild_data['last_activity'] = time.time()
        
        if stable_message_id:
            try:
                stable_message = await channel.fetch_message(int(stable_message_id))
                logger.debug(f'Found existing stable message {stable_message_id} in guild {guild_id}')
            except discord.NotFound:
                logger.info(f'Stable message {stable_message_id} not found, will create new one')
                pass
            except discord.Forbidden:
                logger.error(f'No permission to fetch message {stable_message_id} in guild {guild_id}')
                return False
                
        if not stable_message:
            try:
                stable_message = await channel.send('🎶 **Music Bot UI Initialized** 🎶')
                guild_data['stable_message_id'] = stable_message.id
                logger.info(f'Created new stable message {stable_message.id} in guild {guild_id}')
            except discord.Forbidden:
                logger.error(f'No permission to send messages in channel {channel.id} for guild {guild_id}')
                return False
                
        guild_data['stable_message'] = stable_message

        # **FIX: Immediately update the stable message with embeds and view to ensure buttons work**
        from ui.embeds import update_stable_message
        
        # Add a small delay to ensure message is fully created
        await asyncio.sleep(0.5)
        
        # Force update the message with proper embeds and interactive view
        await update_stable_message(guild_id)
        logger.debug(f'Updated stable message {stable_message.id} with embeds and view in guild {guild_id}')
        
        # Ensure guild data is saved with the updated message info
        await data_manager.save_guilds_data(client)

        return True
    except Exception as e:
        logger.error(f'Failed to restore stable message in guild {guild_id}: {e}')
        return False

@client.event
async def on_message(message):
    """Handle messages in music channels"""
    logger.debug(f"on_message event in guild {getattr(message.guild, 'id', 'DM')} with content: {message.content}")
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

            # Auto-clear old messages after processing play request
            from utils.message_utils import clear_channel_messages
            stable_message_id = guild_data.get('stable_message_id')
            if stable_message_id:
                try:
                    await clear_channel_messages(message.channel, stable_message_id)
                    logger.debug(f"Auto-cleared messages in guild {guild_id} after processing play request")
                except Exception as e:
                    logger.warning(f"Failed to auto-clear messages in guild {guild_id}: {e}")

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
    # Start optional web UI
    try:
        from web_ui import start_web_ui
        start_web_ui()
    except Exception as e:
        logger.error(f'Failed to start web UI: {e}')

    token = TOKEN or os.getenv('DISCORD_TOKEN')
    if not token:
        raise RuntimeError('DISCORD_TOKEN is not set')
    
    # Add graceful shutdown handler
    async def shutdown():
        logger.info('Shutting down bot gracefully...')
        try:
            await health_monitor.stop()
            # Disconnect all voice clients
            for guild_id in list(player_manager.voice_clients.keys()):
                await player_manager.disconnect_voice_client(guild_id, cleanup_tasks=True)
            # Save final state
            await data_manager.save_guilds_data(client)
            logger.info('Graceful shutdown completed')
        except Exception as e:
            logger.error(f'Error during shutdown: {e}')
    
    # Register shutdown handler
    import signal
    
    def signal_handler(signum, frame):
        logger.info(f'Received signal {signum}, initiating shutdown...')
        loop = asyncio.get_event_loop()
        loop.create_task(shutdown())
        loop.stop()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        client.run(token)
    except KeyboardInterrupt:
        logger.info('Bot stopped by keyboard interrupt')
    except Exception as e:
        logger.error(f'Bot crashed: {e}')
        raise

if __name__ == '__main__':
    main()
