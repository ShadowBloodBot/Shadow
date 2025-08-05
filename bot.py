import discord
import os
from discord.ext import commands
from dotenv import load_dotenv

from ui import ModerationControlView
from scan import Scan
from events import EventHandlers
from mod_commands import ModCommands
from storage import init_db

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"[READY] Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"[SYNC] Synced {len(synced)} commands.")
    except Exception as e:
        print(f"[ERROR] Sync failed: {e}")
    bot.add_view(ModerationControlView())
    init_db()

async def setup_hook():
    await bot.add_cog(Scan(bot))
    await bot.add_cog(EventHandlers(bot))
    await bot.add_cog(ModCommands(bot))

bot.setup_hook = setup_hook

if __name__ == "__main__":
    bot.run(TOKEN)
