import logging
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
        if not stable_message:
            try:
                # Try to fetch existing message first
                stable_message_id = guild_data.get('stable_message_id')
                if stable_message_id:
                    try:
                        stable_message = await channel.fetch_message(int(stable_message_id))
                        guild_data['stable_message'] = stable_message
                    except discord.NotFound:
                        logger.info(f"Stable message {stable_message_id} not found, creating new one")
                        stable_message = None

                if not stable_message:
                    stable_message = await channel.send('🎶 **Music Bot UI Initialized** 🎶')
                    guild_data['stable_message'] = stable_message
                    guild_data['stable_message_id'] = stable_message.id
                    await data_manager.save_guilds_data(client)
            except discord.Forbidden:
                logger.error(f"Permission denied: Cannot create/access messages in channel {channel_id}")
                return
            except Exception as e:
                logger.error(f"Failed to recreate stable message: {e}")
                return

        # Create embeds
        try:
            embeds = [
                create_credits_embed(),
                create_now_playing_embed(guild_id, guild_data),
                create_queue_embed(guild_id)
            ]

            view = MusicControlView()

            # Try to edit the message
            await stable_message.edit(embeds=embeds, view=view)

        except discord.NotFound:
            # Message was deleted, create a new one
            logger.info(f"Stable message was deleted, creating new one for guild {guild_id}")
            try:
                stable_message = await channel.send('🎶 **Music Bot UI Initialized** 🎶')
                guild_data['stable_message'] = stable_message
                guild_data['stable_message_id'] = stable_message.id

                embeds = [
                    create_credits_embed(),
                    create_now_playing_embed(guild_id, guild_data),
                    create_queue_embed(guild_id)
                ]
                view = MusicControlView()
                await stable_message.edit(embeds=embeds, view=view)

            except Exception as recreate_error:
                logger.error(f"Failed to recreate stable message: {recreate_error}")
                return

        except discord.Forbidden:
            logger.error(f"Permission denied: Cannot edit message in guild {guild_id}")
            return
        except discord.HTTPException as e:
            logger.error(f"HTTP error updating stable message in guild {guild_id}: {e}")
            return
        except Exception as e:
            logger.error(f"Unexpected error updating stable message in guild {guild_id}: {e}")
            return

        # Save guild data
        try:
            await data_manager.save_guilds_data(client)
        except Exception as save_error:
            logger.error(f"Failed to save guild data: {save_error}")

    except Exception as e:
        logger.error(f"Critical error in update_stable_message for guild {guild_id}: {e}")

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

            embed.add_field(name='Duration', value=duration_str, inline=False)
            embed.add_field(name='Requested by', value=current_song.get('requester', 'Unknown'), inline=False)

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