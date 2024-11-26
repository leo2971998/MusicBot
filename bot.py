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

# Load the environment variables
load_dotenv()
TOKEN = os.getenv("discord_token") or "YOUR_DISCORD_BOT_TOKEN"

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

# Define global variables for managing queues and voice clients
queues = {}
voice_clients = {}
youtube_base_url = 'https://www.youtube.com/'
youtube_watch_url = youtube_base_url + 'watch?v='

# Adjusted yt_dlp options
yt_dl_options = {
    "format": "bestaudio/best",
    "noplaylist": False,
    "quiet": True,
    "default_search": "auto",
    "extract_flat": False,
    "nocheckcertificate": True,
    "ignoreerrors": True,
}
ytdl = yt_dlp.YoutubeDL(yt_dl_options)

# FFmpeg options for audio playback
ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 '
                      '-reconnect_delay_max 5',
    'options': '-vn'
}

# Data persistence
DATA_FILE = 'guilds_data.json'

def save_guilds_data():
    serializable_data = {}
    for guild_id, guild_data in client.guilds_data.items():
        # Create a copy excluding non-serializable items
        data_to_save = guild_data.copy()
        # Exclude non-serializable items
        data_to_save.pop('stable_message', None)
        data_to_save.pop('disconnect_task', None)
        serializable_data[guild_id] = data_to_save
    data = {
        'guilds_data': serializable_data,
        'playback_modes': {gid: mode.value for gid, mode in
                           client.playback_modes.items()}
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
                    if mode == 'loop':
                        client.playback_modes[gid] = PlaybackMode.REPEAT_ALL
                    elif mode == 'repeat':
                        client.playback_modes[gid] = PlaybackMode.REPEAT_ONE
                    else:
                        client.playback_modes[gid] = PlaybackMode(mode)
            except json.JSONDecodeError:
                print("Invalid JSON in guilds_data.json. "
                      "Initializing with empty data.")
                client.guilds_data = {}
                client.playback_modes = {}
            except ValueError as e:
                print(f"Invalid playback mode value in guilds_data.json: {e}")
                client.playback_modes = {}
    else:
        client.guilds_data = {}
        client.playback_modes = {}

# Bot ready event
@client.event
async def on_ready():
    await client.tree.sync()
    print(f'{client.user} is now online!')
    load_guilds_data()
    for guild_id, guild_data in client.guilds_data.items():
        channel_id = guild_data.get('channel_id')
        stable_message_id = guild_data.get('stable_message_id')
        guild = client.get_guild(int(guild_id))
        if guild:
            channel = guild.get_channel(int(channel_id))
            if channel:
                try:
                    stable_message = await channel.fetch_message(
                        int(stable_message_id))
                    client.guilds_data[guild_id]['stable_message'] = \
                        stable_message
                    await update_stable_message(int(guild_id))
                except Exception as e:
                    print(f"Error fetching stable message for guild "
                          f"{guild_id}: {e}")

# Setup command to create the music channel and stable message
@client.tree.command(name="setup", description="Set up the music channel "
                                               "and bot UI")
@commands.has_permissions(manage_channels=True)
async def setup(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    # Check if the channel exists
    channel = discord.utils.get(interaction.guild.channels,
                                name='leo-song-requests')
    if not channel:
        # Create the channel
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
            )
        }
        channel = await interaction.guild.create_text_channel(
            'leo-song-requests', overwrites=overwrites)
    # Send the stable message
    stable_message = await channel.send('🎶 **Music Bot UI Initialized** 🎶')
    # Store the stable message and channel ID
    client.guilds_data[guild_id] = {
        'channel_id': channel.id,
        'stable_message_id': stable_message.id,
        'current_song': None
    }
    save_guilds_data()
    client.guilds_data[guild_id]['stable_message'] = stable_message
    await interaction.response.send_message(
        'Music commands channel setup complete.', ephemeral=True)
    # Initialize the stable message content
    await update_stable_message(guild_id)
    # Clear other messages
    await clear_channel_messages(channel, stable_message.id)

# Define the MusicControlView
class MusicControlView(View):
    def __init__(self, bot, guild_id):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = guild_id
        self.add_controls()

    def add_controls(self):
        # Clear existing items
        self.clear_items()
        # Add control buttons
        self.add_item(Button(label='⏸️ Pause', style=ButtonStyle.primary, custom_id='pause'))
        self.add_item(Button(label='▶️ Resume', style=ButtonStyle.primary, custom_id='resume'))
        self.add_item(Button(label='⏭️ Skip', style=ButtonStyle.primary, custom_id='skip'))
        self.add_item(Button(label='⏹️ Stop', style=ButtonStyle.primary, custom_id='stop'))
        self.add_item(Button(label='🗑️ Clear Queue', style=ButtonStyle.danger, custom_id='clear_queue'))
        self.add_item(Button(label='🔀 Shuffle', style=ButtonStyle.primary, custom_id='shuffle'))
        # Playback mode buttons
        self.add_item(Button(label='🔁 Normal', style=ButtonStyle.secondary, custom_id='normal_mode'))
        self.add_item(Button(label='🔂 Repeat One', style=ButtonStyle.secondary, custom_id='repeat_one'))
        self.add_item(Button(label='🔁 Repeat All', style=ButtonStyle.secondary, custom_id='repeat_all'))
        # Add Song button
        self.add_item(Button(label='➕ Add Song', style=ButtonStyle.success, custom_id='add_song'))

    def add_select_menu(self, options):
        # Clear existing items
        self.clear_items()
        # Add select menu
        self.add_item(SongSelect(options, self))
        # Cancel button
        self.add_item(Button(label='Cancel', style=ButtonStyle.danger, custom_id='cancel'))

    @discord.ui.button(label='➕ Add Song', style=ButtonStyle.success, custom_id='add_song')
    async def add_song_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = AddSongModal()
        await interaction.response.send_modal(modal)
        # Store the interaction for later use
        modal.interaction = interaction
        modal.view = self

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return True  # Allow all interactions for now

    async def on_timeout(self):
        pass  # Keep the view active indefinitely

    @discord.ui.button(label='Cancel', style=ButtonStyle.danger, custom_id='cancel', row=4)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.add_controls()
        await update_stable_message(self.guild_id)

    async def on_button_click(self, interaction: discord.Interaction):
        custom_id = interaction.data['custom_id']
        guild_id = str(interaction.guild.id)

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
        elif custom_id == 'cancel':
            self.add_controls()
            await update_stable_message(guild_id)

    async def pause(self, interaction):
        guild_id = str(interaction.guild.id)
        voice_client = voice_clients.get(guild_id)
        if voice_client and voice_client.is_playing():
            voice_client.pause()
            await interaction.response.send_message('⏸️ Paused the music.', ephemeral=True)
        else:
            await interaction.response.send_message('❌ Nothing is playing.', ephemeral=True)
        await update_stable_message(guild_id)

    async def resume(self, interaction):
        guild_id = str(interaction.guild.id)
        voice_client = voice_clients.get(guild_id)
        if voice_client and voice_client.is_paused():
            voice_client.resume()
            await interaction.response.send_message('▶️ Resumed the music.', ephemeral=True)
        else:
            await interaction.response.send_message('❌ Nothing is paused.', ephemeral=True)
        await update_stable_message(guild_id)

    async def skip(self, interaction):
        guild_id = str(interaction.guild.id)
        voice_client = voice_clients.get(guild_id)
        if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
            voice_client.stop()
            await interaction.response.send_message('⏭️ Skipped the song.', ephemeral=True)
        else:
            await interaction.response.send_message('❌ Nothing is playing.', ephemeral=True)
        await update_stable_message(guild_id)

    async def stop(self, interaction):
        guild_id = str(interaction.guild.id)
        voice_client = voice_clients.get(guild_id)
        if voice_client:
            voice_client.stop()
            await voice_client.disconnect()
            voice_clients.pop(guild_id, None)
            client.guilds_data[guild_id]['current_song'] = None

            # Cancel the disconnect task if it exists
            disconnect_task = client.guilds_data[guild_id].get('disconnect_task')
            if disconnect_task:
                disconnect_task.cancel()
                client.guilds_data[guild_id]['disconnect_task'] = None

            # Reset playback mode to NORMAL
            client.playback_modes[guild_id] = PlaybackMode.NORMAL

            await interaction.response.send_message(
                '⏹️ Stopped the music and left the voice channel.', ephemeral=True)
        else:
            await interaction.response.send_message(
                '❌ Not connected to a voice channel.', ephemeral=True)
        await update_stable_message(guild_id)

    async def clear_queue(self, interaction):
        guild_id = str(interaction.guild.id)
        if guild_id in queues:
            queues[guild_id].clear()
            await interaction.response.send_message('🗑️ Cleared the queue.', ephemeral=True)
        else:
            await interaction.response.send_message('❌ The queue is already empty.', ephemeral=True)
        await update_stable_message(guild_id)

    async def shuffle(self, interaction):
        guild_id = str(interaction.guild.id)
        queue = queues.get(guild_id)
        if queue:
            random.shuffle(queue)
            await interaction.response.send_message('🔀 Queue shuffled.', ephemeral=True)
        else:
            await interaction.response.send_message('❌ The queue is empty.', ephemeral=True)
        await update_stable_message(guild_id)

    async def set_playback_mode(self, interaction, mode):
        guild_id = str(interaction.guild.id)
        client.playback_modes[guild_id] = mode
        await interaction.response.send_message(f'Playback mode set to: **{mode.name.replace("_", " ").title()}**', ephemeral=True)
        await update_stable_message(guild_id)

class AddSongModal(Modal):
    def __init__(self):
        super().__init__(title="Add Song")
        self.song_input = TextInput(
            label="Song Name or URL",
            placeholder="Enter the song name or YouTube URL",
            required=True,
            max_length=100
        )
        self.add_item(self.song_input)
        self.interaction = None  # Will be set when modal is invoked
        self.view = None  # Will be set when modal is invoked

    async def on_submit(self, interaction: discord.Interaction):
        user_input = self.song_input.value.strip()
        await interaction.response.defer(ephemeral=True)
        # Search for the song
        search_query = f"ytsearch5:{user_input}"
        try:
            search_results = ytdl.extract_info(
                search_query, download=False)['entries']
            if not search_results:
                await interaction.followup.send("❌ No results found.", ephemeral=True)
                return

            # Create options for the select menu
            options = [
                discord.SelectOption(
                    label=entry.get('title', 'Unknown title')[:100],
                    description=entry.get('uploader', '')[:100],
                    value=str(index)
                )
                for index, entry in enumerate(search_results)
            ]

            # Update the view to include the select menu
            self.view.add_select_menu(options)
            self.view.search_results = search_results
            guild_id = str(interaction.guild.id)
            await update_stable_message(guild_id, view=self.view)
            await interaction.followup.send("Select a song from the menu below.", ephemeral=True)

        except Exception as e:
            msg = f"❌ Error searching for the song: {e}"
            await interaction.followup.send(msg, ephemeral=True)

class SongSelect(Select):
    def __init__(self, options, parent_view):
        super().__init__(placeholder="Choose a song...", min_values=1,
                         max_values=1, options=options)
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        selected_index = int(self.values[0])
        selected_song = self.parent_view.search_results[selected_index]
        # Proceed to add the selected song
        await process_play_request(
            interaction.user,
            interaction.guild,
            interaction.channel,
            selected_song['webpage_url'],
            interaction=interaction
        )
        # Revert the view back to controls
        self.parent_view.add_controls()
        guild_id = str(interaction.guild.id)
        await update_stable_message(guild_id, view=self.parent_view)
        await interaction.response.defer()  # Acknowledge the interaction silently

# Create a function to format time
def format_time(seconds):
    minutes = int(seconds) // 60
    seconds = int(seconds) % 60
    return f"{minutes:02d}:{seconds:02d}"

# Update the stable message with current song and queue
async def update_stable_message(guild_id, view=None):
    guild_id = str(guild_id)
    guild_data = client.guilds_data.get(guild_id)
    if not guild_data:
        return
    stable_message = guild_data.get('stable_message')
    if not stable_message:
        return
    queue = queues.get(guild_id, [])
    voice_client = voice_clients.get(guild_id)

    # Now Playing Embed
    if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
        current_song = guild_data.get('current_song')
        duration = guild_data.get('song_duration')
        duration_str = format_time(duration)

        now_playing_embed = Embed(
            title='🎶 Now Playing',
            description=f"**[{current_song['title']}]"
                        f"({current_song['webpage_url']})**",
            color=0x1db954
        )
        now_playing_embed.set_thumbnail(url=current_song.get('thumbnail'))
        now_playing_embed.add_field(name='Duration',
                                    value=f"`{duration_str}`", inline=False)
        # Add requester
        now_playing_embed.add_field(name='Requested by',
                                    value=current_song.get('requester',
                                                           'Unknown'),
                                    inline=False)

        # Add playback mode to the embed
        playback_mode = client.playback_modes.get(
            guild_id, PlaybackMode.NORMAL).name.replace('_', ' ').title()
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
            [f"{idx + 1}. **[{song['title']}]({song['webpage_url']})** — "
             f"*{song.get('requester', 'Unknown')}*" for idx, song in
             enumerate(queue)]
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
        print(f"Rate limit hit when updating message in guild {guild_id}: {e}")

    save_guilds_data()

# Clear messages in the channel except the stable message
async def clear_channel_messages(channel, stable_message_id):
    async for message in channel.history(limit=100):
        if message.id != stable_message_id and not message.pinned:
            try:
                await message.delete()
            except discord.Forbidden:
                print(f"Permission error: Cannot delete message {message.id}")
            except discord.HTTPException as e:
                print(f"Failed to delete message {message.id}: {e}")

# Function to cancel any scheduled disconnect task
def cancel_disconnect_task(guild_id):
    disconnect_task = client.guilds_data.get(guild_id, {}).get(
        'disconnect_task')
    if disconnect_task:
        disconnect_task.cancel()
        client.guilds_data[guild_id]['disconnect_task'] = None

# Play the next song in the queue
async def play_next(guild_id):
    guild_id = str(guild_id)

    playback_mode = client.playback_modes.get(guild_id, PlaybackMode.NORMAL)

    if playback_mode == PlaybackMode.REPEAT_ONE:
        # Re-play the current song
        current_song = client.guilds_data[guild_id]['current_song']
        await play_song(guild_id, current_song)
    else:
        if queues.get(guild_id):
            song_info = queues[guild_id].pop(0)
            client.guilds_data[guild_id]['current_song'] = song_info
            await play_song(guild_id, song_info)

            if playback_mode == PlaybackMode.REPEAT_ALL:
                # Append the song back to the end of the queue
                queues[guild_id].append(song_info)
        else:
            # No more songs in the queue
            client.guilds_data[guild_id]['current_song'] = None

            # Schedule a delayed disconnect
            if not client.guilds_data[guild_id].get('disconnect_task'):
                disconnect_task = client.loop.create_task(
                    disconnect_after_delay(guild_id, delay=300))  # 5 minutes
                client.guilds_data[guild_id]['disconnect_task'] = \
                    disconnect_task

            # Reset playback mode to NORMAL
            client.playback_modes[guild_id] = PlaybackMode.NORMAL
            await update_stable_message(guild_id)

# Function to play a song
async def play_song(guild_id, song_info):
    guild_id = str(guild_id)
    voice_client = voice_clients[guild_id]

    # Cancel any scheduled disconnect task
    cancel_disconnect_task(guild_id)

    song_url = song_info.get('url')
    if not song_url and 'formats' in song_info:
        # Get the best audio format
        for fmt in song_info['formats']:
            if fmt.get('acodec') != 'none':
                song_url = fmt['url']
                break
    if not song_url:
        print(f"No valid audio URL found for {song_info.get('title')}")
        return

    # Stop any currently playing audio
    if voice_client.is_playing() or voice_client.is_paused():
        voice_client.stop()

    player = discord.FFmpegPCMAudio(song_url, **ffmpeg_options)

    def after_playing(error):
        if error:
            print(f"Error occurred while playing: {error}")
        future = asyncio.run_coroutine_threadsafe(play_next(guild_id),
                                                  client.loop)
        try:
            future.result()
        except Exception as e:
            print(f"Error in play_next: {e}")

    voice_client.play(
        player,
        after=after_playing
    )
    channel_id = client.guilds_data[guild_id]['channel_id']
    channel = client.get_channel(int(channel_id))
    await channel.send(
        f"🎶 Now playing: **{song_info.get('title', 'Unknown title')}**"
    )
    client.guilds_data[guild_id]['current_song'] = song_info

    # Record the song duration
    client.guilds_data[guild_id]['song_duration'] = song_info.get(
        'duration', 0)

    await update_stable_message(guild_id)
    save_guilds_data()

# Helper function to process play requests
async def process_play_request(user, guild, channel, link, interaction=None,
                               play_next=False):
    guild_id = str(guild.id)
    # Initialize guild data if not present
    if guild_id not in client.guilds_data:
        client.guilds_data[guild_id] = {}

    # Get the existing voice client
    voice_client = voice_clients.get(guild_id)
    user_voice_channel = user.voice.channel if user.voice else None

    if not user_voice_channel:
        msg = "❌ You are not connected to a voice channel."
        if interaction:
            await interaction.followup.send(msg, ephemeral=True)
        else:
            sent_msg = await channel.send(msg)
            # Schedule deletion
            await asyncio.sleep(5)
            await sent_msg.delete()
        return

    if voice_client:
        if voice_client.channel != user_voice_channel:
            # Move the bot to the user's voice channel
            await voice_client.move_to(user_voice_channel)
    else:
        # Connect to the user's voice channel
        voice_client = await user_voice_channel.connect()
        voice_clients[guild_id] = voice_client

    # Cancel any scheduled disconnect task
    cancel_disconnect_task(guild_id)

    # Adjusted search handling using yt_dlp's built-in search
    try:
        data = await client.loop.run_in_executor(None, lambda: ytdl.extract_info(link, download=False))
    except Exception as e:
        msg = f"❌ Error extracting song information: {e}"
        if interaction:
            await interaction.followup.send(msg, ephemeral=True)
        else:
            sent_msg = await channel.send(msg)
            # Schedule deletion
            await asyncio.sleep(5)
            await sent_msg.delete()
        return

    if not data:
        msg = "❌ No results found for your query."
        if interaction:
            await interaction.followup.send(msg, ephemeral=True)
        else:
            sent_msg = await channel.send(msg)
            await asyncio.sleep(5)
            await sent_msg.delete()
        return

    # Handle single video or playlist
    if 'entries' in data and data.get('_type') == 'playlist':
        # Playlist detected
        playlist_entries = data['entries']
        added_songs = []
        for entry in playlist_entries:
            if entry is None:
                continue  # Skip if entry is None
            song_info = entry
            song_info['requester'] = user.mention  # Add requester information
            # Add to queue
            if guild_id not in queues:
                queues[guild_id] = []
            if play_next:
                queues[guild_id].insert(0, song_info)
            else:
                queues[guild_id].append(song_info)
            added_songs.append(song_info['title'])
        msg = f"🎶 Added playlist **{data.get('title', 'Unknown playlist')}** with " \
              f"{len(added_songs)} songs to the queue."
        if interaction:
            await interaction.followup.send(msg, ephemeral=True)
        else:
            sent_msg = await channel.send(msg)
            # Schedule deletion
            await asyncio.sleep(5)
            await sent_msg.delete()

        # Start playing if not already playing
        if not voice_client.is_playing() and not voice_client.is_paused():
            await play_next(guild_id)
    else:
        # Single video
        song_info = data
        song_info['requester'] = user.mention  # Add requester information

        # Add to queue
        if guild_id not in queues:
            queues[guild_id] = []
        if play_next:
            queues[guild_id].insert(0, song_info)
        else:
            queues[guild_id].append(song_info)

        # Play or queue the song
        if not voice_client.is_playing():
            client.guilds_data[guild_id]['current_song'] = song_info
            await play_song(guild_id, song_info)
            msg = f"🎶 Now playing: **{song_info.get('title', 'Unknown title')}**"
            if interaction:
                await interaction.followup.send(msg, ephemeral=True)
            else:
                sent_msg = await channel.send(msg)
                # Schedule deletion
                await asyncio.sleep(5)
                await sent_msg.delete()
        else:
            msg = f"➕ Added to queue: **{song_info.get('title', 'Unknown title')}**"
            if interaction:
                await interaction.followup.send(msg, ephemeral=True)
            else:
                sent_msg = await channel.send(msg)
                # Schedule deletion
                await asyncio.sleep(5)
                await sent_msg.delete()

    # Clear messages except the stable message
    guild_data = client.guilds_data.get(guild_id)
    if guild_data:
        stable_message_id = guild_data.get('stable_message_id')
        channel_id = guild_data.get('channel_id')
        if stable_message_id and channel_id:
            channel = client.get_channel(int(channel_id))
            await clear_channel_messages(channel, int(stable_message_id))

    await update_stable_message(guild_id)

# Slash command to play a song or add to the queue
@client.tree.command(name="play", description="Play a song or add it to the queue")
@app_commands.describe(link="The URL or name of the song to play")
async def play_command(interaction: discord.Interaction, link: str):
    await interaction.response.defer(ephemeral=True)
    await process_play_request(interaction.user, interaction.guild,
                               interaction.channel, link, interaction=interaction)

# Slash command to play a song next
@client.tree.command(name="playnext", description="Play a song next")
@app_commands.describe(link="The URL or name of the song to play next")
async def playnext_command(interaction: discord.Interaction, link: str):
    await interaction.response.defer(ephemeral=True)
    await process_play_request(interaction.user, interaction.guild,
                               interaction.channel, link, interaction=interaction,
                               play_next=True)

# Slash command to remove a song from the queue
@client.tree.command(name="remove", description="Remove a song from the queue")
@app_commands.describe(index="The position of the song in the queue to remove")
async def remove_command(interaction: discord.Interaction, index: int):
    guild_id = str(interaction.guild.id)
    queue = queues.get(guild_id)
    if queue and 1 <= index <= len(queue):
        removed_song = queue.pop(index - 1)
        await interaction.response.send_message(
            f'❌ Removed **{removed_song["title"]}** from the queue.', ephemeral=True)
        await update_stable_message(guild_id)
    else:
        await interaction.response.send_message('❌ Invalid song index.', ephemeral=True)

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
                print(f"Permission error: Cannot delete message {message.id}")
            except discord.HTTPException as e:
                print(f"Failed to delete message {message.id}: {e}")

            # Treat the message content as a song request
            await process_play_request(message.author, message.guild,
                                       message.channel, message.content)
        else:
            # Process commands in other channels as usual
            await client.process_commands(message)
    else:
        await client.process_commands(message)

# Function to handle delayed disconnect
async def disconnect_after_delay(guild_id, delay):
    try:
        await asyncio.sleep(delay)
        voice_client = voice_clients.get(guild_id)
        if voice_client and not voice_client.is_playing():
            await voice_client.disconnect()
            voice_clients.pop(guild_id, None)  # Safely remove the voice client
            # Remove the disconnect task reference
            client.guilds_data[guild_id]['disconnect_task'] = None
            await update_stable_message(guild_id)
    except asyncio.CancelledError:
        # The task was cancelled, do nothing
        pass

# Run the bot
client.run(TOKEN)
