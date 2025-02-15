import discord
from discord.ext import commands
from discord.ui import Button, View, Modal, TextInput
from discord import Embed, ButtonStyle, app_commands
import os
import asyncio
import yt_dlp
from dotenv import load_dotenv
import json
import random
from enum import Enum
import base64
import time
import requests

# Load the environment variables
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN") or "YOUR_DISCORD_BOT_TOKEN"

# Spotify credentials from .env
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

# Global variables for Spotify token caching
spotify_access_token = None
spotify_token_expiry = 0

def get_spotify_token():
    global spotify_access_token, spotify_token_expiry
    if spotify_access_token and time.time() < spotify_token_expiry:
        return spotify_access_token

    token_url = "https://accounts.spotify.com/api/token"
    auth_str = f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}"
    b64_auth_str = base64.b64encode(auth_str.encode()).decode()
    headers = {
        "Authorization": f"Basic {b64_auth_str}"
    }
    data = {
        "grant_type": "client_credentials"
    }
    response = requests.post(token_url, headers=headers, data=data)
    if response.status_code != 200:
        raise Exception("Could not authenticate with Spotify")
    token_info = response.json()
    spotify_access_token = token_info.get("access_token")
    expires_in = token_info.get("expires_in")
    spotify_token_expiry = time.time() + expires_in - 10  # refresh a few seconds early
    return spotify_access_token

def search_spotify_track(query):
    token = get_spotify_token()
    headers = {
        "Authorization": f"Bearer {token}"
    }
    search_url = "https://api.spotify.com/v1/search"
    params = {
        "q": query,
        "type": "track",
        "limit": 5
    }
    response = requests.get(search_url, headers=headers, params=params)
    if response.status_code != 200:
        return None
    return response.json()

# Set up bot intents and command prefix
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.voice_states = True  # Required for voice channel handling

client = commands.Bot(command_prefix=".", intents=intents)
client.guilds_data = {}

# Define playback modes using Enum
class PlaybackMode(Enum):
    NORMAL = 'normal'
    REPEAT_ONE = 'repeat_one'

client.playback_modes = {}

# Queues & voice clients
queues = {}
voice_clients = {}

# yt-dlp options
yt_dl_options = {
    "format": "bestaudio/best",
    "postprocessors": [
        {
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'opus',
            'preferredquality': '192',
        }
    ],
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
                    if mode == 'repeat':
                        client.playback_modes[gid] = PlaybackMode.REPEAT_ONE
                    else:
                        try:
                            client.playback_modes[gid] = PlaybackMode(mode)
                        except ValueError:
                            client.playback_modes[gid] = PlaybackMode.NORMAL
            except json.JSONDecodeError:
                print("Invalid JSON in guilds_data.json. Initializing with empty data.")
                client.guilds_data = {}
                client.playback_modes = {}
            except ValueError as e:
                print(f"Invalid playback mode value in guilds_data.json: {e}")
                client.playback_modes = {}
    else:
        client.guilds_data = {}
        client.playback_modes = {}

def is_setup():
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
    print(f'{client.user} is now jamming!')

    for guild_id in list(client.guilds_data.keys()):
        guild_data = client.guilds_data[guild_id]
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
                stable_message = await channel.send('🎶 **Music Bot UI Initialized** 🎶')
                client.guilds_data[guild_id]['stable_message'] = stable_message
                client.guilds_data[guild_id]['stable_message_id'] = stable_message.id
                save_guilds_data()
        else:
            stable_message = await channel.send('🎶 **Music Bot UI Initialized** 🎶')
            client.guilds_data[guild_id]['stable_message'] = stable_message
            client.guilds_data[guild_id]['stable_message_id'] = stable_message.id
            save_guilds_data()

        await update_stable_message(guild_id)

    await client.tree.sync()

@client.tree.command(name="setup", description="Set up the music channel and bot UI")
@commands.has_permissions(manage_channels=True)
async def setup(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
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
    stable_message = await channel.send('🎶 **Music Bot UI Initialized** 🎶')
    client.guilds_data[guild_id] = {
        'channel_id': channel.id,
        'stable_message_id': stable_message.id,
        'current_song': None
    }
    save_guilds_data()
    client.guilds_data[guild_id]['stable_message'] = stable_message
    await interaction.response.send_message('Music commands channel setup complete.', ephemeral=True)
    await update_stable_message(guild_id)
    await clear_channel_messages(channel, stable_message.id)

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
            await interaction.response.send_message('⏸️ Paused the music.')
        else:
            await interaction.response.send_message('❌ Nothing is playing.')
        await update_stable_message(guild_id)
        await self.delete_interaction_message(interaction)

    @discord.ui.button(label='▶️ Resume', style=ButtonStyle.primary)
    async def resume_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = str(interaction.guild.id)
        voice_client = voice_clients.get(guild_id)
        if voice_client and voice_client.is_paused():
            voice_client.resume()
            await interaction.response.send_message('▶️ Resumed the music.')
        else:
            await interaction.response.send_message('❌ Nothing is paused.')
        await update_stable_message(guild_id)
        await self.delete_interaction_message(interaction)

    @discord.ui.button(label='⏭️ Skip', style=ButtonStyle.primary)
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = str(interaction.guild.id)
        voice_client = voice_clients.get(guild_id)
        if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
            voice_client.stop()
            await interaction.response.send_message('⏭️ Skipped the song.')
        else:
            await interaction.response.send_message('❌ Nothing is playing.')
        await update_stable_message(guild_id)
        await self.delete_interaction_message(interaction)

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
            await interaction.response.send_message('⏹️ Stopped the music and left the voice channel.')
        else:
            await interaction.response.send_message('❌ Not connected to a voice channel.')
        await update_stable_message(guild_id)
        await self.delete_interaction_message(interaction)

    @discord.ui.button(label='🗑️ Clear Queue', style=ButtonStyle.danger)
    async def clear_queue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = str(interaction.guild.id)
        if guild_id in queues:
            queues[guild_id].clear()
            await interaction.response.send_message('🗑️ Cleared the queue.')
        else:
            await interaction.response.send_message('❌ The queue is already empty.')
        await update_stable_message(guild_id)
        await self.delete_interaction_message(interaction)

    @discord.ui.button(label='🔁 Normal', style=ButtonStyle.secondary)
    async def normal_mode_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = str(interaction.guild.id)
        client.playback_modes[guild_id] = PlaybackMode.NORMAL
        await interaction.response.send_message('Playback mode set to: **Normal**')
        await update_stable_message(guild_id)
        await self.delete_interaction_message(interaction)

    @discord.ui.button(label='🔂 Repeat', style=ButtonStyle.secondary)
    async def repeat_one_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = str(interaction.guild.id)
        client.playback_modes[guild_id] = PlaybackMode.REPEAT_ONE
        await interaction.response.send_message('Playback mode set to: **Repeat**')
        await update_stable_message(guild_id)
        await self.delete_interaction_message(interaction)

    @discord.ui.button(label='🔀 Shuffle', style=ButtonStyle.primary)
    async def shuffle_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = str(interaction.guild.id)
        queue = queues.get(guild_id)
        if queue:
            random.shuffle(queue)
            await interaction.response.send_message('🔀 Queue shuffled.')
        else:
            await interaction.response.send_message('❌ The queue is empty.')
        await update_stable_message(guild_id)
        await self.delete_interaction_message(interaction)

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

    async def delete_interaction_message(self, interaction):
        try:
            message = await interaction.original_response()
            await asyncio.sleep(5)
            await message.delete()
        except Exception as e:
            print(f"Error deleting interaction message: {e}")


class AddSongModal(Modal):
    def __init__(self, interaction: discord.Interaction, play_next=False):
        title = "Play Next" if play_next else "Add Song"
        super().__init__(title=title)
        self.interaction = interaction
        self.play_next = play_next
        self.song_input = TextInput(
            label="Song Name or URL",
            placeholder="Enter the song name or URL",
            required=True
        )
        self.add_item(self.song_input)

    async def on_submit(self, interaction: discord.Interaction):
        song_name_or_url = self.song_input.value.strip()
        await interaction.response.defer(thinking=True)

        response_message = await process_play_request(
            interaction.user,
            interaction.guild,
            interaction.channel,
            song_name_or_url,
            interaction=interaction,
            play_next=self.play_next
        )

        if response_message:
            try:
                await interaction.followup.send(response_message)
            except discord.errors.NotFound:
                print("Interaction message not found. Followup message could not be sent.")
            except Exception as e:
                print(f"Unexpected error sending followup: {e}")

        guild_id = str(interaction.guild.id)
        guild_data = client.guilds_data.get(guild_id)
        if guild_data:
            stable_message_id = guild_data.get('stable_message_id')
            channel_id = guild_data.get('channel_id')
            if stable_message_id and channel_id:
                channel = client.get_channel(int(channel_id))
                await asyncio.sleep(5)
                await clear_channel_messages(channel, int(stable_message_id))


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
        await interaction.response.defer(thinking=True)

        spotify_data = search_spotify_track(spotify_query)
        if not spotify_data:
            await interaction.followup.send("❌ Error searching Spotify.", ephemeral=True)
            return
        tracks = spotify_data.get("tracks", {}).get("items", [])
        if not tracks:
            await interaction.followup.send("❌ No tracks found on Spotify.", ephemeral=True)
            return

        query_lower = spotify_query.lower()
        filtered_tracks = []
        if "charlie puth" in query_lower:
            filtered_tracks = [
                track for track in tracks
                if any("charlie puth" in artist["name"].lower() for artist in track.get("artists", []))
            ]

        if filtered_tracks:
            best_track = max(filtered_tracks, key=lambda x: x.get("popularity", 0))
        else:
            best_track = max(tracks, key=lambda x: x.get("popularity", 0))

        track_name = best_track.get("name")
        artists = ", ".join(a.get("name") for a in best_track.get("artists", []))

        # We'll pass 'source' = 'spotify' as extra metadata
        # so it displays as Spotify in the UI
        extra_meta = {
            "spotify_url": best_track.get("external_urls", {}).get("spotify"),
            "source": "spotify"
        }

        # Construct a YouTube search for the track name & artist (for playback)
        search_query = f"{track_name} {artists}"

        response_message = await process_play_request(
            interaction.user,
            interaction.guild,
            interaction.channel,
            search_query,
            interaction=interaction,
            play_next=self.play_next
            # CRITICAL: pass the extra_meta so the item is flagged as 'spotify'
            # otherwise it stays as a default "youtube" track
            # The line below is the FIX:
            , extra_meta=extra_meta
        )

        if response_message:
            try:
                await interaction.followup.send(response_message, ephemeral=True)
            except Exception as e:
                print(f"Error sending followup: {e}")

        await update_stable_message(str(interaction.guild.id))
        guild_data = client.guilds_data.get(str(interaction.guild.id))
        if guild_data:
            channel = client.get_channel(int(guild_data.get("channel_id")))
            if channel:
                await asyncio.sleep(5)
                await clear_channel_messages(channel, int(guild_data.get("stable_message_id")))


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
        index = self.song_index.value.strip()
        guild_id = str(interaction.guild.id)
        queue = queues.get(guild_id)
        try:
            index = int(index)
            if queue and 1 <= index <= len(queue):
                removed_song = queue.pop(index - 1)
                await interaction.response.send_message(
                    f'❌ Removed **{removed_song["title"]}** from the queue.',
                    ephemeral=True
                )
                await update_stable_message(guild_id)
            else:
                await interaction.response.send_message('❌ Invalid song index.', ephemeral=True)
        except ValueError:
            await interaction.response.send_message('❌ Please enter a valid number.', ephemeral=True)


def format_time(seconds):
    minutes = int(seconds) // 60
    secs = int(seconds) % 60
    return f"{minutes:02d}:{secs:02d}"

async def update_stable_message(guild_id):
    # same code from your snippet, just updated to check 'source'
    guild_id = str(guild_id)
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
        try:
            stable_message = await channel.send('🎶 **Music Bot UI Initialized** 🎶')
            guild_data['stable_message'] = stable_message
            guild_data['stable_message_id'] = stable_message.id
            save_guilds_data()
        except Exception as e:
            print(f"Failed to recreate stable message: {e}")
            return

    credits_embed = Embed(
        title="Music Bot UI",
        description="Made by **Leo Nguyen**",
        color=0x1db954
    )

    queue = queues.get(guild_id, [])
    voice_client = voice_clients.get(guild_id)

    if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
        current_song = guild_data.get('current_song')
        duration = guild_data.get('song_duration', 0)
        duration_str = format_time(duration)

        # Check the source to color it differently
        source = current_song.get('source', 'youtube')
        if source == 'spotify':
            now_title = "🎶 Now Playing (Spotify)"
            now_color = 0x1db954  # Spotify green
            link_url = current_song.get('spotify_url') or current_song.get('webpage_url')
        else:
            now_title = "🎶 Now Playing (YouTube)"
            now_color = 0xff0000
            link_url = current_song.get('webpage_url')

        now_playing_embed = Embed(
            title=now_title,
            description=f"**[{current_song['title']}]({link_url})**",
            color=now_color
        )
        if current_song.get('thumbnail'):
            now_playing_embed.set_thumbnail(url=current_song['thumbnail'])
        now_playing_embed.add_field(name='Duration', value=f"{duration_str}", inline=False)
        now_playing_embed.add_field(name='Requested by', value=current_song.get('requester', 'Unknown'), inline=False)

        playback_mode = client.playback_modes.get(guild_id, PlaybackMode.NORMAL)
        now_playing_embed.set_footer(text=f'Playback Mode: {playback_mode.value}')
    else:
        now_playing_embed = Embed(
            title='🎶 Now Playing',
            description='No music is currently playing.',
            color=0x1db954
        )

    def get_source_icon(song):
        return "🎧" if song.get('source') == 'spotify' else "📺"

    if queue:
        queue_description = '\n'.join(
            f"{idx + 1}. {get_source_icon(song)} **[{song['title']}]({song.get('spotify_url', song.get('webpage_url'))})** — *{song.get('requester', 'Unknown')}*"
            for idx, song in enumerate(queue)
        )
    else:
        queue_description = 'No songs in the queue.'

    queue_embed = Embed(
        title='📜 Current Queue',
        description=queue_description,
        color=0x1db954
    )
    queue_embed.set_footer(text=f"Total songs in queue: {len(queue)}")

    view = MusicControlView(queue)
    try:
        await stable_message.edit(embeds=[credits_embed, now_playing_embed, queue_embed], view=view)
    except discord.HTTPException as e:
        print(f"Error updating stable message in guild {guild_id}: {e}")

    save_guilds_data()

async def clear_channel_messages(channel, stable_message_id):
    if not stable_message_id:
        return
    try:
        async for message in channel.history(limit=100):
            if message.id != stable_message_id and not message.pinned:
                try:
                    await message.delete()
                    await asyncio.sleep(0.1)
                except discord.Forbidden:
                    print(f"Permission error: Cannot delete message {message.id}")
                except discord.HTTPException as e:
                    print(f"Failed to delete message {message.id}: {e}")
    except Exception as e:
        print(f"Error clearing channel messages: {e}")

def cancel_disconnect_task(guild_id):
    disconnect_task = client.guilds_data.get(guild_id, {}).get('disconnect_task')
    if disconnect_task:
        disconnect_task.cancel()
        client.guilds_data[guild_id]['disconnect_task'] = None

async def play_next(guild_id):
    guild_id = str(guild_id)
    progress_task = client.guilds_data[guild_id].get('progress_task')
    if progress_task:
        progress_task.cancel()
        client.guilds_data[guild_id]['progress_task'] = None

    playback_mode = client.playback_modes.get(guild_id, PlaybackMode.NORMAL)

    if playback_mode == PlaybackMode.REPEAT_ONE:
        current_song = client.guilds_data[guild_id]['current_song']
        await play_song(guild_id, current_song)
    else:
        if queues.get(guild_id):
            song_info = queues[guild_id].pop(0)
            client.guilds_data[guild_id]['current_song'] = song_info
            await play_song(guild_id, song_info)
        else:
            client.guilds_data[guild_id]['current_song'] = None
            if not client.guilds_data[guild_id].get('disconnect_task'):
                disconnect_task = client.loop.create_task(disconnect_after_delay(guild_id, delay=300))
                client.guilds_data[guild_id]['disconnect_task'] = disconnect_task
            client.playback_modes[guild_id] = PlaybackMode.NORMAL
            await update_stable_message(guild_id)

async def play_song(guild_id, song_info):
    guild_id = str(guild_id)
    voice_client = voice_clients.get(guild_id)
    if not voice_client:
        print(f"No voice client for guild {guild_id}")
        return
    cancel_disconnect_task(guild_id)

    song_url = song_info.get('url')
    if not song_url and 'formats' in song_info:
        for fmt in song_info['formats']:
            if fmt.get('acodec') != 'none':
                song_url = fmt['url']
                break

    if not song_url:
        print(f"No valid audio URL found for {song_info.get('title')}")
        return

    if voice_client.is_playing() or voice_client.is_paused():
        voice_client.stop()

    player = discord.FFmpegPCMAudio(song_url, **ffmpeg_options)

    def after_playing(error):
        if error:
            print(f"Error occurred while playing: {error}")
        future = asyncio.run_coroutine_threadsafe(play_next(guild_id), client.loop)
        try:
            future.result()
        except Exception as e:
            print(f"Error in play_next: {e}")

    voice_client.play(player, after=after_playing)
    client.guilds_data[guild_id]['current_song'] = song_info
    client.guilds_data[guild_id]['song_duration'] = song_info.get('duration', 0)

    channel_id = client.guilds_data[guild_id]['channel_id']
    channel = client.get_channel(int(channel_id))
    try:
        await channel.send(f"🎶 Now playing: **{song_info.get('title', 'Unknown title')}**")
    except Exception as e:
        print(f"Failed to send now-playing message: {e}")

    await update_stable_message(guild_id)
    save_guilds_data()


async def disconnect_after_delay(guild_id, delay):
    try:
        await asyncio.sleep(delay)
        voice_client = voice_clients.get(guild_id)
        if voice_client and not voice_client.is_playing():
            await voice_client.disconnect()
            voice_clients.pop(guild_id, None)
            client.guilds_data[guild_id]['disconnect_task'] = None
            await update_stable_message(guild_id)
    except asyncio.CancelledError:
        pass

async def process_play_request(user, guild, channel, link, interaction=None, play_next=False, extra_meta=None):
    """
    The key difference is that if this is a Spotify track, we pass extra_meta={'source': 'spotify', ...}
    so the 'source' is recognized and the item is displayed in green with the '🎧' icon in the queue.
    """
    guild_id = str(guild.id)
    guild_data = client.guilds_data.get(guild_id)
    if not guild_data or not guild_data.get('channel_id'):
        return "❌ Please run /setup to initialize the music channel first."

    if not isinstance(user, discord.Member):
        user = guild.get_member(user.id) or await guild.fetch_member(user.id)

    if not user.voice:
        await guild.request_members(user_ids=[user.id])
        user = guild.get_member(user.id)

    user_voice_channel = user.voice.channel if user.voice else None
    if not user_voice_channel:
        return "❌ You are not connected to a voice channel."

    voice_client = voice_clients.get(guild_id)
    try:
        if voice_client:
            if voice_client.channel != user_voice_channel:
                await voice_client.move_to(user_voice_channel)
        else:
            voice_client = await user_voice_channel.connect()
            voice_clients[guild_id] = voice_client
    except discord.errors.ClientException as e:
        print(f"ClientException: {e}")
        return f"❌ An error occurred: {e}"
    except Exception as e:
        print(f"Unexpected error: {e}")
        return f"❌ An unexpected error occurred: {e}"

    cancel_disconnect_task(guild_id)

    # If this is a normal search (not a direct link):
    if 'list=' not in link and 'watch?v=' not in link and 'youtu.be/' not in link:
        search_query = f"ytsearch:{link}"
        try:
            search_results = ytdl.extract_info(search_query, download=False)['entries']
            if not search_results:
                return "❌ No results found."
            best_result = max(search_results, key=lambda x: x.get('view_count', 0))
            data = best_result
        except Exception as e:
            return f"❌ Error searching for the song: {e}"
    else:
        loop = asyncio.get_event_loop()
        try:
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(link, download=False))
        except Exception as e:
            return f"❌ Error extracting song information: {e}"

    # Single track vs playlist
    if 'entries' not in data:
        song_info = data
        song_info['requester'] = user.mention

        # If we got extra Spotify data, set it
        if extra_meta:
            song_info.update(extra_meta)  # e.g. {"spotify_url": "...", "source": "spotify"}
        else:
            # default to youtube
            song_info['source'] = 'youtube'

        if not voice_client.is_playing() and not voice_client.is_paused():
            client.guilds_data[guild_id]['current_song'] = song_info
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
        # It's a playlist
        playlist_entries = data['entries']
        added_songs = []
        if play_next:
            for entry in reversed(playlist_entries):
                if entry is None:
                    continue
                song_info = entry
                song_info['requester'] = user.mention
                # if we have extra_meta, apply it
                if extra_meta:
                    song_info.update(extra_meta)
                else:
                    song_info['source'] = 'youtube'
                if guild_id not in queues:
                    queues[guild_id] = []
                queues[guild_id].insert(0, song_info)
                added_songs.append(song_info['title'])
            msg = (f"🎶 Added playlist **{data.get('title', 'Unknown playlist')}** "
                   f"with {len(added_songs)} songs to play next.")
        else:
            for entry in playlist_entries:
                if entry is None:
                    continue
                song_info = entry
                song_info['requester'] = user.mention
                if extra_meta:
                    song_info.update(extra_meta)
                else:
                    song_info['source'] = 'youtube'
                if guild_id not in queues:
                    queues[guild_id] = []
                queues[guild_id].append(song_info)
                added_songs.append(song_info['title'])
            msg = (f"🎶 Added playlist **{data.get('title', 'Unknown playlist')}** "
                   f"with {len(added_songs)} songs to the queue.")

        if not voice_client.is_playing() and not voice_client.is_paused():
            await play_next(guild_id)

    stable_message_id = guild_data.get('stable_message_id')
    channel_id = guild_data.get('channel_id')
    if stable_message_id and channel_id:
        ch = client.get_channel(int(channel_id))
        await clear_channel_messages(ch, int(stable_message_id))

    await update_stable_message(guild_id)
    return msg

async def delete_interaction_message(interaction):
    try:
        message = await interaction.original_response()
        await asyncio.sleep(5)
        await message.delete()
    except Exception as e:
        print(f"Error deleting interaction message: {e}")

@client.tree.command(name="play", description="Play a song or add it to the queue")
@is_setup()
@app_commands.describe(link="The URL or name of the song to play")
async def play_command(interaction: discord.Interaction, link: str):
    await interaction.response.defer()
    response_message = await process_play_request(
        interaction.user,
        interaction.guild,
        interaction.channel,
        link,
        interaction=interaction
    )
    if response_message:
        await interaction.followup.send(response_message)
    await delete_interaction_message(interaction)

@client.tree.command(name="playnext", description="Play a song next")
@is_setup()
@app_commands.describe(link="The URL or name of the song to play next")
async def playnext_command(interaction: discord.Interaction, link: str):
    await interaction.response.defer()
    response_message = await process_play_request(
        interaction.user,
        interaction.guild,
        interaction.channel,
        link,
        interaction=interaction,
        play_next=True
    )
    if response_message:
        await interaction.followup.send(response_message)
    await delete_interaction_message(interaction)

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    if not message.guild:
        return
    guild_id = str(message.guild.id)
    guild_data = client.guilds_data.get(guild_id)
    if guild_data:
        channel_id = guild_data.get('channel_id')
        if channel_id and message.channel.id == int(channel_id):
            try:
                await message.delete()
            except discord.Forbidden:
                print(f"Permission error: Cannot delete message {message.id}")
            except discord.HTTPException as e:
                print(f"Failed to delete message {message.id}: {e}")
            response_message = await process_play_request(
                message.author,
                message.guild,
                message.channel,
                message.content
            )
            if response_message:
                sent_msg = await message.channel.send(response_message)
                await asyncio.sleep(5)
                try:
                    await sent_msg.delete()
                except:
                    pass
        else:
            await client.process_commands(message)
    else:
        await client.process_commands(message)

async def disconnect_after_delay(guild_id, delay):
    try:
        await asyncio.sleep(delay)
        voice_client = voice_clients.get(guild_id)
        if voice_client and not voice_client.is_playing():
            await voice_client.disconnect()
            voice_clients.pop(guild_id, None)
            client.guilds_data[guild_id]['disconnect_task'] = None
            await update_stable_message(guild_id)
    except asyncio.CancelledError:
        pass

if __name__ == "__main__":
    client.run(TOKEN)
