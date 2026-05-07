import asyncio
import logging
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bot_state import client, data_manager
from config import LOG_FORMAT, LOG_LEVEL, MUSIC_CHANNEL_NAME, TOKEN
from utils.guild_setup import ensure_guild_music_panel


logging.basicConfig(level=getattr(logging, LOG_LEVEL), format=LOG_FORMAT)
logger = logging.getLogger(__name__)


@client.event
async def on_ready():
    logger.info("Running one-time setup for %s guild(s)", len(client.guilds))
    await data_manager.load_guilds_data(client)

    prepared = 0
    failed = 0
    for guild in client.guilds:
        try:
            guild_data, channel, _ = await ensure_guild_music_panel(
                guild,
                channel_name=MUSIC_CHANNEL_NAME,
                create_channel=True,
            )
            if guild_data and channel:
                prepared += 1
                logger.info("Prepared music panel for guild %s in channel %s", guild.id, channel.id)
            else:
                failed += 1
                logger.warning("Could not prepare music panel for guild %s", guild.id)
        except Exception:
            failed += 1
            logger.exception("Failed to prepare music panel for guild %s", guild.id)

    await data_manager.save_guilds_data(client)
    logger.info("Finished one-time guild setup: prepared=%s failed=%s", prepared, failed)
    await client.close()


def main():
    token = TOKEN or os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN is not set")
    client.run(token)


if __name__ == "__main__":
    main()
