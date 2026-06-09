import os
import sys
import socket
import logging
import discord

# ==========================================
# TELEMETRY & LOGGING
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("ShadowSyn.Core")

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    logger.critical("DISCORD_TOKEN is not set. Halting container.")
    sys.exit(1)

# ==========================================
# INTENTS CONFIGURATION
# ==========================================
intents = discord.Intents.default()
intents.guilds = True
intents.voice_states = True
intents.members = True
intents.message_content = True

# ==========================================
# CORE BOT ARCHITECTURE
# ==========================================
class ShadowBot(discord.Bot):
    """
    ShadowSyn Master Instance
    Engineered with armored gateway synchronization to prevent 403 fatal lockups.
    """
    async def sync_commands(self, **kwargs) -> None:
        """
        Overrides the native Py-cord sync_commands method to intercept 
        HTTP 403 Forbidden errors during application command registration.
        """
        try:
            logger.info("Initiating application command synchronization...")
            await super().sync_commands(**kwargs)
            logger.info("Slash commands successfully synchronized with Discord Gateway.")
        except discord.errors.Forbidden:
            logger.error(
                "CRITICAL INFRASTRUCTURE ERROR: 403 Forbidden (50001: Missing Access)\n"
                "The bot container cannot register Slash Commands.\n"
                "CAUSE: The bot was invited to the guild without the 'applications.commands' OAuth2 scope.\n"
                "RESOLUTION: Kick the bot and re-invite using a URL with BOTH 'bot' and 'applications.commands' scopes checked."
            )
        except Exception as e:
            logger.error(f"Unhandled exception during command sync: {e}")

bot = ShadowBot(intents=intents)

# ==========================================
# MODULE INTEGRATION (COGS)
# ==========================================
cogs_list = [
    "cogs.utility",
    "cogs.war",
    "cogs.casino",
    "cogs.jtc",
    "cogs.audit_logs",
    "cogs.tts",
    "cogs.tracker",
    "cogs.steam_tracker",
    "cogs.invest_bot",
    "cogs.admin_secure",
    "cogs.suburbs_database",
]

for cog in cogs_list:
    try:
        bot.load_extension(cog)
        logger.info(f"Loaded extension: {cog}")
    except Exception as e:
        logger.error(f"Failed to load extension {cog}: {e}")

# ==========================================
# EVENT LISTENERS
# ==========================================
@bot.event
async def on_ready():
    logger.info(f"Master Bot is online! Logged in as {bot.user}")
    logger.info(f"Connected to {len(bot.guilds)} guild(s).")

# ==========================================
# EXECUTION & NETWORK PATCHING
# ==========================================
if __name__ == "__main__":
    # --- RAILWAY IPV4 NETWORK PATCH ---
    # Guarded block: Forces Railway to route UDP audio packets over IPv4.
    # Essential for FFmpeg/Opus payload delivery on Railway's IPv6-heavy network.
    if not hasattr(socket, "_ipv4_patched"):
        old_getaddrinfo = socket.getaddrinfo
        def new_getaddrinfo(*args, **kwargs):
            responses = old_getaddrinfo(*args, **kwargs)
            return [response for response in responses if response[0] == socket.AF_INET]
        socket.getaddrinfo = new_getaddrinfo
        socket._ipv4_patched = True
        logger.info("Railway IPv4 socket patch applied to local execution context.")
    
    logger.info("Booting ShadowSyn...")
    bot.run(TOKEN)
