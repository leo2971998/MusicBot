import discord
from discord.ext import commands
from discord.ui import Button, View
from discord import Embed, ButtonStyle
import os
import asyncio
import yt_dlp
from dotenv import load_dotenv
import urllib.parse, urllib.request, re
import json

# Load the environment variables
load_dotenv()
TOKEN = os.getenv("discord_token") or "YOUR_DISCORD_BOT_TOKEN"

# Set up bot intents and command prefix
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
client = commands.Bot(command_prefix=".", intents=intents)
client.guilds_data = {}  # Initialize guilds_data here

# Define global variables for managing queues and voice clients
queues = {}
voice_clients = {}
youtube_base_url = 'https://www.youtube.com/'
youtube_results_url = youtube_base_url + 'results?'
youtube_watch_url = youtube_base_url + 'watch?v='
yt_dl_options = {"format": "bestaudio/best", "noplaylist": False}  # Allow playlists
ytdl = yt_dlp.YoutubeDL(yt_dl_options)

# FFmpeg options for audio playback
ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -filter:a "volume=0.25"'
}

# Data persistence
DATA_FILE = 'guilds_data.json'

def save_guilds_data():
    serializable_data = {}
    for guild_id, guild_data in client.guilds_data.items():
        # Create a copy excluding non-serializable items
        data_to_save = guild_data.copy()
        data_to_save.pop('stable_message', None)
        serializable_data[guild_id] = data_to_save
    with open(DATA_FILE, 'w') as f:
        json.dump(serializable_data, f)

def load_guilds_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            try:
                client.guilds_data = json.load(f)
            except json.JSONDecodeError:
                print("Invalid JSON in guilds_data.json. Initializing with empty data.")
                client.guilds_data = {}
    else:
        client.guilds_data = {}

# Bot ready event
@client.event
async def on_ready():
    await client.tree.sync()
    print(f'{client.user} is now jamming!')
    load_guilds_data()
    for guild_id, guild_data in client.guilds_data.items():
        channel_id = guild_data.get('channel_id')
        stable_message_id = guild_data.get('stable_message_id')
        guild = client.get_guild(int(guild_id))
        if guild:
            channel = guild.get_channel(int(channel_id))
            if channel:
                try:
                    stable_message = await channel.fetch_message(int(stable_message_id))
                    client.guilds_data[guild_id]['stable_message'] = stable_message
                    await update_stable_message(int(guild_id))
                except Exception as e:
                    print(f"Error fetching stable message for guild {guild_id}: {e}")

# Setup command to create the music channel and stable message
@client.tree.command(name="setup", description="Set up the music channel and bot UI")
@commands.has_permissions(manage_channels=True)
async def setup(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
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
    client.guilds_data[guild_id] = {
        'channel_id': channel.id,
        'stable_message_id': stable_message.id,
        'current_song': None
    }
    save_guilds_data()
    client.guilds_data[guild_id]['stable_message'] = stable_message
    await interaction.response.send_message('Music commands channel setup complete.', ephemeral=True)
    # Initialize the stable message content
    await update_stable_message(guild_id)
    # Clear other messages
    await clear_channel_messages(channel, stable_message.id)

# Update the stable message with current song and queue
async def update_stable_message(guild_id):
    guild_data = client.guilds_data.get(str(guild_id))
    if not guild_data:
        return
    stable_message = guild_data.get('stable_message')
    if not stable_message:
        return
    queue = queues.get(str(guild_id), [])
    voice_client = voice_clients.get(str(guild_id))

    # Now Playing Embed
    if voice_client and voice_client.is_playing():
        current_song = guild_data.get('current_song')
        now_playing_embed = Embed(
            title='🎶 Now Playing',
            description=f"**[{current_song['title']}]({current_song['webpage_url']})**",
            color=0x1db954
        )
        now_playing_embed.set_thumbnail(url=current_song.get('thumbnail'))
        now_playing_embed.set_footer(text='Use the buttons below to control playback.')
    else:
        now_playing_embed = Embed(
            title='🎶 Now Playing',
            description='No music is currently playing.',
            color=0x1db954
        )

    # Queue Embed
    if queue:
        queue_description = '\n'.join(
            [f"{idx + 1}. **[{song['title']}]({song['webpage_url']})**" for idx, song in enumerate(queue)]
        )
    else:
        queue_description = 'No songs in the queue.'
    queue_embed = Embed(
        title='📜 Current Queue',
        description=queue_description,
        color=0x1db954
    )
    queue_embed.set_footer(text=f"Total songs in queue: {len(queue)}")

    # Create a View for all buttons
    view = View()

    # Control Buttons
    view.add_item(Button(label='⏸️ Pause', style=ButtonStyle.primary, custom_id='pause'))
    view.add_item(Button(label='▶️ Resume', style=ButtonStyle.primary, custom_id='resume'))
    view.add_item(Button(label='⏭️ Skip', style=ButtonStyle.primary, custom_id='skip'))
    view.add_item(Button(label='⏹️ Stop', style=ButtonStyle.primary, custom_id='stop'))
    view.add_item(Button(label='🗑️ Clear Queue', style=ButtonStyle.danger, custom_id='clear_queue'))

    # Remove Buttons for Queue
    total_components = len(view.children)
    max_components = 25  # Discord allows up to 25 components
    for idx, song in enumerate(queue):
        if total_components >= max_components:
            break  # Cannot add more components
        button = Button(
            label=f"❌ Remove {idx + 1}",
            style=ButtonStyle.secondary,
            custom_id=f'remove_{idx}'
        )
        view.add_item(button)
        total_components += 1

    await stable_message.edit(content=None, embeds=[now_playing_embed, queue_embed], view=view)
    save_guilds_data()

# Clear messages in the channel except the stable message
async def clear_channel_messages(channel, stable_message_id):
    async for message in channel.history(limit=100):
        if message.id != stable_message_id:
            try:
                await message.delete()
            except discord.Forbidden:
                print(f"Permission error: Cannot delete message {message.id}")
            except discord.HTTPException as e:
                print(f"Failed to delete message {message.id}: {e}")

# Play the next song in the queue
async def play_next(guild_id):
    guild_id = str(guild_id)
    if queues.get(guild_id):
        song_info = queues[guild_id].pop(0)
        client.guilds_data[guild_id]['current_song'] = song_info
        await play_song(guild_id, song_info)
    else:
        # No more songs in the queue
        client.guilds_data[guild_id]['current_song'] = None
        voice_client = voice_clients.get(guild_id)
        if voice_client:
            await voice_client.disconnect()
            del voice_clients[guild_id]
        await update_stable_message(guild_id)

# Function to play a song
async def play_song(guild_id, song_info):
    guild_id = str(guild_id)
    voice_client = voice_clients[guild_id]
    song_url = song_info['url']
    player = discord.FFmpegOpusAudio(song_url, **ffmpeg_options)
    if not voice_client.is_playing():
        def after_playing(error):
            if error:
                print(f"Error occurred while playing: {error}")
            future = asyncio.run_coroutine_threadsafe(play_next(guild_id), client.loop)
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
        await channel.send(f"🎶 Now playing: **{song_info.get('title', 'Unknown title')}**")
        client.guilds_data[guild_id]['current_song'] = song_info
    else:
        # Add to queue
        if guild_id not in queues:
            queues[guild_id] = []
        queues[guild_id].append(song_info)
        channel_id = client.guilds_data[guild_id]['channel_id']
        channel = client.get_channel(int(channel_id))
        await channel.send(f"➕ Added to queue: **{song_info.get('title', 'Unknown title')}**")
    await update_stable_message(guild_id)
    save_guilds_data()

# Helper function to process play requests
async def process_play_request(user, guild, channel, link, interaction=None):
    guild_id = str(guild.id)
    # Connect to the voice channel if not already connected
    voice_client = voice_clients.get(guild_id)
    if not voice_client or not voice_client.is_connected():
        if user.voice and user.voice.channel:
            voice_client = await user.voice.channel.connect()
            voice_clients[guild_id] = voice_client
        else:
            msg = "❌ You are not connected to a voice channel."
            if interaction:
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await channel.send(msg)
            return
    else:
        voice_client = voice_clients[guild_id]

    # Search and retrieve YouTube link if not already a direct link or playlist
    if ('youtube.com/watch?v=' not in link and 'youtu.be/' not in link) and ('youtube.com/playlist?' not in link):
        query_string = urllib.parse.urlencode({'search_query': link})
        try:
            with urllib.request.urlopen(youtube_results_url + query_string) as response:
                html_content = response.read().decode()
            search_results = re.findall(r'/watch\?v=(.{11})', html_content)
            if not search_results:
                msg = "❌ No results found for your query."
                if interaction:
                    await interaction.followup.send(msg, ephemeral=True)
                else:
                    await channel.send(msg)
                return
            link = youtube_watch_url + search_results[0]
        except Exception as e:
            msg = f"❌ Error searching for the song: {e}"
            if interaction:
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await channel.send(msg)
            return

    # Extract audio and play
    loop = asyncio.get_event_loop()
    try:
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(link, download=False))
    except Exception as e:
        msg = f"❌ Error extracting song information: {e}"
        if interaction:
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await channel.send(msg)
        return

    # Handle playlist
    if 'entries' in data:
        playlist_entries = data['entries']
        added_songs = []
        for entry in playlist_entries:
            if entry is None:
                continue  # Skip if entry is None
            song_info = entry
            # Add to queue
            if guild_id not in queues:
                queues[guild_id] = []
            queues[guild_id].append(song_info)
            added_songs.append(song_info['title'])
        msg = f"🎶 Added playlist **{data.get('title', 'Unknown playlist')}** with {len(added_songs)} songs to the queue."
        if interaction:
            await interaction.followup.send(msg)
        else:
            await channel.send(msg)
    else:
        song_info = data  # Store the entire data for later use

        # Initialize guild data if not present
        if guild_id not in client.guilds_data:
            client.guilds_data[guild_id] = {}

        # Play or queue the song
        if not voice_client.is_playing():
            client.guilds_data[guild_id]['current_song'] = song_info
            await play_song(guild_id, song_info)
            msg = f"🎶 Now playing: **{song_info.get('title', 'Unknown title')}**"
            if interaction:
                await interaction.followup.send(msg)
            else:
                await channel.send(msg)
        else:
            if guild_id not in queues:
                queues[guild_id] = []
            queues[guild_id].append(song_info)
            msg = f"➕ Added to queue: **{song_info.get('title', 'Unknown title')}**"
            if interaction:
                await interaction.followup.send(msg)
            else:
                await channel.send(msg)

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
@discord.app_commands.describe(link="The URL or name of the song to play")
async def play_command(interaction: discord.Interaction, link: str):
    await interaction.response.defer(ephemeral=False)
    await process_play_request(interaction.user, interaction.guild, interaction.channel, link, interaction=interaction)

# Pause command
@client.tree.command(name="pause", description="Pause the currently playing song")
async def pause_command(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    voice_client = voice_clients.get(guild_id)
    if voice_client and voice_client.is_playing():
        voice_client.pause()
        await interaction.response.send_message("⏸️ Paused the music.", ephemeral=True)
        await update_stable_message(guild_id)
    else:
        await interaction.response.send_message("❌ Nothing is playing.", ephemeral=True)

# Resume command
@client.tree.command(name="resume", description="Resume the paused song")
async def resume_command(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    voice_client = voice_clients.get(guild_id)
    if voice_client and voice_client.is_paused():
        voice_client.resume()
        await interaction.response.send_message("▶️ Resumed the music.", ephemeral=True)
        await update_stable_message(guild_id)
    else:
        await interaction.response.send_message("❌ Nothing is paused.", ephemeral=True)

# Stop command
@client.tree.command(name="stop", description="Stop the music and leave the voice channel")
async def stop_command(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    voice_client = voice_clients.get(guild_id)
    if voice_client:
        voice_client.stop()
        await voice_client.disconnect()
        del voice_clients[guild_id]
        queues.pop(guild_id, None)
        client.guilds_data[guild_id]['current_song'] = None
        await interaction.response.send_message("⏹️ Stopped the music and left the voice channel.", ephemeral=True)
        await update_stable_message(guild_id)
    else:
        await interaction.response.send_message("❌ Not connected to a voice channel.", ephemeral=True)

# Clear Queue command
@client.tree.command(name="clear_queue", description="Clear the song queue")
async def clear_queue_command(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    if guild_id in queues:
        queues[guild_id].clear()
        await interaction.response.send_message("🗑️ Queue cleared!", ephemeral=True)
    else:
        await interaction.response.send_message("❌ There is no queue to clear.", ephemeral=True)
    await update_stable_message(guild_id)

# Handle button interactions
@client.event
async def on_interaction(interaction):
    if not interaction.type == discord.InteractionType.component:
        return
    guild_id = str(interaction.guild.id)
    custom_id = interaction.data['custom_id']
    voice_client = voice_clients.get(guild_id)

    if custom_id == 'pause':
        if voice_client and voice_client.is_playing():
            voice_client.pause()
            await interaction.response.send_message('⏸️ Paused the music.', ephemeral=True)
        else:
            await interaction.response.send_message('❌ Nothing is playing.', ephemeral=True)
    elif custom_id == 'resume':
        if voice_client and voice_client.is_paused():
            voice_client.resume()
            await interaction.response.send_message('▶️ Resumed the music.', ephemeral=True)
        else:
            await interaction.response.send_message('❌ Nothing is paused.', ephemeral=True)
    elif custom_id == 'skip':
        if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
            voice_client.stop()
            await interaction.response.send_message('⏭️ Skipped the song.', ephemeral=True)
            # No need to call play_next here; it will be called automatically by after_playing
        else:
            await interaction.response.send_message('❌ Nothing is playing.', ephemeral=True)
    elif custom_id == 'stop':
        if voice_client:
            voice_client.stop()
            await voice_client.disconnect()
            del voice_clients[guild_id]
            queues.pop(guild_id, None)
            client.guilds_data[guild_id]['current_song'] = None
            await interaction.response.send_message('⏹️ Stopped the music and left the voice channel.', ephemeral=True)
        else:
            await interaction.response.send_message('❌ Not connected to a voice channel.', ephemeral=True)
    elif custom_id == 'clear_queue':
        if guild_id in queues:
            queues[guild_id].clear()
            await interaction.response.send_message('🗑️ Cleared the queue.', ephemeral=True)
        else:
            await interaction.response.send_message('❌ The queue is already empty.', ephemeral=True)
    elif custom_id.startswith('remove_'):
        try:
            index = int(custom_id.split('_')[1])
            queue = queues.get(guild_id)
            if queue and 0 <= index < len(queue):
                removed_song = queue.pop(index)
                await interaction.response.send_message(f'❌ Removed **{removed_song["title"]}** from the queue.', ephemeral=True)
            else:
                await interaction.response.send_message('❌ Invalid song index.', ephemeral=True)
        except (IndexError, ValueError):
            await interaction.response.send_message('❌ Invalid remove command.', ephemeral=True)
    else:
        await interaction.response.send_message('❌ Unknown interaction.', ephemeral=True)

    await update_stable_message(guild_id)

    # Clear messages in the channel after interaction
    guild_data = client.guilds_data.get(guild_id)
    if guild_data:
        stable_message_id = guild_data.get('stable_message_id')
        channel_id = guild_data.get('channel_id')
        if stable_message_id and channel_id:
            channel = client.get_channel(int(channel_id))
            await clear_channel_messages(channel, int(stable_message_id))

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
            await process_play_request(message.author, message.guild, message.channel, message.content)
        else:
            # Process commands in other channels as usual
            await client.process_commands(message)
    else:
        await client.process_commands(message)

# Run the bot
client.run(TOKEN)
