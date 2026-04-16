import os
from enum import Enum
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Bot Configuration
TOKEN = os.getenv('DISCORD_TOKEN')
DATA_FILE = 'guilds_data.json'
MUSIC_CHANNEL_NAME = 'leo-song-requests'

# FFmpeg options - Enhanced for better streaming stability
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -nostdin',
    'options': '-vn -loglevel warning'
}

YTDL_HTTP_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    ),
}

YTDL_EXTRACTOR_ARGS = {
    'youtube': {
        'player_client': ['android_music', 'android', 'web'],
    }
}


def _build_ytdl_options(*, flat: bool = False) -> dict:
    options = {
        'format': 'bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'default_search': 'ytsearch',
        'source_address': '0.0.0.0',
        'nocheckcertificate': True,
        'extractor_retries': 3,
        'retries': 3,
        'extractor_args': YTDL_EXTRACTOR_ARGS,
        'http_headers': YTDL_HTTP_HEADERS,
    }

    if flat:
        options.update({
            'extract_flat': True,
            'skip_download': True,
            'writeinfojson': False,
            'writethumbnail': False,
            'writesubtitles': False,
            'writeautomaticsub': False,
            'ignoreerrors': True,
        })
    else:
        options.update({
            'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
            'restrictfilenames': True,
            'noplaylist': True,
            'ignoreerrors': False,
            'logtostderr': False,
        })

    return options


# YT-DLP options - updated for better YouTube compatibility
YTDL_FORMAT_OPTS = _build_ytdl_options()

# Fast search options for Phase 1 (basic search with minimal metadata)
FAST_SEARCH_OPTS = _build_ytdl_options(flat=True)

# Full metadata options for Phase 2 (when user selects a song)
FULL_METADATA_OPTS = _build_ytdl_options()

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
