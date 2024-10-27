import discord
from discord.ext import commands
import os
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("discord_token")

# Define intents and enable necessary ones, such as message content and guilds.
intents = discord.Intents.default()
intents.message_content = True  # Enables message content access

# Pass intents as an argument
client = commands.Bot(command_prefix=".", intents=intents)

@client.event
async def on_ready():
    print(f'Logged in as {client.user}')

client.run(TOKEN)
