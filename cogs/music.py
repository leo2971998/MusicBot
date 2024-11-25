# cogs/music.py

import discord
from discord.ext import commands
from discord import app_commands, Embed
import yt_dlp
from utils.data_persistence import save_guilds_data, load_guilds_data
from utils.helpers import format_time, create_progress_bar_emoji
from views.music_controls import MusicControlView
import asyncio
import time
import urllib.parse
import urllib.request
import re

class Music(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.client.guilds_data = {}
        self.voice_clients = {}
        self.queues = {}
        self.youtube_base_url = 'https://www.youtube.com/'
        self.youtube_results_url = self.youtube_base_url + 'results?'
        self.youtube_watch_url = self.youtube_base_url + 'watch?v='
        self.ytdl = yt_dlp.YoutubeDL({
            "format": "bestaudio/best",
            "noplaylist": False,
            "quiet": True,
            "default_search": "auto",
            "extract_flat": False,
            "nocheckcertificate": True,
        })
        self.ffmpeg_options = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn'
        }

    @commands.Cog.listener()
    async def on_ready(self):
        load_guilds_data(self.client)
        for guild_id, guild_data in self.client.guilds_data.items():
            channel_id = guild_data.get('channel_id')
            stable_message_id = guild_data.get('stable_message_id')
            guild = self.client.get_guild(int(guild_id))
            if guild:
                channel = guild.get_channel(int(channel_id))
                if channel:
                    try:
                        stable_message = await channel.fetch_message(int(stable_message_id))
                        self.client.guilds_data[guild_id]['stable_message'] = stable_message
                        await self.update_stable_message(int(guild_id))
                    except Exception as e:
                        print(f"Error fetching stable message for guild {guild_id}: {e}")

    @app_commands.command(name="setup", description="Set up the music channel and bot UI")
    @commands.has_permissions(manage_channels=True)
    async def setup(self, interaction: discord.Interaction):
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
        self.client.guilds_data[guild_id] = {
            'channel_id': channel.id,
            'stable_message_id': stable_message.id,
            'current_song': None
        }
        save_guilds_data(self.client)
        self.client.guilds_data[guild_id]['stable_message'] = stable_message
        await interaction.response.send_message('Music commands channel setup complete.', ephemeral=True)
        # Initialize the stable message content
        await self.update_stable_message(guild_id)
        # Clear other messages
        await self.clear_channel_messages(channel, stable_message.id)

    @app_commands.command(name="play", description="Play a song or add it to the queue")
    @discord.app_commands.describe(link="The URL or name of the song to play")
    async def play(self, interaction: discord.Interaction, link: str):
        await interaction.response.defer(ephemeral=False)
        await self.process_play_request(interaction.user, interaction.guild, interaction.channel, link, interaction=interaction)

    @app_commands.command(name="pause", description="Pause the currently playing song")
    async def pause_command(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)
        voice_client = self.voice_clients.get(guild_id)
        if voice_client and voice_client.is_playing():
            voice_client.pause()
            await interaction.response.send_message("⏸️ Paused the music.", ephemeral=True)
            await self.update_stable_message(guild_id)
        else:
            await interaction.response.send_message("❌ Nothing is playing.", ephemeral=True)

    @app_commands.command(name="resume", description="Resume the paused song")
    async def resume_command(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)
        voice_client = self.voice_clients.get(guild_id)
        if voice_client and voice_client.is_paused():
            voice_client.resume()
            await interaction.response.send_message("▶️ Resumed the music.", ephemeral=True)
            await self.update_stable_message(guild_id)
        else:
            await interaction.response.send_message("❌ Nothing is paused.", ephemeral=True)

    @app_commands.command(name="stop", description="Stop the music and leave the voice channel")
    async def stop_command(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)
        voice_client = self.voice_clients.get(guild_id)
        if voice_client:
            voice_client.stop()
            await voice_client.disconnect()
            self.voice_clients.pop(guild_id, None)
            self.queues.pop(guild_id, None)
            self.client.guilds_data[guild_id]['current_song'] = None

            # Cancel the progress updater task
            progress_task = self.client.guilds_data[guild_id].get('progress_task')
            if progress_task:
                progress_task.cancel()
                self.client.guilds_data[guild_id]['progress_task'] = None

            # Cancel the disconnect task if it exists
            disconnect_task = self.client.guilds_data[guild_id].get('disconnect_task')
            if disconnect_task:
                disconnect_task.cancel()
                self.client.guilds_data[guild_id]['disconnect_task'] = None

            await interaction.response.send_message("⏹️ Stopped the music and left the voice channel.", ephemeral=True)
            await self.update_stable_message(guild_id)
        else:
            await interaction.response.send_message("❌ Not connected to a voice channel.", ephemeral=True)

    @app_commands.command(name="clear_queue", description="Clear the song queue")
    async def clear_queue_command(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)
        if guild_id in self.queues:
            self.queues[guild_id].clear()
            await interaction.response.send_message("🗑️ Queue cleared!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ There is no queue to clear.", ephemeral=True)
        await self.update_stable_message(guild_id)

    @app_commands.command(name="nowplaying", description="Show the current song and progress")
    async def nowplaying_command(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)
        guild_data = self.client.guilds_data.get(guild_id)
        if not guild_data or not guild_data.get('current_song'):
            await interaction.response.send_message("No song is currently playing.", ephemeral=True)
            return

        current_song = guild_data['current_song']
        start_time = guild_data['song_start_time']
        duration = guild_data['song_duration']
        elapsed = time.monotonic() - start_time
        elapsed = min(elapsed, duration)

        elapsed_str = format_time(elapsed)
        duration_str = format_time(duration)
        progress_bar = create_progress_bar_emoji(elapsed, duration)

        now_playing_embed = Embed(
            title='🎶 Now Playing',
            description=f"**[{current_song['title']}]({current_song['webpage_url']})**",
            color=0x1db954
        )
        now_playing_embed.set_thumbnail(url=current_song.get('thumbnail'))
        now_playing_embed.add_field(name='Progress', value=f"`{elapsed_str} / {duration_str}`\n{progress_bar}", inline=False)

        await interaction.response.send_message(embed=now_playing_embed, ephemeral=True)

    # Event handler for message deletion and processing song requests
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author == self.client.user:
            return  # Ignore messages from the bot itself

        guild_id = str(message.guild.id)
        guild_data = self.client.guilds_data.get(guild_id)
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
                await self.process_play_request(message.author, message.guild, message.channel, message.content)
            else:
                # Process commands in other channels as usual
                await self.client.process_commands(message)
        else:
            await self.client.process_commands(message)

    # Utility Functions

    async def update_stable_message(self, guild_id):
        guild_id = str(guild_id)
        guild_data = self.client.guilds_data.get(guild_id)
        if not guild_data:
            return
        stable_message = guild_data.get('stable_message')
        if not stable_message:
            return
        queue = self.queues.get(guild_id, [])
        voice_client = self.voice_clients.get(guild_id)

        # Now Playing Embed
        if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
            current_song = guild_data.get('current_song')
            start_time = guild_data.get('song_start_time')
            duration = guild_data.get('song_duration')

            elapsed = time.monotonic() - start_time
            elapsed = min(elapsed, duration)  # Ensure elapsed doesn't exceed duration
            remaining = max(0, duration - elapsed)

            elapsed_str = format_time(elapsed)
            duration_str = format_time(duration)

            # Create a progress bar with emoji blocks
            progress_bar = create_progress_bar_emoji(elapsed, duration)

            now_playing_embed = Embed(
                title='🎶 Now Playing',
                description=f"**[{current_song['title']}]({current_song['webpage_url']})**",
                color=0x1db954
            )
            now_playing_embed.set_thumbnail(url=current_song.get('thumbnail'))

            # Add progress information
            now_playing_embed.add_field(name='Progress', value=f"`{elapsed_str} / {duration_str}`\n{progress_bar}", inline=False)
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

        # Create the MusicControlView
        view = MusicControlView(queue, self)

        try:
            await stable_message.edit(content=None, embeds=[now_playing_embed, queue_embed], view=view)
        except discord.errors.HTTPException as e:
            print(f"Rate limit hit when updating message in guild {guild_id}: {e}")

        save_guilds_data(self.client)

    async def play_next(self, guild_id):
        guild_id = str(guild_id)
        # Cancel the progress updater task
        progress_task = self.client.guilds_data[guild_id].get('progress_task')
        if progress_task:
            progress_task.cancel()
            self.client.guilds_data[guild_id]['progress_task'] = None

        if self.queues.get(guild_id):
            song_info = self.queues[guild_id].pop(0)
            self.client.guilds_data[guild_id]['current_song'] = song_info
            await self.play_song(guild_id, song_info)
        else:
            # No more songs in the queue
            self.client.guilds_data[guild_id]['current_song'] = None

            # Schedule a delayed disconnect
            if not self.client.guilds_data[guild_id].get('disconnect_task'):
                disconnect_task = self.client.loop.create_task(self.disconnect_after_delay(guild_id, delay=300))  # 5 minutes
                self.client.guilds_data[guild_id]['disconnect_task'] = disconnect_task

            await self.update_stable_message(guild_id)

    async def play_song(self, guild_id, song_info):
        guild_id = str(guild_id)
        voice_client = self.voice_clients[guild_id]

        # Cancel any scheduled disconnect task
        self.cancel_disconnect_task(guild_id)

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
        player = discord.FFmpegPCMAudio(song_url, **self.ffmpeg_options)
        if not voice_client.is_playing():
            def after_playing(error):
                if error:
                    print(f"Error occurred while playing: {error}")
                future = asyncio.run_coroutine_threadsafe(self.play_next(guild_id), self.client.loop)
                try:
                    future.result()
                except Exception as e:
                    print(f"Error in play_next: {e}")

            voice_client.play(
                player,
                after=after_playing
            )
            channel_id = self.client.guilds_data[guild_id]['channel_id']
            channel = self.client.get_channel(int(channel_id))
            await channel.send(f"🎶 Now playing: **{song_info.get('title', 'Unknown title')}**")
            self.client.guilds_data[guild_id]['current_song'] = song_info

            # Record the start time and duration using time.monotonic()
            self.client.guilds_data[guild_id]['song_start_time'] = time.monotonic()
            self.client.guilds_data[guild_id]['song_duration'] = song_info.get('duration', 0)

            # Start the progress updater task
            self.client.guilds_data[guild_id]['progress_task'] = self.client.loop.create_task(self.update_progress(guild_id))
        else:
            # Add to queue
            if guild_id not in self.queues:
                self.queues[guild_id] = []
            self.queues[guild_id].append(song_info)
            channel_id = self.client.guilds_data[guild_id]['channel_id']
            channel = self.client.get_channel(int(channel_id))
            await channel.send(f"➕ Added to queue: **{song_info.get('title', 'Unknown title')}**")
        await self.update_stable_message(guild_id)
        save_guilds_data(self.client)

    async def update_progress(self, guild_id):
        guild_id = str(guild_id)
        try:
            while True:
                await asyncio.sleep(5)  # Update every 5 seconds to avoid rate limits
                voice_client = self.voice_clients.get(guild_id)
                if not voice_client or not voice_client.is_playing():
                    break  # Stop updating if not playing

                await self.update_stable_message(guild_id)
        except asyncio.CancelledError:
            # Task was cancelled, exit gracefully
            pass
        except Exception as e:
            print(f"Error in update_progress for guild {guild_id}: {e}")

    async def process_play_request(self, user, guild, channel, link, interaction=None):
        guild_id = str(guild.id)
        # Connect to the voice channel if not already connected
        voice_client = self.voice_clients.get(guild_id)
        if not voice_client or not voice_client.is_connected():
            if user.voice and user.voice.channel:
                voice_client = await user.voice.channel.connect()
                self.voice_clients[guild_id] = voice_client
            else:
                msg = "❌ You are not connected to a voice channel."
                if interaction:
                    await interaction.followup.send(msg, ephemeral=True)
                else:
                    await channel.send(msg)
                return
        else:
            voice_client = self.voice_clients[guild_id]

        # Cancel any scheduled disconnect task
        self.cancel_disconnect_task(guild_id)

        # Adjusted playlist detection
        if 'list=' not in link and 'watch?v=' not in link and 'youtu.be/' not in link:
            # Treat as search query
            query_string = urllib.parse.urlencode({'search_query': link})
            try:
                with urllib.request.urlopen(self.youtube_results_url + query_string) as response:
                    html_content = response.read().decode()
                search_results = re.findall(r'/watch\?v=(.{11})', html_content)
                if not search_results:
                    msg = "❌ No results found for your query."
                    if interaction:
                        await interaction.followup.send(msg, ephemeral=True)
                    else:
                        await channel.send(msg)
                    return
                link = self.youtube_watch_url + search_results[0]
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
            data = await loop.run_in_executor(None, lambda: self.ytdl.extract_info(link, download=False))
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
                song_info = entry  # Use the entry directly
                # Add to queue
                if guild_id not in self.queues:
                    self.queues[guild_id] = []
                self.queues[guild_id].append(song_info)
                added_songs.append(song_info['title'])
            msg = f"🎶 Added playlist **{data.get('title', 'Unknown playlist')}** with {len(added_songs)} songs to the queue."
            if interaction:
                await interaction.followup.send(msg)
            else:
                await channel.send(msg)

            # Start playing if not already playing
            if not voice_client.is_playing() and not voice_client.is_paused():
                await self.play_next(guild_id)

        else:
            # Single video
            song_info = data  # Store the entire data for later use

            # Initialize guild data if not present
            if guild_id not in self.client.guilds_data:
                self.client.guilds_data[guild_id] = {}

            # Play or queue the song
            if not voice_client.is_playing():
                self.client.guilds_data[guild_id]['current_song'] = song_info
                await self.play_song(guild_id, song_info)
                msg = f"🎶 Now playing: **{song_info.get('title', 'Unknown title')}**"
                if interaction:
                    await interaction.followup.send(msg)
                else:
                    await channel.send(msg)
            else:
                if guild_id not in self.queues:
                    self.queues[guild_id] = []
                self.queues[guild_id].append(song_info)
                msg = f"➕ Added to queue: **{song_info.get('title', 'Unknown title')}**"
                if interaction:
                    await interaction.followup.send(msg)
                else:
                    await channel.send(msg)

        # Clear messages except the stable message
        guild_data = self.client.guilds_data.get(guild_id)
        if guild_data:
            stable_message_id = guild_data.get('stable_message_id')
            channel_id = guild_data.get('channel_id')
            if stable_message_id and channel_id:
                channel = self.client.get_channel(int(channel_id))
                await self.clear_channel_messages(channel, int(stable_message_id))

        await self.update_stable_message(guild_id)

    def cancel_disconnect_task(self, guild_id):
        disconnect_task = self.client.guilds_data.get(guild_id, {}).get('disconnect_task')
        if disconnect_task:
            disconnect_task.cancel()
            self.client.guilds_data[guild_id]['disconnect_task'] = None

    async def clear_channel_messages(self, channel, stable_message_id):
        async for message in channel.history(limit=100):
            if message.id != stable_message_id:
                try:
                    await message.delete()
                except discord.Forbidden:
                    print(f"Permission error: Cannot delete message {message.id}")
                except discord.HTTPException as e:
                    print(f"Failed to delete message {message.id}: {e}")

    async def disconnect_after_delay(self, guild_id, delay):
        try:
            await asyncio.sleep(delay)
            voice_client = self.voice_clients.get(guild_id)
            if voice_client and not voice_client.is_playing():
                await voice_client.disconnect()
                self.voice_clients.pop(guild_id, None)
                # Remove the disconnect task reference
                self.client.guilds_data[guild_id]['disconnect_task'] = None
                await self.update_stable_message(guild_id)
        except asyncio.CancelledError:
            # The task was cancelled, do nothing
            pass

async def setup(client):
    await client.add_cog(Music(client))
