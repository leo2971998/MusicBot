import discord
from discord.ext import commands
import os
import asyncio
import yt_dlp
from dotenv import load_dotenv
import urllib.parse, urllib.request, re

# Load the environment variables
load_dotenv()
TOKEN = os.getenv("discord_token")

# Set up bot intents and command prefix
intents = discord.Intents.default()
intents.message_content = True
client = commands.Bot(command_prefix=".", intents=intents)

# Define global variables for managing queues and voice clients
queues = {}
voice_clients = {}
youtube_base_url = 'https://www.youtube.com/'
youtube_results_url = youtube_base_url + 'results?'
youtube_watch_url = youtube_base_url + 'watch?v='
yt_dl_options = {"format": "bestaudio/best"}
ytdl = yt_dlp.YoutubeDL(yt_dl_options)

# FFmpeg options for audio playback
ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -filter:a "volume=0.25"'
}

# Bot ready event
@client.event
async def on_ready():
    print(f'{client.user} is now jamming!')

# Play the next song in the queue
async def play_next(ctx):
    if queues.get(ctx.guild.id):
        link = queues[ctx.guild.id].pop(0)
        await play(ctx, link=link)

# Play command to play a song or add to the queue
@client.command(name="play")
async def play(ctx, *, link):
    try:
        # Connect to the voice channel if not already connected
        if ctx.guild.id not in voice_clients or not voice_clients[ctx.guild.id].is_connected():
            voice_client = await ctx.author.voice.channel.connect()
            voice_clients[ctx.guild.id] = voice_client
        else:
            voice_client = voice_clients[ctx.guild.id]

        # Search and retrieve YouTube link if not already a direct link
        if youtube_base_url not in link:
            query_string = urllib.parse.urlencode({'search_query': link})
            content = urllib.request.urlopen(youtube_results_url + query_string)
            search_results = re.findall(r'/watch\?v=(.{11})', content.read().decode())
            link = youtube_watch_url + search_results[0]

        # Extract audio and play
        data = await asyncio.get_event_loop().run_in_executor(None, lambda: ytdl.extract_info(link, download=False))
        song = data['url']
        player = discord.FFmpegOpusAudio(song, **ffmpeg_options)

        if not voice_client.is_playing():
            voice_client.play(player, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), client.loop))
            await ctx.send(f"Now playing: {data.get('title', 'Unknown title')}")
        else:
            # Add to queue if something is already playing
            if ctx.guild.id not in queues:
                queues[ctx.guild.id] = []
            queues[ctx.guild.id].append(link)
            await ctx.send(f"Added to queue: {data.get('title', 'Unknown title')}")

    except Exception as e:
        print(e)
        await ctx.send("An error occurred while trying to play the song.")

# Clear the song queue
@client.command(name="clear_queue")
async def clear_queue(ctx):
    if ctx.guild.id in queues:
        queues[ctx.guild.id].clear()
        await ctx.send("Queue cleared!")
    else:
        await ctx.send("There is no queue to clear.")

# Pause the current song
@client.command(name="pause")
async def pause(ctx):
    try:
        if ctx.guild.id in voice_clients and voice_clients[ctx.guild.id].is_playing():
            voice_clients[ctx.guild.id].pause()
            await ctx.send("Paused the music.")
    except Exception as e:
        print(e)

# Resume the current song
@client.command(name="resume")
async def resume(ctx):
    try:
        if ctx.guild.id in voice_clients and voice_clients[ctx.guild.id].is_paused():
            voice_clients[ctx.guild.id].resume()
            await ctx.send("Resumed the music.")
    except Exception as e:
        print(e)

# Stop the music and disconnect from the voice channel
@client.command(name="stop")
async def stop(ctx):
    try:
        if ctx.guild.id in voice_clients:
            voice_clients[ctx.guild.id].stop()
            await voice_clients[ctx.guild.id].disconnect()
            del voice_clients[ctx.guild.id]
            await ctx.send("Stopped the music and left the voice channel.")
    except Exception as e:
        print(e)

# Add a song to the queue
@client.command(name="queue")
async def queue(ctx, *, url):
    if ctx.guild.id not in queues:
        queues[ctx.guild.id] = []
    queues[ctx.guild.id].append(url)
    await ctx.send("Added to queue!")

# Run the bot
client.run(TOKEN)
