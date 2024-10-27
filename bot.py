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
TOKEN = os.getenv("discord_token")

# Set up bot intents and command prefix
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
client = commands.Bot(command_prefix=".", intents=intents)

# Define global variables for managing queues and voice clients
queues = {}
voice_clients = {}
youtube_base_url = 'https://www.youtube.com/'
youtube_results_url = youtube_base_url + 'results?'
youtube_watch_url = youtube_base_url + 'watch?v='
yt_dl_options = {"format": "bestaudio/best", "noplaylist": True}
ytdl = yt_dlp.YoutubeDL(yt_dl_options)

# FFmpeg options for audio playback
ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -filter:a "volume=0.25"'
}

# Data persistence
DATA_FILE = 'guilds_data.json'

def save_guilds_data():
    with open(DATA_FILE, 'w') as f:
        json.dump(client.guilds_data, f)

def load_guilds_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            client.guilds_data = json.load(f)
    else:
        client.guilds_data = {}

# Bot ready event
@client.event
async def on_ready():
    print(f'{client.user} is now jamming!')
    load_guilds_data()
    for guild_id, guild_data in client.guilds_data.items():
        channel_id = guild_data.get('channel_id')
        stable_message_id = guild_data.get('stable_message_id')
        guild = client.get_guild(int(guild_id))
        if guild:
            channel = guild.get_channel(int(channel_id))
            if channel:
                stable_message = await channel.fetch_message(int(stable_message_id))
                client.guilds_data[guild_id]['stable_message'] = stable_message
                await update_stable_message(int(guild_id))

# Setup command to create the music channel and stable message
@client.command(name="setup")
@commands.has_permissions(manage_channels=True)
async def setup(ctx):
    guild_id = str(ctx.guild.id)
    channel = discord.utils.get(ctx.guild.channels, name='leo-song-requests')
    if not channel:
        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
            )
        }
        channel = await ctx.guild.create_text_channel('leo-song-requests', overwrites=overwrites)
    stable_message = await channel.send('Setting up the music bot UI...')
    if not hasattr(client, 'guilds_data'):
        client.guilds_data = {}
    client.guilds_data[guild_id] = {
        'channel_id': channel.id,
        'stable_message_id': stable_message.id,
        'stable_message': stable_message,
        'current_song': None
    }
    save_guilds_data()
    await ctx.send('Music commands channel setup complete.')
    await update_stable_message(guild_id)

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

    view = View()
    view.add_item(Button(label='⏸️ Pause', style=ButtonStyle.primary, custom_id='pause'))
    view.add_item(Button(label='▶️ Play', style=ButtonStyle.primary, custom_id='resume'))
    view.add_item(Button(label='⏭️ Skip', style=ButtonStyle.primary, custom_id='skip'))
    view.add_item(Button(label='⏹️ Stop', style=ButtonStyle.primary, custom_id='stop'))

    total_components = len(view.children)
    max_components = 25
    for idx, song in enumerate(queue):
        if total_components >= max_components:
            break
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
    messages = await channel.history(limit=100).flatten()
    messages_to_delete = [msg for msg in messages if msg.id != stable_message_id]
    if messages_to_delete:
        await channel.delete_messages(messages_to_delete)

# Play the next song in the queue
async def play_next(ctx):
    guild_id = str(ctx.guild.id)
    if queues.get(guild_id):
        song_info = queues[guild_id].pop(0)
        client.guilds_data[guild_id]['current_song'] = song_info
        await play_song(ctx, song_info)
    else:
        client.guilds_data[guild_id]['current_song'] = None
        voice_client = voice_clients.get(guild_id)
        if voice_client:
            await voice_client.disconnect()
            del voice_clients[guild_id]
        await update_stable_message(guild_id)

# Function to play a song
async def play_song(ctx, song_info):
    guild_id = str(ctx.guild.id)
    voice_client = voice_clients[guild_id]
    song_url = song_info['url']
    player = discord.FFmpegOpusAudio(song_url, **ffmpeg_options)
    if not voice_client.is_playing():
        voice_client.play(player, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), client.loop))
        await ctx.send(f"Now playing: {song_info.get('title', 'Unknown title')}")
        client.guilds_data[guild_id]['current_song'] = song_info
    else:
        if guild_id not in queues:
            queues[guild_id] = []
        queues[guild_id].append(song_info)
        await ctx.send(f"Added to queue: {song_info.get('title', 'Unknown title')}")
    await update_stable_message(guild_id)
    save_guilds_data()

# Play command to play a song or add to the queue
@client.command(name="play")
async def play(ctx, *, link):
    if str(ctx.guild.id) not in voice_clients or not voice_clients[str(ctx.guild.id)].is_connected():
        if ctx.author.voice and ctx.author.voice.channel:
            voice_client = await ctx.author.voice.channel.connect()
            voice_clients[str(ctx.guild.id)] = voice_client
        else:
            await ctx.send("You are not connected to a voice channel.")
            return
    else:
        voice_client = voice_clients[str(ctx.guild.id)]

    if 'youtube.com/watch?v=' not in link and 'youtu.be/' not in link:
        query_string = urllib.parse.urlencode({'search_query': link})
        content = urllib.request.urlopen(youtube_results_url + query_string)
        search_results = re.findall(r'/watch\?v=(.{11})', content.read().decode())
        if not search_results:
            await ctx.send("No results found for your query.")
            return
        link = youtube_watch_url + search_results[0]

    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, lambda: ytdl.extract_info(link, download=False))
    song_info = data

    if 'entries' in data:
        await ctx.send("Playlists are not supported.")
        return

    guild_id = str(ctx.guild.id)
    if not hasattr(client, 'guilds_data'):
        client.guilds_data = {}
    if guild_id not in client.guilds_data:
        client.guilds_data[guild_id] = {}

    if not voice_client.is_playing():
        client.guilds_data[guild_id]['current_song'] = song_info
        await play_song(ctx, song_info)
    else:
        if guild_id not in queues:
            queues[guild_id] = []
        queues[guild_id].append(song_info)
        await ctx.send(f"Added to queue: {data.get('title', 'Unknown title')}")
        await update_stable_message(guild_id)

    guild_data = client.guilds_data.get(guild_id)
    if guild_data:
        stable_message_id = guild_data.get('stable_message_id')
        channel_id = guild_data.get('channel_id')
        if stable_message_id and channel_id:
            channel = client.get_channel(int(channel_id))
            await clear_channel_messages(channel, int(stable_message_id))

# Handle button interactions
@client.event
async def on_interaction(interaction):
    guild_id = str(interaction.guild.id)
    custom_id = interaction.data['custom_id']
    voice_client = voice_clients.get(guild_id)

    if custom_id == 'pause':
        if voice_client and voice_client.is_playing():
            voice_client.pause()
            await interaction.response.send_message('Paused the music.', ephemeral=True)
        else:
            await interaction.response.send_message('Nothing is playing.', ephemeral=True)
    elif custom_id == 'resume':
        if voice_client and voice_client.is_paused():
            voice_client.resume()
            await interaction.response.send_message('Resumed the music.', ephemeral=True)
        elif custom_id == 'skip':
        if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
            voice_client.stop()
            await interaction.response.send_message('Skipped the song.', ephemeral=True)
    elif custom_id == 'stop':
        if voice_client:
            await voice_client.disconnect()
            del voice_clients[guild_id]
            queues.pop(guild_id, None)
            client.guilds_data[guild_id]['current_song'] = None
            await interaction.response.send_message('Stopped the music and left the voice channel.', ephemeral=True)
    elif custom_id.startswith('remove_'):
        index = int(custom_id.split('_')[1])
        queue = queues.get(guild_id)
        if queue and 0 <= index < len(queue):
            removed_song = queue.pop(index)
            await interaction.response.send_message(f'Removed **{removed_song["title"]}** from the queue.', ephemeral=True)
    await update_stable_message(guild_id)

# Clear the song queue
@client.command(name="clear_queue")
async def clear_queue(ctx):
    guild_id = str(ctx.guild.id)
    if guild_id in queues:
        queues[guild_id].clear()
        await ctx.send("Queue cleared!")
    else:
        await ctx.send("There is no queue to clear.")
    await update_stable_message(guild_id)

# Pause the current song
@client.command(name="pause")
async def pause(ctx):
    guild_id = str(ctx.guild.id)
    voice_client = voice_clients.get(guild_id)
    if voice_client and voice_client.is_playing():
        voice_client.pause()
        await ctx.send("Paused the music.")
        await update_stable_message(guild_id)

# Resume the current song
@client.command(name="resume")
async def resume(ctx):
    guild_id = str(ctx.guild.id)
    voice_client = voice_clients.get(guild_id)
    if voice_client and voice_client.is_paused():
        voice_client.resume()
        await ctx.send("Resumed the music.")
        await update_stable_message(guild_id)

# Stop the music and disconnect from the voice channel
@client.command(name="stop")
async def stop(ctx):
    guild_id = str(ctx.guild.id)
    voice_client = voice_clients.get(guild_id)
    if voice_client:
        voice_client.stop()
        await voice_client.disconnect()
        del voice_clients[guild_id]
        queues.pop(guild_id, None)
        client.guilds_data[guild_id]['current_song'] = None
        await ctx.send("Stopped the music and left the voice channel.")
    await update_stable_message(guild_id)

# Add a song to the queue
@client.command(name="queue")
async def queue_command(ctx, *, link):
    guild_id = str(ctx.guild.id)
    if 'youtube.com/watch?v=' not in link and 'youtu.be/' not in link:
        query_string = urllib.parse.urlencode({'search_query': link})
        content = urllib.request.urlopen(youtube_results_url + query_string)
        search_results = re.findall(r'/watch\?v=(.{11})', content.read().decode())
        if not search_results:
            await ctx.send("No results found for your query.")
            return
        link = youtube_watch_url + search_results[0]

    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, lambda: ytdl.extract_info(link, download=False))
    song_info = data

    if 'entries' in data:
        await ctx.send("Playlists are not supported.")
        return

    if guild_id not in queues:
        queues[guild_id] = []
    queues[guild_id].append(song_info)
    await ctx.send(f"Added to queue: {song_info.get('title', 'Unknown title')}")
    await update_stable_message(guild_id)

# Run the bot
client.run(TOKEN)
