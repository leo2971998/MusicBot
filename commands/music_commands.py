import asyncio
import logging
import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp as youtube_dl
from config import YTDL_FORMAT_OPTS, FFMPEG_OPTIONS, PlaybackMode
from utils.validators import is_setup

logger = logging.getLogger(__name__)

# Initialize YouTube DL
ytdl = youtube_dl.YoutubeDL(YTDL_FORMAT_OPTS)

def setup_music_commands(client, queue_manager, player_manager, data_manager):
    """Setup music-related commands"""

    @client.tree.command(name="play", description="Play a song or add it to the queue")
    @is_setup()
    @app_commands.describe(link="The URL or name of the song to play")
    async def play_command(interaction: discord.Interaction, link: str):
        """Play command"""
        await interaction.response.defer()

        try:
            response_message = await process_play_request(
                interaction.user,
                interaction.guild,
                interaction.channel,
                link,
                client,
                queue_manager,
                player_manager,
                data_manager
            )

            if response_message:
                await interaction.followup.send(response_message, ephemeral=True)

            # Clean up after delay
            await _cleanup_interaction_message(interaction)

        except Exception as e:
            logger.error(f"Error in play command: {e}")
            await interaction.followup.send("❌ An error occurred while processing your request.", ephemeral=True)

    @client.tree.command(name="playnext", description="Play a song next in the queue")
    @is_setup()
    @app_commands.describe(link="The URL or name of the song to play next")
    async def playnext_command(interaction: discord.Interaction, link: str):
        """Play next command"""
        await interaction.response.defer()

        try:
            response_message = await process_play_request(
                interaction.user,
                interaction.guild,
                interaction.channel,
                link,
                client,
                queue_manager,
                player_manager,
                data_manager,
                play_next=True
            )

            if response_message:
                await interaction.followup.send(response_message, ephemeral=True)

            await _cleanup_interaction_message(interaction)

        except Exception as e:
            logger.error(f"Error in playnext command: {e}")
            await interaction.followup.send("❌ An error occurred while processing your request.", ephemeral=True)

async def process_play_request(user, guild, channel, link, client, queue_manager,
                               player_manager, data_manager, play_next=False, extra_meta=None):
    """Process a play request from various sources"""
    try:
        guild_id = str(guild.id)
        guild_data = client.guilds_data.get(guild_id)

        if not guild_data or not guild_data.get('channel_id'):
            return "❌ Please run /setup to initialize the music channel first."

        # Ensure user is a guild member
        if not isinstance(user, discord.Member):
            user = guild.get_member(user.id) or await guild.fetch_member(user.id)

        # Check if user is in a voice channel
        if not user.voice or not user.voice.channel:
            return "❌ You are not connected to a voice channel."

        user_voice_channel = user.voice.channel

        # Get or create voice client
        try:
            voice_client = await player_manager.get_or_create_voice_client(guild_id, user_voice_channel)
        except Exception as e:
            return f"❌ Could not connect to voice channel: {e}"

        notify_channel = None
        if (
            voice_client.channel != user_voice_channel
            and (voice_client.is_playing() or voice_client.is_paused())
        ):
            # Let the user know where the bot is currently playing
            notify_channel = voice_client.channel

        # Extract song information
        song_data = await _extract_song_data(link)
        if not song_data:
            return "❌ Could not extract song information."

        # Process single track vs playlist
        if 'entries' not in song_data:
            msg = await _process_single_song(
                song_data,
                user,
                guild_id,
                client,
                queue_manager,
                player_manager,
                data_manager,
                play_next,
                extra_meta,
            )
        else:
            msg = await _process_playlist(
                song_data,
                user,
                guild_id,
                client,
                queue_manager,
                player_manager,
                data_manager,
                play_next,
                extra_meta,
            )

        if notify_channel:
            msg += (
                f"\n🔊 Bot is currently playing in {notify_channel.mention}."
                " Join that channel to listen."
            )

        return msg

    except Exception as e:
        logger.error(f"Error processing play request: {e}")
        return "❌ An error occurred while processing your request."

async def _extract_song_data(link):
    """Extract song data using yt-dlp"""
    try:
        loop = asyncio.get_running_loop()

        # Determine if it's a search or direct link
        if 'list=' not in link and 'watch?v=' not in link and 'youtu.be/' not in link:
            search_query = f"ytsearch:{link}"
            search_results = await loop.run_in_executor(
                None, lambda: ytdl.extract_info(search_query, download=False)
            )

            if not search_results.get('entries'):
                return None

            # Get the best result by view count
            best_result = max(search_results['entries'], key=lambda x: x.get('view_count', 0))
            return best_result
        else:
            # Direct link
            return await loop.run_in_executor(
                None, lambda: ytdl.extract_info(link, download=False)
            )

    except Exception as e:
        logger.error(f"Error extracting song data: {e}")
        return None

async def _process_single_song(song_data, user, guild_id, client, queue_manager,
                               player_manager, data_manager, play_next, extra_meta):
    """Process a single song"""
    try:
        song_info = song_data.copy()
        song_info['requester'] = user.mention

        if extra_meta:
            song_info.update(extra_meta)
        else:
            song_info['source'] = 'youtube'

        voice_client = player_manager.voice_clients.get(guild_id)

        if not voice_client.is_playing() and not voice_client.is_paused():
            # Play immediately
            client.guilds_data[guild_id]['current_song'] = song_info
            await _play_song(guild_id, song_info, client, player_manager, queue_manager, data_manager)
            msg = f"🎶 Now playing: **{song_info.get('title', 'Unknown title')}**"
        else:
            # Add to queue
            queue_manager.add_song(guild_id, song_info, play_next)
            if play_next:
                msg = f"➕ Added to play next: **{song_info.get('title', 'Unknown title')}**"
            else:
                msg = f"➕ Added to queue: **{song_info.get('title', 'Unknown title')}**"

        # Update UI
        from ui.embeds import update_stable_message
        await update_stable_message(guild_id)

        return msg

    except Exception as e:
        logger.error(f"Error processing single song: {e}")
        return "❌ Error processing the song."

async def _process_playlist(song_data, user, guild_id, client, queue_manager,
                            player_manager, data_manager, play_next, extra_meta):
    """Process a playlist"""
    try:
        entries = song_data.get('entries', [])
        added_songs = []

        for entry in entries:
            if entry is None:
                continue

            song_info = entry.copy()
            song_info['requester'] = user.mention

            if extra_meta:
                song_info.update(extra_meta)
            else:
                song_info['source'] = 'youtube'

            queue_manager.add_song(guild_id, song_info, False)  # Always add to end for playlists
            added_songs.append(song_info['title'])

        # Start playing if nothing is currently playing
        voice_client = player_manager.voice_clients.get(guild_id)
        if not voice_client.is_playing() and not voice_client.is_paused():
            await _play_next_song(guild_id, client, queue_manager, player_manager, data_manager)

        # Update UI
        from ui.embeds import update_stable_message
        await update_stable_message(guild_id)

        playlist_title = song_data.get('title', 'Unknown playlist')
        return f"🎶 Added playlist **{playlist_title}** with {len(added_songs)} songs to the queue."

    except Exception as e:
        logger.error(f"Error processing playlist: {e}")
        return "❌ Error processing the playlist."

async def _play_song(guild_id, song_info, client, player_manager, queue_manager, data_manager):
    """Play a specific song"""
    try:
        voice_client = player_manager.voice_clients.get(guild_id)
        if not voice_client:
            logger.error(f"No voice client for guild {guild_id}")
            return

        # Create audio source
        url = song_info.get('url')
        if not url:
            logger.error(f"No URL found for song in guild {guild_id}")
            return

        source = discord.FFmpegPCMAudio(url, **FFMPEG_OPTIONS)

        # Define callback for when song ends
        def after_playing(error):
            if error:
                logger.error(f"Player error in guild {guild_id}: {error}")

            # Schedule next song
            coro = _play_next_song(guild_id, client, queue_manager, player_manager, data_manager)
            asyncio.run_coroutine_threadsafe(coro, client.loop)

        # Start playing
        await player_manager.play_audio_source(guild_id, source, after_playing)

        # Store song duration
        duration = song_info.get('duration', 0)
        client.guilds_data[guild_id]['song_duration'] = duration

        # Save data
        await data_manager.save_guilds_data(client)

        logger.info(f"Started playing '{song_info.get('title')}' in guild {guild_id}")

    except Exception as e:
        logger.error(f"Error playing song in guild {guild_id}: {e}")

async def _play_next_song(guild_id, client, queue_manager, player_manager, data_manager):
    """Play the next song in queue"""
    try:
        playback_mode = client.playback_modes.get(guild_id, PlaybackMode.NORMAL)

        if playback_mode == PlaybackMode.REPEAT_ONE:
            # Repeat current song
            current_song = client.guilds_data[guild_id].get('current_song')
            if current_song:
                await _play_song(guild_id, current_song, client, player_manager, queue_manager, data_manager)
            return

        # Get next song from queue
        next_song = queue_manager.get_next_song(guild_id)
        if next_song:
            client.guilds_data[guild_id]['current_song'] = next_song
            await _play_song(guild_id, next_song, client, player_manager, queue_manager, data_manager)
        else:
            # No more songs, clean up
            client.guilds_data[guild_id]['current_song'] = None
            client.playback_modes[guild_id] = PlaybackMode.NORMAL

            # Schedule disconnect after delay
            from config import IDLE_DISCONNECT_DELAY
            disconnect_task = asyncio.create_task(
                _disconnect_after_delay(guild_id, player_manager, IDLE_DISCONNECT_DELAY)
            )
            player_manager.add_task(guild_id, 'disconnect_task', disconnect_task)

        # Update UI
        from ui.embeds import update_stable_message
        await update_stable_message(guild_id)

    except Exception as e:
        logger.error(f"Error playing next song in guild {guild_id}: {e}")

async def _disconnect_after_delay(guild_id, player_manager, delay):
    """Disconnect after a delay if nothing is playing"""
    try:
        await asyncio.sleep(delay)
        voice_client = player_manager.voice_clients.get(guild_id)
        if voice_client and not voice_client.is_playing():
            await player_manager.disconnect_voice_client(guild_id)
            from ui.embeds import update_stable_message
            await update_stable_message(guild_id)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Error in disconnect delay for guild {guild_id}: {e}")

async def _cleanup_interaction_message(interaction, delay=5):
    """Clean up interaction message after delay"""
    try:
        await asyncio.sleep(delay)
        message = await interaction.original_response()
        await message.delete()
    except Exception:
        pass  # Message might already be deleted
