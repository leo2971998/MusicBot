import asyncio
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

import discord
from discord.ext import commands

from utils.song_utils import create_song_info

logger = logging.getLogger(__name__)
_SKIP = object()

class GuildDataManager:
    """Manages persistent data for Discord guilds"""

    def __init__(self, data_file: str = "guilds_data.json"):
        self.data_file = Path(data_file)
        self._save_lock = asyncio.Lock()

    async def load_guilds_data(self, client: commands.Bot) -> None:
        """Load guild data from persistent storage"""
        try:
            logger.debug(f"Loading guild data from {self.data_file}")
            if self.data_file.exists():
                with self.data_file.open('r', encoding='utf-8') as f:
                    loaded_data = json.load(f)

                if not isinstance(loaded_data, dict):
                    logger.warning("Guild data file did not contain an object; starting fresh")
                    client.guilds_data = {}
                    return

                client.guilds_data = loaded_data
                logger.info(f"Loaded data for {len(client.guilds_data)} guilds")
            else:
                client.guilds_data = {}
                logger.info("No existing guild data found, starting fresh")
        except Exception as e:
            logger.error(f"Error loading guild data: {e}")
            client.guilds_data = {}

    async def save_guilds_data(self, client: commands.Bot) -> None:
        """Save guild data to persistent storage"""
        async with self._save_lock:
            temp_path = None
            try:
                logger.debug(f"Saving guild data to {self.data_file}")
                data_to_save = self._prepare_data_for_save(client.guilds_data)
                self.data_file.parent.mkdir(parents=True, exist_ok=True)

                with tempfile.NamedTemporaryFile(
                    'w',
                    encoding='utf-8',
                    dir=str(self.data_file.parent),
                    delete=False,
                ) as temp_file:
                    temp_path = temp_file.name
                    json.dump(data_to_save, temp_file, indent=2, ensure_ascii=False)
                    temp_file.write('\n')

                os.replace(temp_path, self.data_file)
                logger.info(f"Saved data for {len(data_to_save)} guilds")
            except Exception as e:
                logger.error(f"Error saving guild data: {e}")
                if temp_path:
                    try:
                        os.unlink(temp_path)
                    except OSError:
                        pass

    def _prepare_data_for_save(self, guilds_data: dict) -> dict:
        data_to_save = {}
        for guild_id, guild_data in guilds_data.items():
            if not isinstance(guild_data, dict):
                continue

            cleaned_data = {}
            for key, value in guild_data.items():
                if key == 'stable_message' or isinstance(value, discord.Message):
                    continue

                if key == 'current_song' and isinstance(value, dict):
                    value = create_song_info(value)

                cleaned_value = self._make_json_safe(value)
                if cleaned_value is not _SKIP:
                    cleaned_data[str(key)] = cleaned_value

            data_to_save[str(guild_id)] = cleaned_data

        return data_to_save

    def _make_json_safe(self, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value

        if isinstance(value, dict):
            cleaned = {}
            for key, item in value.items():
                if not isinstance(key, (str, int, float, bool)):
                    continue

                cleaned_item = self._make_json_safe(item)
                if cleaned_item is not _SKIP:
                    cleaned[str(key)] = cleaned_item
            return cleaned

        if isinstance(value, (list, tuple)):
            cleaned = []
            for item in value:
                cleaned_item = self._make_json_safe(item)
                if cleaned_item is not _SKIP:
                    cleaned.append(cleaned_item)
            return cleaned

        return _SKIP

    def get_guild_data(self, client: commands.Bot, guild_id: str) -> dict:
        """Get data for a specific guild"""
        return client.guilds_data.get(guild_id, {})

    def set_guild_data(self, client: commands.Bot, guild_id: str, data: dict) -> None:
        """Set data for a specific guild"""
        if guild_id not in client.guilds_data:
            client.guilds_data[guild_id] = {}
        client.guilds_data[guild_id].update(data)

    def remove_guild_data(self, client: commands.Bot, guild_id: str) -> None:
        """Remove data for a specific guild"""
        client.guilds_data.pop(guild_id, None)
