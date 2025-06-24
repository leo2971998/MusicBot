import asyncio
import logging
from typing import Dict, Optional, Callable
import discord
from discord.ext import commands

logger = logging.getLogger(__name__)

class PlayerManager:
    """Improved player management with better error handling and cleanup"""

    def __init__(self):
        self.voice_clients: Dict[str, discord.VoiceClient] = {}
        self.active_tasks: Dict[str, Dict[str, asyncio.Task]] = {}

    async def get_or_create_voice_client(self, guild_id: str, user_voice_channel: discord.VoiceChannel) -> Optional[discord.VoiceClient]:
        """Get existing voice client or create new one with proper error handling"""
        try:
            voice_client = self.voice_clients.get(guild_id)

            if voice_client:
                if voice_client.channel != user_voice_channel:
                    if not voice_client.is_playing() and not voice_client.is_paused():
                        logger.info(
                            f"Moving voice client in guild {guild_id} to {user_voice_channel}"
                        )
                        await voice_client.move_to(user_voice_channel)
                    else:
                        logger.info(
                            f"Voice client already playing in {voice_client.channel}; not moving"
                        )
                return voice_client
            else:
                logger.info(f"Connecting to voice channel {user_voice_channel} in guild {guild_id}")
                voice_client = await user_voice_channel.connect()
                self.voice_clients[guild_id] = voice_client
                return voice_client

        except discord.ClientException as e:
            logger.error(f"ClientException in guild {guild_id}: {e}")
            raise
        except discord.errors.Forbidden as e:
            logger.error(f"Permission error in guild {guild_id}: {e}")
            raise
        except discord.errors.ConnectionClosed as e:
            logger.warning(
                f"Voice connection closed unexpectedly in guild {guild_id}: {e}"
            )
            self.voice_clients.pop(guild_id, None)
            raise
        except Exception as e:
            logger.error(
                f"Unexpected error connecting to voice in guild {guild_id}: {e}"
            )
            self.voice_clients.pop(guild_id, None)
            raise

    async def disconnect_voice_client(self, guild_id: str, cleanup_tasks: bool = True) -> bool:
        """Safely disconnect voice client and cleanup resources"""
        try:
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
            return True

        except Exception as e:
            logger.error(f"Error playing audio in guild {guild_id}: {e}")
            return False

    async def health_check(self) -> Dict[str, bool]:
        """Check health of all voice clients"""
        health_status = {}

        for guild_id, voice_client in self.voice_clients.items():
            try:
                is_healthy = (
                        voice_client.is_connected() and
                        voice_client.channel is not None
                )
                health_status[guild_id] = is_healthy

                if not is_healthy:
                    logger.warning(f"Unhealthy voice client in guild {guild_id}")

            except Exception as e:
                logger.error(f"Health check error for guild {guild_id}: {e}")
                health_status[guild_id] = False

        return health_status
