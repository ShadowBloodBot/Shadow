# bot.py

import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

from ui import ModerationControlView
from log_utils import setup_logging

from storage import init_db
from events import EventHandlers
from scan_command import Scan

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")
APPLICATION_ID = os.getenv("APPLICATION_ID")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents, application_id=APPLICATION_ID)

@bot.event
async def on_ready():
    print(f"[✅] Logged in as {bot.user} ({bot.user.id})")

async def setup_hook():
    setup_logging()
    init_db()
    await bot.add_cog(EventHandlers(bot))
    await bot.add_cog(Scan(bot))
    bot.add_view(ModerationControlView())  # Persistent View

bot.setup_hook = setup_hook

@bot.tree.command(name="shadow", description="Open the moderation panel")
async def shadow(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)

    await interaction.response.send_message(
        content=f"👮 Moderation Panel for <@{interaction.user.id}>",
        view=ModerationControlView(),
        ephemeral=True
    )

bot.run(TOKEN)
