# cogs/events.py

import discord
from discord.ext import commands

class Events(commands.Cog):
    def __init__(self, client):
        self.client = client

    # Example event listener
    @commands.Cog.listener()
    async def on_member_join(self, member):
        # Handle the event
        print(f"{member.name} has joined the server.")

async def setup(client):
    await client.add_cog(Events(client))
