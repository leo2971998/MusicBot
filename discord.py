import discord
from discord.ext import commands
import os
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("discord_token")

client = commands.Bot(command_prefix=".")

@client.event
async def on_ready():
    print(f'Logged in as {client.user}')

client.run(TOKEN)
