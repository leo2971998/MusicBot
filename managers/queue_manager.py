import logging
import random
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Maximum queue size to prevent memory issues
MAX_QUEUE_SIZE = 100

class QueueManager:
    """Manages music queues for all guilds"""

    def __init__(self):
        self.queues: Dict[str, List[dict]] = {}
        self.repeat_all_playlists: Dict[str, List[dict]] = {}  # Stores the full playlist for repeat all mode

    def get_queue(self, guild_id: str) -> List[dict]:
        """Get queue for a guild"""
        return self.queues.get(guild_id, [])

    def add_song(self, guild_id: str, song_info: dict, play_next: bool = False) -> bool:
        """Add a song to the queue with size limits"""
        try:
            if guild_id not in self.queues:
                self.queues[guild_id] = []

            queue = self.queues[guild_id]
            
            # Check queue size limit
            if len(queue) >= MAX_QUEUE_SIZE:
                logger.warning(f"Queue for guild {guild_id} is at maximum size ({MAX_QUEUE_SIZE})")
                return False

            if play_next:
                queue.insert(0, song_info)
            else:
                queue.append(song_info)

            logger.info(f"Added song '{song_info.get('title', 'Unknown')}' to guild {guild_id} queue (queue size: {len(queue)})")
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

    def save_repeat_all_playlist(self, guild_id: str):
        """Save the current queue state for repeat all mode"""
        queue = self.queues.get(guild_id, [])
        if queue:
            self.repeat_all_playlists[guild_id] = queue.copy()
            logger.info(f"Saved {len(queue)} songs for repeat all mode in guild {guild_id}")
            return True
        return False

    def restore_repeat_all_playlist(self, guild_id: str) -> bool:
        """Restore the saved playlist for repeat all mode"""
        saved_playlist = self.repeat_all_playlists.get(guild_id, [])
        if saved_playlist:
            self.queues[guild_id] = saved_playlist.copy()
            logger.info(f"Restored {len(saved_playlist)} songs for repeat all mode in guild {guild_id}")
            return True
        return False

    def get_repeat_all_playlist(self, guild_id: str) -> List[dict]:
        """Get the saved repeat all playlist"""
        return self.repeat_all_playlists.get(guild_id, [])

    def move_song(self, guild_id: str, from_pos: int, to_pos: int) -> bool:
        """Move a song from one position to another (1-indexed)"""
        try:
            queue = self.queues.get(guild_id, [])
            if not queue:
                return False
            
            # Convert to 0-indexed
            from_idx = from_pos - 1
            to_idx = to_pos - 1
            
            if not (0 <= from_idx < len(queue) and 0 <= to_idx < len(queue)):
                logger.warning(f"Invalid positions for move_song in guild {guild_id}: from={from_pos}, to={to_pos}, queue_length={len(queue)}")
                return False
            
            song = queue.pop(from_idx)
            queue.insert(to_idx, song)
            logger.info(f"Moved song '{song.get('title', 'Unknown')}' from position {from_pos} to {to_pos} in guild {guild_id}")
            return True
        except Exception as e:
            logger.error(f"Error moving song in guild {guild_id}: {e}")
            return False
    
    def jump_to_song(self, guild_id: str, position: int) -> list:
        """Remove all songs before the given position, return removed songs"""
        try:
            queue = self.queues.get(guild_id, [])
            if not queue or position < 1 or position > len(queue):
                logger.warning(f"Invalid position for jump_to_song in guild {guild_id}: position={position}, queue_length={len(queue)}")
                return []
            
            # Remove songs before position (1-indexed)
            removed = queue[:position - 1]
            self.queues[guild_id] = queue[position - 1:]
            logger.info(f"Jumped to position {position} in guild {guild_id}, removed {len(removed)} songs")
            return removed
        except Exception as e:
            logger.error(f"Error jumping to song in guild {guild_id}: {e}")
            return []
    
    def remove_range(self, guild_id: str, start: int, end: int) -> int:
        """Remove songs from start to end (inclusive, 1-indexed)"""
        try:
            queue = self.queues.get(guild_id, [])
            if not queue:
                return 0
            
            # Convert to 0-indexed and validate
            start_idx = max(0, start - 1)
            end_idx = min(len(queue), end)
            
            if start_idx >= end_idx:
                logger.warning(f"Invalid range for remove_range in guild {guild_id}: start={start}, end={end}")
                return 0
            
            removed_count = end_idx - start_idx
            del queue[start_idx:end_idx]
            logger.info(f"Removed {removed_count} songs (positions {start}-{end}) from guild {guild_id}")
            return removed_count
        except Exception as e:
            logger.error(f"Error removing range in guild {guild_id}: {e}")
            return 0
    
    def get_queue_page(self, guild_id: str, page: int = 1, per_page: int = 10) -> tuple:
        """Get paginated queue. Returns (songs, total_pages, current_page)"""
        try:
            queue = self.queues.get(guild_id, [])
            if not queue:
                return [], 0, 0
            
            total_pages = (len(queue) + per_page - 1) // per_page
            page = max(1, min(page, total_pages))
            
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            
            logger.debug(f"Retrieved page {page}/{total_pages} for guild {guild_id} queue")
            return queue[start_idx:end_idx], total_pages, page
        except Exception as e:
            logger.error(f"Error getting queue page for guild {guild_id}: {e}")
            return [], 0, 0

    def cleanup_guild(self, guild_id: str):
        """Clean up queue data for a guild"""
        self.queues.pop(guild_id, None)
        self.repeat_all_playlists.pop(guild_id, None)
        logger.info(f"Cleaned up queue for guild {guild_id}")