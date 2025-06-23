import logging
import random
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class QueueManager:
    """Manages music queues for all guilds"""

    def __init__(self):
        self.queues: Dict[str, List[dict]] = {}

    def get_queue(self, guild_id: str) -> List[dict]:
        """Get queue for a guild"""
        return self.queues.get(guild_id, [])

    def add_song(self, guild_id: str, song_info: dict, play_next: bool = False) -> bool:
        """Add a song to the queue"""
        try:
            if guild_id not in self.queues:
                self.queues[guild_id] = []

            if play_next:
                self.queues[guild_id].insert(0, song_info)
            else:
                self.queues[guild_id].append(song_info)

            logger.info(f"Added song '{song_info.get('title', 'Unknown')}' to guild {guild_id} queue")
            return True

        except Exception as e:
            logger.error(f"Error adding song to queue in guild {guild_id}: {e}")
            return False

    def get_next_song(self, guild_id: str) -> Optional[dict]:
        """Get and remove the next song from queue"""
        queue = self.queues.get(guild_id, [])
        if queue:
            return queue.pop(0)
        return None

    def remove_song(self, guild_id: str, index: int) -> Optional[dict]:
        """Remove a song at specific index"""
        try:
            queue = self.queues.get(guild_id, [])
            if 1 <= index <= len(queue):
                removed_song = queue.pop(index - 1)
                logger.info(f"Removed song at index {index} from guild {guild_id}")
                return removed_song
            return None
        except Exception as e:
            logger.error(f"Error removing song from guild {guild_id}: {e}")
            return None

    def clear_queue(self, guild_id: str) -> int:
        """Clear the entire queue and return count of removed songs"""
        queue = self.queues.get(guild_id, [])
        count = len(queue)
        self.queues[guild_id] = []
        logger.info(f"Cleared {count} songs from guild {guild_id} queue")
        return count

    def shuffle_queue(self, guild_id: str) -> bool:
        """Shuffle the queue"""
        try:
            queue = self.queues.get(guild_id, [])
            if queue:
                random.shuffle(queue)
                logger.info(f"Shuffled queue for guild {guild_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error shuffling queue for guild {guild_id}: {e}")
            return False

    def get_queue_length(self, guild_id: str) -> int:
        """Get the length of the queue"""
        return len(self.queues.get(guild_id, []))

    def cleanup_guild(self, guild_id: str):
        """Clean up queue data for a guild"""
        self.queues.pop(guild_id, None)
        logger.info(f"Cleaned up queue for guild {guild_id}")