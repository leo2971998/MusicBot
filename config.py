import os
from enum import Enum
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def _get_bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


def _get_int_env(name: str, default: int, *, minimum: int | None = None) -> int:
    value = os.getenv(name)
    if value is None:
        return default

    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default

    if minimum is not None and parsed < minimum:
        return default

    return parsed


# Bot Configuration
TOKEN = os.getenv('DISCORD_TOKEN')
DATA_FILE = 'guilds_data.json'
MUSIC_CHANNEL_NAME = 'leo-song-requests'
MAX_QUERY_LENGTH = _get_int_env("MAX_QUERY_LENGTH", 500, minimum=1)

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
        'nocheckcertificate': _get_bool_env('YTDL_NO_CHECK_CERTIFICATE', False),
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
_LOG_LEVELS = {'CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG', 'NOTSET'}
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
if LOG_LEVEL not in _LOG_LEVELS:
    LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# How long to stay connected when idle (in seconds)
IDLE_DISCONNECT_DELAY = _get_int_env("IDLE_DISCONNECT_DELAY", 120, minimum=0)

# Health check and cleanup intervals (in seconds)
HEALTH_CHECK_INTERVAL = _get_int_env("HEALTH_CHECK_INTERVAL", 300, minimum=1)  # 5 minutes
MEMORY_CLEANUP_INTERVAL = _get_int_env("MEMORY_CLEANUP_INTERVAL", 600, minimum=1)  # 10 minutes
MAX_GUILD_DATA_AGE = _get_int_env("MAX_GUILD_DATA_AGE", 86400, minimum=1)  # 24 hours
