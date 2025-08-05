import os
import discord
import asyncio
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

# 🔧 Internal imports (ensure these files exist in same folder)
from ui import ModerationControlView
from events import EventHandlers
from scan import Scan
from storage import init_db
from log_utils import setup_logging

# 🧠 Discord intents
intents = discord.Intents.all()

# 🎮 Define the ShadowBot class
class ShadowBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.logger = setup_logging()
        init_db()  # 📦 Initialize persistent storage
        self.synced = False  # Slash command sync tracker

    async def setup_hook(self):
        # 🎮 Load persistent views
        try:
            self.add_view(ModerationControlView())
        except Exception as e:
            print(f"[ERROR] Loading ModerationControlView: {e}")

        # 🧠 Register event handler
        self.add_listener(EventHandlers(self).on_ready, name="on_ready")

        # ⚙️ Register application slash command
        try:
            self.tree.add_command(Scan().scan_members)
        except Exception as e:
            print(f"[ERROR] Registering /scan: {e}")

        # 🔁 Sync commands globally once
        if not self.synced:
            try:
                await self.tree.sync()
                self.synced = True
                print("✅ Slash commands synced globally.")
            except Exception as e:
                print(f"[SYNC ERROR] Could not sync commands: {e}")

# 🧪 Load environment and token
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# 🔐 Entry point
if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("❌ DISCORD_TOKEN not set in environment variables.")

    bot = ShadowBot()

    try:
        bot.run(TOKEN)
    except Exception as e:
        print(f"[FATAL ERROR] Bot failed to start: {e}")
