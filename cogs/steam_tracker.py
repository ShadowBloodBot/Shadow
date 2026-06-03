import os
import json
import logging
import asyncio
import aiohttp
import discord
from discord.ext import commands, tasks

# ==============================================================================
# TELEMETRY & ENVIRONMENT CONFIGURATION
# ==============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | [ShadowSyn] %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler()]  # Strictly stdout, no local .log files
)
logger = logging.getLogger("ShadowSyn.SteamTracker")

# Railway stateless compliance: Persistent storage must target the mounted volume
PERSIST_PATH = os.getenv("PERSIST_PATH", "/data")
STEAM_STATE_FILE = os.path.join(PERSIST_PATH, "steam_releases.json")
STEAM_TEMP_FILE = os.path.join(PERSIST_PATH, "steam_releases.tmp")

# Standardized UX
SHADOWSYN_COLOR = discord.Color(0x2B0B35)
STEAM_API_URL = "https://store.steampowered.com/api/featuredcategories"

# ==============================================================================
# CORE COG ARCHITECTURE: STEAM RELEASES TRACKER
# ==============================================================================
class SteamReleasesTracker(discord.Cog):
    def __init__(self, bot: discord.Bot):
        self.bot = bot
        self.session = None
        
        # In-memory state tracking
        self.targets = []      # List of Channel/Thread IDs to post in
        self.seen_apps = []    # List of recently posted App IDs to prevent duplicates
        
        # Initialize architecture
        self._ensure_persist_dir()
        self._load_state()
        self.release_scanner.start()

    def cog_unload(self):
        self.release_scanner.cancel()
        if self.session and not self.session.closed:
            asyncio.create_task(self.session.close())
        logger.info("SteamReleasesTracker Cog unloaded. Task loop terminated.")

    # --------------------------------------------------------------------------
    # ATOMIC PERSISTENCE LAYER
    # --------------------------------------------------------------------------
    def _ensure_persist_dir(self):
        if not os.path.exists(PERSIST_PATH):
            try:
                os.makedirs(PERSIST_PATH, exist_ok=True)
                logger.info(f"Created persistence directory at {PERSIST_PATH}")
            except Exception as e:
                logger.error(f"Failed to create persistence directory: {e}")

    def _load_state(self):
        if os.path.exists(STEAM_STATE_FILE):
            try:
                with open(STEAM_STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.targets = data.get("targets", [])
                    self.seen_apps = data.get("seen_apps", [])
                logger.info(f"Loaded {len(self.targets)} targets and {len(self.seen_apps)} seen apps.")
            except Exception as e:
                logger.error(f"Corruption detected in {STEAM_STATE_FILE}, starting fresh. Error: {e}")
                self.targets = []
                self.seen_apps = []
        else:
            logger.info("No existing Steam state file found. Initializing empty state.")
            self.targets = []
            self.seen_apps = []

    def _save_state(self):
        data = {
            "targets": self.targets,
            "seen_apps": self.seen_apps[-1000:]  # Cap at 1000 to prevent unbounded memory scaling
        }
        try:
            # Atomic save: Write to temp, then replace
            with open(STEAM_TEMP_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            os.replace(STEAM_TEMP_FILE, STEAM_STATE_FILE)
            logger.info("Successfully executed atomic save for Steam state.")
        except Exception as e:
            logger.error(f"Failed to save Steam state: {e}")

    # --------------------------------------------------------------------------
    # BACKGROUND TASK LOOP
    # --------------------------------------------------------------------------
    @tasks.loop(minutes=30)
    async def release_scanner(self):
        if not self.targets:
            return  # No point querying API if we have zero configured output channels

        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()

        try:
            async with self.session.get(STEAM_API_URL, timeout=15) as response:
                if response.status != 200:
                    logger.warning(f"Steam API returned non-200 status: {response.status}")
                    return
                
                data = await response.json()
                
        except Exception as e:
            logger.error(f"Network failure while fetching Steam API: {e}")
            return # Silent fail on network errors, will retry next loop iteration

        # Safely extract new releases
        new_releases = data.get("new_releases", {}).get("items", [])
        new_items_found = False

        for item in new_releases:
            app_id = item.get("id")
            if not app_id or app_id in self.seen_apps:
                continue

            # App is newly discovered
            self.seen_apps.append(app_id)
            new_items_found = True
            
            await self._dispatch_release(item)

        if new_items_found:
            self._save_state()

    @release_scanner.before_loop
    async def before_scanner(self):
        await self.bot.wait_until_ready()
        logger.info("Steam API scanner loop primed and running.")

    # --------------------------------------------------------------------------
    # EMBED DISPATCHER
    # --------------------------------------------------------------------------
    async def _dispatch_release(self, item: dict):
        app_id = item.get("id")
        name = item.get("name", "Unknown Title")
        store_url = f"https://store.steampowered.com/app/{app_id}/"
        image_url = item.get("header_image")
        
        # Price formatting
        price_cents = item.get("final_price", 0)
        currency = item.get("currency", "USD")
        if price_cents == 0:
            price_str = "Free / TBD"
        else:
            price_str = f"{(price_cents / 100):.2f} {currency}"

        embed = discord.Embed(
            title=f"🚀 New Steam Release: {name}",
            url=store_url,
            color=SHADOWSYN_COLOR
        )
        if image_url:
            embed.set_image(url=image_url)
        
        embed.add_field(name="Price", value=price_str, inline=True)
        embed.add_field(name="Platforms", value=self._format_platforms(item), inline=True)
        embed.set_footer(text=f"App ID: {app_id} | ShadowSyn Network")

        # Fan out to all registered targets
        targets_to_remove = []
        for target_id in self.targets:
            try:
                channel = self.bot.get_channel(target_id)
                if not channel:
                    channel = await self.bot.fetch_channel(target_id)
                
                await channel.send(embed=embed)
            except discord.Forbidden:
                logger.warning(f"Missing permissions for target {target_id}. Scheduling removal.")
                targets_to_remove.append(target_id)
            except discord.NotFound:
                logger.warning(f"Target {target_id} no longer exists. Scheduling removal.")
                targets_to_remove.append(target_id)
            except Exception as e:
                logger.error(f"Failed to dispatch to {target_id}: {e}")

        # Cleanup dead targets to prevent memory/API waste
        if targets_to_remove:
            for t in targets_to_remove:
                if t in self.targets:
                    self.targets.remove(t)
            self._save_state()

    def _format_platforms(self, item: dict) -> str:
        platforms = []
        if item.get("windows_available"): platforms.append("Windows")
        if item.get("mac_available"): platforms.append("Mac")
        if item.get("linux_available"): platforms.append("Linux")
        return ", ".join(platforms) if platforms else "Unknown"

    # --------------------------------------------------------------------------
    # SLASH COMMAND INTERFACE
    # --------------------------------------------------------------------------
    steam_admin = discord.SlashCommandGroup(
        "steam", 
        "ShadowSyn administrative commands for Steam integrations",
        default_member_permissions=discord.Permissions(administrator=True)
    )

    @steam_admin.command(name="register_thread", description="Bind Steam new releases feed to the current channel or thread.")
    async def register_thread(self, ctx: discord.ApplicationContext):
        target_id = ctx.channel.id
        
        if target_id in self.targets:
            await ctx.respond("This thread/channel is already registered for Steam releases.", ephemeral=True)
            return

        self.targets.append(target_id)
        self._save_state()
        
        embed = discord.Embed(
            title="System Bound",
            description=f"✅ Steam New Releases will now be routed to <#{target_id}>.",
            color=SHADOWSYN_COLOR
        )
        await ctx.respond(embed=embed, ephemeral=True)
        logger.info(f"Target {target_id} bound to Steam tracking by {ctx.author}.")

    @steam_admin.command(name="unregister_thread", description="Unbind Steam new releases feed from the current channel or thread.")
    async def unregister_thread(self, ctx: discord.ApplicationContext):
        target_id = ctx.channel.id
        
        if target_id not in self.targets:
            await ctx.respond("This thread/channel is not currently registered.", ephemeral=True)
            return

        self.targets.remove(target_id)
        self._save_state()
        
        embed = discord.Embed(
            title="System Unbound",
            description=f"⛔ Steam New Releases have been detached from <#{target_id}>.",
            color=SHADOWSYN_COLOR
        )
        await ctx.respond(embed=embed, ephemeral=True)
        logger.info(f"Target {target_id} unbound from Steam tracking by {ctx.author}.")


# ==============================================================================
# ENTRY POINT
# ==============================================================================
def setup(bot: discord.Bot):
    bot.add_cog(SteamReleasesTracker(bot))

if __name__ == "__main__":
    # Provides fully runnable standalone execution if initialized directly
    bot = discord.Bot(intents=discord.Intents.default())
    setup(bot)
    
    @bot.event
    async def on_ready():
        logger.info(f"ShadowSyn Instance Online. Authorized as {bot.user}")

    token = os.getenv("DISCORD_TOKEN")
    if token:
        bot.run(token)
    else:
        logger.error("DISCORD_TOKEN environment variable is not set. Execution aborted.")
