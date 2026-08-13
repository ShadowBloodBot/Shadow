import os
import json
import logging
import asyncio
import aiohttp
import discord
from discord.ext import commands, tasks

from cogs.guild_registry import REGISTERED_GUILD_IDS, is_registered_guild

# ==============================================================================
# TELEMETRY & ENVIRONMENT CONFIGURATION
# ==============================================================================
logger = logging.getLogger("ShadowSyn.SteamTracker")

PERSIST_PATH = os.getenv("PERSIST_PATH", "/data")
STEAM_STATE_FILE = os.path.join(PERSIST_PATH, "steam_releases.json")
STEAM_TEMP_FILE = os.path.join(PERSIST_PATH, "steam_releases.tmp")

SHADOWSYN_COLOR = discord.Color(0x2B0B35)
STEAM_API_URL = "https://store.steampowered.com/api/featuredcategories"
STEAM_APP_DETAILS_URL = "https://store.steampowered.com/api/appdetails"

# ==============================================================================
# CORE COG ARCHITECTURE: STEAM RELEASES TRACKER
# ==============================================================================
class SteamReleasesTracker(discord.Cog):
    def __init__(self, bot: discord.Bot):
        self.bot = bot
        self.session = None
        
        self.targets = {}      # Dictionary tracking {channel_id_str: filter_string_or_None}
        self.seen_apps = []
        self._last_saved_fingerprint: str | None = None

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
                    
                    raw_targets = data.get("targets", {})
                    if isinstance(raw_targets, list):
                        self.targets = {str(t): None for t in raw_targets}
                        self._save_state() 
                    else:
                        self.targets = raw_targets
                        
                    self.seen_apps = data.get("seen_apps", [])
                self._last_saved_fingerprint = self._state_fingerprint()
                logger.info(f"Loaded {len(self.targets)} targets and {len(self.seen_apps)} seen apps.")
            except Exception as e:
                logger.error(f"Corruption detected in {STEAM_STATE_FILE}, starting fresh. Error: {e}")
                self.targets = {}
                self.seen_apps = []
        else:
            logger.info("No existing Steam state file found. Initializing empty state.")
            self.targets = {}
            self.seen_apps = []

    def _state_fingerprint(self) -> str:
        capped = self.seen_apps[-1000:]
        return json.dumps(
            {"targets": self.targets, "seen_apps": capped},
            sort_keys=True,
            separators=(",", ":"),
        )

    def _save_state(self) -> bool:
        """Sync disk write — must only run off the event loop (via to_thread)."""
        fingerprint = self._state_fingerprint()
        if fingerprint == self._last_saved_fingerprint:
            return False
        data = {
            "targets": self.targets,
            "seen_apps": self.seen_apps[-1000:],
        }
        try:
            with open(STEAM_TEMP_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, separators=(",", ":"))
            os.replace(STEAM_TEMP_FILE, STEAM_STATE_FILE)
            self._last_saved_fingerprint = fingerprint
            logger.info("Successfully executed atomic save for Steam state.")
            return True
        except Exception as e:
            logger.error(f"Failed to save Steam state: {e}")
            return False

    async def _save_state_async(self) -> None:
        """Non-blocking persist — keeps Discord heartbeats/interactions alive."""
        await asyncio.to_thread(self._save_state)

    # --------------------------------------------------------------------------
    # BACKGROUND TASK LOOP
    # --------------------------------------------------------------------------
    @tasks.loop(minutes=30)
    async def release_scanner(self):
        if not self.targets:
            return  

        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()

        try:
            async with self.session.get(f"{STEAM_API_URL}?cc=au", timeout=15) as response:
                if response.status != 200:
                    logger.warning(f"Steam API returned non-200 status: {response.status}")
                    return
                
                data = await response.json()
                
        except Exception as e:
            logger.error(f"Network failure while fetching Steam API: {e}")
            return 

        new_releases = data.get("new_releases", {}).get("items", [])
        new_items_found = False

        for item in new_releases:
            app_id = item.get("id")
            if not app_id or app_id in self.seen_apps:
                continue

            self.seen_apps.append(app_id)
            new_items_found = True
            
            # Initialize classification arrays
            item["genres"] = []
            item["categories"] = []

            try:
                async with self.session.get(f"{STEAM_APP_DETAILS_URL}?appids={app_id}&cc=au", timeout=15) as detail_res:
                    if detail_res.status == 200:
                        detail_data = await detail_res.json()
                        app_data = detail_data.get(str(app_id), {}).get("data")
                        
                        if app_data:
                            # Extract explicit currency information
                            price_overview = app_data.get("price_overview")
                            if price_overview:
                                item["final_price"] = price_overview.get("final")
                                item["currency"] = price_overview.get("currency")
                            elif app_data.get("is_free"):
                                item["final_price"] = 0
                                item["currency"] = "AUD"
                            
                            # Extract primary classification metadata arrays
                            item["genres"] = [g.get("description", "") for g in app_data.get("genres", [])]
                            item["categories"] = [c.get("description", "") for c in app_data.get("categories", [])]
            except Exception as e:
                logger.error(f"Failed secondary appdetails fetch for {app_id}: {e}")
            
            await self._dispatch_release(item)
            await asyncio.sleep(1.5)  # Throttling metric to stay within API bounds

        if new_items_found:
            await self._save_state_async()

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
        
        genres = item.get("genres", [])
        categories = item.get("categories", [])
        
        # Merge both metadata datasets to evaluate user taxonomy filters accurately
        combined_metadata = [meta.lower() for meta in (genres + categories) if meta]

        price_cents = item.get("final_price", 0)
        currency = item.get("currency", "AUD")
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
        
        if genres:
            embed.add_field(name="Genres", value=", ".join(genres[:5]), inline=False)
        if categories:
            embed.add_field(name="Features", value=", ".join(categories[:5]), inline=False)
            
        embed.set_footer(text=f"App ID: {app_id} | ShadowSyn Network")

        # Exclusive routing: catch-all targets always receive the payload, while
        # competing filtered targets are scored so only the single best match wins.
        catch_all_targets = []
        scored_targets = []  # (score_tuple, target_id_str)

        for target_id_str, metadata_filter in self.targets.items():
            if not metadata_filter:
                catch_all_targets.append(target_id_str)
                continue

            required_tags = self._parse_filter(metadata_filter)
            if not required_tags:
                catch_all_targets.append(target_id_str)
                continue

            if not self._filter_matches(required_tags, combined_metadata):
                continue

            scored_targets.append((self._score_match(item, required_tags), target_id_str))

        recipients = list(catch_all_targets)
        if scored_targets:
            # Highest score wins; ties fall through to the tuple's secondary ordering.
            scored_targets.sort(key=lambda entry: entry[0], reverse=True)
            winner_id_str = scored_targets[0][1]
            if winner_id_str not in recipients:
                recipients.append(winner_id_str)

        targets_to_remove = []
        for target_id_str in recipients:
            target_id = int(target_id_str)

            try:
                channel = self.bot.get_channel(target_id)
                if not channel:
                    channel = await self.bot.fetch_channel(target_id)
                
                await channel.send(embed=embed)
            except discord.Forbidden:
                logger.warning(f"Missing permissions for target {target_id}. Scheduling removal.")
                targets_to_remove.append(target_id_str)
            except discord.NotFound:
                logger.warning(f"Target {target_id} no longer exists. Scheduling removal.")
                targets_to_remove.append(target_id_str)
            except Exception as e:
                logger.error(f"Failed to dispatch to {target_id}: {e}")

        if targets_to_remove:
            for t in targets_to_remove:
                if t in self.targets:
                    del self.targets[t]
            await self._save_state_async()

    def _parse_filter(self, metadata_filter: str) -> list:
        # Split the user's input by commas to allow multi-tag targeting
        return [tag.strip().lower() for tag in metadata_filter.split(",") if tag.strip()]

    def _filter_matches(self, required_tags: list, combined_metadata: list) -> bool:
        # Verify that ALL required tags exist in the game's combined metadata
        return all(
            any(req_tag in meta for meta in combined_metadata)
            for req_tag in required_tags
        )

    def _score_match(self, item: dict, required_tags: list) -> tuple:
        # Ranking key for exclusive routing (higher tuple wins):
        #  1. Lead alignment: game's first genre matches the filter's lead tag
        #  2. Category hits: feature-tag matches (PvP/Co-op) outrank genre-only hits
        #  3. Specificity: a filter with more required tags is more targeted
        genres = [g.lower() for g in item.get("genres", []) if g]
        categories = [c.lower() for c in item.get("categories", []) if c]

        lead_tag = required_tags[0] if required_tags else ""
        lead_genre_aligned = 1 if (genres and lead_tag and lead_tag in genres[0]) else 0

        category_hits = sum(
            1 for req_tag in required_tags
            if any(req_tag in cat for cat in categories)
        )

        return (lead_genre_aligned, category_hits, len(required_tags))

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
        guild_ids=REGISTERED_GUILD_IDS,
        default_member_permissions=discord.Permissions(administrator=True)
    )

    @steam_admin.command(name="register_thread", description="Bind Steam new releases feed to the current channel or thread.")
    async def register_thread(
        self, 
        ctx: discord.ApplicationContext,
        genre_filter: discord.Option(str, "Filter by genre/feature (e.g., Survival, Co-op, PvP)", required=False, default=None)
    ):
        target_id = str(ctx.channel.id)
        
        self.targets[target_id] = genre_filter
        await self._save_state_async()

        msg = f"✅ Steam New Releases will now be routed to <#{target_id}>."
        if genre_filter:
            msg += f"\n🎯 Metadata Filter Active: **{genre_filter}**"
            
        embed = discord.Embed(
            title="System Bound",
            description=msg,
            color=SHADOWSYN_COLOR
        )
        await ctx.respond(embed=embed, ephemeral=True)
        logger.info(f"Target {target_id} bound to Steam tracking. Filter: {genre_filter}")

    @steam_admin.command(name="unregister_thread", description="Unbind Steam new releases feed from the current channel or thread.")
    async def unregister_thread(self, ctx: discord.ApplicationContext):
        target_id = str(ctx.channel.id)
        
        if target_id not in self.targets:
            await ctx.respond("This thread/channel is not currently registered.", ephemeral=True)
            return

        del self.targets[target_id]
        await self._save_state_async()

        embed = discord.Embed(
            title="System Unbound",
            description=f"⛔ Steam New Releases have been detached from <#{target_id}>.",
            color=SHADOWSYN_COLOR
        )
        await ctx.respond(embed=embed, ephemeral=True)
        logger.info(f"Target {target_id} unbound from Steam tracking by {ctx.author}.")

    @steam_admin.command(name="test", description="Send a dummy Steam release to test thread permissions.")
    async def test_steam(self, ctx: discord.ApplicationContext):
        if not self.targets:
            return await ctx.respond("❌ No threads registered. Run `/steam register_thread` first.", ephemeral=True)

        await ctx.respond("🚀 Firing test transmission to all registered targets...", ephemeral=True)
        
        dummy_item = {
            "id": 400,
            "name": "ShadowSyn Tracker (System Test)",
            "header_image": "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/400/header.jpg",
            "final_price": 2999,
            "currency": "AUD",
            "windows_available": True,
            "mac_available": True,
            "linux_available": False,
            "genres": ["Action", "Survival", "Indie"],
            "categories": ["Co-op", "Multi-player", "PvP"]
        }
        
        await self._dispatch_release(dummy_item)

# ==============================================================================
# ENTRY POINT
# ==============================================================================
def setup(bot: discord.Bot):
    bot.add_cog(SteamReleasesTracker(bot))

if __name__ == "__main__":
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
