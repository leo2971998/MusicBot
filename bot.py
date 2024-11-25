# bot.py

import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import asyncio

# Load the environment variables
load_dotenv()
TOKEN = os.getenv("discord_token") or "YOUR_DISCORD_BOT_TOKEN"

# Set up bot intents
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

client = commands.Bot(command_prefix=".", intents=intents)

async def load_cogs():
    await client.load_extension("cogs.music")
    await client.load_extension("cogs.events")

@client.event
async def on_ready():
    await client.tree.sync()
    print(f'{client.user} is now jamming!')

async def main():
    async with client:
        await load_cogs()
        await client.start(TOKEN)

# Entry point
if __name__ == "__main__":
    asyncio.run(main())
