import asyncio
import logging
import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp as youtube_dl
from config import YTDL_FORMAT_OPTS, FFMPEG_OPTIONS, PlaybackMode, FULL_METADATA_OPTS
from utils.validators import is_setup
from utils.search_cache import search_cache
from utils.search_optimizer import search_optimizer

logger = logging.getLogger(__name__)

# Initialize YouTube DL instances
ytdl = youtube_dl.YoutubeDL(YTDL_FORMAT_OPTS)
full_metadata_ytdl = youtube_dl.YoutubeDL(FULL_METADATA_OPTS)

def setup_music_commands(client, queue_manager, player_manager, data_manager):
    """Setup music-related commands"""

    @client.tree.command(name="search", description="Search for music and auto-play the most viewed result")
    @is_setup()
    @app_commands.describe(query="Search query for finding music")
    async def search_command(interaction: discord.Interaction, query: str):
        """Search command with auto-selection of most viewed result"""
        logger.debug(f"/search invoked by {interaction.user} in guild {interaction.guild_id} with query: {query}")
        await interaction.response.defer()

        try:
            # Show searching message
            await interaction.followup.send(f"🔍 Searching for: **{query}**...", ephemeral=True)
            
            # Get the best result directly using optimized search
            from utils.search_optimizer import search_optimizer
            
            # Check cache first
            from utils.search_cache import search_cache
            optimized_query = search_optimizer.preprocess_query(query)
            cached_result = search_cache.get(query, search_mode=False)  # Check for single result cache
            
            if cached_result:
                logger.debug(f"Using cached result for query: {query}")
                best_result = cached_result
            else:
                # Get fresh result
                best_result = await search_optimizer.get_best_result(optimized_query)
                
                if not best_result:
                    # Fallback to multi-result search and pick the best
                    search_results = await _extract_song_data(query, search_mode=True)
                    if search_results and len(search_results) > 0:
                        best_result = max(search_results, key=lambda x: x.get('view_count', 0))
                    else:
                        await interaction.edit_original_response(content="❌ No search results found.")
                        return
                
                # Cache the single result
                if best_result:
                    search_cache.set(query, best_result, search_mode=False, ttl=3600)  # 1 hour
            
            logger.debug(f"Auto-selected best result: {best_result.get('title')} with {best_result.get('view_count', 0):,} views")
            
            # Process the best result immediately
            response_message = await process_play_request(
                interaction.user,
                interaction.guild,
                interaction.channel,
                best_result.get('webpage_url', best_result.get('url')),
                client,
                queue_manager,
                player_manager,
                data_manager
            )
            
            # Update message to show what was selected and played
            try:
                await interaction.edit_original_response(
                    content=f"🎶 Found and playing: **{best_result.get('title', 'Unknown')}** by **{best_result.get('uploader', 'Unknown Artist')}**\n{response_message}"
                )
            except discord.NotFound:
                pass  # Message might have been deleted

        except Exception as e:
            logger.error(f"Error in search command: {e}")
            await interaction.followup.send("❌ An error occurred while searching.", ephemeral=True)

    @client.tree.command(name="quickplay", description="Quickly play the most viewed search result")
    @is_setup()
    @app_commands.describe(query="Search query for finding music")
    async def quickplay_command(interaction: discord.Interaction, query: str):
        """Quick play command - auto-selects most viewed result for speed"""
        logger.debug(f"/quickplay invoked by {interaction.user} in guild {interaction.guild_id} with query: {query}")
        await interaction.response.defer()

        try:
            # Show searching message
            await interaction.followup.send(f"⚡ Quick playing: **{query}**...", ephemeral=True)
            
            # Get the best result directly using optimized search
            from utils.search_optimizer import search_optimizer
            
            # Check cache first
            from utils.search_cache import search_cache
            optimized_query = search_optimizer.preprocess_query(query)
            cached_result = search_cache.get(query, search_mode=False)  # Check for single result cache
            
            if cached_result:
                logger.debug(f"Using cached result for quickplay query: {query}")
                best_result = cached_result
            else:
                # Get fresh result
                best_result = await search_optimizer.get_best_result(optimized_query)
                
                if not best_result:
                    # Fallback to multi-result search and pick the best
                    search_results = await _extract_song_data(query, search_mode=True)
                    if search_results and len(search_results) > 0:
                        best_result = max(search_results, key=lambda x: x.get('view_count', 0))
                    else:
                        await interaction.edit_original_response(content="❌ No search results found.")
                        return
                
                # Cache the single result
                if best_result:
                    search_cache.set(query, best_result, search_mode=False, ttl=3600)  # 1 hour
            
            logger.debug(f"Auto-selected best result for quickplay: {best_result.get('title')} with {best_result.get('view_count', 0):,} views")
            
            # Process the best result immediately
            response_message = await process_play_request(
                interaction.user,
                interaction.guild,
                interaction.channel,
                best_result.get('webpage_url', best_result.get('url')),
                client,
                queue_manager,
                player_manager,
                data_manager
            )
            
            # Update message to show what was selected and played
            try:
                await interaction.edit_original_response(
                    content=f"⚡ Quick played: **{best_result.get('title', 'Unknown')}** by **{best_result.get('uploader', 'Unknown Artist')}**\n{response_message}"
                )
            except discord.NotFound:
                pass  # Message might have been deleted

        except Exception as e:
            logger.error(f"Error in quickplay command: {e}")
            await interaction.followup.send("❌ An error occurred while quick playing.", ephemeral=True)

    @client.tree.command(name="search_preview", description="Search for music with preview and manual selection")
    @is_setup()
    @app_commands.describe(query="Search query for finding music")
    async def search_preview_command(interaction: discord.Interaction, query: str):
        """Legacy search command with preview and manual selection"""
        logger.debug(f"/search_preview invoked by {interaction.user} in guild {interaction.guild_id} with query: {query}")
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
            logger.error(f"Error in search preview command: {e}")
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
    """Extract song data using optimized yt-dlp with caching and two-phase approach"""
    try:
        # Determine if it's a search or direct link
        is_search = 'list=' not in link and 'watch?v=' not in link and 'youtu.be/' not in link
        
        if is_search:
            # Check cache first
            cached_result = search_cache.get(link, search_mode)
            if cached_result is not None:
                logger.debug(f"Returning cached results for query: {link}")
                return cached_result
            
            # Preprocess query for better results
            optimized_query = search_optimizer.preprocess_query(link)
            
            if search_mode:
                # Use fast search for search mode - optimized for auto-selection (fewer results)
                search_results = await search_optimizer.fast_search(optimized_query, max_results=3)
                
                if search_results:
                    # Cache the results
                    search_cache.set(link, search_results, search_mode=True, ttl=1800)  # 30 minutes
                    return search_results
                else:
                    # Fallback to regular search if fast search fails
                    logger.debug(f"Fast search failed, using fallback for: {link}")
                    fallback_results = await search_optimizer.search_with_fallback(optimized_query, max_results=3)
                    if fallback_results:
                        search_cache.set(link, fallback_results, search_mode=True, ttl=900)  # 15 minutes for fallback
                        return fallback_results
            else:
                # For direct play, use fast search and get the best result
                search_results = await search_optimizer.fast_search(optimized_query, max_results=3)
                
                if search_results and len(search_results) > 0:
                    # Get best result by view count, but ensure we have full metadata for playback
                    best_result = max(search_results, key=lambda x: x.get('view_count', 0))
                    
                    # If it's a fast result, get full metadata for playback
                    if best_result.get('_fast_result', False):
                        full_metadata = await search_optimizer.get_full_metadata(best_result['webpage_url'])
                        if full_metadata:
                            best_result = full_metadata
                    
                    # Cache the result
                    search_cache.set(link, best_result, search_mode=False, ttl=3600)  # 1 hour
                    return best_result
                else:
                    # Fallback to regular search
                    logger.debug(f"Fast search failed for direct play, using fallback for: {link}")
                    loop = asyncio.get_running_loop()
                    search_query = f"ytsearch:{optimized_query}"
                    search_results = await loop.run_in_executor(
                        None, lambda: full_metadata_ytdl.extract_info(search_query, download=False)
                    )
                    
                    if search_results and search_results.get('entries'):
                        best_result = max(search_results['entries'], key=lambda x: x.get('view_count', 0))
                        search_cache.set(link, best_result, search_mode=False, ttl=1800)  # 30 minutes
                        return best_result
        else:
            # Direct link - use full metadata extraction
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None, lambda: full_metadata_ytdl.extract_info(link, download=False)
            )
            return result

        return None

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
