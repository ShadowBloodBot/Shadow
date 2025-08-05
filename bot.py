# 🔹 1. Imports
import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
from config import SHADOW_ROLE_ID
from ui import ShadowControlPanel
from moderation import auto_flag_new_members
from storage import save_flags, load_flags
from filters import get_severity_score

# 🔹 2. Init
load_dotenv()
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# 🔹 3. Helper
def has_shadow_access(user: discord.Member) -> bool:
    allowed_names = ["Mover & Shaker"]
    return SHADOW_ROLE_ID in [r.id for r in user.roles] or any(r.name in allowed_names for r in user.roles)

# 🔹 4. Events
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"🌐 Synced {len(synced)} global slash command(s).")
    except Exception as e:
        print(f"❌ Slash sync failed: {e}")

# 🔹 5. Slash Commands
@bot.tree.command(name="scan", description="Scan all members and flag suspicious ones")
async def scan(interaction: discord.Interaction):
    # entire scan function from earlier
    ...

@bot.tree.command(name="shadow", description="Open the Shadow Moderation Panel")
async def shadow(interaction: discord.Interaction):
    ...

# 🔹 6. Runtime
if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if token:
        bot.run(token)
    else:
        print("❌ DISCORD_TOKEN not found in environment.")
