"""
Vote management utilities for the music bot.
Handles vote skip functionality with smart thresholds.
"""

import logging
from typing import Set, Optional
import discord

logger = logging.getLogger(__name__)

class VoteManager:
    """Manages vote skip functionality for guilds"""
    
    @staticmethod
    def get_required_votes(voice_channel: discord.VoiceChannel) -> int:
        """
        Calculate required votes based on voice channel member count.
        Excludes bots from the count.
        
        Vote calculation logic:
        - 1-2 users: 1 vote needed
        - 3-4 users: 2 votes needed  
        - 5-6 users: 3 votes needed
        - 7+ users: 50% of users (rounded up)
        """
        if not voice_channel:
            return 1
            
        # Count only human users (exclude bots)
        human_users = [member for member in voice_channel.members if not member.bot]
        user_count = len(human_users)
        
        if user_count <= 2:
            return 1
        elif user_count <= 4:
            return 2
        elif user_count <= 6:
            return 3
        else:
            # 50% of users, rounded up
            return max(1, (user_count + 1) // 2)
    
    @staticmethod
    def add_vote(guild_data: dict, user_id: int) -> bool:
        """
        Add a vote for the current user.
        Returns True if vote was added, False if user already voted.
        """
        if 'vote_skip' not in guild_data:
            guild_data['vote_skip'] = {
                'votes': [],  # Use list instead of set for JSON serialization
                'song_id': None  # Track which song the votes are for
            }
        
        # Check if user already voted
        if user_id in guild_data['vote_skip']['votes']:
            return False
            
        # Add the vote
        guild_data['vote_skip']['votes'].append(user_id)
        logger.debug(f"Added vote from user {user_id}, total votes: {len(guild_data['vote_skip']['votes'])}")
        return True
    
    @staticmethod
    def check_vote_threshold(guild_data: dict, voice_channel: discord.VoiceChannel) -> bool:
        """
        Check if vote threshold has been reached.
        Returns True if enough votes to skip.
        """
        if 'vote_skip' not in guild_data:
            return False
            
        current_votes = len(guild_data['vote_skip']['votes'])
        required_votes = VoteManager.get_required_votes(voice_channel)
        
        logger.debug(f"Vote check: {current_votes}/{required_votes}")
        return current_votes >= required_votes
    
    @staticmethod
    def reset_votes(guild_data: dict, song_id: Optional[str] = None):
        """
        Reset votes for a new song.
        Optionally track which song the votes are for.
        """
        guild_data['vote_skip'] = {
            'votes': [],  # Use list instead of set for JSON serialization
            'song_id': song_id
        }
        logger.debug(f"Reset votes for song {song_id}")
    
    @staticmethod
    def get_vote_status(guild_data: dict, voice_channel: discord.VoiceChannel) -> dict:
        """
        Get current vote status for display.
        Returns dict with current votes, required votes, and percentage.
        """
        if 'vote_skip' not in guild_data:
            guild_data['vote_skip'] = {'votes': [], 'song_id': None}  # Use list instead of set for JSON serialization
            
        current_votes = len(guild_data['vote_skip']['votes'])
        required_votes = VoteManager.get_required_votes(voice_channel)
        percentage = int((current_votes / required_votes) * 100) if required_votes > 0 else 0
        
        return {
            'current_votes': current_votes,
            'required_votes': required_votes,
            'percentage': percentage,
            'can_skip': current_votes >= required_votes
        }
    
    @staticmethod
    def remove_user_vote(guild_data: dict, user_id: int) -> bool:
        """
        Remove a user's vote (e.g., when they leave the voice channel).
        Returns True if vote was removed, False if user hadn't voted.
        """
        if 'vote_skip' not in guild_data:
            return False
            
        if user_id in guild_data['vote_skip']['votes']:
            guild_data['vote_skip']['votes'].remove(user_id)
            logger.debug(f"Removed vote from user {user_id}")
            return True
        return False
    
    @staticmethod
    def is_song_requestor(guild_data: dict, user_id: int) -> bool:
        """
        Check if the user is the requestor of the current song.
        Returns True if user requested the current song, False otherwise.
        """
        current_song = guild_data.get('current_song')
        if not current_song:
            return False
            
        # Check for requester_id field first (more reliable)
        requester_id = current_song.get('requester_id')
        if requester_id is not None:
            return requester_id == user_id
            
        # Fallback: Extract user ID from requester mention (format: <@user_id>)
        requester = current_song.get('requester', '')
        if not requester:
            return False
            
        # Handle mention format <@user_id>
        if requester.startswith('<@') and requester.endswith('>'):
            try:
                # Remove <@ and > from the mention
                requester_id = int(requester[2:-1])
                return requester_id == user_id
            except ValueError:
                logger.warning(f"Could not parse requester mention: {requester}")
                return False
        else:
            # Fallback: try direct comparison if stored as string
            try:
                return int(requester) == user_id
            except (ValueError, TypeError):
                return False