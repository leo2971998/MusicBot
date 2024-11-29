import discord
from discord.ext import commands
from discord.ui import Button, View, Modal, TextInput, Select
from discord import Embed, ButtonStyle, app_commands
import os
import asyncio
import yt_dlp
from dotenv import load_dotenv
import json
import random
from enum import Enum
import logging
import time
from threading import Lock
from collections import defaultdict

# Configure logging for better traceability
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('discord_bot.log'),
        logging.StreamHandler()
    ]
)

# Load the environment variables
load_dotenv()
TOKEN = os.getenv("discord_token")
if not TOKEN:
    raise ValueError("discord_token environment variable not set")

# Constants for resource management
MAX_QUEUE_SIZE = 500
MAX_SONG_DURATION = 3600  # 1 hour
UPDATE_COOLDOWN = 2.0  # seconds

# Set up bot intents and command prefix
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
client = commands.Bot(command_prefix=".", intents=intents)
client.guilds_data = {}

# Define playback modes using Enum
class PlaybackMode(Enum):
    NORMAL = 'normal'
    REPEAT_ONE = 'repeat_one'
    REPEAT_ALL = 'repeat_all'

# Initialize playback modes
client.playback_modes = {}

# Data persistence
DATA_FILE = 'guilds_data.json'

def save_guilds_data():
    serializable_data = {}
    for guild_id, guild_data in client.guilds_data.items():
        data_to_save = guild_data.copy()
        # Exclude non-serializable items
        data_to_save.pop('stable_message', None)
        data_to_save.pop('disconnect_task', None)
        data_to_save.pop('lock', None)
        serializable_data[guild_id] = data_to_save
    data = {
        'guilds_data': serializable_data,
        'playback_modes': {gid: mode.value for gid, mode in client.playback_modes.items()}
    }
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f)

def load_guilds_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            try:
                data = json.load(f)
                client.guilds_data = data.get('guilds_data', {})
                # Map old playback modes to new ones
                old_playback_modes = data.get('playback_modes', {})
                client.playback_modes = {}
                for gid, mode in old_playback_modes.items():
                    client.playback_modes[gid] = PlaybackMode(mode)
            except json.JSONDecodeError:
                logging.error("Invalid JSON in guilds_data.json. Initializing with empty data.")
                client.guilds_data = {}
                client.playback_modes = {}
            except ValueError as e:
                logging.error(f"Invalid playback mode value in guilds_data.json: {e}")
                client.playback_modes = {}
    else:
        client.guilds_data = {}
        client.playback_modes = {}

# Guild State class for thread safety
class GuildState:
    def __init__(self):
        self.queue = []
        self.voice_client = None
        self.current_song = None
        self.channel_id = None
        self.stable_message_id = None
        self.stable_message = None
        self.disconnect_task = None
        self.song_duration = 0
        self.lock = Lock()
        self.last_update = 0

    async def add_to_queue(self, song, play_next=False):
        with self.lock:
            if len(self.queue) >= MAX_QUEUE_SIZE:
                return False
            if play_next:
                self.queue.insert(0, song)
            else:
                self.queue.append(song)
        return True

    async def get_next_song(self):
        with self.lock:
            if self.queue:
                return self.queue.pop(0)
            else:
                return None

    def clear_queue(self):
        with self.lock:
            self.queue.clear()

    def shuffle_queue(self):
        with self.lock:
            random.shuffle(self.queue)

    def get_queue(self):
        with self.lock:
            return self.queue.copy()

guild_states = defaultdict(GuildState)

# Bot ready event
@client.event
async def on_ready():
    await client.tree.sync()
    logging.info(f'{client.user} is now online!')
    load_guilds_data()
    for guild_id, guild_data in client.guilds_data.items():
        guild_state = guild_states[guild_id]
        guild_state.channel_id = guild_data.get('channel_id')
        guild_state.stable_message_id = guild_data.get('stable_message_id')
        guild = client.get_guild(int(guild_id))
        if guild:
            channel = guild.get_channel(int(guild_state.channel_id))
            if channel:
                try:
                    stable_message = await channel.fetch_message(int(guild_state.stable_message_id))
                    guild_state.stable_message = stable_message
                    await update_stable_message(guild_id)
                except Exception as e:
                    logging.error(f"Error fetching stable message for guild {guild_id}: {e}")

# Error handling event
@client.event
async def on_error(event, *args, **kwargs):
    logging.error(f"Error in {event}", exc_info=True)

# Voice state update event for cleanup
@client.event
async def on_voice_state_update(member, before, after):
    if member.id == client.user.id:
        if before.channel and not after.channel:  # Bot was disconnected
            guild_id = str(member.guild.id)
            guild_state = guild_states[guild_id]
            guild_state.voice_client = None
            guild_state.current_song = None
            await update_stable_message(guild_id)

# Setup command to create the music channel and stable message
@client.tree.command(name="setup", description="Set up the music channel and bot UI")
@commands.has_permissions(manage_channels=True)
async def setup(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    guild_state = guild_states[guild_id]
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
    guild_state.channel_id = channel.id
    guild_state.stable_message_id = stable_message.id
    guild_state.stable_message = stable_message
    client.guilds_data[guild_id] = {
        'channel_id': channel.id,
        'stable_message_id': stable_message.id
    }
    save_guilds_data()
    await interaction.response.send_message('Music commands channel setup complete.', ephemeral=True)
    # Initialize the stable message content
    await update_stable_message(guild_id)
    # Clear other messages
    await clear_channel_messages(channel, stable_message.id)

# Rate limit decorator
def rate_limit():
    def decorator(func):
        async def wrapper(*args, **kwargs):
            interaction = args[0]
            ctx = await client.get_context(interaction)
            if ctx.guild is None:
                return
            bucket = getattr(client, f"cd_{func.__name__}", {})
            guild_bucket = bucket.get(ctx.guild.id, {})
            current = time.time()
            # Clear old entries
            guild_bucket = {k: v for k, v in guild_bucket.items() if current - v < 60}
            if len(guild_bucket) >= 10:  # Max 10 commands per minute per guild
                await interaction.followup.send("Rate limit exceeded. Please wait.", ephemeral=True)
                return
            guild_bucket[ctx.author.id] = current
            bucket[ctx.guild.id] = guild_bucket
            setattr(client, f"cd_{func.__name__}", bucket)
            await func(*args, **kwargs)
        return wrapper
    return decorator

# Create a function to format time
def format_time(seconds):
    minutes = int(seconds) // 60
    seconds = int(seconds) % 60
    return f"{minutes:02d}:{seconds:02d}"

# Update the stable message with current song and queue
async def update_stable_message(guild_id, view=None):
    guild_id = str(guild_id)
    guild_state = guild_states[guild_id]
    current_time = time.time()
    if current_time - guild_state.last_update < UPDATE_COOLDOWN:
        return
    guild_state.last_update = current_time

    stable_message = guild_state.stable_message
    if not stable_message:
        return
    queue = guild_state.get_queue()
    voice_client = guild_state.voice_client

    # Now Playing Embed
    if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
        current_song = guild_state.current_song
        duration = guild_state.song_duration
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
        playback_mode = client.playback_modes.get(guild_id, PlaybackMode.NORMAL).name.replace('_', ' ').title()
        now_playing_embed.set_footer(text=f'Playback Mode: {playback_mode}')
    else:
        now_playing_embed = Embed(
            title='🎶 Now Playing',
            description='No music is currently playing.',
            color=0x1db954
        )

    # Queue Embed
    if queue:
        queue_description = '\n'.join(
            [f"{idx + 1}. **[{song['title']}]({song['webpage_url']})** — *{song.get('requester', 'Unknown')}*"
             for idx, song in enumerate(queue)]
        )
    else:
        queue_description = 'No songs in the queue.'
    queue_embed = Embed(
        title='📜 Current Queue',
        description=queue_description,
        color=0x1db954
    )
    queue_embed.set_footer(text=f"Total songs in queue: {len(queue)}")

    # Use the provided view or create a new one
    if not view:
        view = MusicControlView(client, guild_id)

    try:
        await stable_message.edit(content='', embeds=[now_playing_embed, queue_embed], view=view)
    except discord.errors.HTTPException as e:
        logging.error(f"Error when updating message in guild {guild_id}: {e}")

    save_guilds_data()

# Clear messages in the channel except the stable message
async def clear_channel_messages(channel, stable_message_id):
    def check(msg):
        return msg.id != stable_message_id and not msg.pinned
    await channel.purge(limit=100, check=check)

# Function to cancel any scheduled disconnect task
def cancel_disconnect_task(guild_id):
    guild_state = guild_states[guild_id]
    disconnect_task = guild_state.disconnect_task
    if disconnect_task:
        disconnect_task.cancel()
        guild_state.disconnect_task = None

# Function to handle delayed disconnect
async def disconnect_after_delay(guild_id, delay):
    try:
        await asyncio.sleep(delay)
        guild_state = guild_states[guild_id]
        voice_client = guild_state.voice_client
        if voice_client and not voice_client.is_playing():
            await voice_client.disconnect()
            guild_state.voice_client = None
            guild_state.disconnect_task = None
            await update_stable_message(guild_id)
    except asyncio.CancelledError:
        # The task was cancelled, do nothing
        pass

# Function to play the next song
async def play_next(guild_id):
    guild_id = str(guild_id)
    guild_state = guild_states[guild_id]
    playback_mode = client.playback_modes.get(guild_id, PlaybackMode.NORMAL)

    if playback_mode == PlaybackMode.REPEAT_ONE:
        # Re-play the current song
        current_song = guild_state.current_song
        await play_song(guild_id, current_song)
    else:
        next_song = await guild_state.get_next_song()
        if next_song:
            guild_state.current_song = next_song
            await play_song(guild_id, next_song)

            if playback_mode == PlaybackMode.REPEAT_ALL:
                # Append the song back to the end of the queue
                await guild_state.add_to_queue(next_song)
        else:
            # No more songs in the queue
            guild_state.current_song = None

            # Schedule a delayed disconnect
            if not guild_state.disconnect_task:
                disconnect_task = client.loop.create_task(
                    disconnect_after_delay(guild_id, delay=300))  # 5 minutes
                guild_state.disconnect_task = disconnect_task

            # Reset playback mode to NORMAL
            client.playback_modes[guild_id] = PlaybackMode.NORMAL
            await update_stable_message(guild_id)

# Function to play a song
async def play_song(guild_id, song_info):
    guild_id = str(guild_id)
    guild_state = guild_states[guild_id]
    voice_client = guild_state.voice_client

    # Cancel any scheduled disconnect task
    cancel_disconnect_task(guild_id)

    # Get the direct audio URL
    song_url = song_info.get('url')
    if not song_url:
        # Re-extract the song info to get the URL
        ytdl_options = {
            "format": "bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            "default_search": "auto",
            "nocheckcertificate": True,
            "ignoreerrors": True,
        }
        with yt_dlp.YoutubeDL(ytdl_options) as ytdl:
            try:
                song_info = await client.loop.run_in_executor(
                    None, lambda: ytdl.extract_info(song_info['webpage_url'], download=False))
                song_url = song_info['url']
                guild_state.current_song = song_info
            except Exception as e:
                logging.error(f"Error re-extracting song info: {e}")
                return

    if not song_url:
        logging.error(f"No valid audio URL found for {song_info.get('title')}")
        return

    # Stop any currently playing audio
    if voice_client.is_playing() or voice_client.is_paused():
        voice_client.stop()

    # FFmpeg options for audio playback
    ffmpeg_options = {
        'before_options': '-reconnect 1 -reconnect_streamed 1 '
                          '-reconnect_delay_max 5',
        'options': '-vn'
    }

    player = discord.FFmpegPCMAudio(song_url, **ffmpeg_options)

    def after_playing(error):
        if error:
            logging.error(f"Error occurred while playing: {error}")
        future = asyncio.run_coroutine_threadsafe(play_next(guild_id), client.loop)
        try:
            future.result()
        except Exception as e:
            logging.error(f"Error in play_next: {e}")

    voice_client.play(player, after=after_playing)
    channel = client.get_channel(int(guild_state.channel_id))
    await channel.send(
        f"🎶 Now playing: **{song_info.get('title', 'Unknown title')}**"
    )

    # Record the song duration
    guild_state.song_duration = song_info.get('duration', 0)

    await update_stable_message(guild_id)
    save_guilds_data()

# Helper function to extract song info with retries
async def extract_song_info(link, retries=3):
    for attempt in range(retries):
        try:
            ytdl_options = {
                "format": "bestaudio/best",
                "quiet": True,
                "no_warnings": True,
                "default_search": "auto",
                "nocheckcertificate": True,
                "ignoreerrors": True,
            }
            ytdl = yt_dlp.YoutubeDL(ytdl_options)
            data = await asyncio.wait_for(
                client.loop.run_in_executor(None, lambda: ytdl.extract_info(link, download=False)), timeout=20)
            return data
        except yt_dlp.DownloadError as e:
            if attempt == retries - 1:
                raise
            await asyncio.sleep(1 * (attempt + 1))
        except asyncio.TimeoutError:
            if attempt == retries - 1:
                raise
            await asyncio.sleep(1 * (attempt + 1))
    return None

# Helper function to validate voice state
async def validate_voice_state(user, guild, interaction):
    user_voice_channel = user.voice.channel if user.voice else None
    if not user_voice_channel:
        msg = "❌ You are not connected to a voice channel."
        await interaction.followup.send(msg, ephemeral=True)
        return False
    return True

# Helper function to handle voice client
async def handle_voice_client(user_voice_channel, guild_id, interaction):
    guild_state = guild_states[guild_id]
    voice_client = guild_state.voice_client
    bot_member = user_voice_channel.guild.me
    permissions = user_voice_channel.permissions_for(bot_member)
    if not permissions.connect or not permissions.speak:
        msg = "❌ I don't have permission to join and speak in your voice channel."
        await interaction.followup.send(msg, ephemeral=True)
        return None
    if user_voice_channel.user_limit and len(user_voice_channel.members) >= user_voice_channel.user_limit:
        msg = "❌ Voice channel is full!"
        await interaction.followup.send(msg, ephemeral=True)
        return None
    if voice_client:
        if voice_client.channel != user_voice_channel:
            # Move the bot to the user's voice channel
            await voice_client.move_to(user_voice_channel)
    else:
        # Connect to the user's voice channel
        try:
            voice_client = await user_voice_channel.connect(timeout=20.0)
            guild_state.voice_client = voice_client
        except Exception as e:
            msg = f"❌ Error connecting to voice channel: {e}"
            await interaction.followup.send(msg, ephemeral=True)
            return None
    return voice_client

# Helper function to process song data
async def process_song_data(data, user, guild_id, interaction, play_next=False):
    guild_state = guild_states[guild_id]
    # Handle single video or playlist
    if 'entries' in data and data.get('_type') == 'playlist':
        # Playlist detected
        await process_playlist(data, user, guild_id, interaction, play_next)
    else:
        # Single video
        song_info = data
        song_info['requester'] = user.mention  # Add requester information

        # Check song duration
        if song_info.get('duration', 0) > MAX_SONG_DURATION:
            await interaction.followup.send("❌ Song is too long! Maximum duration is 1 hour.", ephemeral=True)
            return

        # Add to queue
        success = await guild_state.add_to_queue(song_info, play_next=play_next_flag)
        if not success:
            await interaction.followup.send("❌ Queue is full! Please wait before adding more songs.", ephemeral=True)
            return

        # Play or queue the song
        voice_client = guild_state.voice_client
        if not voice_client.is_playing():
            guild_state.current_song = song_info
            await play_song(guild_id, song_info)
            msg = f"🎶 Now playing: **{song_info.get('title', 'Unknown title')}**"
            await interaction.followup.send(msg, ephemeral=True)
        else:
            msg = f"➕ Added to queue: **{song_info.get('title', 'Unknown title')}**"
            await interaction.followup.send(msg, ephemeral=True)

# Helper function to process playlist
async def process_playlist(data, user, guild_id, interaction, play_next=False):
    guild_state = guild_states[guild_id]
    playlist_entries = data['entries']
    chunks = [playlist_entries[i:i + 20] for i in range(0, len(playlist_entries), 20)]
    for chunk in chunks:
        tasks = [process_single_song(entry, user, guild_id, play_next) for entry in chunk if entry]
        await asyncio.gather(*tasks)
    msg = f"🎶 Added playlist **{data.get('title', 'Unknown playlist')}** to the queue."
    await interaction.followup.send(msg, ephemeral=True)
    # Start playing if not already playing
    voice_client = guild_state.voice_client
    if not voice_client.is_playing() and not voice_client.is_paused():
        await play_next_song(guild_id)

# Helper function to process a single song
async def process_single_song(entry, user, guild_id, play_next):
    guild_state = guild_states[guild_id]
    song_info = entry
    song_info['requester'] = user.mention  # Add requester information
    # Check song duration
    if song_info.get('duration', 0) > MAX_SONG_DURATION:
        return
    # Add to queue
    success = await guild_state.add_to_queue(song_info, play_next=play_next)
    if not success:
        return

# Helper function to process play requests
@rate_limit()
async def process_play_request(interaction: discord.Interaction, link: str, play_next=False):
    user = interaction.user
    guild = interaction.guild
    guild_id = str(guild.id)
    guild_state = guild_states[guild_id]
    await interaction.response.defer(ephemeral=True)

    # Validate voice state
    if not await validate_voice_state(user, guild, interaction):
        return

    # Handle voice client
    voice_client = await handle_voice_client(user.voice.channel, guild_id, interaction)
    if not voice_client:
        return

    # Cancel any scheduled disconnect task
    cancel_disconnect_task(guild_id)

    # Extract song info
    try:
        data = await extract_song_info(link)
    except Exception as e:
        msg = f"❌ Error extracting song information: {e}"
        await interaction.followup.send(msg, ephemeral=True)
        return

    if not data:
        msg = "❌ No results found for your query."
        await interaction.followup.send(msg, ephemeral=True)
        return

    # Process song data
    await process_song_data(data, user, guild_id, interaction, play_next)

    # Clear messages except the stable message
    stable_message_id = guild_state.stable_message_id
    channel_id = guild_state.channel_id
    if stable_message_id and channel_id:
        channel = client.get_channel(int(channel_id))
        await clear_channel_messages(channel, int(stable_message_id))

    await update_stable_message(guild_id)

# Slash command to play a song or add to the queue
@client.tree.command(name="play", description="Play a song or add it to the queue")
@app_commands.describe(link="The URL or name of the song to play")
async def play_command(interaction: discord.Interaction, link: str):
    await process_play_request(interaction, link)

# Slash command to play a song next
@client.tree.command(name="playnext", description="Play a song next")
@app_commands.describe(link="The URL or name of the song to play next")
async def playnext_command(interaction: discord.Interaction, link: str):
    await process_play_request(interaction, link, play_next=True)

# Slash command to remove a song from the queue
@client.tree.command(name="remove", description="Remove a song from the queue")
@app_commands.describe(index="The position of the song in the queue to remove")
@commands.cooldown(1, 5, commands.BucketType.user)
async def remove_command(interaction: discord.Interaction, index: int):
    guild_id = str(interaction.guild.id)
    guild_state = guild_states[guild_id]
    queue = guild_state.get_queue()
    if queue and 1 <= index <= len(queue):
        with guild_state.lock:
            removed_song = guild_state.queue.pop(index - 1)
        await interaction.response.send_message(f'❌ Removed **{removed_song["title"]}** from the queue.', ephemeral=True)
        await update_stable_message(guild_id)
    else:
        await interaction.response.send_message('❌ Invalid song index.', ephemeral=True)

# Event handler for message deletion and processing song requests
@client.event
async def on_message(message):
    if message.author == client.user:
        return  # Ignore messages from the bot itself

    guild_id = str(message.guild.id)
    guild_state = guild_states[guild_id]
    if guild_state:
        channel_id = guild_state.channel_id
        if message.channel.id == int(channel_id):
            # Delete the message
            try:
                await message.delete()
            except discord.Forbidden:
                logging.error(f"Permission error: Cannot delete message {message.id}")
            except discord.HTTPException as e:
                logging.error(f"Failed to delete message {message.id}: {e}")

            # Treat the message content as a song request
            # Create a mock interaction object
            class MockInteraction:
                def __init__(self, user, guild, channel):
                    self.user = user
                    self.guild = guild
                    self.channel = channel
                    self.followup = channel

                async def response(self):
                    pass

                async def defer(self, ephemeral=True):
                    pass

            interaction = MockInteraction(message.author, message.guild, message.channel)
            await process_play_request(interaction, message.content)
        else:
            # Process commands in other channels as usual
            await client.process_commands(message)
    else:
        await client.process_commands(message)

# Define the MusicControlView
class MusicControlView(View):
    def __init__(self, bot, guild_id):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = guild_id
        self.search_results = []
        self.add_controls()

    def add_controls(self):
        self.clear_items()
        self.add_item(ControlButton('⏸️ Pause', ButtonStyle.primary, 'pause', self))
        self.add_item(ControlButton('▶️ Resume', ButtonStyle.primary, 'resume', self))
        self.add_item(ControlButton('⏭️ Skip', ButtonStyle.primary, 'skip', self))
        self.add_item(ControlButton('⏹️ Stop', ButtonStyle.primary, 'stop', self))
        self.add_item(ControlButton('🗑️ Clear Queue', ButtonStyle.danger, 'clear_queue', self))
        self.add_item(ControlButton('🔀 Shuffle', ButtonStyle.primary, 'shuffle', self))
        # Playback mode buttons
        self.add_item(ControlButton('🔁 Normal', ButtonStyle.secondary, 'normal_mode', self))
        self.add_item(ControlButton('🔂 Repeat One', ButtonStyle.secondary, 'repeat_one', self))
        self.add_item(ControlButton('🔁 Repeat All', ButtonStyle.secondary, 'repeat_all', self))
        # Add Song button
        self.add_item(ControlButton('➕ Add Song', ButtonStyle.success, 'add_song', self))
        # Add the select menu
        self.song_select = SongSelect(self)
        self.add_item(self.song_select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return True  # Allow all interactions for now

    async def on_timeout(self):
        pass  # Keep the view active indefinitely

    async def on_button_click(self, interaction: discord.Interaction, custom_id):
        guild_id = str(interaction.guild.id)
        guild_state = guild_states[guild_id]

        if custom_id == 'pause':
            await self.pause(interaction)
        elif custom_id == 'resume':
            await self.resume(interaction)
        elif custom_id == 'skip':
            await self.skip(interaction)
        elif custom_id == 'stop':
            await self.stop(interaction)
        elif custom_id == 'clear_queue':
            await self.clear_queue(interaction)
        elif custom_id == 'shuffle':
            await self.shuffle(interaction)
        elif custom_id == 'normal_mode':
            await self.set_playback_mode(interaction, PlaybackMode.NORMAL)
        elif custom_id == 'repeat_one':
            await self.set_playback_mode(interaction, PlaybackMode.REPEAT_ONE)
        elif custom_id == 'repeat_all':
            await self.set_playback_mode(interaction, PlaybackMode.REPEAT_ALL)
        elif custom_id == 'add_song':
            await self.add_song(interaction)

    async def pause(self, interaction):
        guild_id = str(interaction.guild.id)
        guild_state = guild_states[guild_id]
        voice_client = guild_state.voice_client
        if voice_client and voice_client.is_playing():
            voice_client.pause()
            await interaction.response.send_message('⏸️ Paused the music.', ephemeral=True)
        else:
            await interaction.response.send_message('❌ Nothing is playing.', ephemeral=True)
        await update_stable_message(guild_id)

    async def resume(self, interaction):
        guild_id = str(interaction.guild.id)
        guild_state = guild_states[guild_id]
        voice_client = guild_state.voice_client
        if voice_client and voice_client.is_paused():
            voice_client.resume()
            await interaction.response.send_message('▶️ Resumed the music.', ephemeral=True)
        else:
            await interaction.response.send_message('❌ Nothing is paused.', ephemeral=True)
        await update_stable_message(guild_id)

    async def skip(self, interaction):
        guild_id = str(interaction.guild.id)
        guild_state = guild_states[guild_id]
        voice_client = guild_state.voice_client
        if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
            voice_client.stop()
            await interaction.response.send_message('⏭️ Skipped the song.', ephemeral=True)
        else:
            await interaction.response.send_message('❌ Nothing is playing.', ephemeral=True)
        await update_stable_message(guild_id)

    async def stop(self, interaction):
        guild_id = str(interaction.guild.id)
        guild_state = guild_states[guild_id]
        voice_client = guild_state.voice_client
        if voice_client:
            voice_client.stop()
            await voice_client.disconnect()
            guild_state.voice_client = None
            guild_state.current_song = None

            # Cancel the disconnect task if it exists
            disconnect_task = guild_state.disconnect_task
            if disconnect_task:
                disconnect_task.cancel()
                guild_state.disconnect_task = None

            # Reset playback mode to NORMAL
            client.playback_modes[guild_id] = PlaybackMode.NORMAL

            await interaction.response.send_message('⏹️ Stopped the music and left the voice channel.', ephemeral=True)
        else:
            await interaction.response.send_message('❌ Not connected to a voice channel.', ephemeral=True)
        await update_stable_message(guild_id)

    async def clear_queue(self, interaction):
        guild_id = str(interaction.guild.id)
        guild_state = guild_states[guild_id]
        queue = guild_state.get_queue()
        if queue:
            guild_state.clear_queue()
            await interaction.response.send_message('🗑️ Cleared the queue.', ephemeral=True)
        else:
            await interaction.response.send_message('❌ The queue is already empty.', ephemeral=True)
        await update_stable_message(guild_id)

    async def shuffle(self, interaction):
        guild_id = str(interaction.guild.id)
        guild_state = guild_states[guild_id]
        queue = guild_state.get_queue()
        if queue:
            guild_state.shuffle_queue()
            await interaction.response.send_message('🔀 Queue shuffled.', ephemeral=True)
        else:
            await interaction.response.send_message('❌ The queue is empty.', ephemeral=True)
        await update_stable_message(guild_id)

    async def set_playback_mode(self, interaction, mode):
        guild_id = str(interaction.guild.id)
        client.playback_modes[guild_id] = mode
        await interaction.response.send_message(f'Playback mode set to: **{mode.name.replace("_", " ").title()}**', ephemeral=True)
        await update_stable_message(guild_id)

    async def add_song(self, interaction):
        modal = AddSongModal(self)
        await interaction.response.send_modal(modal)

# Custom button class
class ControlButton(Button):
    def __init__(self, label, style, custom_id, parent_view):
        super().__init__(label=label, style=style, custom_id=custom_id)
        self.parent_view = parent_view  # Store parent view

    async def callback(self, interaction: discord.Interaction):
        await self.parent_view.on_button_click(interaction, self.custom_id)

# Modal to add song
class AddSongModal(Modal):
    def __init__(self, parent_view):
        super().__init__(title="Add Song")
        self.song_input = TextInput(
            label="Song Name or URL",
            placeholder="Enter the song name or YouTube URL",
            required=True,
            max_length=100
        )
        self.add_item(self.song_input)
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        user_input = self.song_input.value.strip()
        await interaction.response.defer(ephemeral=True)
        # Search for the song
        search_query = f"ytsearch5:{user_input}"
        try:
            data = await extract_song_info(search_query)
            if not data or 'entries' not in data:
                await interaction.followup.send("❌ No results found.", ephemeral=True)
                return
            search_results = data['entries']
            self.parent_view.search_results = search_results
            self.parent_view.song_select.update_options(search_results)
            guild_id = str(interaction.guild.id)
            await update_stable_message(guild_id, view=self.parent_view)
            await interaction.followup.send("Select a song from the menu below.", ephemeral=True)
        except Exception as e:
            msg = f"❌ Error searching for the song: {e}"
            await interaction.followup.send(msg, ephemeral=True)

# Song selection menu
class SongSelect(Select):
    def __init__(self, parent_view):
        self.parent_view = parent_view
        # Create a placeholder option
        placeholder_option = discord.SelectOption(
            label="No search results yet.",
            description="Click 'Add Song' to search.",
            value="placeholder",
            default=True
        )
        super().__init__(
            placeholder="No search results yet. Click 'Add Song' to search.",
            min_values=1,
            max_values=1,
            options=[placeholder_option],
            disabled=True
        )

    def update_options(self, search_results):
        self.options = [
            discord.SelectOption(
                label=entry.get('title', 'Unknown title')[:100],
                description=entry.get('uploader', '')[:100],
                value=str(index)
            )
            for index, entry in enumerate(search_results)
        ]
        self.disabled = False
        self.placeholder = "Select a song..."
        # Clear default selections
        for option in self.options:
            option.default = False
        # Update the select menu in the parent view
        self.parent_view.remove_item(self)
        self.parent_view.add_item(self)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "placeholder":
            await interaction.response.defer()
            return
        selected_index = int(self.values[0])
        selected_song = self.parent_view.search_results[selected_index]
        # Proceed to add the selected song
        guild_id = str(interaction.guild.id)
        guild_state = guild_states[guild_id]
        user = interaction.user
        song_info = selected_song
        song_info['requester'] = user.mention  # Add requester information

        # Check song duration
        if song_info.get('duration', 0) > MAX_SONG_DURATION:
            await interaction.response.send_message("❌ Song is too long! Maximum duration is 1 hour.", ephemeral=True)
            return

        # Add to queue
        success = await guild_state.add_to_queue(song_info)
        if not success:
            await interaction.response.send_message("❌ Queue is full! Please wait before adding more songs.", ephemeral=True)
            return

        # Play or queue the song
        voice_client = guild_state.voice_client
        if not voice_client.is_playing():
            guild_state.current_song = song_info
            await play_song(guild_id, song_info)
            msg = f"🎶 Now playing: **{song_info.get('title', 'Unknown title')}**"
            await interaction.response.send_message(msg, ephemeral=True)
        else:
            msg = f"➕ Added to queue: **{song_info.get('title', 'Unknown title')}**"
            await interaction.response.send_message(msg, ephemeral=True)

        # Reset the select menu
        self.reset()
        await update_stable_message(guild_id, view=self.parent_view)

    def reset(self):
        # Reset the select menu to initial state
        placeholder_option = discord.SelectOption(
            label="No search results yet.",
            description="Click 'Add Song' to search.",
            value="placeholder",
            default=True
        )
        self.options = [placeholder_option]
        self.disabled = True
        self.placeholder = "No search results yet. Click 'Add Song' to search."
        self.parent_view.search_results = []
        # Update the select menu in the parent view
        self.parent_view.remove_item(self)
        self.parent_view.add_item(self)

# Run the bot
client.run(TOKEN)
