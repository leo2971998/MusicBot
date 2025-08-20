import discord
from discord.ext import commands

from managers.data_manager import GuildDataManager
from managers.player_manager import PlayerManager
from managers.queue_manager import QueueManager
from managers.health_monitor import HealthMonitor

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
client = commands.Bot(command_prefix='!', intents=intents)

# Managers
data_manager = GuildDataManager()
player_manager = PlayerManager()
queue_manager = QueueManager()

# Health monitoring system
health_monitor = HealthMonitor(client, player_manager, queue_manager, data_manager)

# In-memory data
client.guilds_data = {}
client.playback_modes = {}
