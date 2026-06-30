import asyncio
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
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._commands_synced = False

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

from cogs.guild_registry import (  # noqa: E402
    REGISTERED_GUILD_IDS,
    SHADOW_BACKUP_GUILD_ID,
    SHADOW_MAIN_GUILD_ID,
    load_registry,
)

TARGET_GUILD_ID = SHADOW_MAIN_GUILD_ID

# ==========================================
# MODULE INTEGRATION (COGS)
# ==========================================
cogs_list = [
    "cogs.utility",
    "cogs.war",
    "cogs.casino",
    "cogs.jtc",
    "cogs.audit_logs",
    "cogs.content_filter",
    "cogs.tts",
    "cogs.music",
    "cogs.tracker",
    "cogs.steam_tracker",
    "cogs.clips",
    "cogs.steam_codes",
    "cogs.member_utils",
    "cogs.admin_secure",
    "cogs.member_backup",
    "cogs.hub",
    "cogs.game_roles",
    "cogs.welcome",
    "cogs.sand",
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

    load_registry(force=True)
    connected = {g.id for g in bot.guilds}
    for gid, label in (
        (SHADOW_MAIN_GUILD_ID, "ShadowMain"),
        (SHADOW_BACKUP_GUILD_ID, "ShadowBackup"),
    ):
        status = "online" if gid in connected else "MISSING"
        logger.info("Guild %s (%s): %s", label, gid, status)

    for cmd in bot.pending_application_commands:
        subs = [getattr(s, "name", "?") for s in (getattr(cmd, "subcommands", None) or [])]
        if subs:
            logger.info(f"App command: /{cmd.name} → {', '.join(subs)}")
        else:
            logger.info(f"App command: /{cmd.name}")

    if not bot._commands_synced:
        bot._commands_synced = True
        try:
            await bot.sync_commands(guild_ids=REGISTERED_GUILD_IDS)
            logger.info("Guild slash sync complete for ShadowMain + ShadowBackup")
        except discord.errors.Forbidden:
            logger.error(
                "403 during guild slash sync — re-invite bot with applications.commands scope"
            )
        except Exception as e:
            logger.error(f"Guild slash sync failed: {e}")


@bot.event
async def on_application_command_error(ctx: discord.ApplicationContext, error: Exception):
    cmd_name = ctx.command.name if ctx.command else "?"
    logger.exception("Slash command failed: /%s", cmd_name)
    message = f"⚠️ Command error: {error}"
    try:
        if not ctx.response.is_done():
            await ctx.respond(message, ephemeral=True)
        else:
            await ctx.followup.send(message, ephemeral=True)
    except Exception:
        pass


# ==========================================
# EXECUTION & NETWORK PATCHING
# ==========================================
if __name__ == "__main__":
    # Windows: use SelectorEventLoop so asyncio.get_event_loop() works for local dev
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

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
