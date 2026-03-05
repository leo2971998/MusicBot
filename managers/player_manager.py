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
        self.connection_locks: Dict[str, asyncio.Lock] = {}

    def _get_connection_lock(self, guild_id: str) -> asyncio.Lock:
        lock = self.connection_locks.get(guild_id)
        if lock is None:
            lock = asyncio.Lock()
            self.connection_locks[guild_id] = lock
        return lock

    async def get_or_create_voice_client(self, guild_id: str, user_voice_channel: discord.VoiceChannel) -> Optional[discord.VoiceClient]:
        """Get existing voice client or create new one with proper error handling"""
        lock = self._get_connection_lock(guild_id)
        async with lock:
            try:
                logger.debug(
                    f"get_or_create_voice_client called for guild {guild_id} in channel {user_voice_channel}"
                )
                voice_client = self.voice_clients.get(guild_id)

                permissions = user_voice_channel.permissions_for(user_voice_channel.guild.me)
                if not permissions.connect or not permissions.speak:
                    raise commands.BotMissingPermissions([perm for perm, allowed in {
                        'connect': permissions.connect,
                        'speak': permissions.speak
                    }.items() if not allowed])

                # Drop stale cached clients before trying to reuse them.
                if voice_client and not voice_client.is_connected():
                    logger.warning(
                        f"Discarding stale voice client in guild {guild_id}"
                    )
                    self.voice_clients.pop(guild_id, None)
                    voice_client = None

                if voice_client:
                    if voice_client.channel != user_voice_channel:
                        if not voice_client.is_playing() and not voice_client.is_paused():
                            logger.info(
                                f"Moving voice client in guild {guild_id} to {user_voice_channel}"
                            )
                            try:
                                await voice_client.move_to(user_voice_channel)
                            except discord.errors.ConnectionClosed as e:
                                logger.warning(
                                    f"Voice move failed in guild {guild_id} due to closed connection: {e}"
                                )
                                try:
                                    await voice_client.disconnect()
                                except Exception:
                                    logger.debug(
                                        f"Ignoring disconnect error while cleaning up stale voice client in guild {guild_id}"
                                    )
                                self.voice_clients.pop(guild_id, None)
                                voice_client = None
                        else:
                            logger.info(
                                f"Voice client already playing in {voice_client.channel}; not moving"
                            )

                    if voice_client:
                        return voice_client

                # Connect with guarded retries to avoid transient handshake failures.
                for attempt in range(1, 5):
                    try:
                        logger.info(
                            f"Connecting to voice channel {user_voice_channel} in guild {guild_id} (attempt {attempt}/4)"
                        )
                        voice_client = await user_voice_channel.connect(
                            timeout=20.0,
                            reconnect=False,
                            self_deaf=True,
                        )

                        for _ in range(10):
                            if voice_client.is_connected():
                                break
                            await asyncio.sleep(0.2)

                        if not voice_client.is_connected():
                            raise ConnectionError("Voice client did not become connected")

                        logger.debug(
                            f"Voice client connected status in guild {guild_id}: {voice_client.is_connected()}"
                        )
                        self.voice_clients[guild_id] = voice_client
                        return voice_client

                    except discord.errors.ConnectionClosed as e:
                        close_code = getattr(e, "code", None)
                        logger.warning(
                            f"Voice connection closed in guild {guild_id} (attempt {attempt}/4, code={close_code}): {e}"
                        )
                        self.voice_clients.pop(guild_id, None)
                        stale_client = user_voice_channel.guild.voice_client
                        if stale_client:
                            try:
                                await stale_client.disconnect()
                            except Exception:
                                logger.debug(
                                    f"Ignoring stale voice disconnect error in guild {guild_id}"
                                )

                        # Force a clean server-side voice state reset before retry.
                        try:
                            await user_voice_channel.guild.change_voice_state(channel=None)
                        except Exception:
                            logger.debug(
                                f"Ignoring guild voice-state reset error in guild {guild_id}"
                            )

                        if attempt < 4:
                            backoff = 2.5 * attempt if close_code == 4017 else 1.5 * attempt
                            await asyncio.sleep(backoff)
                            continue
                        raise
                    except discord.ClientException as e:
                        logger.error(f"ClientException in guild {guild_id}: {e}")
                        self.voice_clients.pop(guild_id, None)
                        if attempt < 4:
                            await asyncio.sleep(1.0)
                            continue
                        raise
                    except Exception as e:
                        logger.error(
                            f"Unexpected connect error in guild {guild_id} (attempt {attempt}/4): {e}"
                        )
                        self.voice_clients.pop(guild_id, None)
                        if attempt < 4:
                            await asyncio.sleep(1.0)
                            continue
                        raise

                return None

            except discord.errors.Forbidden as e:
                logger.error(f"Permission error in guild {guild_id}: {e}")
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
            logger.debug(f"disconnect_voice_client called for guild {guild_id}")
            voice_client = self.voice_clients.get(guild_id)
            if voice_client:
                if voice_client.is_connected():
                    await voice_client.disconnect()
                self.voice_clients.pop(guild_id, None)
                logger.info(f"Disconnected voice client in guild {guild_id}")

            if cleanup_tasks:
                await self.cleanup_guild_tasks(guild_id)

            self.connection_locks.pop(guild_id, None)

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

    def cancel_task(self, guild_id: str, task_name: str) -> None:
        """Cancel a registered task if it exists"""
        logger.debug(f"Cancelling task {task_name} for guild {guild_id}")
        guild_tasks = self.active_tasks.get(guild_id)
        if not guild_tasks:
            return

        task = guild_tasks.pop(task_name, None)
        if task and not task.done():
            task.cancel()

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
