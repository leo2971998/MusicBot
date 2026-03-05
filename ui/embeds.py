import asyncio
import logging
import time
from typing import Dict

import discord
from discord import Embed

from config import PlaybackMode
from ui.views import MusicControlView
from utils.format_utils import format_time

logger = logging.getLogger(__name__)

UI_REFRESH_DEBOUNCE_SECONDS = 0.5

_refresh_tasks: Dict[str, asyncio.Task] = {}
_persistent_views: Dict[str, MusicControlView] = {}
_registered_view_message_ids: Dict[str, int] = {}


def create_progress_bar(elapsed: float, duration: float, length: int = 20) -> str:
    """Create a visual progress bar for song playback."""
    if duration <= 0:
        return '▬' * length

    progress = min(max(elapsed, 0) / duration, 1.0)
    filled = int(progress * length)
    bar = '█' * filled + '░' * (length - filled)
    return f"{format_time(int(elapsed))} {bar} {format_time(int(duration))}"


def _song_icon(song: dict) -> str:
    return '🎧' if song.get('source') == 'spotify' else '📺'


def _song_link(song: dict) -> str:
    return song.get('spotify_url') or song.get('webpage_url') or song.get('url') or ''


def _format_queue_preview(queue: list) -> str:
    if not queue:
        return 'No songs queued.\n\nQueue: **0 songs**'

    lines = []
    for index, song in enumerate(queue[:3], start=1):
        title = song.get('title', 'Unknown title')
        requester = song.get('requester', 'Unknown')
        icon = _song_icon(song)
        link = _song_link(song)

        if link:
            lines.append(f"{index}. {icon} **[{title}]({link})** — *{requester}*")
        else:
            lines.append(f"{index}. {icon} **{title}** — *{requester}*")

    return '\n'.join(lines) + f"\n\nQueue: **{len(queue)} songs**"


def _get_or_create_view(guild_id: str) -> MusicControlView:
    view = _persistent_views.get(guild_id)
    if view is None:
        view = MusicControlView(guild_id=guild_id, timeout=None)
        _persistent_views[guild_id] = view
    return view


def _register_persistent_view(client, guild_id: str, message_id: int, view: MusicControlView) -> None:
    """Register persistent views once per guild/message id pair."""
    current_message_id = _registered_view_message_ids.get(guild_id)
    if current_message_id == message_id:
        return

    client.add_view(view, message_id=message_id)
    _registered_view_message_ids[guild_id] = message_id


def forget_guild_ui(guild_id: str) -> None:
    """Forget cached UI state for guilds that were removed/invalidated."""
    guild_id = str(guild_id)
    task = _refresh_tasks.pop(guild_id, None)
    if task and not task.done():
        task.cancel()

    _persistent_views.pop(guild_id, None)
    _registered_view_message_ids.pop(guild_id, None)


def create_now_playing_embed(guild_id: str, guild_data: dict) -> Embed:
    """Create the single compact stable embed used in the main panel."""
    from bot_state import client, player_manager, queue_manager

    voice_client = player_manager.voice_clients.get(guild_id)
    queue = queue_manager.get_queue(guild_id)
    current_song = guild_data.get('current_song')

    has_active_playback = bool(voice_client and (voice_client.is_playing() or voice_client.is_paused()))

    if current_song and has_active_playback:
        duration = int(guild_data.get('song_duration', current_song.get('duration') or 0))
        duration_str = format_time(duration) if duration > 0 else 'Unknown'

        song_title = current_song.get('title', 'Unknown title')
        song_link = _song_link(current_song)
        song_line = f"🎵 **[{song_title}]({song_link})**" if song_link else f"🎵 **{song_title}**"

        embed = Embed(
            title='Now Playing',
            description=song_line,
            color=0x1DB954,
        )

        embed.add_field(name='Requester', value=current_song.get('requester', 'Unknown'), inline=True)
        embed.add_field(name='Duration', value=duration_str, inline=True)

        if current_song.get('thumbnail'):
            embed.set_thumbnail(url=current_song['thumbnail'])

        start_time = guild_data.get('song_start_time')
        if start_time and duration > 0:
            elapsed = max(0, min(time.time() - start_time, duration))
            end_timestamp = int(start_time + duration)
            status = '⏸ Paused' if voice_client.is_paused() else '▶ Playing'
            embed.add_field(
                name=f'{status} Progress',
                value=f"`{create_progress_bar(elapsed, duration)}`\nEnds <t:{end_timestamp}:R>",
                inline=False,
            )
        else:
            embed.add_field(
                name='Status',
                value='⏸ Paused' if voice_client.is_paused() else '▶ Playing',
                inline=False,
            )
    else:
        embed = Embed(
            title='Now Playing',
            description='No music is currently playing.',
            color=0x5865F2,
        )

    try:
        if voice_client and voice_client.channel:
            from utils.vote_manager import VoteManager

            vote_status = VoteManager.get_vote_status(guild_data, voice_client.channel)
            if vote_status['current_votes'] > 0:
                bar = '█' * vote_status['current_votes'] + '░' * (
                    vote_status['required_votes'] - vote_status['current_votes']
                )
                embed.add_field(
                    name='Vote to Skip',
                    value=(
                        f"🗳 **{vote_status['current_votes']}/{vote_status['required_votes']}** votes\n"
                        f"`{bar}` {vote_status['percentage']}%"
                    ),
                    inline=False,
                )
    except Exception as error:
        logger.warning('Failed to render vote status for guild %s: %s', guild_id, error)

    embed.add_field(name='Up Next', value=_format_queue_preview(queue), inline=False)

    playback_mode = client.playback_modes.get(guild_id, PlaybackMode.NORMAL)
    embed.set_footer(text=f'Playback Mode: {playback_mode.value}')

    return embed


async def _debounced_update(guild_id: str) -> None:
    try:
        await asyncio.sleep(UI_REFRESH_DEBOUNCE_SECONDS)
        await _update_stable_message_now(guild_id)
    except asyncio.CancelledError:
        logger.debug('Cancelled pending UI refresh for guild %s', guild_id)
    finally:
        _refresh_tasks.pop(guild_id, None)


async def update_stable_message(guild_id: str, force: bool = False):
    """Request a stable-message update. Debounced by default per guild."""
    guild_id = str(guild_id)

    if force:
        pending_task = _refresh_tasks.pop(guild_id, None)
        if pending_task and not pending_task.done():
            pending_task.cancel()
        await _update_stable_message_now(guild_id)
        return

    existing_task = _refresh_tasks.get(guild_id)
    if existing_task and not existing_task.done():
        return

    _refresh_tasks[guild_id] = asyncio.create_task(_debounced_update(guild_id))


async def _update_stable_message_now(guild_id: str):
    """Render and apply stable-message UI immediately."""
    try:
        from bot_state import client, data_manager

        guild_id = str(guild_id)
        guild_data = client.guilds_data.get(guild_id)
        if not guild_data:
            logger.warning('No guild data found for guild %s', guild_id)
            return

        channel_id = guild_data.get('channel_id')
        if not channel_id:
            logger.warning('No channel_id found for guild %s', guild_id)
            return

        channel = client.get_channel(int(channel_id))
        if not channel:
            logger.warning('Channel %s not found for guild %s', channel_id, guild_id)
            return

        stable_message = guild_data.get('stable_message')
        stable_message_changed = False

        if not stable_message:
            stable_message_id = guild_data.get('stable_message_id')
            if stable_message_id:
                try:
                    stable_message = await channel.fetch_message(int(stable_message_id))
                    guild_data['stable_message'] = stable_message
                except discord.NotFound:
                    stable_message = None
                except discord.Forbidden:
                    logger.error(
                        'Permission denied while fetching stable message %s in guild %s',
                        stable_message_id,
                        guild_id,
                    )
                    return

        if not stable_message:
            try:
                stable_message = await channel.send('🎶 **Music Bot UI Initialized** 🎶')
                guild_data['stable_message'] = stable_message
                guild_data['stable_message_id'] = stable_message.id
                stable_message_changed = True
            except discord.Forbidden:
                logger.error('Permission denied while creating stable message in guild %s', guild_id)
                return
            except Exception:
                logger.exception('Failed to create stable message for guild %s', guild_id)
                return

        embed = create_now_playing_embed(guild_id, guild_data)
        view = _get_or_create_view(guild_id)
        view.sync_with_guild_state()

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                await stable_message.edit(embed=embed, view=view)
                _register_persistent_view(client, guild_id, stable_message.id, view)
                break
            except discord.NotFound:
                try:
                    stable_message = await channel.send('🎶 **Music Bot UI Initialized** 🎶')
                    guild_data['stable_message'] = stable_message
                    guild_data['stable_message_id'] = stable_message.id
                    stable_message_changed = True
                    await stable_message.edit(embed=embed, view=view)
                    _register_persistent_view(client, guild_id, stable_message.id, view)
                    break
                except Exception:
                    logger.exception('Failed to recreate stable message for guild %s', guild_id)
                    return
            except discord.Forbidden:
                logger.error('Permission denied while editing stable message in guild %s', guild_id)
                return
            except discord.HTTPException as error:
                if attempt < max_retries:
                    logger.warning(
                        'HTTP error updating stable message in guild %s (attempt %s/%s): %s',
                        guild_id,
                        attempt,
                        max_retries,
                        error,
                    )
                    await asyncio.sleep(1)
                else:
                    logger.error(
                        'HTTP error updating stable message in guild %s after %s attempts: %s',
                        guild_id,
                        max_retries,
                        error,
                    )
                    return
            except Exception as error:
                if attempt < max_retries:
                    logger.warning(
                        'Unexpected error updating stable message in guild %s (attempt %s/%s): %s',
                        guild_id,
                        attempt,
                        max_retries,
                        error,
                    )
                    await asyncio.sleep(1)
                else:
                    logger.error(
                        'Unexpected error updating stable message in guild %s after %s attempts: %s',
                        guild_id,
                        max_retries,
                        error,
                    )
                    return

        if stable_message_changed:
            try:
                await data_manager.save_guilds_data(client)
            except Exception:
                logger.exception('Failed to save guild data after stable message id change in guild %s', guild_id)

    except Exception:
        logger.exception('Critical error in update_stable_message for guild %s', guild_id)
