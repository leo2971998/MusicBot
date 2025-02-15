import discord
from discord.ext import commands
from discord.ui import Button, View, Modal, TextInput
from discord import Embed, ButtonStyle, app_commands
import os
import asyncio
import yt_dlp
import json
import random
from enum import Enum
import base64
import time
import requests

# --- Load environment variables ---
from dotenv import load_dotenv
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN") or "YOUR_DISCORD_BOT_TOKEN"

# --- Spotify credentials (optional if you use Spotify) ---
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

spotify_access_token = None
spotify_token_expiry = 0

def get_spotify_token():
    """
    Retrieves a cached token if not expired, otherwise requests a new one from Spotify.
    """
    global spotify_access_token, spotify_token_expiry
    if spotify_access_token and time.time() < spotify_token_expiry:
        return spotify_access_token

    token_url = "https://accounts.spotify.com/api/token"
    auth_str = f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}"
    b64_auth_str = base64.b64encode(auth_str.encode()).decode()
    headers = {"Authorization": f"Basic {b64_auth_str}"}
    data = {"grant_type": "client_credentials"}
    response = requests.post(token_url, headers=headers, data=data)
    if response.status_code != 200:
        raise Exception("Could not authenticate with Spotify")

    token_info = response.json()
    spotify_access_token = token_info["access_token"]
    expires_in = token_info["expires_in"]
    spotify_token_expiry = time.time() + expires_in - 10
    return spotify_access_token

def search_spotify_track(query):
    """
    Searches Spotify for tracks given a query. Returns JSON data with up to 5 results.
    """
    token = get_spotify_token()
    headers = {"Authorization": f"Bearer {token}"}
    search_url = "https://api.spotify.com/v1/search"
    params = {"q": query, "type": "track", "limit": 5}
    response = requests.get(search_url, headers=headers, params=params)
    if response.status_code != 200:
        return None
    return response.json()

# --- Set up bot intents and command prefix ---
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.voice_states = True

client = commands.Bot(command_prefix=".", intents=intents)
client.guilds_data = {}

# --- Playback modes ---
class PlaybackMode(Enum):
    NORMAL = 'normal'
    REPEAT_ONE = 'repeat_one'

client.playback_modes = {}

# --- Queues and voice clients ---
queues = {}
voice_clients = {}

# --- yt-dlp options ---
import yt_dlp

yt_dl_options = {
    "format": "bestaudio/best",
    "postprocessors": [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'opus',
        'preferredquality': '192',
    }],
    "noplaylist": True,
    "quiet": True,
    "default_search": "auto",
    "extract_flat": False,
    "nocheckcertificate": True,
}
ytdl = yt_dlp.YoutubeDL(yt_dl_options)

ffmpeg_options = {
    'before_options': '-re -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -b:a 192k'
}

# --- Data file for saving guild data ---
DATA_FILE = 'guilds_data.json'

def save_guilds_data():
    serializable_data = {}
    for guild_id, guild_data in client.guilds_data.items():
        data_to_save = guild_data.copy()
        data_to_save.pop('stable_message', None)
        data_to_save.pop('progress_task', None)
        data_to_save.pop('disconnect_task', None)
        serializable_data[guild_id] = data_to_save

    data = {
        'guilds_data': serializable_data,
        'playback_modes': {gid: mode.value for gid, mode in client.playback_modes.items()}
    }
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f)

def load_guilds_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            try:
                data = json.load(f)
                client.guilds_data = data.get('guilds_data', {})
                old_playback_modes = data.get('playback_modes', {})
                client.playback_modes = {}
                for gid, mode in old_playback_modes.items():
                    # Convert old mode strings to new PlaybackMode if needed
                    if mode == 'repeat':
                        client.playback_modes[gid] = PlaybackMode.REPEAT_ONE
                    else:
                        try:
                            client.playback_modes[gid] = PlaybackMode(mode)
                        except ValueError:
                            client.playback_modes[gid] = PlaybackMode.NORMAL
            except (json.JSONDecodeError, ValueError) as e:
                print("Error loading guild data:", e)
                client.guilds_data = {}
                client.playback_modes = {}
    else:
        client.guilds_data = {}
        client.playback_modes = {}

def is_setup():
    """
    A check that ensures the guild has run /setup before allowing music commands.
    """
    async def predicate(interaction: discord.Interaction):
        guild_id = str(interaction.guild_id)
        guild_data = client.guilds_data.get(guild_id)
        if not guild_data or not guild_data.get('channel_id'):
            await interaction.response.send_message(
                "❌ Please run /setup to initialize the music channel first.",
                ephemeral=True
            )
            return False
        return True
    return app_commands.check(predicate)

@client.event
async def on_ready():
    load_guilds_data()
    print(f"{client.user} is now jamming!")
    # Clear global commands to avoid duplicates
    client.tree.clear_commands(guild=None)

    # Option A: Register commands globally (can take up to 1 hour to appear):
    await client.tree.sync()

    # Option B (faster testing): specify a GUILD_ID for immediate commands:
    # TEST_GUILD_ID = 123456789012345678  # replace with your server's ID as an integer
    # await client.tree.sync(guild=discord.Object(id=TEST_GUILD_ID))

    # Re-fetch the stable message for each guild
    for guild_id, guild_data in list(client.guilds_data.items()):
        guild = client.get_guild(int(guild_id))
        if not guild:
            del client.guilds_data[guild_id]
            continue

        channel_id = guild_data.get('channel_id')
        if not channel_id:
            del client.guilds_data[guild_id]
            continue

        channel = guild.get_channel(int(channel_id))
        if not channel:
            del client.guilds_data[guild_id]
            continue

        stable_message_id = guild_data.get('stable_message_id')
        if stable_message_id:
            try:
                stable_message = await channel.fetch_message(int(stable_message_id))
                client.guilds_data[guild_id]['stable_message'] = stable_message
            except Exception as e:
                print(f"Error fetching stable message for guild {guild_id}: {e}. Recreating...")
                stable_message = await channel.send("🎶 **Music Bot UI Initialized** 🎶")
                client.guilds_data[guild_id]['stable_message'] = stable_message
                client.guilds_data[guild_id]['stable_message_id'] = stable_message.id
                save_guilds_data()
        else:
            stable_message = await channel.send("🎶 **Music Bot UI Initialized** 🎶")
            client.guilds_data[guild_id]['stable_message'] = stable_message
            client.guilds_data[guild_id]['stable_message_id'] = stable_message.id
            save_guilds_data()

        await update_stable_message(guild_id)

@client.tree.command(name="setup", description="Set up the music channel and bot UI")
@commands.has_permissions(manage_channels=True)
async def setup(interaction: discord.Interaction):
    """
    Creates or re-uses a #leo-song-requests channel, posts the stable UI message,
    and saves the data for this guild.
    """
    guild_id = str(interaction.guild.id)
    # Look for an existing channel named 'leo-song-requests'
    channel = discord.utils.get(interaction.guild.channels, name='leo-song-requests')
    if not channel:
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
            )
        }
        channel = await interaction.guild.create_text_channel('leo-song-requests', overwrites=overwrites)

    # Create the stable message
    stable_message = await channel.send("🎶 **Music Bot UI Initialized** 🎶")

    # Save data
    client.guilds_data[guild_id] = {
        'channel_id': channel.id,
        'stable_message_id': stable_message.id,
        'current_song': None
    }
    client.guilds_data[guild_id]['stable_message'] = stable_message
    save_guilds_data()

    await interaction.response.send_message("Music commands channel setup complete.", ephemeral=True)
    await update_stable_message(guild_id)
    await clear_channel_messages(channel, stable_message.id)

# Guard to avoid double registration of slash commands
if not hasattr(client, "_commands_registered"):
    @client.tree.command(
        name="play",
        description="Play a YouTube song (URL or search). For Spotify, use the UI button."
    )
    @is_setup()
    @app_commands.describe(link="YouTube URL or search query")
    async def play_command(interaction: discord.Interaction, link: str):
        await interaction.response.defer(ephemeral=True, thinking=True)
        response_message = await process_play_request(
            interaction.user,
            interaction.guild,
            interaction.channel,
            link
        )
        if response_message:
            await interaction.followup.send(response_message, ephemeral=True)

    @client.tree.command(
        name="playnext",
        description="Queue a YouTube song to play next. For Spotify, use the UI button."
    )
    @is_setup()
    @app_commands.describe(link="YouTube URL or search query")
    async def playnext_command(interaction: discord.Interaction, link: str):
        await interaction.response.defer(ephemeral=True, thinking=True)
        response_message = await process_play_request(
            interaction.user,
            interaction.guild,
            interaction.channel,
            link,
            play_next=True
        )
        if response_message:
            await interaction.followup.send(response_message, ephemeral=True)

    client._commands_registered = True

# ----------------------------- Music Control UI -----------------------------
class MusicControlView(View):
    def __init__(self, queue):
        super().__init__(timeout=None)
        self.queue = queue

    @discord.ui.button(label='⏸️ Pause', style=ButtonStyle.primary)
    async def pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = str(interaction.guild.id)
        voice_client = voice_clients.get(guild_id)
        if voice_client and voice_client.is_playing():
            voice_client.pause()
            await interaction.response.send_message('⏸️ Paused the music.', ephemeral=True)
        else:
            await interaction.response.send_message('❌ Nothing is playing.', ephemeral=True)
        await update_stable_message(guild_id)

    @discord.ui.button(label='▶️ Resume', style=ButtonStyle.primary)
    async def resume_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = str(interaction.guild.id)
        voice_client = voice_clients.get(guild_id)
        if voice_client and voice_client.is_paused():
            voice_client.resume()
            await interaction.response.send_message('▶️ Resumed the music.', ephemeral=True)
        else:
            await interaction.response.send_message('❌ Nothing is paused.', ephemeral=True)
        await update_stable_message(guild_id)

    @discord.ui.button(label='⏭️ Skip', style=ButtonStyle.primary)
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = str(interaction.guild.id)
        voice_client = voice_clients.get(guild_id)
        if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
            voice_client.stop()
            await interaction.response.send_message('⏭️ Skipped the song.', ephemeral=True)
        else:
            await interaction.response.send_message('❌ Nothing is playing.', ephemeral=True)
        await update_stable_message(guild_id)

    @discord.ui.button(label='⏹️ Stop', style=ButtonStyle.primary)
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = str(interaction.guild.id)
        voice_client = voice_clients.get(guild_id)
        if voice_client:
            voice_client.stop()
            await voice_client.disconnect()
            voice_clients.pop(guild_id, None)
            client.guilds_data[guild_id]['current_song'] = None
            disconnect_task = client.guilds_data[guild_id].get('disconnect_task')
            if disconnect_task:
                disconnect_task.cancel()
                client.guilds_data[guild_id]['disconnect_task'] = None
            client.playback_modes[guild_id] = PlaybackMode.NORMAL
            await interaction.response.send_message('⏹️ Stopped and left the voice channel.', ephemeral=True)
        else:
            await interaction.response.send_message('❌ Not connected to a voice channel.', ephemeral=True)
        await update_stable_message(guild_id)

    @discord.ui.button(label='🗑️ Clear Queue', style=ButtonStyle.danger)
    async def clear_queue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = str(interaction.guild.id)
        if guild_id in queues and queues[guild_id]:
            queues[guild_id].clear()
            await interaction.response.send_message('🗑️ Cleared the queue.', ephemeral=True)
        else:
            await interaction.response.send_message('❌ The queue is already empty.', ephemeral=True)
        await update_stable_message(guild_id)

    @discord.ui.button(label='🔁 Normal', style=ButtonStyle.secondary)
    async def normal_mode_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = str(interaction.guild.id)
        client.playback_modes[guild_id] = PlaybackMode.NORMAL
        await interaction.response.send_message('Playback mode set to: **Normal**', ephemeral=True)
        await update_stable_message(guild_id)

    @discord.ui.button(label='🔂 Repeat', style=ButtonStyle.secondary)
    async def repeat_one_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = str(interaction.guild.id)
        client.playback_modes[guild_id] = PlaybackMode.REPEAT_ONE
        await interaction.response.send_message('Playback mode set to: **Repeat**', ephemeral=True)
        await update_stable_message(guild_id)

    @discord.ui.button(label='🔀 Shuffle', style=ButtonStyle.primary)
    async def shuffle_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = str(interaction.guild.id)
        queue = queues.get(guild_id)
        if queue:
            random.shuffle(queue)
            await interaction.response.send_message('🔀 Queue shuffled.', ephemeral=True)
        else:
            await interaction.response.send_message('❌ The queue is empty.', ephemeral=True)
        await update_stable_message(guild_id)

    @discord.ui.button(label='➕ Add Song', style=ButtonStyle.success)
    async def add_song_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = AddSongModal(interaction)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label='➕ Play Next', style=ButtonStyle.success)
    async def add_next_song_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = AddSongModal(interaction, play_next=True)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label='➕ Add Spotify Song', style=ButtonStyle.success)
    async def add_spotify_song_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = AddSpotifySongModal(interaction)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label='❌ Remove', style=ButtonStyle.danger)
    async def remove_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = RemoveSongModal(interaction)
        await interaction.response.send_modal(modal)

# ----------------------------- Modals -----------------------------
class AddSongModal(Modal):
    def __init__(self, interaction: discord.Interaction, play_next=False):
        title = "Play Next" if play_next else "Add Song"
        super().__init__(title=title)
        self.interaction = interaction
        self.play_next = play_next

        self.title_input = TextInput(
            label="Song Title",
            placeholder="Enter the song title",
            required=True
        )
        self.artist_input = TextInput(
            label="Artist",
            placeholder="Enter the artist name",
            required=True
        )
        self.add_item(self.title_input)
        self.add_item(self.artist_input)

    async def on_submit(self, interaction: discord.Interaction):
        song_title = self.title_input.value.strip()
        artist = self.artist_input.value.strip()
        search_query = f"{song_title} {artist}"

        await interaction.response.defer(ephemeral=True, thinking=True)
        response_message = await process_play_request(
            interaction.user,
            interaction.guild,
            interaction.channel,
            search_query,
            play_next=self.play_next
        )
        if response_message:
            await interaction.followup.send(response_message, ephemeral=True)
        # We do not delete ephemeral messages—Discord handles them automatically.

class AddSpotifySongModal(Modal):
    def __init__(self, interaction: discord.Interaction, play_next=False):
        title = "Play Next Spotify" if play_next else "Add Spotify Song"
        super().__init__(title=title)
        self.interaction = interaction
        self.play_next = play_next

        self.spotify_input = TextInput(
            label="Spotify URL or Query",
            placeholder="Enter a Spotify track URL or search query",
            required=True
        )
        self.add_item(self.spotify_input)

    async def on_submit(self, interaction: discord.Interaction):
        spotify_query = self.spotify_input.value.strip()
        await interaction.response.defer(ephemeral=True, thinking=True)

        spotify_data = search_spotify_track(spotify_query)
        if not spotify_data:
            await interaction.followup.send("❌ Error searching Spotify.", ephemeral=True)
            return

        tracks = spotify_data.get("tracks", {}).get("items", [])
        if not tracks:
            await interaction.followup.send("❌ No tracks found on Spotify.", ephemeral=True)
            return

        # Optional example filter: "charlie puth"
        query_lower = spotify_query.lower()
        filtered_tracks = []
        if "charlie puth" in query_lower:
            filtered_tracks = [
                t for t in tracks
                if any("charlie puth" in artist["name"].lower() for artist in t.get("artists", []))
            ]

        if filtered_tracks:
            best_track = max(filtered_tracks, key=lambda x: x.get("popularity", 0))
        else:
            best_track = max(tracks, key=lambda x: x.get("popularity", 0))

        track_name = best_track["name"]
        artists = ", ".join(a["name"] for a in best_track["artists"])
        spotify_url = best_track.get("external_urls", {}).get("spotify")

        search_query = f"{track_name} {artists}"
        extra_meta = {"spotify_url": spotify_url, "source": "spotify"}

        response_message = await process_play_request(
            interaction.user,
            interaction.guild,
            interaction.channel,
            search_query,
            play_next=self.play_next,
            extra_meta=extra_meta
        )
        if response_message:
            await interaction.followup.send(response_message, ephemeral=True)
        await update_stable_message(str(interaction.guild.id))

class RemoveSongModal(Modal):
    def __init__(self, interaction: discord.Interaction):
        super().__init__(title="Remove Song")
        self.interaction = interaction
        self.song_index = TextInput(
            label="Song Index",
            placeholder="Enter the number of the song to remove",
            required=True
        )
        self.add_item(self.song_index)

    async def on_submit(self, interaction: discord.Interaction):
        index_str = self.song_index.value.strip()
        guild_id = str(interaction.guild.id)
        queue = queues.get(guild_id, [])

        if not queue:
            await interaction.response.send_message("❌ The queue is empty.", ephemeral=True)
            return

        try:
            index = int(index_str)
            if 1 <= index <= len(queue):
                removed_song = queue.pop(index - 1)
                await interaction.response.send_message(
                    f'❌ Removed **{removed_song["title"]}** from the queue.',
                    ephemeral=True
                )
                await update_stable_message(guild_id)
            else:
                await interaction.response.send_message("❌ Invalid song index.", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("❌ Please enter a valid number.", ephemeral=True)

# ----------------------------- Main Music Logic -----------------------------

def format_time(seconds: float) -> str:
    minutes = int(seconds) // 60
    secs = int(seconds) % 60
    return f"{minutes:02d}:{secs:02d}"

def cancel_disconnect_task(guild_id: str):
    """
    Cancels any pending auto-disconnect task for this guild.
    """
    disconnect_task = client.guilds_data.get(guild_id, {}).get('disconnect_task')
    if disconnect_task:
        disconnect_task.cancel()
        client.guilds_data[guild_id]['disconnect_task'] = None

async def disconnect_after_delay(guild_id: str, delay: int):
    """
    Disconnects the bot from voice if it's idle (not playing) after a delay.
    """
    try:
        await asyncio.sleep(delay)
        voice_client = voice_clients.get(guild_id)
        if voice_client and not voice_client.is_playing():
            await voice_client.disconnect()
            voice_clients.pop(guild_id, None)
            client.guilds_data[guild_id]['disconnect_task'] = None
            await update_stable_message(guild_id)
    except asyncio.CancelledError:
        # Another request canceled this task
        pass

async def process_play_request(
    user: discord.abc.User,
    guild: discord.Guild,
    channel: discord.abc.Messageable,
    link: str,
    play_next=False,
    extra_meta=None
):
    """
    Main logic to handle a 'play' or 'playnext' request for a given link or search query.
    """
    guild_id = str(guild.id)
    guild_data = client.guilds_data.get(guild_id)
    if not guild_data or not guild_data.get('channel_id'):
        return "❌ Please run /setup to initialize the music channel first."

    # Ensure user is a Member with voice info
    if not isinstance(user, discord.Member):
        user = guild.get_member(user.id) or await guild.fetch_member(user.id)
    if not user or not user.voice or not user.voice.channel:
        return "❌ You are not connected to a voice channel."

    user_voice_channel = user.voice.channel
    voice_client = voice_clients.get(guild_id)

    # Connect or move to user's channel
    try:
        if voice_client:
            if voice_client.channel != user_voice_channel:
                await voice_client.move_to(user_voice_channel)
        else:
            voice_client = await user_voice_channel.connect()
            voice_clients[guild_id] = voice_client
    except discord.errors.ClientException as e:
        return f"❌ An error occurred: {e}"
    except Exception as e:
        return f"❌ An unexpected error occurred: {e}"

    cancel_disconnect_task(guild_id)

    # Distinguish search from direct URL
    if 'list=' not in link and 'watch?v=' not in link and 'youtu.be/' not in link:
        # It's likely a search
        search_query = f"ytsearch:{link}"
        try:
            results = ytdl.extract_info(search_query, download=False)["entries"]
            if not results:
                return "❌ No results found on YouTube."
            best_result = max(results, key=lambda x: x.get('view_count', 0))
            data = best_result
        except Exception as e:
            return f"❌ Error searching for the song: {e}"
    else:
        # It's a direct link or playlist
        loop = asyncio.get_event_loop()
        try:
            data = await loop.run_in_executor(
                None, lambda: ytdl.extract_info(link, download=False)
            )
        except Exception as e:
            return f"❌ Error extracting song information: {e}"

    # Single track vs. playlist
    if "entries" not in data:
        # Single track
        song_info = data
        song_info["requester"] = user.mention
        if extra_meta:
            song_info.update(extra_meta)  # e.g., 'spotify_url', 'source'='spotify'
        else:
            song_info["source"] = "youtube"

        if not voice_client.is_playing() and not voice_client.is_paused():
            client.guilds_data[guild_id]["current_song"] = song_info
            await play_song(guild_id, song_info)
            msg = f"🎶 Now playing: **{song_info.get('title', 'Unknown title')}**"
        else:
            if guild_id not in queues:
                queues[guild_id] = []
            if play_next:
                queues[guild_id].insert(0, song_info)
                msg = f"➕ Added to play next: **{song_info.get('title', 'Unknown title')}**"
            else:
                queues[guild_id].append(song_info)
                msg = f"➕ Added to queue: **{song_info.get('title', 'Unknown title')}**"

    else:
        # Playlist
        playlist_entries = data["entries"]
        added_songs = []
        if play_next:
            # Insert in reverse order so first is next to play
            for entry in reversed(playlist_entries):
                if entry is None:
                    continue
                entry["requester"] = user.mention
                if guild_id not in queues:
                    queues[guild_id] = []
                queues[guild_id].insert(0, entry)
                added_songs.append(entry["title"])
            msg = (
                f"🎶 Added playlist **{data.get('title','Unknown playlist')}** "
                f"({len(added_songs)} songs) to play next."
            )
        else:
            for entry in playlist_entries:
                if entry is None:
                    continue
                entry["requester"] = user.mention
                if guild_id not in queues:
                    queues[guild_id] = []
                queues[guild_id].append(entry)
                added_songs.append(entry["title"])
            msg = (
                f"🎶 Added playlist **{data.get('title','Unknown playlist')}** "
                f"({len(added_songs)} songs) to the queue."
            )
        # If nothing is playing, start automatically
        if not voice_client.is_playing() and not voice_client.is_paused():
            await play_next(guild_id)

    # Clear the channel messages except the stable message
    stable_message_id = guild_data.get("stable_message_id")
    channel_id = guild_data.get("channel_id")
    if stable_message_id and channel_id:
        ch = client.get_channel(int(channel_id))
        await clear_channel_messages(ch, int(stable_message_id))

    await update_stable_message(guild_id)
    return msg

async def play_song(guild_id: str, song_info: dict):
    voice_client = voice_clients.get(guild_id)
    if not voice_client:
        print(f"No voice client for guild {guild_id}")
        return

    cancel_disconnect_task(guild_id)

    song_url = song_info.get("url")
    # If direct URL not found, fallback to 'formats'
    if not song_url and "formats" in song_info:
        for fmt in song_info["formats"]:
            if fmt.get("acodec") != "none":
                song_url = fmt["url"]
                break
    if not song_url:
        print(f"No valid audio URL found for {song_info.get('title')}")
        return

    if voice_client.is_playing() or voice_client.is_paused():
        voice_client.stop()

    player = discord.FFmpegPCMAudio(song_url, **ffmpeg_options)

    def after_playing(err):
        if err:
            print(f"Error playing track: {err}")
        fut = asyncio.run_coroutine_threadsafe(play_next(guild_id), client.loop)
        try:
            fut.result()
        except Exception as e:
            print(f"Error in play_next: {e}")

    voice_client.play(player, after=after_playing)

    client.guilds_data[guild_id]["current_song"] = song_info
    client.guilds_data[guild_id]["song_duration"] = song_info.get("duration", 0)

    # Announce in the channel
    channel_id = client.guilds_data[guild_id]["channel_id"]
    channel = client.get_channel(int(channel_id))
    if channel:
        try:
            await channel.send(f"🎶 Now playing: **{song_info.get('title','Unknown title')}**")
        except Exception as e:
            print(f"Failed to send now-playing message: {e}")

    await update_stable_message(guild_id)
    save_guilds_data()

async def play_next(guild_id: str):
    progress_task = client.guilds_data[guild_id].get('progress_task')
    if progress_task:
        progress_task.cancel()
        client.guilds_data[guild_id]['progress_task'] = None

    playback_mode = client.playback_modes.get(guild_id, PlaybackMode.NORMAL)
    if playback_mode == PlaybackMode.REPEAT_ONE:
        # Replay the same track
        current_song = client.guilds_data[guild_id]['current_song']
        await play_song(guild_id, current_song)
    else:
        # Normal mode, pop next from queue
        if queues.get(guild_id):
            next_track = queues[guild_id].pop(0)
            client.guilds_data[guild_id]['current_song'] = next_track
            await play_song(guild_id, next_track)
        else:
            # No more songs
            client.guilds_data[guild_id]['current_song'] = None
            if not client.guilds_data[guild_id].get('disconnect_task'):
                disconnect_task = client.loop.create_task(
                    disconnect_after_delay(guild_id, delay=300)
                )
                client.guilds_data[guild_id]['disconnect_task'] = disconnect_task
            client.playback_modes[guild_id] = PlaybackMode.NORMAL
            await update_stable_message(guild_id)

async def update_stable_message(guild_id: str):
    guild_data = client.guilds_data.get(guild_id)
    if not guild_data:
        return

    channel_id = guild_data.get('channel_id')
    if not channel_id:
        return
    channel = client.get_channel(int(channel_id))
    if not channel:
        return

    stable_message = guild_data.get('stable_message')
    if not stable_message:
        # Attempt to recreate if missing
        try:
            stable_message = await channel.send("🎶 **Music Bot UI Initialized** 🎶")
            guild_data['stable_message'] = stable_message
            guild_data['stable_message_id'] = stable_message.id
            save_guilds_data()
        except Exception as e:
            print(f"Failed to recreate stable message: {e}")
            return

    # Embeds
    credits_embed = Embed(
        title="Music Bot UI",
        description="Made by **Leo Nguyen**",
        color=0x1db954
    )

    queue = queues.get(guild_id, [])
    voice_client = voice_clients.get(guild_id)

    # Now playing
    if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
        current_song = guild_data.get('current_song')
        duration = guild_data.get('song_duration', 0)
        duration_str = format_time(duration)
        now_url = current_song.get('spotify_url') or current_song.get('webpage_url')

        now_playing_embed = Embed(
            title="🎶 Now Playing",
            description=f"**[{current_song['title']}]({now_url})**",
            color=0x1db954
        )
        if current_song.get('thumbnail'):
            now_playing_embed.set_thumbnail(url=current_song['thumbnail'])
        now_playing_embed.add_field(name="Duration", value=duration_str, inline=False)
        now_playing_embed.add_field(name="Requested by", value=current_song.get('requester','Unknown'), inline=False)
        playback_mode = client.playback_modes.get(guild_id, PlaybackMode.NORMAL)
        now_playing_embed.set_footer(text=f"Playback Mode: {playback_mode.value}")
    else:
        now_playing_embed = Embed(
            title="🎶 Now Playing",
            description="No music is currently playing.",
            color=0x1db954
        )

    # Queue
    if queue:
        queue_description = "\n".join(
            f"{idx+1}. **[{song['title']}]({song.get('spotify_url', song.get('webpage_url'))})** "
            f"— *{song.get('requester','Unknown')}* ({song.get('source','youtube')})"
            for idx, song in enumerate(queue)
        )
    else:
        queue_description = "No songs in the queue."

    queue_embed = Embed(
        title="📜 Current Queue",
        description=queue_description,
        color=0x1db954
    )
    queue_embed.set_footer(text=f"Total songs in queue: {len(queue)}")

    # Buttons
    view = MusicControlView(queue)
    try:
        await stable_message.edit(embeds=[credits_embed, now_playing_embed, queue_embed], view=view)
    except discord.HTTPException as e:
        print(f"Error updating stable message in guild {guild_id}: {e}")

    save_guilds_data()

async def clear_channel_messages(channel: discord.abc.Messageable, stable_message_id: int):
    """
    Deletes messages in the channel except for the stable message (and pinned ones).
    """
    if not stable_message_id:
        return
    try:
        async for msg in channel.history(limit=100):
            if msg.id != stable_message_id and not msg.pinned:
                try:
                    await msg.delete()
                    await asyncio.sleep(0.1)
                except discord.Forbidden:
                    print(f"Cannot delete msg {msg.id} - no permission.")
                except discord.HTTPException as e:
                    print(f"Error deleting msg {msg.id}: {e}")
    except Exception as e:
        print(f"Error clearing channel messages: {e}")

@client.event
async def on_message(message):
    """
    Allows user to type in #leo-song-requests (if set up) to automatically play a link/search.
    """
    if message.author == client.user or not message.guild:
        return

    guild_id = str(message.guild.id)
    guild_data = client.guilds_data.get(guild_id)
    if guild_data:
        channel_id = guild_data.get('channel_id')
        if channel_id and message.channel.id == int(channel_id):
            # Delete their text message to keep the channel clean
            try:
                await message.delete()
            except (discord.Forbidden, discord.HTTPException):
                pass

            # Attempt to parse it as a play request
            resp = await process_play_request(
                message.author,
                message.guild,
                message.channel,
                message.content
            )
            if resp:
                temp = await message.channel.send(resp)
                await asyncio.sleep(5)
                try:
                    await temp.delete()
                except:
                    pass
        else:
            await client.process_commands(message)
    else:
        await client.process_commands(message)


if __name__ == "__main__":
    client.run(TOKEN)
