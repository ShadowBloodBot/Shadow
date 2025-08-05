import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from ui import ModerationControlView
from scan import Scan
from logging import getLogger
from log_utils import setup_logging

# Load .env and get token
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
APPLICATION_ID = os.getenv("APPLICATION_ID")

# Intents
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents, application_id=APPLICATION_ID)

# Set up logging
logger = getLogger("shadowbot")
setup_logging(logger)

@bot.event
async def on_ready():
    print(f"[READY] Logged in as {bot.user} (ID: {bot.user.id})")
    print("------")

async def setup_hook():
    # Register all persistent views
    try:
        view = ModerationControlView()
        for item in view.children:
            if isinstance(item, discord.ui.Select) or isinstance(item, discord.ui.Button):
                if not item.custom_id:
                    item.custom_id = f"shadow_{item.__class__.__name__}"
        bot.add_view(view)
    except Exception as e:
        logger.error(f"[ERROR] Failed to register persistent view: {e}")

    # Load Cogs
    try:
        await bot.add_cog(Scan(bot))
    except Exception as e:
        logger.error(f"[ERROR] Failed to load Scan cog: {e}")

    # Sync commands globally
    try:
        await bot.tree.sync()
        print("[SYNC] Slash commands synced globally.")
    except Exception as e:
        logger.error(f"[ERROR] Slash command sync failed: {e}")

# Register setup_hook
bot.setup_hook = setup_hook

# Run bot
if __name__ == "__main__":
    if not TOKEN:
        raise ValueError("DISCORD_TOKEN not found in environment variables.")
    try:
        bot.run(TOKEN)
    except Exception as e:
        logger.error(f"[CRITICAL] Bot failed to start: {e}")
