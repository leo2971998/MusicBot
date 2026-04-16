import logging
import time
from typing import Optional, Tuple

import discord

from config import MUSIC_CHANNEL_NAME

logger = logging.getLogger(__name__)


def resolve_music_channel(
    guild: discord.Guild,
    guild_data: Optional[dict] = None,
    *,
    channel_name: str = MUSIC_CHANNEL_NAME,
) -> Optional[discord.TextChannel]:
    """Resolve the configured music channel or fall back to the default channel name."""
    guild_data = guild_data or {}
    channel_id = guild_data.get('channel_id')

    if channel_id:
        try:
            channel = guild.get_channel(int(channel_id))
        except (TypeError, ValueError):
            channel = None

        if isinstance(channel, discord.TextChannel):
            return channel

    channel = discord.utils.get(guild.text_channels, name=channel_name)
    if isinstance(channel, discord.TextChannel):
        return channel

    return None


async def ensure_guild_music_panel(
    guild: discord.Guild,
    *,
    channel_name: str = MUSIC_CHANNEL_NAME,
    create_channel: bool = False,
) -> Tuple[Optional[dict], Optional[discord.TextChannel], bool]:
    """
    Ensure a guild has a valid music channel and stable panel.

    Returns ``(guild_data, channel, changed)`` when recovery succeeds,
    otherwise ``(None, None, False)``.
    """
    from bot_state import client, data_manager
    from ui.embeds import update_stable_message

    guild_id = str(guild.id)
    guild_data = client.guilds_data.setdefault(guild_id, {})
    changed = False

    channel = resolve_music_channel(guild, guild_data, channel_name=channel_name)
    if channel is None and create_channel:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
            )
        }
        channel = await guild.create_text_channel(channel_name, overwrites=overwrites)
        logger.info("Created music channel '%s' in guild %s", channel_name, guild_id)
        changed = True

    if channel is None:
        return None, None, False

    if guild_data.get('channel_id') != channel.id:
        guild_data['channel_id'] = channel.id
        changed = True

    if 'current_song' not in guild_data:
        guild_data['current_song'] = None
        changed = True

    if not guild_data.get('last_activity'):
        guild_data['last_activity'] = time.time()
        changed = True

    try:
        await update_stable_message(guild_id, force=True)
    except Exception:
        logger.exception('Failed to refresh stable panel for guild %s', guild_id)

    if changed:
        await data_manager.save_guilds_data(client)

    return guild_data, channel, changed
