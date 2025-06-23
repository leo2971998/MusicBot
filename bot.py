import discord
from discord.ext import commands
import logging
import asyncio
import os
from config import TOKEN, LOG_LEVEL, LOG_FORMAT, PlaybackMode
from managers.data_manager import GuildDataManager
from managers.player_manager import PlayerManager
from managers.queue_manager import QueueManager

# Setup logging
logging.basicConfig(level=getattr(logging, LOG_LEVEL), format=LOG_FORMAT)
logger = logging.getLogger(__name__)

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
client = commands.Bot(command_prefix='!', intents=intents)

# Initialize managers
data_manager = GuildDataManager()
player_manager = PlayerManager()
queue_manager = QueueManager()

# Global data structures
client.guilds_data = {}
client.playback_modes = {}

@client.event
async def on_ready():
    """Bot startup event"""
    logger.info(f'{client.user} is now jamming!')

    # Load saved data
    await data_manager.load_guilds_data(client)

    # Clean up and restore guild states
    await restore_guild_states()

    # Sync slash commands
    try:
        synced = await client.tree.sync()
        logger.info(f"Synced {len(synced)} slash commands")
    except Exception as e:
        logger.error(f"Failed to sync commands: {e}")

async def restore_guild_states():
    """Restore guild states on bot restart"""
    guilds_to_remove = []
    restored_count = 0

    for guild_id in list(client.guilds_data.keys()):
        guild_data = client.guilds_data[guild_id]
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

        # Restore stable message
        if await restore_stable_message(guild_id, guild_data, channel):
            restored_count += 1

    # Clean up invalid guilds
    for guild_id in guilds_to_remove:
        del client.guilds_data[guild_id]
        client.playback_modes.pop(guild_id, None)
        queue_manager.cleanup_guild(guild_id)

    if guilds_to_remove:
        await data_manager.save_guilds_data(client)
        logger.info(f"Cleaned up {len(guilds_to_remove)} invalid guilds")

    logger.info(f"Restored {restored_count} guild states")

async def restore_stable_message(guild_id: str, guild_data: dict, channel: discord.TextChannel) -> bool:
    """Restore or create the stable message for a guild"""
    try:
        stable_message_id =