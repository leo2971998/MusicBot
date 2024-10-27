import discord
from discord.ext import commands
from discord import ButtonStyle, SelectOption, Embed
from discord.ui import Button, View, Select
import os
import asyncio
import yt_dlp
from dotenv import load_dotenv
import urllib.parse, urllib.request, re

def run_bot():
    load_dotenv()
    TOKEN = os.getenv('discord_token')
    intents = discord.Intents.default()
    intents.message_content = True
    client = commands.Bot(command_prefix=".", intents=intents)

    queues = {}
    voice_clients = {}
    youtube_base_url = 'https://www.youtube.com/'
    youtube_results_url = youtube_base_url + 'results?'
    youtube_watch_url = youtube_base_url + 'watch?v='
    yt_dl_options = {"format": "bestaudio/best"}
    ytdl = yt_dlp.YoutubeDL(yt_dl_options)
    ffmpeg_options = {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
        'options': '-vn -filter:a "volume=0.25"'
    }

    @client.event
    async def on_ready():
        print(f'{client.user} is now jamming')

    async def play_next(ctx):
        if queues[ctx.guild.id] != []:
            link = queues[ctx.guild.id].pop(0)
            await play(ctx, link=link)

    # Embed to display song info
    async def send_song_embed(ctx, title, url):
        embed = Embed(title="Now Playing", description=title, url=url, color=0x1DB954)
        embed.set_footer(text="MusicBot")
        await ctx.send(embed=embed)

    # Playback buttons
    class PlaybackControls(View):
        def __init__(self, ctx):
            super().__init__()
            self.ctx = ctx

        @discord.ui.button(label="Pause", style=ButtonStyle.primary)
        async def pause_button(self, button, interaction):
            try:
                voice_clients[interaction.guild.id].pause()
                await interaction.response.send_message("Paused the music.", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(str(e), ephemeral=True)

        @discord.ui.button(label="Resume", style=ButtonStyle.success)
        async def resume_button(self, button, interaction):
            try:
                voice_clients[interaction.guild.id].resume()
                await interaction.response.send_message("Resumed the music.", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(str(e), ephemeral=True)

        @discord.ui.button(label="Stop", style=ButtonStyle.danger)
        async def stop_button(self, button, interaction):
            try:
                voice_clients[interaction.guild.id].stop()
                await voice_clients[interaction.guild.id].disconnect()
                await interaction.response.send_message("Stopped the music and disconnected.", ephemeral=True)
                del voice_clients[interaction.guild.id]
            except Exception as e:
                await interaction.response.send_message(str(e), ephemeral=True)

    # Queue select dropdown
    class QueueDropdown(View):
        def __init__(self, ctx, queue):
            super().__init__()
            self.ctx = ctx
            options = [
                SelectOption(label=f"{i+1}. {song[:80]}", description="Queued Song", value=song)
                for i, song in enumerate(queue)
            ]
            self.select = Select(placeholder="Select a song from the queue", options=options, min_values=1, max_values=1)
            self.select.callback = self.select_callback
            self.add_item(self.select)

        async def select_callback(self, interaction):
            selected_song = self.select.values[0]
            await interaction.response.send_message(f"Selected song: {selected_song}")

    @client.command(name="play")
    async def play(ctx, *, link):
        try:
            voice_client = await ctx.author.voice.channel.connect()
            voice_clients[voice_client.guild.id] = voice_client
        except Exception as e:
            print(e)

        try:
            if youtube_base_url not in link:
                query_string = urllib.parse.urlencode({'search_query': link})
                content = urllib.request.urlopen(youtube_results_url + query_string)
                search_results = re.findall(r'/watch\?v=(.{11})', content.read().decode())
                link = youtube_watch_url + search_results[0]

            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(link, download=False))

            song = data['url']
            title = data.get('title', 'Unknown Title')
            await send_song_embed(ctx, title, link)

            player = discord.FFmpegOpusAudio(song, **ffmpeg_options)
            voice_clients[ctx.guild.id].play(player, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), client.loop))
            await ctx.send(view=PlaybackControls(ctx))  # Show playback buttons
        except Exception as e:
            print(e)

    @client.command(name="queue")
async def queue(ctx, *, url=None):
    if url:
        # Add song to the queue if a URL is provided
        if ctx.guild.id not in queues:
            queues[ctx.guild.id] = []
        queues[ctx.guild.id].append(url)
        await ctx.send("Added to queue!")

    if ctx.guild.id in queues and queues[ctx.guild.id]:
        # Show the queue dropdown if there are songs in the queue
        await ctx.send("Here is your queue:", view=QueueDropdown(ctx, queues[ctx.guild.id]))
    else:
        # Inform the user if the queue is empty
        await ctx.send("The queue is currently empty.")

    client.run(TOKEN)
