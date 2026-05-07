"""Helpers for keeping song records compact and JSON-safe."""

from typing import Any

SONG_TEXT_LIMIT = 300


def _clean_text(value: Any, *, max_length: int | None = SONG_TEXT_LIMIT) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    if max_length is not None and len(text) > max_length:
        return text[: max_length - 3].rstrip() + "..."

    return text


def _clean_int(value: Any) -> int | None:
    if value in (None, ""):
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def create_song_info(raw_song: dict, *, user=None, extra_meta: dict | None = None) -> dict:
    """Build the small song payload needed for queueing, playback, and display."""
    raw_song = raw_song or {}
    song_info = {}

    for key in (
        "id",
        "title",
        "uploader",
        "webpage_url",
        "url",
        "thumbnail",
        "spotify_url",
        "requester",
        "source",
    ):
        max_length = None if key in {"url", "webpage_url"} else SONG_TEXT_LIMIT
        value = _clean_text(raw_song.get(key), max_length=max_length)
        if value is not None:
            song_info[key] = value

    duration = _clean_int(raw_song.get("duration"))
    if duration is not None:
        song_info["duration"] = max(0, duration)

    if user is not None:
        song_info["requester"] = user.mention
        song_info["requester_id"] = user.id
    else:
        requester_id = _clean_int(raw_song.get("requester_id"))
        if requester_id is not None:
            song_info["requester_id"] = requester_id

    if extra_meta:
        for key, value in extra_meta.items():
            if isinstance(value, (str, int, float, bool)) or value is None:
                song_info[key] = value
    else:
        song_info.setdefault("source", "youtube")

    if not song_info.get("title"):
        song_info["title"] = "Unknown title"

    return song_info
