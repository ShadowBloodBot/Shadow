# bot.py
import os
import discord
from discord.ext import commands

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise SystemExit("❌ DISCORD_TOKEN is not set.")

# --- SET UP INTENTS ---
intents = discord.Intents.default()
intents.guilds = True
intents.voice_states = True
intents.members = True
intents.message_content = True

bot = discord.Bot(intents=intents)

# --- LOAD COGS (MODULES) ---
cogs_list = [
    "cogs.utility",
    "cogs.war",
    "cogs.music",
    "cogs.casino",
    "cogs.tower",
    "cogs.jtc",
    "cogs.audit_logs",
    "cogs.tts"  # <-- Added the new TTS module here
]

for cog in cogs_list:
    try:
        bot.load_extension(cog)
        print(f"✅ Loaded {cog}")
    except Exception as e:
        print(f"❌ Failed to load {cog}: {e}")

@bot.event
async def on_ready():
    print(f"🚀 Master Bot is online! Logged in as {bot.user}")

if __name__ == "__main__":
    bot.run(TOKEN)
