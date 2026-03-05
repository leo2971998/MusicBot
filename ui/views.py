import logging
from typing import Optional

import discord
from discord import ButtonStyle, Embed
from discord.ui import Button, View

from config import PlaybackMode

logger = logging.getLogger(__name__)


class PlaybackModeSelect(discord.ui.Select):
    def __init__(self, *, row: Optional[int] = None, custom_id: Optional[str] = None):
        options = [
            discord.SelectOption(
                label='Normal',
                emoji='🔁',
                value='normal',
                description='Play through queue once',
            ),
            discord.SelectOption(
                label='Repeat Song',
                emoji='🔂',
                value='repeat_one',
                description='Repeat current song',
            ),
            discord.SelectOption(
                label='Repeat Queue',
                emoji='🔄',
                value='repeat_all',
                description='Loop entire queue',
            ),
        ]
        init_kwargs = {
            'placeholder': '🎵 Playback Mode',
            'options': options,
        }
        if row is not None:
            init_kwargs['row'] = row
        if custom_id is not None:
            init_kwargs['custom_id'] = custom_id
        super().__init__(**init_kwargs)

    async def callback(self, interaction: discord.Interaction):
        from bot_state import client, queue_manager
        from ui.embeds import update_stable_message

        if not interaction.guild:
            await interaction.response.send_message('❌ This control can only be used in a server.', ephemeral=True)
            return

        guild_id = str(interaction.guild.id)
        mode_map = {
            'normal': PlaybackMode.NORMAL,
            'repeat_one': PlaybackMode.REPEAT_ONE,
            'repeat_all': PlaybackMode.REPEAT_ALL,
        }

        selected_mode = self.values[0]
        client.playback_modes[guild_id] = mode_map[selected_mode]

        if selected_mode == 'repeat_all':
            current_song = client.guilds_data.get(guild_id, {}).get('current_song')
            if current_song or queue_manager.get_queue_length(guild_id) > 0:
                playlist = []
                if current_song:
                    playlist.append(current_song)
                playlist.extend(queue_manager.get_queue(guild_id))
                queue_manager.repeat_all_playlists[guild_id] = playlist
                logger.info('Saved %s songs for repeat-all mode in guild %s', len(playlist), guild_id)

        mode_labels = {
            'normal': 'Normal',
            'repeat_one': 'Repeat Song',
            'repeat_all': 'Repeat Queue',
        }

        await interaction.response.send_message(
            f'🎵 Playback mode: **{mode_labels[selected_mode]}**',
            ephemeral=True,
        )
        await update_stable_message(guild_id)


class QueuePaginationView(View):
    """Pagination view for browsing large queues."""

    def __init__(self, guild_id: str, current_page: int = 1):
        super().__init__(timeout=60)
        self.guild_id = guild_id
        self.current_page = current_page

    @discord.ui.button(label='◀ Prev', style=ButtonStyle.secondary)
    async def prev_page(self, interaction: discord.Interaction, button: Button):
        try:
            from bot_state import queue_manager

            self.current_page = max(1, self.current_page - 1)
            songs, total_pages, _ = queue_manager.get_queue_page(self.guild_id, self.current_page)

            if not songs and total_pages == 0:
                await interaction.response.send_message('❌ Queue is empty', ephemeral=True)
                return

            embed = self._create_queue_embed_paginated(self.current_page)
            self._update_button_states(total_pages)
            await interaction.response.edit_message(embed=embed, view=self)
        except Exception as error:
            logger.error('Error in prev_page for guild %s: %s', self.guild_id, error)
            await interaction.response.send_message('❌ Error navigating queue', ephemeral=True)

    @discord.ui.button(label='Next ▶', style=ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: Button):
        try:
            from bot_state import queue_manager

            _, total_pages, _ = queue_manager.get_queue_page(self.guild_id, self.current_page)
            if total_pages == 0:
                await interaction.response.send_message('❌ Queue is empty', ephemeral=True)
                return

            self.current_page = min(total_pages, self.current_page + 1)
            embed = self._create_queue_embed_paginated(self.current_page)
            self._update_button_states(total_pages)
            await interaction.response.edit_message(embed=embed, view=self)
        except Exception as error:
            logger.error('Error in next_page for guild %s: %s', self.guild_id, error)
            await interaction.response.send_message('❌ Error navigating queue', ephemeral=True)

    def _update_button_states(self, total_pages: int):
        for item in self.children:
            if isinstance(item, Button):
                if item.label == '◀ Prev':
                    item.disabled = self.current_page <= 1
                elif item.label == 'Next ▶':
                    item.disabled = self.current_page >= total_pages

    def _create_queue_embed_paginated(self, page: int = 1) -> Embed:
        try:
            from bot_state import queue_manager

            songs, total_pages, current_page = queue_manager.get_queue_page(self.guild_id, page, per_page=10)

            def source_icon(song: dict) -> str:
                return '🎧' if song.get('source') == 'spotify' else '📺'

            if songs:
                start_pos = (current_page - 1) * 10
                song_lines = []
                for idx, song in enumerate(songs, start=1):
                    position = start_pos + idx
                    title = song.get('title', 'Unknown')
                    requester = song.get('requester', 'Unknown')
                    link = song.get('spotify_url') or song.get('webpage_url')
                    if link:
                        song_lines.append(
                            f"{position}. {source_icon(song)} **[{title}]({link})** — *{requester}*"
                        )
                    else:
                        song_lines.append(
                            f"{position}. {source_icon(song)} **{title}** — *{requester}*"
                        )
                queue_description = '\n'.join(song_lines)
            else:
                queue_description = 'No songs in the queue.'

            embed = Embed(
                title=f'📜 Queue (Page {current_page}/{total_pages if total_pages > 0 else 1})',
                description=queue_description,
                color=0x1DB954,
            )
            total_songs = queue_manager.get_queue_length(self.guild_id)
            embed.set_footer(
                text=(
                    f'Total songs in queue: {total_songs} | '
                    f'Page {current_page} of {total_pages if total_pages > 0 else 1}'
                )
            )
            return embed
        except Exception as error:
            logger.error('Error creating paginated queue embed for guild %s: %s', self.guild_id, error)
            return Embed(
                title='📜 Queue',
                description='Error loading queue.',
                color=0xFF0000,
            )


class QueueManagementView(View):
    """Ephemeral queue-management controls shown behind the Manage button."""

    def __init__(self, guild_id: str):
        super().__init__(timeout=120)
        self.guild_id = guild_id
        self.add_item(PlaybackModeSelect(row=2))

    async def _safe_response(self, interaction: discord.Interaction, message: str):
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)

    @discord.ui.button(label='➕ Add', style=ButtonStyle.success, row=0)
    async def add_song_button(self, interaction: discord.Interaction, button: Button):
        from ui.modals import AddSongModal

        await interaction.response.send_modal(AddSongModal(preview_mode=False))

    @discord.ui.button(label='⏩ Play Next', style=ButtonStyle.success, row=0)
    async def add_next_song_button(self, interaction: discord.Interaction, button: Button):
        from ui.modals import AddSongModal

        await interaction.response.send_modal(AddSongModal(play_next=True, preview_mode=False))

    @discord.ui.button(label='🔀 Shuffle', style=ButtonStyle.secondary, row=0)
    async def shuffle_button(self, interaction: discord.Interaction, button: Button):
        from bot_state import queue_manager
        from ui.embeds import update_stable_message

        if queue_manager.shuffle_queue(self.guild_id):
            await self._safe_response(interaction, '🔀 Queue shuffled.')
            await update_stable_message(self.guild_id)
            return

        await self._safe_response(interaction, '❌ The queue is empty.')

    @discord.ui.button(label='🗑 Clear', style=ButtonStyle.danger, row=1)
    async def clear_queue_button(self, interaction: discord.Interaction, button: Button):
        from bot_state import queue_manager
        from ui.embeds import update_stable_message

        removed = queue_manager.clear_queue(self.guild_id)
        if removed > 0:
            await self._safe_response(interaction, f'🗑 Cleared {removed} songs from the queue.')
            await update_stable_message(self.guild_id)
            return

        await self._safe_response(interaction, '❌ The queue is already empty.')

    @discord.ui.button(label='↕ Move', style=ButtonStyle.secondary, row=1)
    async def move_button(self, interaction: discord.Interaction, button: Button):
        from ui.modals import MoveSongModal

        await interaction.response.send_modal(MoveSongModal())

    @discord.ui.button(label='❌ Remove', style=ButtonStyle.danger, row=1)
    async def remove_button(self, interaction: discord.Interaction, button: Button):
        from ui.modals import RemoveRangeModal

        await interaction.response.send_modal(RemoveRangeModal())


class MusicControlView(View):
    """Compact persistent music control view for the stable panel."""

    def __init__(self, guild_id: str, timeout: Optional[float] = None):
        super().__init__(timeout=timeout)
        self.guild_id = str(guild_id)
        self.sync_with_guild_state()

    def sync_with_guild_state(self):
        """Rebuild controls based on latest voice/playback state."""
        self.clear_items()
        self._build_controls()

    def _build_controls(self):
        from bot_state import player_manager

        voice_client = player_manager.voice_clients.get(self.guild_id)
        has_active_playback = bool(
            voice_client and (voice_client.is_playing() or voice_client.is_paused())
        )
        is_paused = bool(voice_client and voice_client.is_paused())

        if not has_active_playback:
            toggle_label = '⏯ Play/Pause'
            toggle_style = ButtonStyle.secondary
        elif is_paused:
            toggle_label = '⏯ Play'
            toggle_style = ButtonStyle.success
        else:
            toggle_label = '⏯ Pause'
            toggle_style = ButtonStyle.primary

        self._add_button(
            label=toggle_label,
            style=toggle_style,
            row=0,
            custom_id='toggle_play_pause_button',
            callback=self.toggle_play_pause_button,
        )
        self._add_button(
            label='⏭ Skip',
            style=ButtonStyle.primary,
            row=0,
            custom_id='skip_button',
            callback=self.skip_button,
            disabled=not has_active_playback,
        )
        self._add_button(
            label='⏹ Stop',
            style=ButtonStyle.danger,
            row=0,
            custom_id='stop_button',
            callback=self.stop_button,
            disabled=not has_active_playback,
        )
        self._add_button(
            label='📜 Queue',
            style=ButtonStyle.secondary,
            row=0,
            custom_id='view_queue_button',
            callback=self.view_queue_button,
        )

        self._add_button(
            label='⚙ Manage',
            style=ButtonStyle.secondary,
            row=1,
            custom_id='manage_queue_button',
            callback=self.manage_queue_button,
        )

    def _add_button(self, *, label: str, style: ButtonStyle, row: int, custom_id: str, callback, disabled: bool = False):
        button = Button(
            label=label,
            style=style,
            row=row,
            custom_id=custom_id,
            disabled=disabled,
        )
        button.callback = callback
        self.add_item(button)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item):
        logger.exception('Interaction error in guild %s for item %s', interaction.guild_id, getattr(item, 'custom_id', 'unknown'))

        message = f'❌ An error occurred while processing your request: {error}'
        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except Exception:
            logger.exception('Failed to send interaction error message')

        try:
            from ui.embeds import update_stable_message

            guild_id = self._resolve_guild_id(interaction)
            await update_stable_message(guild_id)
        except Exception:
            logger.exception('Failed to refresh stable message after interaction error')

    def _resolve_guild_id(self, interaction: discord.Interaction) -> str:
        if interaction.guild:
            return str(interaction.guild.id)
        return self.guild_id

    async def _safe_interaction_response(
        self,
        interaction: discord.Interaction,
        message: str,
        *,
        ephemeral: bool = True,
    ) -> None:
        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=ephemeral)
            else:
                await interaction.response.send_message(message, ephemeral=ephemeral)
        except Exception:
            logger.exception('Failed sending interaction response in guild %s', interaction.guild_id)

    async def toggle_play_pause_button(self, interaction: discord.Interaction):
        from bot_state import player_manager
        from ui.embeds import update_stable_message

        guild_id = self._resolve_guild_id(interaction)
        voice_client = player_manager.voice_clients.get(guild_id)

        if not voice_client:
            await self._safe_interaction_response(interaction, '❌ The bot is not connected to a voice channel.')
            return

        if voice_client.is_playing():
            voice_client.pause()
            await self._safe_interaction_response(interaction, '⏸ Paused the music.')
        elif voice_client.is_paused():
            voice_client.resume()
            await self._safe_interaction_response(interaction, '▶ Resumed the music.')
        else:
            await self._safe_interaction_response(interaction, '❌ Nothing is currently playing.')

        await update_stable_message(guild_id)

    async def skip_button(self, interaction: discord.Interaction):
        from bot_state import client, player_manager
        from ui.embeds import update_stable_message
        from utils.vote_manager import VoteManager

        guild_id = self._resolve_guild_id(interaction)
        user_id = interaction.user.id

        voice_client = player_manager.voice_clients.get(guild_id)
        if not voice_client or not (voice_client.is_playing() or voice_client.is_paused()):
            await self._safe_interaction_response(interaction, '❌ Nothing is playing.')
            return

        if not interaction.user.voice or not interaction.user.voice.channel:
            await self._safe_interaction_response(interaction, '❌ You must be in the voice channel to skip.')
            return

        if interaction.user.voice.channel != voice_client.channel:
            await self._safe_interaction_response(
                interaction,
                f'❌ You must be in {voice_client.channel.mention} to skip.',
            )
            return

        guild_data = client.guilds_data.get(guild_id, {})
        if VoteManager.is_song_requestor(guild_data, user_id):
            voice_client.stop()
            VoteManager.reset_votes(guild_data)
            await self._safe_interaction_response(interaction, '⏭ Song skipped by requester.')
            await update_stable_message(guild_id)
            return

        if not VoteManager.add_vote(guild_data, user_id):
            await self._safe_interaction_response(interaction, '❌ You have already voted to skip this song.')
            return

        if VoteManager.check_vote_threshold(guild_data, voice_client.channel):
            voice_client.stop()
            VoteManager.reset_votes(guild_data)
            await self._safe_interaction_response(interaction, '⏭ Vote threshold reached. Skipping song.')
        else:
            vote_status = VoteManager.get_vote_status(guild_data, voice_client.channel)
            progress_bar = (
                '█' * vote_status['current_votes']
                + '░' * (vote_status['required_votes'] - vote_status['current_votes'])
            )
            await self._safe_interaction_response(
                interaction,
                (
                    f"🗳 Vote added: **{vote_status['current_votes']}/{vote_status['required_votes']}** "
                    f"to skip.\n`{progress_bar}` {vote_status['percentage']}%"
                ),
            )

        await update_stable_message(guild_id)

    async def stop_button(self, interaction: discord.Interaction):
        from bot_state import client, player_manager
        from ui.embeds import update_stable_message

        guild_id = self._resolve_guild_id(interaction)
        await player_manager.disconnect_voice_client(guild_id)

        if guild_id in client.guilds_data:
            client.guilds_data[guild_id]['current_song'] = None
        client.playback_modes[guild_id] = PlaybackMode.NORMAL

        await self._safe_interaction_response(interaction, '⏹ Stopped playback and disconnected.')
        await update_stable_message(guild_id)

    async def view_queue_button(self, interaction: discord.Interaction):
        from bot_state import queue_manager

        guild_id = self._resolve_guild_id(interaction)
        queue_length = queue_manager.get_queue_length(guild_id)
        if queue_length == 0:
            await self._safe_interaction_response(interaction, '📜 The queue is empty.')
            return

        view = QueuePaginationView(guild_id, current_page=1)
        embed = view._create_queue_embed_paginated(page=1)
        _, total_pages, _ = queue_manager.get_queue_page(guild_id, 1)
        view._update_button_states(total_pages)

        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def manage_queue_button(self, interaction: discord.Interaction):
        from bot_state import queue_manager

        guild_id = self._resolve_guild_id(interaction)
        queue_length = queue_manager.get_queue_length(guild_id)
        manage_view = QueueManagementView(guild_id)
        message = (
            '⚙ Queue Manager\n'
            'Use this menu for queue edits, add/play-next, and playback mode.\n'
            f'Queue: **{queue_length} songs**'
        )

        if interaction.response.is_done():
            await interaction.followup.send(message, view=manage_view, ephemeral=True)
        else:
            await interaction.response.send_message(message, view=manage_view, ephemeral=True)
