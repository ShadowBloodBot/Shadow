# bot.py
import os
import socket

# ==========================================
# --- RAILWAY IPV6 NETWORK PATCH ---
# Force Python to only use IPv4. This bypasses Railway's broken IPv6 UDP routing
# which causes Discord Voice WebSockets to silently drop and ghost.
old_getaddrinfo = socket.getaddrinfo
def new_getaddrinfo(*args, **kwargs):
    responses = old_getaddrinfo(*args, **kwargs)
    return [response for response in responses if response[0] == socket.AF_INET]
socket.getaddrinfo = new_getaddrinfo
# ==========================================

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
    "cogs.casino",
    "cogs.tower",
    "cogs.jtc",
    "cogs.audit_logs",
    "cogs.tts"
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
