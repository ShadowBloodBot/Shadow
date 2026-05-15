# bot.py
import os
import socket
import discord

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
# Notice: "cogs.music" is removed to keep the Voice Gateway 100% dedicated and stable for TTS.
cogs_list = [
    "cogs.utility",
    "cogs.war",
    "cogs.casino",
    "cogs.spire",
    "cogs.jtc",
    "cogs.audit_logs",
    "cogs.tts",
    "cogs.tracker"
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
    # ==========================================
    # --- RAILWAY IPV4 NETWORK PATCH ---
    # Guarded block: Forces Railway to route UDP audio packets over IPv4.
    # Placed at the very bottom to prevent infinite import recursion crashes!
    if not hasattr(socket, "_ipv4_patched"):
        old_getaddrinfo = socket.getaddrinfo
        def new_getaddrinfo(*args, **kwargs):
            responses = old_getaddrinfo(*args, **kwargs)
            return [response for response in responses if response[0] == socket.AF_INET]
        socket.getaddrinfo = new_getaddrinfo
        socket._ipv4_patched = True
    # ==========================================
    
    bot.run(TOKEN)
