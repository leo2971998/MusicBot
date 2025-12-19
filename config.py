import os
from enum import Enum
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Bot Configuration
TOKEN = os.getenv('DISCORD_TOKEN')
DATA_FILE = 'guilds_data.json'
MUSIC_CHANNEL_NAME = 'leo-song-requests'

# FFmpeg options
FFMPEG_OPTIONS = {
    'before_options': ' -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

# YT-DLP options
YTDL_FORMAT_OPTS = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
}

# Fast search options for Phase 1 (basic search with minimal metadata)
FAST_SEARCH_OPTS = {
    'format': 'bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'extract_flat': True,  # Don't extract full metadata
    'skip_download': True,
    'writeinfojson': False,
    'writethumbnail': False,
    'writesubtitles': False,
    'writeautomaticsub': False,
    'ignoreerrors': True,
    'no_check_certificate': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
}

# Full metadata options for Phase 2 (when user selects a song)
FULL_METADATA_OPTS = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
}

class PlaybackMode(Enum):
    NORMAL = "Normal"
    REPEAT_ONE = "Repeat"
    REPEAT_ALL = "Repeat All"

# Spotify Configuration
SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')

# Logging Configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# How long to stay connected when idle (in seconds)
IDLE_DISCONNECT_DELAY = int(os.getenv("IDLE_DISCONNECT_DELAY", "120"))

# Health check and cleanup intervals (in seconds)
HEALTH_CHECK_INTERVAL = int(os.getenv("HEALTH_CHECK_INTERVAL", "300"))  # 5 minutes
MEMORY_CLEANUP_INTERVAL = int(os.getenv("MEMORY_CLEANUP_INTERVAL", "600"))  # 10 minutes
MAX_GUILD_DATA_AGE = int(os.getenv("MAX_GUILD_DATA_AGE", "86400"))  # 24 hours
