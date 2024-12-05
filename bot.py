import discord
from discord.ext import commands
from discord.ui import Button, View, Modal, TextInput
from discord import Embed, ButtonStyle
import os
import asyncio
import yt_dlp
from dotenv import load_dotenv
import json
import random
from enum import Enum
import logging
from asyncio import Lock, TimeoutError
from contextlib import asynccontextmanager

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('musicbot.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger('MusicBot')

# Load the environment variables
load_dotenv()
TOKEN = os.getenv("discord_token") or "YOUR_DISCORD_BOT_TOKEN"

# Set up bot intents and command prefix
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.voice_states = True  # Enable voice_states intent

# Data persistence
DATA_FILE = 'guilds_data.json'
MAX_QUEUE_SIZE = 500  # Limit the queue size to prevent memory leaks

# Define playback modes using Enum
class PlaybackMode(Enum):
    NORMAL = 'normal'
    REPEAT_ONE = 'repeat_one'

# Adjusted yt_dlp options
yt_dl_options = {
    "format": "bestaudio/best",
    "noplaylist": False,
    "quiet": True,
    "default_search": "auto",
    "extract_flat": False,
    "nocheckcertificate": True,
    "geo_bypass": True,
}
ytdl = yt_dlp.YoutubeDL(yt_dl_options)

# FFmpeg options for audio playback
ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

def format_time(seconds: int) -> str:
    minutes = seconds // 60
    seconds = seconds % 60
    return f"{minutes:02d}:{seconds:02d}"

class ThreadSafeQueue:
    def __init__(self):
        self._queue = []
        self._lock = asyncio.Lock()

    async def add(self, item, position=None):
        async with self._lock:
            if len(self._queue) >= MAX_QUEUE_SIZE:
                return False
            if position is not None:
                self._queue.insert(min(position, len(self._queue)), item)
            else:
                self._queue.append(item)
            return True

    async def remove(self, index):
        async with self._lock:
            if 0 <= index < len(self._queue):
                return self._queue.pop(index)
            return None

    async def clear(self):
        async with self._lock:
            self._queue.clear()

    async def get_all(self):
        async with self._lock:
            return self._queue.copy()

    async def shuffle(self):
        async with self._lock:
            random.shuffle(self._queue)

    async def __len__(self):
        async with self._lock:
            return len(self._queue)

class MusicBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(command_prefix=".", intents=intents, *args, **kwargs)
        self.guild_locks = {}
        self.guilds_data = {}
        self.queues = {}
        self.voice_clients_dict = {}
        self.playback_modes = {}
        self.data_lock = Lock()
        self.active_tasks = set()
        self.voice_state_heartbeat_task = self.loop.create_task(self.voice_state_heartbeat())

    def get_guild_lock(self, guild_id):
        if guild_id not in self.guild_locks:
            self.guild_locks[guild_id] = Lock()
        return self.guild_locks[guild_id]

    @asynccontextmanager
    async def guild_lock_timeout(self, guild_id: str, timeout: float = 30.0):
        lock = self.get_guild_lock(guild_id)
        try:
            await asyncio.wait_for(lock.acquire(), timeout)
            yield
        except TimeoutError:
            logger.error(f"Lock acquisition timeout for guild {guild_id}")
            raise
        finally:
            if lock.locked():
                lock.release()

    async def save_guilds_data(self):
        async with self.data_lock:
            # Prepare data for saving
            serializable_data = {}
            for guild_id, guild_data in self.guilds_data.items():
                data_to_save = guild_data.copy()
                data_to_save.pop('stable_message', None)
                data_to_save.pop('progress_task', None)
                data_to_save.pop('disconnect_task', None)
                serializable_data[guild_id] = data_to_save
            data = {
                'guilds_data': serializable_data,
                'playback_modes': {gid: mode.value for gid, mode in self.playback_modes.items()}
            }
            # Save to file atomically
            temp_file = f"{DATA_FILE}.tmp"
            try:
                with open(temp_file, 'w') as f:
                    json.dump(data, f)
                os.replace(temp_file, DATA_FILE)
            except (IOError, OSError) as e:
                logger.error(f"Failed to save guild data: {e}")
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except OSError:
                        pass
                raise

    async def load_guilds_data(self):
        if os.path.exists(DATA_FILE):
            async with self.data_lock:
                with open(DATA_FILE, 'r') as f:
                    try:
                        data = json.load(f)
                        self.guilds_data = data.get('guilds_data', {})
                        # Map old playback modes to new ones
                        old_playback_modes = data.get('playback_modes', {})
                        self.playback_modes = {}
                        for gid, mode in old_playback_modes.items():
                            if mode == 'repeat':
                                self.playback_modes[gid] = PlaybackMode.REPEAT_ONE
                            else:
                                self.playback_modes[gid] = PlaybackMode.NORMAL
                    except json.JSONDecodeError:
                        logger.error("Invalid JSON in guilds_data.json. Initializing with empty data.")
                        self.guilds_data = {}
                        self.playback_modes = {}
                    except ValueError as e:
                        logger.error(f"Invalid playback mode value in guilds_data.json: {e}")
                        self.playback_modes = {}
        else:
            self.guilds_data = {}
            self.playback_modes = {}

    async def on_ready(self):
        await self.tree.sync()
        logger.info(f'{self.user} is now jamming!')
        await self.load_guilds_data()
        for guild_id, guild_data in self.guilds_data.items():
            channel_id = guild_data.get('channel_id')
            stable_message_id = guild_data.get('stable_message_id')
            guild = self.get_guild(int(guild_id))
            if guild:
                channel = guild.get_channel(int(channel_id))
                if channel:
                    try:
                        stable_message = await channel.fetch_message(int(stable_message_id))
                        self.guilds_data[guild_id]['stable_message'] = stable_message
                    except Exception as e:
                        logger.error(f"Error fetching stable message for guild {guild_id}: {e}")
                        await self.recover_stable_message(guild_id)
                    await self.update_stable_message(int(guild_id))

    async def recover_stable_message(self, guild_id: str) -> bool:
        try:
            async with self.guild_lock_timeout(guild_id):
                guild_data = self.guilds_data.get(guild_id)
                if not guild_data:
                    return False

                channel_id = guild_data.get('channel_id')
                channel = self.get_channel(int(channel_id)) if channel_id else None

                if not channel:
                    return False

                new_message = await channel.send('🎶 **Music Bot UI Initialized** 🎶')
                guild_data['stable_message'] = new_message
                guild_data['stable_message_id'] = new_message.id
                await self.save_guilds_data()
                await self.update_stable_message(guild_id)
                return True

        except Exception as e:
            logger.error(f"Error recovering stable message for guild {guild_id}: {e}")
            return False

    async def update_stable_message(self, guild_id):
        guild_id = str(guild_id)
        async with self.guild_lock_timeout(guild_id):
            try:
                guild_data = self.guilds_data.get(guild_id)
                if not guild_data:
                    return
                stable_message = guild_data.get('stable_message')
                channel_id = guild_data.get('channel_id')
                channel = self.get_channel(int(channel_id)) if channel_id else None
                if not channel:
                    return
                if not stable_message:
                    # Recreate the stable message
                    await self.recover_stable_message(guild_id)
                    return

                queue = await self.get_queue(guild_id)
                voice_client = self.voice_clients_dict.get(guild_id)

                # Now Playing Embed
                if voice_client and voice_client.is_connected() and (voice_client.is_playing() or voice_client.is_paused()):
                    current_song = guild_data.get('current_song')
                    if current_song:
                        duration = guild_data.get('song_duration', 0)
                        duration_str = format_time(duration)

                        now_playing_embed = Embed(
                            title='🎶 Now Playing',
                            description=f"**[{current_song['title']}]({current_song['webpage_url']})**",
                            color=0x1db954
                        )
                        now_playing_embed.set_thumbnail(url=current_song.get('thumbnail'))
                        now_playing_embed.add_field(name='Duration', value=f"`{duration_str}`", inline=False)
                        # Add requester
                        now_playing_embed.add_field(name='Requested by', value=current_song.get('requester', 'Unknown'), inline=False)

                        # Add playback mode to the embed
                        playback_mode = self.playback_modes.get(guild_id, PlaybackMode.NORMAL).name.replace('_', ' ').title()
                        now_playing_embed.set_footer(text=f'Playback Mode: {playback_mode}')
                    else:
                        now_playing_embed = Embed(
                            title='🎶 Now Playing',
                            description='No music is currently playing.',
                            color=0x1db954
                        )
                else:
                    now_playing_embed = Embed(
                        title='🎶 Now Playing',
                        description='No music is currently playing.',
                        color=0x1db954
                    )

                # Queue Embed
                if queue:
                    queue_description = '\n'.join(
                        [f"{idx + 1}. **[{song['title']}]({song['webpage_url']})** — *{song.get('requester', 'Unknown')}*" for idx, song in enumerate(queue)]
                    )
                else:
                    queue_description = 'No songs in the queue.'
                queue_embed = Embed(
                    title='📜 Current Queue',
                    description=queue_description,
                    color=0x1db954
                )
                queue_embed.set_footer(text=f"Total songs in queue: {len(queue)}")

                # Create the MusicControlView
                view = MusicControlView(queue, self)

                try:
                    await stable_message.edit(content=None, embeds=[now_playing_embed, queue_embed], view=view)
                except discord.NotFound:
                    # Message was deleted, recover it
                    await self.recover_stable_message(guild_id)
                except discord.HTTPException as e:
                    logger.error(f"Failed to update stable message in guild {guild_id}: {e}")

                await self.save_guilds_data()
            except Exception as e:
                logger.exception(f"Error in update_stable_message for guild {guild_id}: {e}")

    async def clear_channel_messages(self, channel, stable_message_id):
        # Make sure stable_message_id is valid
        if not stable_message_id:
            return
        try:
            async for message in channel.history(limit=100):
                if message.id != stable_message_id and not message.pinned:
                    try:
                        await message.delete()
                    except discord.Forbidden:
                        logger.warning(f"Permission error: Cannot delete message {message.id}")
                    except discord.HTTPException as e:
                        logger.error(f"Failed to delete message {message.id}: {e}")
        except Exception as e:
            logger.exception(f"Error clearing messages in channel {channel.id}: {e}")

    async def cancel_disconnect_task(self, guild_id):
        async with self.guild_lock_timeout(guild_id):
            disconnect_task = self.guilds_data.get(guild_id, {}).get('disconnect_task')
            if disconnect_task:
                disconnect_task.cancel()
                self.guilds_data[guild_id]['disconnect_task'] = None

    async def play_next(self, guild_id):
        guild_id = str(guild_id)
        async with self.guild_lock_timeout(guild_id):
            # Cancel the progress updater task if you have one
            progress_task = self.guilds_data[guild_id].get('progress_task')
            if progress_task:
                progress_task.cancel()
                self.guilds_data[guild_id]['progress_task'] = None

            playback_mode = self.playback_modes.get(guild_id, PlaybackMode.NORMAL)

            if playback_mode == PlaybackMode.REPEAT_ONE:
                # Re-play the current song
                current_song = self.guilds_data[guild_id]['current_song']
                await self.play_song(guild_id, current_song)
            else:
                song_info = await self.pop_queue(guild_id)
                if song_info:
                    self.guilds_data[guild_id]['current_song'] = song_info
                    await self.play_song(guild_id, song_info)
                else:
                    # No more songs in the queue
                    self.guilds_data[guild_id]['current_song'] = None

                    # Schedule a delayed disconnect
                    if not self.guilds_data[guild_id].get('disconnect_task'):
                        disconnect_task = await self.schedule_task(self.disconnect_after_delay(guild_id, delay=300))  # 5 minutes
                        self.guilds_data[guild_id]['disconnect_task'] = disconnect_task

                    # Reset playback mode to NORMAL
                    self.playback_modes[guild_id] = PlaybackMode.NORMAL
                    await self.update_stable_message(guild_id)

    async def play_song(self, guild_id, song_info):
        guild_id = str(guild_id)
        try:
            async with self.guild_lock_timeout(guild_id):
                voice_client = self.voice_clients_dict.get(guild_id)

                if not voice_client or not voice_client.is_connected():
                    logger.error(f"No voice client for guild {guild_id}")
                    await self.play_next(guild_id)
                    return

                # Cancel any scheduled disconnect task
                await self.cancel_disconnect_task(guild_id)

                song_url = song_info.get('url')
                if not song_url and 'formats' in song_info:
                    # Get the best audio format
                    for fmt in song_info['formats']:
                        if fmt.get('acodec') != 'none':
                            song_url = fmt['url']
                            break
                if not song_url:
                    logger.error(f"No valid audio URL found for {song_info.get('title')}")
                    await self.play_next(guild_id)
                    return

                # Stop any currently playing audio
                if voice_client.is_playing() or voice_client.is_paused():
                    voice_client.stop()

                try:
                    player = discord.FFmpegPCMAudio(song_url, **ffmpeg_options)
                except Exception as e:
                    logger.exception(f"Error creating FFmpegPCMAudio: {e}")
                    await self.play_next(guild_id)
                    return

                def after_playing(error):
                    if error:
                        logger.error(f"Error occurred while playing: {error}")
                    future = asyncio.run_coroutine_threadsafe(self.play_next(guild_id), self.loop)
                    try:
                        future.result()
                    except Exception as e:
                        logger.error(f"Error in play_next: {e}")

                voice_client.play(
                    player,
                    after=after_playing
                )
                channel_id = self.guilds_data[guild_id]['channel_id']
                channel = self.get_channel(int(channel_id))
                await channel.send(f"🎶 Now playing: **{song_info.get('title', 'Unknown title')}**")
                self.guilds_data[guild_id]['current_song'] = song_info

                # Record the song duration
                self.guilds_data[guild_id]['song_duration'] = song_info.get('duration', 0)

                await self.update_stable_message(guild_id)
                await self.save_guilds_data()
        except Exception as e:
            logger.exception(f"Error in play_song: {e}")
            await self.play_next(guild_id)

    async def process_play_request(self, user, guild, channel, link, interaction=None, play_next=False):
        guild_id = str(guild.id)
        async with self.guild_lock_timeout(guild_id):
            # Initialize guild data if not present
            if guild_id not in self.guilds_data:
                self.guilds_data[guild_id] = {}

            # Ensure the user is a Member, not just a User
            if not isinstance(user, discord.Member):
                user = guild.get_member(user.id) or await guild.fetch_member(user.id)

            # Refresh the member's voice state
            await guild.chunk()
            user = guild.get_member(user.id)

            user_voice_channel = user.voice.channel if user.voice else None

            if not user_voice_channel:
                msg = "❌ You are not connected to a voice channel."
                return msg

            # Ensure voice connection
            connected = await self.ensure_voice_connection(user_voice_channel, guild_id)
            if not connected:
                msg = "❌ Failed to connect to the voice channel."
                return msg

            voice_client = self.voice_clients_dict.get(guild_id)

            # Cancel any scheduled disconnect task
            await self.cancel_disconnect_task(guild_id)

            try:
                data = await self.extract_song_info(link)
            except ValueError as e:
                return f"❌ {e}"

            # Handle single video
            if 'entries' not in data:
                song_info = data
                song_info['requester'] = user.mention  # Add requester information

                # Play or queue the song
                if not voice_client.is_playing() and not voice_client.is_paused():
                    self.guilds_data[guild_id]['current_song'] = song_info
                    await self.play_song(guild_id, song_info)
                    msg = f"🎶 Now playing: **{song_info.get('title', 'Unknown title')}**"
                else:
                    added = await self.add_to_queue(guild_id, song_info, play_next)
                    if not added:
                        msg = f"❌ The queue is full. Cannot add more songs."
                        return msg
                    if play_next:
                        msg = f"➕ Added to play next: **{song_info.get('title', 'Unknown title')}**"
                    else:
                        msg = f"➕ Added to queue: **{song_info.get('title', 'Unknown title')}**"
            else:
                # Playlist detected
                playlist_entries = data['entries']
                added_songs = []
                if play_next:
                    # Reverse the entries to maintain order when inserting at the front
                    for entry in reversed(playlist_entries):
                        if entry is None:
                            continue  # Skip if entry is None
                        song_info = entry
                        song_info['requester'] = user.mention  # Add requester information
                        added = await self.add_to_queue(guild_id, song_info, play_next)
                        if not added:
                            msg = f"❌ The queue is full. Cannot add more songs."
                            return msg
                        added_songs.append(song_info['title'])
                    msg = f"🎶 Added playlist **{data.get('title', 'Unknown playlist')}** with {len(added_songs)} songs to play next."
                else:
                    for entry in playlist_entries:
                        if entry is None:
                            continue  # Skip if entry is None
                        song_info = entry
                        song_info['requester'] = user.mention  # Add requester information
                        added = await self.add_to_queue(guild_id, song_info)
                        if not added:
                            msg = f"❌ The queue is full. Cannot add more songs."
                            return msg
                        added_songs.append(song_info['title'])
                    msg = f"🎶 Added playlist **{data.get('title', 'Unknown playlist')}** with {len(added_songs)} songs to the queue."

                # Start playing if not already playing
                if not voice_client.is_playing() and not voice_client.is_paused():
                    await self.play_next(guild_id)

            # Clear messages except the stable message
            guild_data = self.guilds_data.get(guild_id)
            if guild_data:
                stable_message_id = guild_data.get('stable_message_id')
                channel_id = guild_data.get('channel_id')
                if stable_message_id and channel_id:
                    channel = self.get_channel(int(channel_id))
                    await self.clear_channel_messages(channel, int(stable_message_id))

            await self.update_stable_message(guild_id)
            return msg

    async def extract_song_info(self, query: str) -> dict:
        try:
            if 'list=' not in query and 'watch?v=' not in query and 'youtu.be/' not in query:
                search_query = f"ytsearch:{query}"
                data = await self.loop.run_in_executor(None, lambda: ytdl.extract_info(search_query, download=False))
                if not data.get('entries'):
                    raise ValueError("No results found.")
                return data['entries'][0]
            else:
                data = await self.loop.run_in_executor(None, lambda: ytdl.extract_info(query, download=False))
                return data
        except yt_dlp.DownloadError as e:
            logger.error(f"yt_dlp error: {e}")
            raise ValueError(f"Failed to fetch video information: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error in extract_song_info: {e}")
            raise ValueError("An unexpected error occurred while processing the video.")

    async def add_to_queue(self, guild_id: str, song_info: dict, play_next: bool = False) -> bool:
        if guild_id not in self.queues:
            self.queues[guild_id] = ThreadSafeQueue()
        queue = self.queues[guild_id]
        if play_next:
            return await queue.add(song_info, position=0)
        else:
            return await queue.add(song_info)

    async def remove_from_queue(self, guild_id: str, index: int):
        if guild_id in self.queues:
            queue = self.queues[guild_id]
            return await queue.remove(index)
        return None

    async def pop_queue(self, guild_id: str):
        if guild_id in self.queues:
            queue = self.queues[guild_id]
            return await queue.remove(0)
        return None

    async def get_queue(self, guild_id: str):
        if guild_id in self.queues:
            queue = self.queues[guild_id]
            return await queue.get_all()
        else:
            return []

    async def disconnect_after_delay(self, guild_id, delay):
        try:
            await asyncio.sleep(delay)
            voice_client = self.voice_clients_dict.get(guild_id)
            if voice_client and not voice_client.is_playing() and not voice_client.is_paused():
                await voice_client.disconnect()
                self.voice_clients_dict.pop(guild_id, None)
                # Remove the disconnect task reference
                async with self.guild_lock_timeout(guild_id):
                    self.guilds_data[guild_id]['disconnect_task'] = None
                await self.update_stable_message(guild_id)
        except asyncio.CancelledError:
            # The task was cancelled, do nothing
            pass
        except Exception as e:
            logger.error(f"Error in disconnect_after_delay for guild {guild_id}: {e}")

    async def ensure_voice_connection(self, voice_channel, guild_id: str) -> bool:
        MAX_RETRIES = 3
        retry_delay = 1.0

        for attempt in range(MAX_RETRIES):
            try:
                if voice_client := self.voice_clients_dict.get(guild_id):
                    if voice_client.is_connected():
                        if voice_client.channel != voice_channel:
                            await voice_client.move_to(voice_channel)
                        return True
                    else:
                        self.voice_clients_dict.pop(guild_id, None)

                voice_client = await voice_channel.connect(timeout=10.0)
                self.voice_clients_dict[guild_id] = voice_client
                return True

            except Exception as e:
                logger.error(f"Voice connection attempt {attempt + 1} failed for guild {guild_id}: {e}")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2
                continue

        return False

    async def schedule_task(self, coro):
        task = self.loop.create_task(coro)
        self.active_tasks.add(task)
        task.add_done_callback(self.active_tasks.discard)
        return task

    async def close(self):
        # Cancel all active tasks
        for task in self.active_tasks:
            task.cancel()
        await asyncio.gather(*self.active_tasks, return_exceptions=True)
        self.active_tasks.clear()
        await super().close()

    async def voice_state_heartbeat(self):
        while True:
            for guild_id, voice_client in list(self.voice_clients_dict.items()):
                try:
                    if not voice_client.is_connected():
                        logger.warning(f"Voice client disconnected for guild {guild_id}")
                        self.voice_clients_dict.pop(guild_id, None)
                        await self.update_stable_message(guild_id)
                except Exception as e:
                    logger.error(f"Error in voice heartbeat for guild {guild_id}: {e}")
            await asyncio.sleep(30)  # Check every 30 seconds

    async def on_voice_state_update(self, member, before, after):
        try:
            guild_id = str(member.guild.id)
            voice_client = self.voice_clients_dict.get(guild_id)

            # Bot was disconnected
            if member.id == self.user.id and after.channel is None:
                await self.cleanup_voice_state(guild_id)

            # Check if bot is alone in channel
            elif before.channel and voice_client and voice_client.channel == before.channel:
                if len([m for m in before.channel.members if not m.bot]) == 0:
                    await self.cleanup_voice_state(guild_id)

        except Exception as e:
            logger.error(f"Error in voice state update: {e}")

    async def cleanup_voice_state(self, guild_id: str):
        try:
            async with self.guild_lock_timeout(guild_id):
                if voice_client := self.voice_clients_dict.pop(guild_id, None):
                    try:
                        if voice_client.is_playing():
                            voice_client.stop()
                        if voice_client.is_connected():
                            await voice_client.disconnect()
                    except Exception as e:
                        logger.error(f"Error disconnecting voice client: {e}")

                # Clean up guild data
                guild_data = self.guilds_data.get(guild_id, {})
                if guild_data:
                    if task := guild_data.get('disconnect_task'):
                        task.cancel()
                    if task := guild_data.get('progress_task'):
                        task.cancel()
                    guild_data['current_song'] = None
                    guild_data['disconnect_task'] = None
                    guild_data['progress_task'] = None

                # Reset playback mode
                self.playback_modes[guild_id] = PlaybackMode.NORMAL

                # Clear queue
                if guild_id in self.queues:
                    await self.queues[guild_id].clear()

                await self.update_stable_message(guild_id)
                await self.save_guilds_data()

        except Exception as e:
            logger.error(f"Error in cleanup_voice_state: {e}")

    async def on_guild_remove(self, guild):
        guild_id = str(guild.id)
        try:
            async with self.guild_lock_timeout(guild_id):
                # Cleanup voice
                if voice_client := self.voice_clients_dict.pop(guild_id, None):
                    try:
                        await voice_client.disconnect()
                    except Exception as e:
                        logger.error(f"Error disconnecting voice client for guild {guild_id}: {e}")

                # Cleanup queues and data
                if guild_id in self.queues:
                    await self.queues[guild_id].clear()
                    self.queues.pop(guild_id, None)
                if guild_data := self.guilds_data.pop(guild_id, None):
                    if task := guild_data.get('disconnect_task'):
                        task.cancel()
                    if task := guild_data.get('progress_task'):
                        task.cancel()

                await self.save_guilds_data()
        except Exception as e:
            logger.error(f"Error cleaning up guild {guild_id}: {e}")

    async def on_error(self, event, *args, **kwargs):
        logger.error(f"Error in event {event}: {args} {kwargs}")
        logger.exception("Exception occurred")

class MusicControlView(View):
    def __init__(self, queue, bot):
        super().__init__(timeout=None)
        self.queue = queue
        self.bot = bot

    @discord.ui.button(label='⏸️ Pause', style=ButtonStyle.primary)
    async def pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_interaction_safely(interaction, self.pause_action)

    async def pause_action(self):
        guild_id = str(self.bot.user.guild.id)
        voice_client = self.bot.voice_clients_dict.get(guild_id)
        if voice_client and voice_client.is_connected() and voice_client.is_playing():
            voice_client.pause()
            return '⏸️ Paused the music.'
        else:
            return '❌ Nothing is playing.'

    @discord.ui.button(label='▶️ Resume', style=ButtonStyle.primary)
    async def resume_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_interaction_safely(interaction, self.resume_action)

    async def resume_action(self):
        guild_id = str(self.bot.user.guild.id)
        voice_client = self.bot.voice_clients_dict.get(guild_id)
        if voice_client and voice_client.is_connected() and voice_client.is_paused():
            voice_client.resume()
            return '▶️ Resumed the music.'
        else:
            return '❌ Nothing is paused.'

    @discord.ui.button(label='⏭️ Skip', style=ButtonStyle.primary)
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_interaction_safely(interaction, self.skip_action)

    async def skip_action(self):
        guild_id = str(self.bot.user.guild.id)
        voice_client = self.bot.voice_clients_dict.get(guild_id)
        if voice_client and voice_client.is_connected() and (voice_client.is_playing() or voice_client.is_paused()):
            voice_client.stop()
            return '⏭️ Skipped the song.'
        else:
            return '❌ Nothing is playing.'

    @discord.ui.button(label='⏹️ Stop', style=ButtonStyle.primary)
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_interaction_safely(interaction, self.stop_action)

    async def stop_action(self):
        guild_id = str(self.bot.user.guild.id)
        voice_client = self.bot.voice_clients_dict.get(guild_id)
        if voice_client:
            await voice_client.disconnect()
            self.bot.voice_clients_dict.pop(guild_id, None)
            self.bot.guilds_data[guild_id]['current_song'] = None

            # Cancel the disconnect task if it exists
            disconnect_task = self.bot.guilds_data[guild_id].get('disconnect_task')
            if disconnect_task:
                disconnect_task.cancel()
                self.bot.guilds_data[guild_id]['disconnect_task'] = None

            # Reset playback mode to NORMAL
            self.bot.playback_modes[guild_id] = PlaybackMode.NORMAL

            return '⏹️ Stopped the music and left the voice channel.'
        else:
            return '❌ Not connected to a voice channel.'

    @discord.ui.button(label='🗑️ Clear Queue', style=ButtonStyle.danger)
    async def clear_queue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_interaction_safely(interaction, self.clear_queue_action)

    async def clear_queue_action(self):
        guild_id = str(self.bot.user.guild.id)
        if guild_id in self.bot.queues:
            await self.bot.queues[guild_id].clear()
            return '🗑️ Cleared the queue.'
        else:
            return '❌ The queue is already empty.'

    @discord.ui.button(label='🔁 Normal', style=ButtonStyle.secondary)
    async def normal_mode_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_interaction_safely(interaction, self.set_normal_mode)

    async def set_normal_mode(self):
        guild_id = str(self.bot.user.guild.id)
        self.bot.playback_modes[guild_id] = PlaybackMode.NORMAL
        return 'Playback mode set to: **Normal**'

    @discord.ui.button(label='🔂 Repeat', style=ButtonStyle.secondary)
    async def repeat_one_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_interaction_safely(interaction, self.set_repeat_mode)

    async def set_repeat_mode(self):
        guild_id = str(self.bot.user.guild.id)
        self.bot.playback_modes[guild_id] = PlaybackMode.REPEAT_ONE
        return 'Playback mode set to: **Repeat**'

    @discord.ui.button(label='🔀 Shuffle', style=ButtonStyle.primary)
    async def shuffle_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_interaction_safely(interaction, self.shuffle_queue_action)

    async def shuffle_queue_action(self):
        guild_id = str(self.bot.user.guild.id)
        if guild_id in self.bot.queues:
            await self.bot.queues[guild_id].shuffle()
            return '🔀 Queue shuffled.'
        else:
            return '❌ The queue is empty.'

    @discord.ui.button(label='➕ Add Song', style=ButtonStyle.success)
    async def add_song_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = AddSongModal(interaction, self.bot)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label='➕ Play Next', style=ButtonStyle.success)
    async def add_next_song_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = AddSongModal(interaction, self.bot, play_next=True)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label='❌ Remove', style=ButtonStyle.danger)
    async def remove_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = RemoveSongModal(interaction, self.bot)
        await interaction.response.send_modal(modal)

    async def handle_interaction_safely(self, interaction: discord.Interaction, action):
        try:
            await interaction.response.defer(ephemeral=True)
            async with asyncio.timeout(5.0):
                result = await action()
            await interaction.followup.send(result, ephemeral=True)
            guild_id = str(interaction.guild.id)
            await self.bot.update_stable_message(guild_id)
        except asyncio.TimeoutError:
            await interaction.followup.send('⚠️ Operation timed out.', ephemeral=True)
        except Exception as e:
            logger.exception(f"Error handling interaction: {e}")
            await interaction.followup.send('❌ An error occurred.', ephemeral=True)

class AddSongModal(Modal):
    def __init__(self, interaction: discord.Interaction, bot, play_next=False):
        title = "Play Next" if play_next else "Add Song"
        super().__init__(title=title)
        self.interaction = interaction
        self.bot = bot
        self.play_next = play_next
        self.song_input = TextInput(
            label="Song Name or URL",
            placeholder="Enter the song name or URL",
            required=True
        )
        self.add_item(self.song_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            async with asyncio.timeout(15.0):
                song_name_or_url = self.song_input.value.strip()
                if not song_name_or_url:
                    await interaction.followup.send("❌ Please provide a song name or URL.", ephemeral=True)
                    return

                response_message = await self.bot.process_play_request(
                    interaction.user,
                    interaction.guild,
                    interaction.channel,
                    song_name_or_url,
                    interaction=interaction,
                    play_next=self.play_next
                )

                if response_message:
                    await interaction.followup.send(response_message, ephemeral=True)

        except asyncio.TimeoutError:
            await interaction.followup.send("⚠️ Request timed out. Please try again.", ephemeral=True)
        except Exception as e:
            logger.exception(f"Modal submission error: {e}")
            await interaction.followup.send("❌ An error occurred while processing your request.", ephemeral=True)

class RemoveSongModal(Modal):
    def __init__(self, interaction: discord.Interaction, bot):
        super().__init__(title="Remove Song")
        self.interaction = interaction
        self.bot = bot
        self.song_index = TextInput(
            label="Song Index",
            placeholder="Enter the number of the song to remove",
            required=True
        )
        self.add_item(self.song_index)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            index = self.song_index.value.strip()
            index = int(index) - 1  # Convert to 0-based index
            if index < 0:
                raise ValueError("Index cannot be negative.")
            guild_id = str(interaction.guild.id)
            removed_song = await self.bot.remove_from_queue(guild_id, index)
            if removed_song:
                await interaction.response.send_message(f'❌ Removed **{removed_song["title"]}** from the queue.', ephemeral=True)
                await self.bot.update_stable_message(guild_id)
            else:
                await interaction.response.send_message('❌ Invalid song index.', ephemeral=True)
        except ValueError:
            await interaction.response.send_message('❌ Please enter a valid positive number.', ephemeral=True)
        except Exception as e:
            logger.exception(f"Error in RemoveSongModal: {e}")
            await interaction.response.send_message('❌ An error occurred.', ephemeral=True)

class MusicCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(name="setup", description="Set up the music channel and bot UI")
    @commands.has_permissions(manage_channels=True)
    async def setup(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)
        async with self.bot.guild_lock_timeout(guild_id):
            # Check if the channel exists
            channel = discord.utils.get(interaction.guild.channels, name='leo-song-requests')
            if not channel:
                # Create the channel
                overwrites = {
                    interaction.guild.default_role: discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True
                    )
                }
                channel = await interaction.guild.create_text_channel('leo-song-requests', overwrites=overwrites)
            # Send the stable message
            stable_message = await channel.send('🎶 **Music Bot UI Initialized** 🎶')
            # Store the stable message and channel ID
            self.bot.guilds_data[guild_id] = {
                'channel_id': channel.id,
                'stable_message_id': stable_message.id,
                'current_song': None
            }
            await self.bot.save_guilds_data()
            self.bot.guilds_data[guild_id]['stable_message'] = stable_message
            await interaction.response.send_message('Music commands channel setup complete.', ephemeral=True)
            # Initialize the stable message content
            await self.bot.update_stable_message(guild_id)
            # Clear other messages
            await self.bot.clear_channel_messages(channel, stable_message.id)

    @discord.app_commands.command(name="play", description="Play a song or add it to the queue")
    @discord.app_commands.describe(link="The URL or name of the song to play")
    async def play_command(self, interaction: discord.Interaction, link: str):
        try:
            await interaction.response.defer()
            response_message = await self.bot.process_play_request(interaction.user, interaction.guild, interaction.channel, link, interaction=interaction)
            if response_message:
                await interaction.followup.send(response_message)
            # Schedule deletion of the interaction response
            await self.delete_interaction_message(interaction)
        except Exception as e:
            logger.exception(f"Error in play_command: {e}")
            await interaction.followup.send('❌ An error occurred while processing your request.')

    @discord.app_commands.command(name="playnext", description="Play a song next")
    @discord.app_commands.describe(link="The URL or name of the song to play next")
    async def playnext_command(self, interaction: discord.Interaction, link: str):
        try:
            await interaction.response.defer()
            response_message = await self.bot.process_play_request(interaction.user, interaction.guild, interaction.channel, link, interaction=interaction, play_next=True)
            if response_message:
                await interaction.followup.send(response_message)
            # Schedule deletion of the interaction response
            await self.delete_interaction_message(interaction)
        except Exception as e:
            logger.exception(f"Error in playnext_command: {e}")
            await interaction.followup.send('❌ An error occurred while processing your request.')

    async def delete_interaction_message(self, interaction):
        try:
            # Fetch the interaction message
            message = await interaction.original_response()
            # Delete the message after a short delay
            await asyncio.sleep(5)  # Wait 5 seconds before deleting
            await message.delete()
        except Exception as e:
            logger.exception(f"Error deleting interaction message: {e}")

    @discord.app_commands.command(name="skip", description="Skip the current song")
    async def skip_command(self, interaction: discord.Interaction):
        try:
            guild_id = str(interaction.guild.id)
            voice_client = self.bot.voice_clients_dict.get(guild_id)
            if voice_client and voice_client.is_connected() and (voice_client.is_playing() or voice_client.is_paused()):
                voice_client.stop()
                await interaction.response.send_message('⏭️ Skipped the song.')
            else:
                await interaction.response.send_message('❌ Nothing is playing.')
            await self.bot.update_stable_message(guild_id)
        except Exception as e:
            logger.exception(f"Error in skip_command: {e}")
            await interaction.response.send_message('❌ An error occurred while processing your request.')

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You don't have permission to use this command.")
        elif isinstance(error, commands.BotMissingPermissions):
            await ctx.send("❌ I don't have the required permissions to perform this action.")
        else:
            logger.exception(f"An error occurred: {error}")
            await ctx.send("❌ An unexpected error occurred. Please try again later.")

async def main():
    client = MusicBot()
    await client.add_cog(MusicCog(client))

    # Event handler for message deletion and processing song requests
    @client.event
    async def on_message(message):
        if message.author == client.user:
            return  # Ignore messages from the bot itself

        guild_id = str(message.guild.id)
        guild_data = client.guilds_data.get(guild_id)
        if guild_data:
            channel_id = guild_data.get('channel_id')
            if message.channel.id == int(channel_id):
                # Delete the message
                try:
                    await message.delete()
                except discord.Forbidden:
                    logger.warning(f"Permission error: Cannot delete message {message.id}")
                except discord.HTTPException as e:
                    logger.error(f"Failed to delete message {message.id}: {e}")

                # Treat the message content as a song request
                response_message = await client.process_play_request(message.author, message.guild, message.channel, message.content)
                if response_message:
                    sent_msg = await message.channel.send(response_message)
                    # Schedule deletion
                    await asyncio.sleep(5)
                    await sent_msg.delete()
            else:
                # Process commands in other channels as usual
                await client.process_commands(message)
        else:
            await client.process_commands(message)

    await client.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
