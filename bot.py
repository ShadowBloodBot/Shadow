import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

from ui import ShadowControlPanel
from moderation import handle_mass_action, handle_shadowmute
from storage import log_audit
from analytics import post_webhook_log
from role_manager import RoleManagerView
from user_panel import SearchUserModal
from filters import get_flagged_users
from events import EventHandlers

load_dotenv()
intents = discord.Intents.all()

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} slash commands.")
    except Exception as e:
        print(f"❌ Failed to sync commands: {e}")

async def main():
    async with bot:
        await bot.add_cog(EventHandlers(bot))
        await bot.load_extension("scan_command")
        await bot.start(os.getenv("DISCORD_TOKEN"))

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
