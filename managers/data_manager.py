import asyncio
import json
import logging
import os
from typing import Dict, Optional, Callable
import discord
from discord.ext import commands

logger = logging.getLogger(__name__)

class GuildDataManager:
    """Manages persistent data for Discord guilds"""

    def __init__(self, data_file: str = "guilds_data.json"):
        self.data_file = data_file

    async def load_guilds_data(self, client: commands.Bot) -> None:
        """Load guild data from persistent storage"""
        try:
            logger.debug(f"Loading guild data from {self.data_file}")
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r') as f:
                    client.guilds_data = json.load(f)
                logger.info(f"Loaded data for {len(client.guilds_data)} guilds")
            else:
                client.guilds_data = {}
                logger.info("No existing guild data found, starting fresh")
        except Exception as e:
            logger.error(f"Error loading guild data: {e}")
            client.guilds_data = {}

    async def save_guilds_data(self, client: commands.Bot) -> None:
        """Save guild data to persistent storage"""
        try:
            logger.debug(f"Saving guild data to {self.data_file}")
            # Create a copy of the data without the stable_message objects
            # (since they can't be serialized)
            data_to_save = {}
            for guild_id, guild_data in client.guilds_data.items():
                cleaned_data = {}
                for key, value in guild_data.items():
                    # Skip non-serializable objects like discord.Message
                    if key != 'stable_message' and not isinstance(value, discord.Message):
                        cleaned_data[key] = value
                data_to_save[guild_id] = cleaned_data

            with open(self.data_file, 'w') as f:
                json.dump(data_to_save, f, indent=2)
            logger.info(f"Saved data for {len(data_to_save)} guilds")
        except Exception as e:
            logger.error(f"Error saving guild data: {e}")

    def get_guild_data(self, client: commands.Bot, guild_id: str) -> dict:
        """Get data for a specific guild"""
        return client.guilds_data.get(guild_id, {})

    def set_guild_data(self, client: commands.Bot, guild_id: str, data: dict) -> None:
        """Set data for a specific guild"""
        if guild_id not in client.guilds_data:
            client.guilds_data[guild_id] = {}
        client.guilds_data[guild_id].update(data)

    def remove_guild_data(self, client: commands.Bot, guild_id: str) -> None:
        """Remove data for a specific guild"""
        client.guilds_data.pop(guild_id, None)


class PlayerManager:
    """Improved player management with better error handling and cleanup"""

    def __init__(self):
        self.voice_clients: Dict[str, discord.VoiceClient] = {}
        self.active_tasks: Dict[str, Dict[str, asyncio.Task]] = {}

    async def get_or_create_voice_client(self, guild_id: str, user_voice_channel: discord.VoiceChannel) -> Optional[discord.VoiceClient]:
        """Get existing voice client or create new one with proper error handling"""
        try:
            logger.debug(
                f"get_or_create_voice_client called for guild {guild_id} in channel {user_voice_channel}"
            )
            permissions = user_voice_channel.permissions_for(user_voice_channel.guild.me)
            if not permissions.connect or not permissions.speak:
                raise commands.BotMissingPermissions([perm for perm, allowed in {
                    'connect': permissions.connect,
                    'speak': permissions.speak
                }.items() if not allowed])

            voice_client = self.voice_clients.get(guild_id)

            if voice_client:
                if voice_client.channel != user_voice_channel:
                    logger.info(f"Moving voice client in guild {guild_id} to {user_voice_channel}")
                    await voice_client.move_to(user_voice_channel)
                return voice_client
            else:
                logger.info(f"Connecting to voice channel {user_voice_channel} in guild {guild_id}")
                voice_client = await user_voice_channel.connect()
                # Wait briefly to ensure the connection is fully ready
                for _ in range(5):
                    if voice_client.is_connected():
                        break
                    await asyncio.sleep(0.2)
                logger.debug(
                    f"Voice client connected status in guild {guild_id}: {voice_client.is_connected()}"
                )
                self.voice_clients[guild_id] = voice_client
                return voice_client

        except discord.ClientException as e:
            logger.error(f"ClientException in guild {guild_id}: {e}")
            raise
        except discord.errors.Forbidden as e:
            logger.error(f"Permission error in guild {guild_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error connecting to voice in guild {guild_id}: {e}")
            raise

    async def disconnect_voice_client(self, guild_id: str, cleanup_tasks: bool = True) -> bool:
        """Safely disconnect voice client and cleanup resources"""
        try:
            logger.debug(f"disconnect_voice_client called for guild {guild_id}")
            voice_client = self.voice_clients.get(guild_id)
            if voice_client:
                if voice_client.is_connected():
                    await voice_client.disconnect()
                self.voice_clients.pop(guild_id, None)
                logger.info(f"Disconnected voice client in guild {guild_id}")

            if cleanup_tasks:
                await self.cleanup_guild_tasks(guild_id)

            return True

        except Exception as e:
            logger.error(f"Error disconnecting voice client in guild {guild_id}: {e}")
            return False

    async def cleanup_guild_tasks(self, guild_id: str):
        """Clean up all async tasks for a guild"""
        logger.debug(f"cleanup_guild_tasks called for guild {guild_id}")
        if guild_id in self.active_tasks:
            for task_name, task in self.active_tasks[guild_id].items():
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                    logger.info(f"Cancelled task {task_name} for guild {guild_id}")

            del self.active_tasks[guild_id]

    def add_task(self, guild_id: str, task_name: str, task: asyncio.Task):
        """Register a task for cleanup"""
        logger.debug(f"Adding task {task_name} for guild {guild_id}")
        if guild_id not in self.active_tasks:
            self.active_tasks[guild_id] = {}

        # Cancel existing task with same name
        if task_name in self.active_tasks[guild_id]:
            old_task = self.active_tasks[guild_id][task_name]
            if not old_task.done():
                old_task.cancel()

        self.active_tasks[guild_id][task_name] = task

    async def play_audio_source(self, guild_id: str, source, after_callback: Optional[Callable] = None) -> bool:
        """Play audio source with improved error handling"""
        try:
            logger.debug(f"play_audio_source called for guild {guild_id}")
            voice_client = self.voice_clients.get(guild_id)
            if not voice_client:
                logger.error(f"No voice client for guild {guild_id}")
                return False

            if voice_client.is_playing():
                voice_client.stop()
                await asyncio.sleep(0.1)  # Brief pause to ensure cleanup

            # Wrap the after callback with error handling
            def safe_after_callback(error):
                if error:
                    logger.error(f"Player error in guild {guild_id}: {error}")
                if after_callback:
                    try:
                        after_callback(error)
                    except Exception as e:
                        logger.error(f"Error in after callback for guild {guild_id}: {e}")

            voice_client.play(source, after=safe_after_callback)
            logger.info(f"Started playing audio in guild {guild_id}")
            logger.debug(
                f"Voice client status after play in guild {guild_id}: playing={voice_client.is_playing()}"
            )
            return True

        except Exception as e:
            logger.error(f"Error playing audio in guild {guild_id}: {e}")
            return False

    async def health_check(self) -> Dict[str, bool]:
        """Check health of all voice clients"""
        health_status = {}
        logger.debug("Running voice client health check")

        for guild_id, voice_client in self.voice_clients.items():
            try:
                is_healthy = (
                        voice_client.is_connected() and
                        voice_client.channel is not None
                )
                health_status[guild_id] = is_healthy
                logger.debug(
                    f"Health status for guild {guild_id}: {is_healthy}"
                )

                if not is_healthy:
                    logger.warning(f"Unhealthy voice client in guild {guild_id}")

            except Exception as e:
                logger.error(f"Health check error for guild {guild_id}: {e}")
                health_status[guild_id] = False

        logger.debug(f"Health check results: {health_status}")
        return health_status
