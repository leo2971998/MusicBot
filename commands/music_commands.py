import asyncio
import logging
import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp as youtube_dl
from config import YTDL_FORMAT_OPTS, YTDL_SEARCH_OPTS, FFMPEG_OPTIONS, PlaybackMode
from utils.validators import is_setup
from utils.youtube_api import fast_youtube_search
from utils.cache import get_cached_search, cache_search_results

logger = logging.getLogger(__name__)

# Initialize YouTube DL
ytdl = youtube_dl.YoutubeDL(YTDL_FORMAT_OPTS)
ytdl_search = youtube_dl.YoutubeDL(YTDL_SEARCH_OPTS)

def setup_music_commands(client, queue_manager, player_manager, data_manager):
    """Setup music-related commands"""

    @client.tree.command(name="search", description="Search for music and preview results before playing")
    @is_setup()
    @app_commands.describe(query="Search query for finding music")
    async def search_command(interaction: discord.Interaction, query: str):
        """Search command with preview"""
        logger.debug(f"/search invoked by {interaction.user} in guild {interaction.guild_id} with query: {query}")
        await interaction.response.defer()

        try:
            # Get search results
            search_results = await _extract_song_data(query, search_mode=True)
            
            if not search_results or len(search_results) == 0:
                await interaction.followup.send("❌ No search results found.", ephemeral=True)
                return

            # Create search results view and embed
            from ui.search_view import SearchResultsView, create_search_results_embed
            
            view = SearchResultsView(search_results)
            embed = create_search_results_embed(search_results, query)
            
            # Send search results
            message = await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            
            # Wait for selection or timeout
            await view.wait()
            
            # Handle timeout case
            if not view.selection_made and view.selected_index is None:
                # Auto-select first result
                view.selected_index = 0
                first_result = search_results[0]
                
                # Process the first result
                response_message = await process_play_request(
                    interaction.user,
                    interaction.guild,
                    interaction.channel,
                    first_result.get('webpage_url', first_result.get('url')),
                    client,
                    queue_manager,
                    player_manager,
                    data_manager
                )
                
                # Update message to show auto-selection
                try:
                    await interaction.edit_original_response(
                        content=f"⏰ Timeout! Auto-selected: **{first_result.get('title', 'Unknown')}**\n{response_message}",
                        embed=None,
                        view=None
                    )
                except discord.NotFound:
                    pass  # Message might have been deleted

        except Exception as e:
            logger.error(f"Error in search command: {e}")
            await interaction.followup.send("❌ An error occurred while searching.", ephemeral=True)

    @client.tree.command(name="play", description="Play a song or add it to the queue")
    @is_setup()
    @app_commands.describe(link="The URL or name of the song to play")
    async def play_command(interaction: discord.Interaction, link: str):
        """Play command"""
        logger.debug(f"/play invoked by {interaction.user} in guild {interaction.guild_id} with link: {link}")
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
        logger.debug(f"/playnext invoked by {interaction.user} in guild {interaction.guild_id} with link: {link}")
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
        logger.debug(
            f"process_play_request called in guild {guild.id} by {user} with link: {link}"
        )
        guild_id = str(guild.id)
        guild_data = client.guilds_data.get(guild_id)

        if not guild_data or not guild_data.get('channel_id'):
            return "❌ Please run /setup to initialize the music channel first."

        # Update activity timestamp to keep guild data fresh
        import time
        guild_data['last_activity'] = time.time()

        # Ensure user is a guild member
        if not isinstance(user, discord.Member):
            try:
                user = guild.get_member(user.id) or await guild.fetch_member(user.id)
            except discord.NotFound:
                return "❌ Could not find your user information in this guild."

        # Check if user is in a voice channel
        if not user.voice or not user.voice.channel:
            return "❌ You are not connected to a voice channel."

        user_voice_channel = user.voice.channel

        # Get or create voice client with enhanced error handling
        try:
            voice_client = await player_manager.get_or_create_voice_client(
                guild_id, user_voice_channel
            )
            if not voice_client:
                return "❌ Could not connect to voice channel."
        except discord.errors.ConnectionClosed:
            return "❌ Voice connection was closed. Please try again."
        except discord.errors.Forbidden:
            return "❌ I don't have permission to join your voice channel."
        except Exception as e:
            logger.error(f"Unexpected error connecting to voice channel: {e}")
            return f"❌ Could not connect to voice channel: {e}"
            
        # Cancel any pending auto-disconnect while new music is queued
        player_manager.cancel_task(guild_id, "disconnect_task")
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

async def _extract_song_data(link, search_mode=False):
    """Extract song data using optimized search with YouTube API + caching + yt-dlp fallback"""
    try:
        loop = asyncio.get_running_loop()

        # Determine if it's a search or direct link
        is_search = 'list=' not in link and 'watch?v=' not in link and 'youtu.be/' not in link
        
        if is_search:
            if search_mode:
                # Use optimized search for search mode
                return await _fast_search(link)
            else:
                # For direct play, use fast search and pick best result
                search_results = await _fast_search(link, max_results=5)
                if search_results:
                    # Get the best result by view count for direct play
                    best_result = max(search_results, key=lambda x: x.get('view_count', 0))
                    return best_result
                return None
        else:
            # Direct link - use full yt-dlp extraction
            return await loop.run_in_executor(
                None, lambda: ytdl.extract_info(link, download=False)
            )

    except Exception as e:
        logger.error(f"Error extracting song data: {e}")
        return None


async def _fast_search(query: str, max_results: int = 5) -> list:
    """
    Fast search using YouTube API + caching with yt-dlp fallback.
    Returns list of search results.
    """
    import time
    start_time = time.time()
    
    try:
        # Check cache first
        cached_results = await get_cached_search(query)
        if cached_results:
            search_time = time.time() - start_time
            logger.info(f"Cache hit for query '{query}' in {search_time:.3f}s")
            return cached_results[:max_results]
        
        # Try YouTube Data API first
        api_results = await fast_youtube_search(query, max_results)
        if api_results:
            # Cache the results
            await cache_search_results(query, api_results)
            search_time = time.time() - start_time
            logger.info(f"YouTube API search for '{query}' completed in {search_time:.3f}s")
            return api_results
        
        # Fallback to yt-dlp if API fails
        logger.info(f"Falling back to yt-dlp search for query: {query}")
        return await _ytdlp_fallback_search(query, max_results)
        
    except Exception as e:
        logger.error(f"Error in fast search: {e}")
        return await _ytdlp_fallback_search(query, max_results)


async def _ytdlp_fallback_search(query: str, max_results: int = 5) -> list:
    """Fallback to yt-dlp search with optimized settings"""
    import time
    start_time = time.time()
    
    try:
        loop = asyncio.get_running_loop()
        search_query = f"ytsearch{max_results}:{query}"
        
        # Use optimized yt-dlp settings for search
        search_results = await loop.run_in_executor(
            None, lambda: ytdl_search.extract_info(search_query, download=False)
        )
        
        if not search_results or not search_results.get('entries'):
            return []
        
        results = search_results['entries']
        
        # For each result, we need to get full metadata using regular ytdl
        # But only when the user actually selects it (not during search)
        # For now, return the basic info and enhance on selection
        enhanced_results = []
        for result in results:
            if result:  # Sometimes entries can be None
                enhanced_result = {
                    'id': result.get('id', ''),
                    'title': result.get('title', 'Unknown Title'),
                    'uploader': result.get('uploader', result.get('channel', 'Unknown Artist')),
                    'duration': result.get('duration', 0),
                    'view_count': result.get('view_count', 0),
                    'webpage_url': result.get('webpage_url', f"https://www.youtube.com/watch?v={result.get('id', '')}"),
                    'thumbnail': result.get('thumbnail'),
                    'description': result.get('description', ''),
                    'source': 'yt-dlp'
                }
                enhanced_results.append(enhanced_result)
        
        # Cache the results
        if enhanced_results:
            await cache_search_results(query, enhanced_results)
        
        search_time = time.time() - start_time
        logger.info(f"yt-dlp fallback search for '{query}' completed in {search_time:.3f}s")
        
        return enhanced_results
        
    except Exception as e:
        search_time = time.time() - start_time
        logger.error(f"yt-dlp fallback search failed after {search_time:.3f}s: {e}")
        return []


async def _get_full_song_metadata(song_url: str) -> dict:
    """
    Get full song metadata for final playback.
    This is called when user selects a song to get the actual stream URL and full metadata.
    """
    try:
        loop = asyncio.get_running_loop()
        
        # Use full yt-dlp extraction for selected song
        result = await loop.run_in_executor(
            None, lambda: ytdl.extract_info(song_url, download=False)
        )
        
        if result:
            logger.debug(f"Full metadata extracted for: {result.get('title', 'Unknown')}")
            return result
        
        return None
        
    except Exception as e:
        logger.error(f"Error getting full song metadata: {e}")
        return None

async def _process_single_song(song_data, user, guild_id, client, queue_manager,
                               player_manager, data_manager, play_next, extra_meta):
    """Process a single song"""
    try:
        # Check if we need to get full metadata (from fast search results)
        if song_data.get('source') in ['youtube_api', 'yt-dlp'] and not song_data.get('url'):
            # This is a search result, need to get full metadata
            webpage_url = song_data.get('webpage_url')
            if webpage_url:
                logger.debug(f"Getting full metadata for selected song: {song_data.get('title')}")
                full_metadata = await _get_full_song_metadata(webpage_url)
                if full_metadata:
                    # Merge the metadata, keeping some original data
                    song_info = full_metadata.copy()
                    # Keep the original title and uploader if they exist (for consistency)
                    if song_data.get('title'):
                        song_info['title'] = song_data['title']
                    if song_data.get('uploader'):
                        song_info['uploader'] = song_data['uploader']
                else:
                    song_info = song_data.copy()
            else:
                song_info = song_data.copy()
        else:
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
            # Add to queue with error handling for queue limits
            if queue_manager.add_song(guild_id, song_info, play_next):
                if play_next:
                    msg = f"➕ Added to play next: **{song_info.get('title', 'Unknown title')}**"
                else:
                    msg = f"➕ Added to queue: **{song_info.get('title', 'Unknown title')}**"
            else:
                msg = f"❌ Could not add song to queue. Queue may be full (max 100 songs) or there was an error."

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
        logger.debug(f"_play_song called in guild {guild_id} with {song_info.get('title')}")
        voice_client = player_manager.voice_clients.get(guild_id)
        if not voice_client:
            logger.error(f"No voice client for guild {guild_id}")
            return

        # Reset votes for new song
        from utils.vote_manager import VoteManager
        guild_data = client.guilds_data.get(guild_id, {})
        song_id = song_info.get('id', song_info.get('webpage_url', 'unknown'))
        VoteManager.reset_votes(guild_data, song_id)

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
        logger.debug(f"_play_next_song called in guild {guild_id}")
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
        logger.debug(f"_disconnect_after_delay scheduled for guild {guild_id} after {delay}s")
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
        logger.debug(f"Cleaning up interaction message in guild {interaction.guild_id} after {delay}s")
        await asyncio.sleep(delay)
        message = await interaction.original_response()
        await message.delete()
    except Exception:
        pass  # Message might already be deleted
