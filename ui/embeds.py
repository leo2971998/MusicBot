import logging
import asyncio
import traceback
import discord
from discord import Embed
from ui.views import MusicControlView
from utils.format_utils import format_time

logger = logging.getLogger(__name__)

async def update_stable_message(guild_id: str):
    """Update the stable message with current bot state"""
    try:
        # Import here to avoid circular imports
        from bot_state import client, queue_manager, player_manager, data_manager

        guild_id = str(guild_id)
        guild_data = client.guilds_data.get(guild_id)
        if not guild_data:
            logger.warning(f"No guild data found for guild {guild_id}")
            return

        channel_id = guild_data.get('channel_id')
        if not channel_id:
            logger.warning(f"No channel_id found for guild {guild_id}")
            return

        channel = client.get_channel(int(channel_id))
        if not channel:
            logger.warning(f"Channel {channel_id} not found for guild {guild_id}")
            return

        stable_message = guild_data.get('stable_message')
        
        # Enhanced stable message recovery
        if not stable_message:
            stable_message_id = guild_data.get('stable_message_id')
            if stable_message_id:
                try:
                    stable_message = await channel.fetch_message(int(stable_message_id))
                    guild_data['stable_message'] = stable_message
                    logger.debug(f"Recovered stable message {stable_message_id} for guild {guild_id}")
                except discord.NotFound:
                    logger.info(f"Stable message {stable_message_id} not found, creating new one")
                    stable_message = None
                except discord.Forbidden:
                    logger.error(f"Permission denied: Cannot access message {stable_message_id} in guild {guild_id}")
                    return

            if not stable_message:
                try:
                    stable_message = await channel.send('🎶 **Music Bot UI Initialized** 🎶')
                    guild_data['stable_message'] = stable_message
                    guild_data['stable_message_id'] = stable_message.id
                    logger.info(f"Created new stable message {stable_message.id} for guild {guild_id}")
                    await data_manager.save_guilds_data(client)
                except discord.Forbidden:
                    logger.error(f"Permission denied: Cannot create messages in channel {channel_id}")
                    return
                except Exception:
                    logger.exception("Failed to create stable message")
                    return

        # Create embeds with enhanced error handling
        try:
            embeds = []
            
            # Add each embed with individual error handling
            try:
                embeds.append(create_credits_embed())
            except Exception as e:
                logger.warning(f"Failed to create credits embed: {e}")
                
            try:
                embeds.append(create_now_playing_embed(guild_id, guild_data))
            except Exception as e:
                logger.warning(f"Failed to create now playing embed: {e}")
                # Add fallback embed
                embeds.append(discord.Embed(title='🎶 Now Playing', description='Error loading current song', color=0xff0000))
                
            try:
                embeds.append(create_queue_embed(guild_id))
            except Exception as e:
                logger.warning(f"Failed to create queue embed: {e}")
                # Add fallback embed  
                embeds.append(discord.Embed(title='📜 Current Queue', description='Error loading queue', color=0xff0000))

            # Ensure we have at least basic embeds
            if not embeds:
                embeds = [discord.Embed(title='🎶 Music Bot', description='UI temporarily unavailable', color=0xff0000)]

            # Create persistent view so buttons stay active
            view = MusicControlView(timeout=None)
            
            # Update message with retry logic
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    await stable_message.edit(embeds=embeds, view=view)
                    client.add_view(view, message_id=stable_message.id)
                    logger.debug(f"Successfully updated stable message for guild {guild_id} (attempt {attempt + 1})")
                    break
                except discord.NotFound:
                    # Message was deleted, create a new one
                    logger.info(f"Stable message was deleted, creating new one for guild {guild_id}")
                    try:
                        stable_message = await channel.send('🎶 **Music Bot UI Initialized** 🎶')
                        guild_data['stable_message'] = stable_message
                        guild_data['stable_message_id'] = stable_message.id
                        await stable_message.edit(embeds=embeds, view=view)
                        client.add_view(view, message_id=stable_message.id)
                        logger.info(f"Created and updated new stable message {stable_message.id} for guild {guild_id}")
                        break
                    except Exception:
                        logger.exception("Failed to recreate stable message")
                        return
                except discord.Forbidden:
                    logger.error(f"Permission denied: Cannot edit message in guild {guild_id}")
                    return
                except discord.HTTPException as e:
                    if attempt < max_retries - 1:
                        logger.warning(f"HTTP error updating stable message in guild {guild_id} (attempt {attempt + 1}): {e}, retrying...")
                        await asyncio.sleep(1)  # Brief delay before retry
                        continue
                    else:
                        logger.error(f"HTTP error updating stable message in guild {guild_id} after {max_retries} attempts: {e}")
                        return
                except Exception as e:
                    if attempt < max_retries - 1:
                        logger.warning(f"Unexpected error updating stable message in guild {guild_id} (attempt {attempt + 1}): {e}, retrying...")
                        await asyncio.sleep(1)
                        continue
                    else:
                        logger.error(f"Unexpected error updating stable message in guild {guild_id} after {max_retries} attempts: {e}")
                        return

        except Exception:
            logger.exception(f"Critical error creating embeds/view for guild {guild_id}")
            return

        # Save guild data
        try:
            await data_manager.save_guilds_data(client)
        except Exception:
            logger.exception("Failed to save guild data")

    except Exception:
        logger.exception(f"Critical error in update_stable_message for guild {guild_id}")

def create_credits_embed() -> Embed:
    """Create the credits embed"""
    return Embed(
        title="Music Bot UI",
        description="Made by **Leo Nguyen**",
        color=0x1db954
    )

def create_now_playing_embed(guild_id: str, guild_data: dict) -> Embed:
    """Create the now playing embed"""
    try:
        # Import here to avoid circular imports
        from bot_state import player_manager, client

        voice_client = player_manager.voice_clients.get(guild_id)

        if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
            current_song = guild_data.get('current_song')
            if not current_song:
                return _create_empty_now_playing_embed()

            duration = guild_data.get('song_duration', 0)
            duration_str = format_time(duration)

            source = current_song.get('source', 'youtube')
            if source == 'spotify':
                now_title = "🎶 Now Playing (Spotify)"
                now_color = 0x1db954  # Spotify green
                link_url = current_song.get('spotify_url') or current_song.get('webpage_url')
            else:
                now_title = "🎶 Now Playing (YouTube)"
                now_color = 0xff0000
                link_url = current_song.get('webpage_url')

            embed = Embed(
                title=now_title,
                description=f"**[{current_song['title']}]({link_url})**",
                color=now_color
            )

            if current_song.get('thumbnail'):
                embed.set_thumbnail(url=current_song['thumbnail'])

            embed.add_field(name='Duration', value=duration_str, inline=True)
            embed.add_field(name='Requested by', value=current_song.get('requester', 'Unknown'), inline=True)

            # Add vote status if there are any votes
            if voice_client.channel:
                from utils.vote_manager import VoteManager
                vote_status = VoteManager.get_vote_status(guild_data, voice_client.channel)
                
                if vote_status['current_votes'] > 0:
                    progress_bar = "▓" * vote_status['current_votes'] + "░" * (vote_status['required_votes'] - vote_status['current_votes'])
                    vote_text = f"🗳️ **{vote_status['current_votes']}/{vote_status['required_votes']}** votes to skip\n`{progress_bar}` {vote_status['percentage']}%"
                    embed.add_field(name='Vote Skip Progress', value=vote_text, inline=False)

            # Add connection quality indicator
            if voice_client and voice_client.is_connected():
                latency = voice_client.latency * 1000  # Convert to ms
                if latency < 50:
                    quality = "🟢 Excellent"
                elif latency < 100:
                    quality = "🟡 Good"
                elif latency < 200:
                    quality = "🟠 Fair"
                else:
                    quality = "🔴 Poor"
                
                embed.add_field(name='Connection', value=f"{quality} ({latency:.0f}ms)", inline=True)

            playback_mode = client.playback_modes.get(guild_id)
            if playback_mode:
                embed.set_footer(text=f'Playback Mode: {playback_mode.value}')

            return embed
        else:
            return _create_empty_now_playing_embed()
    except Exception as e:
        logger.error(f"Error creating now playing embed: {e}")
        return _create_empty_now_playing_embed()

def _create_empty_now_playing_embed() -> Embed:
    """Create empty now playing embed"""
    return Embed(
        title='🎶 Now Playing',
        description='No music is currently playing.',
        color=0x1db954
    )

def create_queue_embed(guild_id: str) -> Embed:
    """Create the queue embed"""
    try:
        from bot_state import queue_manager

        queue = queue_manager.get_queue(guild_id)

        def get_source_icon(song):
            return "🎧" if song.get('source') == 'spotify' else "📺"

        if queue:
            queue_description = '\n'.join(
                f"{idx + 1}. {get_source_icon(song)} **[{song['title']}]({song.get('spotify_url', song.get('webpage_url'))})** — *{song.get('requester', 'Unknown')}*"
                for idx, song in enumerate(queue[:10])  # Limit to first 10 songs
            )

            if len(queue) > 10:
                queue_description += f"\n... and {len(queue) - 10} more songs"
        else:
            queue_description = 'No songs in the queue.'

        embed = Embed(
            title='📜 Current Queue',
            description=queue_description,
            color=0x1db954
        )
        embed.set_footer(text=f"Total songs in queue: {len(queue) if queue else 0}")

        return embed
    except Exception as e:
        logger.error(f"Error creating queue embed: {e}")
        return Embed(
            title='📜 Current Queue',
            description='Error loading queue.',
            color=0xff0000
        )

def create_queue_embed_paginated(guild_id: str, page: int = 1, per_page: int = 10) -> Embed:
    """Create a paginated queue embed"""
    try:
        from bot_state import queue_manager
        
        songs, total_pages, current_page = queue_manager.get_queue_page(guild_id, page, per_page)
        
        def get_source_icon(song):
            return "🎧" if song.get('source') == 'spotify' else "📺"
        
        if songs:
            # Calculate starting position for this page
            start_pos = (current_page - 1) * per_page
            
            queue_description = '\n'.join(
                f"{start_pos + idx + 1}. {get_source_icon(song)} **[{song['title']}]({song.get('spotify_url', song.get('webpage_url'))})** — *{song.get('requester', 'Unknown')}*"
                for idx, song in enumerate(songs)
            )
        else:
            queue_description = 'No songs in the queue.'
        
        embed = Embed(
            title=f'📜 Queue (Page {current_page}/{total_pages if total_pages > 0 else 1})',
            description=queue_description,
            color=0x1db954
        )
        
        total_songs = queue_manager.get_queue_length(guild_id)
        embed.set_footer(text=f"Total songs in queue: {total_songs} | Page {current_page} of {total_pages if total_pages > 0 else 1}")
        
        return embed
    except Exception as e:
        logger.error(f"Error creating paginated queue embed: {e}")
        return Embed(
            title='📜 Queue',
            description='Error loading queue.',
            color=0xff0000
        )