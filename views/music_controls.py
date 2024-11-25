# views/music_controls.py

import discord
from discord.ui import View, Button
from discord import ButtonStyle

class MusicControlView(View):
    def __init__(self, queue, music_cog):
        super().__init__(timeout=None)
        self.queue = queue
        self.music_cog = music_cog  # Reference to the Music cog
        self.generate_remove_buttons()

    @discord.ui.button(label='⏸️ Pause', style=ButtonStyle.primary)
    async def pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.music_cog.pause_command(interaction)

    @discord.ui.button(label='▶️ Resume', style=ButtonStyle.primary)
    async def resume_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.music_cog.resume_command(interaction)

    @discord.ui.button(label='⏭️ Skip', style=ButtonStyle.primary)
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = str(interaction.guild.id)
        voice_client = self.music_cog.voice_clients.get(guild_id)
        if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
            voice_client.stop()

            # Cancel the progress updater task
            progress_task = self.music_cog.client.guilds_data[guild_id].get('progress_task')
            if progress_task:
                progress_task.cancel()
                self.music_cog.client.guilds_data[guild_id]['progress_task'] = None

            await interaction.response.send_message('⏭️ Skipped the song.', ephemeral=True)
            # No need to call play_next here; it will be called automatically by after_playing
        else:
            await interaction.response.send_message('❌ Nothing is playing.', ephemeral=True)
        await self.music_cog.update_stable_message(guild_id)

    @discord.ui.button(label='⏹️ Stop', style=ButtonStyle.primary)
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.music_cog.stop_command(interaction)

    @discord.ui.button(label='🗑️ Clear Queue', style=ButtonStyle.danger)
    async def clear_queue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.music_cog.clear_queue_command(interaction)

    def generate_remove_buttons(self):
        max_components = 25 - len(self.children)  # Adjust for existing buttons
        for idx, song in enumerate(self.queue):
            if len(self.children) >= max_components:
                break  # Cannot add more components
            button = Button(
                label=f"❌ Remove {idx + 1}",
                style=ButtonStyle.secondary
            )
            button.callback = self.generate_remove_callback(idx)
            self.add_item(button)

    def generate_remove_callback(self, index):
        async def remove_song(interaction: discord.Interaction):
            guild_id = str(interaction.guild.id)
            queue = self.music_cog.queues.get(guild_id)
            if queue and 0 <= index < len(queue):
                removed_song = queue.pop(index)
                await interaction.response.send_message(f'❌ Removed **{removed_song["title"]}** from the queue.', ephemeral=True)
            else:
                await interaction.response.send_message('❌ Invalid song index.', ephemeral=True)
            await self.music_cog.update_stable_message(guild_id)
        return remove_song
