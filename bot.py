import asyncio
import logging
import os
import signal

import discord

from config import TOKEN, LOG_LEVEL, LOG_FORMAT
from bot_state import client, data_manager, player_manager, queue_manager, health_monitor
from utils.guild_setup import ensure_guild_music_panel

# Setup logging
logging.basicConfig(level=getattr(logging, LOG_LEVEL), format=LOG_FORMAT)
logger = logging.getLogger(__name__)


@client.event
async def on_ready():
    logger.info(f'{client.user} has connected to Discord!')
    logger.debug('Loading guild data and restoring states')
    await data_manager.load_guilds_data(client)
    await restore_guild_states()

    try:
        synced = await client.tree.sync()
        logger.info(f'Synced {len(synced)} slash commands')
        logger.debug(f'Synced commands: {[cmd.name for cmd in synced]}')
    except Exception:
        logger.exception('Failed to sync commands')

    try:
        await health_monitor.start()
        logger.info('Health monitoring system started')
    except Exception:
        logger.exception('Failed to start health monitoring')


@client.event
async def on_voice_state_update(member, before, after):
    """Handle voice state changes for vote management."""
    try:
        if before.channel and not after.channel:
            guild_id = str(member.guild.id)
            guild_data = client.guilds_data.get(guild_id)

            voice_client = player_manager.voice_clients.get(guild_id)
            if (
                voice_client
                and voice_client.channel == before.channel
                and guild_data
                and 'vote_skip' in guild_data
            ):
                from utils.vote_manager import VoteManager

                if VoteManager.remove_user_vote(guild_data, member.id):
                    logger.info(
                        "Removed vote from user %s who left voice channel in guild %s",
                        member.id,
                        guild_id,
                    )

                    from ui.embeds import update_stable_message

                    await update_stable_message(guild_id)

    except Exception:
        logger.exception("Error handling voice state update")


@client.event
async def on_disconnect():
    """Handle bot disconnect gracefully."""
    logger.warning('Bot disconnected, stopping health monitor')
    try:
        await health_monitor.stop()
    except Exception:
        logger.exception('Error stopping health monitor')


async def restore_guild_states():
    logger.debug('Restoring guild states')
    known_guild_ids = {str(guild.id) for guild in client.guilds}
    guilds_to_remove = []

    for guild_id in list(client.guilds_data.keys()):
        if not guild_id.isdigit():
            logger.warning(f"Invalid guild_id format: {guild_id}, removing from data")
            guilds_to_remove.append(guild_id)
            continue

        if guild_id not in known_guild_ids:
            guilds_to_remove.append(guild_id)

    for gid in guilds_to_remove:
        client.guilds_data.pop(gid, None)
        client.playback_modes.pop(gid, None)
        queue_manager.cleanup_guild(gid)

        from ui.embeds import forget_guild_ui

        forget_guild_ui(gid)

    if guilds_to_remove:
        await data_manager.save_guilds_data(client)
        logger.info(f'Cleaned up {len(guilds_to_remove)} invalid guilds')

    for guild in client.guilds:
        try:
            guild_data, channel, _ = await ensure_guild_music_panel(guild, create_channel=False)
            if channel:
                logger.debug('Music channel %s restored for guild %s', channel.id, guild.id)
            elif guild_data:
                logger.warning(
                    'Guild %s has saved music data but no matching channel could be recovered',
                    guild.id,
                )
        except Exception:
            logger.exception('Error restoring guild %s', guild.id)


@client.event
async def on_guild_join(guild):
    """Recover the music channel automatically when joining a guild with an existing setup channel."""
    try:
        await ensure_guild_music_panel(guild, create_channel=False)
    except Exception:
        logger.exception('Failed to auto-recover music setup for guild %s', guild.id)


@client.event
async def on_message(message):
    """Handle messages in music channels."""
    logger.debug(
        "on_message event in guild %s with content: %s",
        getattr(message.guild, 'id', 'DM'),
        message.content,
    )
    if message.author == client.user:
        return

    if not message.guild:
        return

    guild_id = str(message.guild.id)
    guild_data = client.guilds_data.get(guild_id)

    if not guild_data or not guild_data.get('channel_id'):
        try:
            guild_data, _, _ = await ensure_guild_music_panel(message.guild, create_channel=False)
        except Exception:
            logger.exception('Failed to auto-recover guild setup for guild %s', guild_id)
            guild_data = None

    if guild_data:
        channel_id = guild_data.get('channel_id')
        if channel_id and message.channel.id == int(channel_id):
            try:
                await message.delete()
            except discord.Forbidden:
                logger.warning(f"Permission error: Cannot delete message {message.id}")
            except discord.HTTPException as e:
                logger.warning(f"Failed to delete message {message.id}: {e}")

            from commands.music_commands import process_play_request

            response_message = await process_play_request(
                message.author,
                message.guild,
                message.channel,
                message.content,
                client,
                queue_manager,
                player_manager,
                data_manager,
            )

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
                await asyncio.sleep(5)
                try:
                    await sent_msg.delete()
                except Exception:
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

    loop = asyncio.get_event_loop()

    def handle_loop_exception(loop, context):
        logger.exception(
            f"Unhandled exception in event loop: {context.get('message')}",
            exc_info=context.get('exception'),
        )

    loop.set_exception_handler(handle_loop_exception)

    async def shutdown():
        logger.info('Shutting down bot gracefully...')
        try:
            await health_monitor.stop()
            for guild_id in list(player_manager.voice_clients.keys()):
                await player_manager.disconnect_voice_client(guild_id, cleanup_tasks=True)
            await data_manager.save_guilds_data(client)
            logger.info('Graceful shutdown completed')
        except Exception:
            logger.exception('Error during shutdown')
        finally:
            await client.close()

    def signal_handler(signum, frame):
        logger.info(f'Received signal {signum}, initiating shutdown...')
        asyncio.run_coroutine_threadsafe(shutdown(), loop)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        client.run(token, log_handler=None)
    except KeyboardInterrupt:
        logger.info('Bot stopped by keyboard interrupt')
    except Exception:
        logger.exception('Bot crashed')
        raise


if __name__ == '__main__':
    main()
