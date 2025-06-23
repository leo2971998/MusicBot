import asyncio
import logging
import discord

logger = logging.getLogger(__name__)

async def clear_channel_messages(channel, stable_message_id, limit=100):
    """Clear messages from channel except stable message"""
    if not stable_message_id:
        return

    try:
        deleted_count = 0
        async for message in channel.history(limit=limit):
            if message.id != stable_message_id and not message.pinned:
                try:
                    await message.delete()
                    deleted_count += 1
                    await asyncio.sleep(0.1)  # Rate limit protection
                except discord.Forbidden:
                    logger.warning(f"Permission error: Cannot delete message {message.id}")
                except discord.HTTPException as e:
                    logger.warning(f"Failed to delete message {message.id}: {e}")

        if deleted_count > 0:
            logger.info(f"Cleared {deleted_count} messages from channel {channel.id}")

    except Exception as e:
        logger.error(f"Error clearing channel messages: {e}")

async def safe_send_message(channel, content, **kwargs):
    """Safely send a message with error handling"""
    try:
        return await channel.send(content, **kwargs)
    except discord.Forbidden:
        logger.error(f"No permission to send message in channel {channel.id}")
        return None
    except discord.HTTPException as e:
        logger.error(f"HTTP error sending message: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error sending message: {e}")
        return None