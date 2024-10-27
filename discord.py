import os
import asyncio
import discord
from discord.ext import commands
from discord.ui import Button, View
import yt_dlp
from dotenv import load_dotenv
import urllib.parse, urllib.request, re

def run_bot():
    load_dotenv()
    TOKEN = os.getenv('discord_token')

    intents = discord.Intents.default()
    intents.message_content = True
    intents.voice_states = True
    client = commands.Bot(command_prefix=".", intents=intents)

    queues = {}
    voice_clients = {}
    yt_dl_options = {"format": "bestaudio/best", "noplaylist": "True"}
    ytdl = yt_dlp.YoutubeDL(yt_dl_options)

    ffmpeg_options = {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
        'options': '-vn -filter:a "volume=0.25"'
    }

    @client.event
    async def on_ready():
        print(f'{client.user} is now jamming')

    async def play_next(ctx):
        if queues.get(ctx.guild.id):
            next_url = queues[ctx.guild.id].pop(0)
            await play_song(ctx, next_url)
        else:
            await voice_clients[ctx.guild.id].disconnect()
            del voice_clients[ctx.guild.id]

    async def play_song(ctx, url):
        try:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
            song = data['url']
            title = data.get('title')
            thumbnail = data.get('thumbnail')
            webpage_url = data.get('webpage_url')

            player = discord.FFmpegPCMAudio(song, **ffmpeg_options)
            voice_client = voice_clients[ctx.guild.id]

            # Create an embed for now playing
            embed = discord.Embed(title="Now Playing", description=f"[{title}]({webpage_url})", color=0x1db954)
            embed.set_thumbnail(url=thumbnail)

            # Create control buttons
            class PlayerControls(View):
                def __init__(self):
                    super().__init__(timeout=None)

                @discord.ui.button(label='Pause', style=discord.ButtonStyle.primary, emoji='⏸️')
                async def pause_button(self, interaction: discord.Interaction, button: Button):
                    if voice_client.is_playing():
                        voice_client.pause()
                        await interaction.response.send_message("Music paused.", ephemeral=True)
                    else:
                        await interaction.response.send_message("No music is playing.", ephemeral=True)

                @discord.ui.button(label='Resume', style=discord.ButtonStyle.primary, emoji='▶️')
                async def resume_button(self, interaction: discord.Interaction, button: Button):
                    if voice_client.is_paused():
                        voice_client.resume()
                        await interaction.response.send_message("Music resumed.", ephemeral=True)
                    else:
                        await interaction.response.send_message("Music is not paused.", ephemeral=True)

                @discord.ui.button(label='Skip', style=discord.ButtonStyle.primary, emoji='⏭️')
                async def skip_button(self, interaction: discord.Interaction, button: Button):
                    if voice_client.is_playing():
                        voice_client.stop()
                        await interaction.response.send_message("Skipped the song.", ephemeral=True)
                    else:
                        await interaction.response.send_message("No music is playing.", ephemeral=True)

                @discord.ui.button(label='Stop', style=discord.ButtonStyle.primary, emoji='⏹️')
                async def stop_button(self, interaction: discord.Interaction, button: Button):
                    if voice_client.is_connected():
                        voice_client.stop()
                        queues[ctx.guild.id] = []
                        await voice_client.disconnect()
                        await interaction.response.send_message("Music stopped and disconnected.", ephemeral=True)
                    else:
                        await interaction.response.send_message("Not connected to a voice channel.", ephemeral=True)

            # Send the embed with buttons
            await ctx.send(embed=embed, view=PlayerControls())

            def after_playing(error):
                if error:
                    print(f"Error occurred: {error}")
                coro = play_next(ctx)
                fut = asyncio.run_coroutine_threadsafe(coro, client.loop)
                try:
                    fut.result()
                except Exception as e:
                    print(f"Error in after_playing: {e}")

            voice_client.play(player, after=after_playing)

        except Exception as e:
            print(f"Error in play_song: {e}")
            await ctx.send("An error occurred while trying to play the track.")

    @client.command(name="play")
    async def play(ctx, *, query):
        try:
            voice_client = voice_clients.get(ctx.guild.id)
            if voice_client is None:
                if ctx.author.voice and ctx.author.voice.channel:
                    voice_client = await ctx.author.voice.channel.connect()
                    voice_clients[ctx.guild.id] = voice_client
                else:
                    await ctx.send("You need to be in a voice channel to play music!")
                    return

            # Search YouTube if a URL is not provided
            if not re.match(r'https?://(?:www\.)?.+', query):
                query_string = urllib.parse.urlencode({'search_query': query})
                html_content = urllib.request.urlopen(f"https://www.youtube.com/results?{query_string}")
                search_results = re.findall(r'/watch\?v=(.{11})', html_content.read().decode())
                url = f"https://www.youtube.com/watch?v={search_results[0]}"
            else:
                url = query

            # If already playing, add to queue
            if voice_client.is_playing() or voice_client.is_paused():
                if ctx.guild.id not in queues:
                    queues[ctx.guild.id] = []
                queues[ctx.guild.id].append(url)
                await ctx.send(f"Added to queue: {url}")
            else:
                await play_song(ctx, url)

        except Exception as e:
            print(f"Error in play command: {e}")
            await ctx.send("An error occurred while trying to play the track.")

    @client.command(name="pause")
    async def pause(ctx):
        voice_client = voice_clients.get(ctx.guild.id)
        if voice_client and voice_client.is_playing():
            voice_client.pause()
            await ctx.send("Music paused.")
        else:
            await ctx.send("No music is playing.")

    @client.command(name="resume")
    async def resume(ctx):
        voice_client = voice_clients.get(ctx.guild.id)
        if voice_client and voice_client.is_paused():
            voice_client.resume()
            await ctx.send("Music resumed.")
        else:
            await ctx.send("Music is not paused.")

    @client.command(name="skip")
    async def skip(ctx):
        voice_client = voice_clients.get(ctx.guild.id)
        if voice_client and voice_client.is_playing():
            voice_client.stop()
            await ctx.send("Skipped the song.")
        else:
            await ctx.send("No music is playing.")

    @client.command(name="stop")
    async def stop(ctx):
        voice_client = voice_clients.get(ctx.guild.id)
        if voice_client and voice_client.is_connected():
            voice_client.stop()
            queues[ctx.guild.id] = []
            await voice_client.disconnect()
            del voice_clients[ctx.guild.id]
            await ctx.send("Music stopped and disconnected.")
        else:
            await ctx.send("Not connected to a voice channel.")

    @client.command(name="queue")
    async def show_queue(ctx):
        if queues.get(ctx.guild.id):
            queue_list = ''
            for idx, url in enumerate(queues[ctx.guild.id], start=1):
                queue_list += f"{idx}. {url}\n"
            embed = discord.Embed(title="Current Queue", description=queue_list, color=0x1db954)
            await ctx.send(embed=embed)
        else:
            await ctx.send("The queue is empty.")

    @client.command(name="clear_queue")
    async def clear_queue(ctx):
        if ctx.guild.id in queues:
            queues[ctx.guild.id].clear()
            await ctx.send("Queue cleared!")
        else:
            await ctx.send("There is no queue to clear.")

    client.run(TOKEN)
