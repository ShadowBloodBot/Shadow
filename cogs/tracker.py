# cogs/tracker.py
import os
import json
import asyncio
import re
import time
import urllib.parse
import logging
from pathlib import Path
from datetime import datetime, timezone

import discord
import httpx
from discord import Option
from discord.ext import commands, tasks

# --- LOGGING CONFIGURATION ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Suppress verbose httpx/httpcore request logging (even for successful requests)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

from cogs.guild_registry import (
    REGISTERED_GUILD_IDS,
    SHADOW_MAIN_GUILD_ID,
    ch_id,
    is_registered_guild,
    resolve_channel,
)

# --- CONSTANTS ---
THEME_PRIMARY        = 0x2B0B35
THEME_WIN            = 0x43B581
THEME_LOSS           = 0xF04747
OWNER_ID             = 482463400929263627
ALERT_AFTER_FAILURES = 5   # consecutive poll failures before a Discord alert fires (~3.75 min)

# --- PERSISTENCE ---
PERSIST_ROOT = Path(os.getenv("PERSIST_PATH", "/data")).resolve()
try:
    PERSIST_ROOT.mkdir(parents=True, exist_ok=True)
except Exception:
    PERSIST_ROOT = Path(".").resolve()

TRACKER_STORE = PERSIST_ROOT / "kill_tracker_api.json"

_DB_DEFAULTS = {
    "target_threads":   {},
    "target_thread_id": None,
    "session_cookie":   None,
    "tracked_players":  [],
    "processed_kills":  [],   # stored as list on disk, used as set in memory
}

# ---------------------------------------------------------------------------
# MODULE-LEVEL HELPERS
# ---------------------------------------------------------------------------

def _atomic_write(file_path: Path, data):
    try:
        content  = json.dumps(list(data) if isinstance(data, set) else data, indent=2)
        tmp_path = file_path.with_suffix(".tmp")
        tmp_path.write_text(content, encoding="utf-8")
        tmp_path.replace(file_path)
    except Exception as e:
        logger.error(f"Persistence Error: {e}")

def extract_player_id(url: str):
    if not url or not isinstance(url, str):
        return None
    match = re.search(r"/players/([^/?]+)", url)
    return match.group(1) if match else None

def is_admin(user: discord.Member) -> bool:
    return user.id == OWNER_ID


# ---------------------------------------------------------------------------
# COG
# ---------------------------------------------------------------------------

class TrackerCog(commands.Cog):
    def __init__(self, bot):
        self.bot                  = bot
        self.db                   = {k: (list(v) if isinstance(v, list) else v) for k, v in _DB_DEFAULTS.items()}
        self.consecutive_failures = 0
        self._load_data()
        self.client = httpx.AsyncClient(timeout=30.0, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
            "Accept":     "application/json",
            "Referer":    "https://fta.gg/"
        })
        self.feed_monitor.start()
        logger.info("✅ TrackerCog initialized")

    def cog_unload(self):
        self.feed_monitor.cancel()
        asyncio.create_task(self.client.aclose())

    # -----------------------------------------------------------------------
    # PERSISTENCE
    # -----------------------------------------------------------------------

    def _load_data(self):
        if TRACKER_STORE.exists():
            try:
                loaded = json.loads(TRACKER_STORE.read_text(encoding="utf-8"))
                for k in _DB_DEFAULTS:
                    if k in loaded:
                        self.db[k] = loaded[k]
            except Exception as e:
                logger.error(f"Failed to load tracker data — starting fresh: {e}")

        # processed_kills: list on disk → set in memory for O(1) dedup lookups
        self.db["processed_kills"] = set(self.db["processed_kills"])

        threads = self.db.get("target_threads")
        if not isinstance(threads, dict):
            threads = {}
        legacy = self.db.get("target_thread_id")
        if legacy and not threads:
            threads[str(SHADOW_MAIN_GUILD_ID)] = int(legacy)
        self.db["target_threads"] = {
            str(k): int(v) for k, v in threads.items() if v is not None
        }

        # Sanitize players: back-fill player_id from profile_url if missing
        sanitized = []
        patched   = False
        for p in self.db["tracked_players"]:
            if not isinstance(p, dict):
                continue
            if not p.get("player_id") and p.get("profile_url"):
                p["player_id"] = extract_player_id(p["profile_url"])
                patched = True
            if p.get("name") and p.get("player_id"):
                sanitized.append(p)
        self.db["tracked_players"] = sanitized
        if patched:
            self._save()

    def _save(self):
        """Serialise in-memory state to disk. Converts processed_kills set → list."""
        payload = dict(self.db)
        payload["processed_kills"] = list(self.db["processed_kills"])
        payload["target_threads"] = self.db.get("target_threads") or {}
        _atomic_write(TRACKER_STORE, payload)

    def _configured_feed_channels(self) -> list[int]:
        threads = self.db.get("target_threads") or {}
        ids: list[int] = []
        seen: set[int] = set()
        for raw in threads.values():
            try:
                cid = int(raw)
            except (TypeError, ValueError):
                continue
            if cid not in seen:
                seen.add(cid)
                ids.append(cid)
        return ids

    async def _resolve_feed_channel(self, channel_id: int):
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except Exception:
                return None
        return channel

    # -----------------------------------------------------------------------
    # AUTOCOMPLETE
    # -----------------------------------------------------------------------

    async def autocomplete_tracked_players(self, ctx: discord.AutocompleteContext):
        return [
            p["name"] for p in self.db["tracked_players"]
            if isinstance(p, dict) and "name" in p
            and ctx.value.lower() in p["name"].lower()
        ][:25]

    # -----------------------------------------------------------------------
    # CUID RESOLUTION
    # -----------------------------------------------------------------------

    async def resolve_internal_cuid(self, guid: str):
        """Translate a public URL GUID into the internal CUID used by fta.gg's API."""
        if guid.startswith("c") and len(guid) > 15:
            return guid   # already a CUID

        payload = {"0": {"json": {"id": guid}}}
        encoded = urllib.parse.quote(json.dumps(payload, separators=(',', ':')))
        url     = f"https://fta.gg/api/trpc/players.getProfile?batch=1&input={encoded}"
        try:
            res  = await self.client.get(url)
            if res.status_code == 200:
                cuid = res.json()[0]["result"]["data"]["json"].get("id")
                if cuid:
                    return cuid
        except Exception as e:
            logger.error(f"CUID Resolve Error for {guid}: {e}")
        return None

    # -----------------------------------------------------------------------
    # FEED MONITOR
    # -----------------------------------------------------------------------

    @tasks.loop(seconds=45)
    async def feed_monitor(self):
        if not self._configured_feed_channels():
            return

        new_events    = []
        tracked_names = [
            p["name"].lower() for p in self.db["tracked_players"]
            if isinstance(p, dict) and p.get("name")
        ]

        headers = {}
        if self.db.get("session_cookie"):
            headers["Cookie"] = self.db["session_cookie"]

        api_url      = "https://fta.gg/api/trpc/players.getWcsKills"
        cuid_patched = False   # flag: do we need to save after the loop?

        for player in self.db["tracked_players"]:
            if not isinstance(player, dict):
                continue

            pid = player.get("player_id")
            if not pid:
                continue

            # Resolve GUID → CUID if needed — flag for a single save after the loop
            if not pid.startswith("c"):
                new_pid = await self.resolve_internal_cuid(pid)
                if new_pid:
                    player["player_id"] = new_pid
                    pid                 = new_pid
                    cuid_patched        = True
                else:
                    continue

            payload = {
                "0": {
                    "json": {"playerId": pid, "serverId": None, "limit": 15},
                    "meta": {"values": {"serverId": ["undefined"]}, "v": 1}
                }
            }
            query_params = {
                "batch": "1",
                "input": json.dumps(payload, separators=(',', ':')),
                "_cb":   str(int(time.time() * 1000))
            }

            try:
                response = await self.client.get(api_url, params=query_params, headers=headers)
                if response.status_code != 200:
                    raise ValueError(f"HTTP {response.status_code}")

                data = response.json()
                if not data or not isinstance(data, list) or "result" not in data[0]:
                    continue

                json_data   = data[0]["result"]["data"]["json"]
                kills_array = []
                if isinstance(json_data, list):
                    kills_array = json_data
                elif isinstance(json_data, dict):
                    for val in json_data.values():
                        if isinstance(val, list):
                            kills_array = val
                            break

                for event in kills_array:
                    if not isinstance(event, dict):
                        continue
                    kill_id = event.get("id")
                    # O(1) set lookup — no linear scan
                    if not kill_id or kill_id in self.db["processed_kills"]:
                        continue
                    self.db["processed_kills"].add(kill_id)
                    new_events.append(event)

                # Reset failure streak on any successful poll
                self.consecutive_failures = 0

            except Exception as e:
                self.consecutive_failures += 1
                logger.error(f"API Poll Failed [{self.consecutive_failures}]: {e}")

                # Fire a single Discord alert when the failure threshold is crossed
                if self.consecutive_failures == ALERT_AFTER_FAILURES:
                    await self._send_feed_alert(
                        f"⚠️ **Telemetry Warning:** API has failed **{ALERT_AFTER_FAILURES}** "
                        f"consecutive polls (~{ALERT_AFTER_FAILURES * 45 // 60} min). "
                        f"Last error: `{e}`\n"
                        f"Feed may be down — run `/tracker_diagnostics` to investigate."
                    )

        # One save after the full loop, not once per player
        if cuid_patched or new_events:
            # Cap memory: trim processed_kills if it grows beyond 1000 entries
            if len(self.db["processed_kills"]) > 1000:
                self.db["processed_kills"] = set(list(self.db["processed_kills"])[:1000])
            self._save()

        if new_events:
            tracked_ids = [
                p["player_id"] for p in self.db["tracked_players"]
                if isinstance(p, dict) and p.get("player_id")
            ]
            new_events.sort(key=lambda x: x.get("timestamp", ""))
            await self.broadcast_kills(new_events, tracked_ids, tracked_names)

    @feed_monitor.before_loop
    async def before_feed_monitor(self):
        await self.bot.wait_until_ready()

    async def _send_feed_alert(self, message: str):
        """Post a plain-text alert to all configured kill-feed channels."""
        for channel_id in self._configured_feed_channels():
            try:
                channel = await self._resolve_feed_channel(channel_id)
                if channel:
                    await channel.send(message)
            except Exception:
                pass

    # -----------------------------------------------------------------------
    # BROADCAST
    # -----------------------------------------------------------------------

    async def broadcast_kills(self, events, tracked_ids, tracked_names):
        channels: list = []
        for channel_id in self._configured_feed_channels():
            channel = await self._resolve_feed_channel(channel_id)
            if channel:
                channels.append(channel)
        if not channels:
            return

        for event in events:
            killer_id   = event.get("killerId")
            victim_id   = event.get("victimId")
            killer_name = event.get("killerName", "Unknown")
            victim_name = event.get("victimName", "Unknown")
            weapon      = event.get("weapon", "Unknown Weapon")
            distance    = event.get("distance", 0)
            server_name = event.get("server", {}).get("shortName", "Unknown Server")

            is_killer_tracked = (killer_id in tracked_ids) or (killer_name.lower() in tracked_names)
            is_victim_tracked = (victim_id in tracked_ids) or (victim_name.lower() in tracked_names)

            color = THEME_WIN if is_killer_tracked else THEME_LOSS if is_victim_tracked else THEME_PRIMARY

            event_time = datetime.now(timezone.utc)
            try:
                if event.get("timestamp"):
                    event_time = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
            except Exception:
                pass

            embed = discord.Embed(
                title=f"⚔️ Kill Feed | {server_name}",
                description=f"**{killer_name}** eliminated **{victim_name}**",
                color=color,
                timestamp=event_time
            )
            embed.add_field(name="🔫 Weapon", value=f"`{weapon}`", inline=True)
            try:
                embed.add_field(name="📏 Distance", value=f"`{float(distance):.1f}m`", inline=True)
            except Exception:
                embed.add_field(name="📏 Distance", value=f"`{distance}m`", inline=True)
            embed.set_footer(text="FTA.gg API Telemetry")

            try:
                for channel in channels:
                    try:
                        await channel.send(embed=embed)
                    except discord.Forbidden:
                        logger.error("Broadcast halted: missing channel permissions for %s.", channel.id)
                        continue
                    except Exception as e:
                        logger.error(f"Broadcast failed for kill on {channel.id}: {e}")
                await asyncio.sleep(1.2)
            except Exception as e:
                logger.error(f"Broadcast loop failed: {e}")
                continue

    # -----------------------------------------------------------------------
    # SLASH COMMANDS
    # -----------------------------------------------------------------------

    @discord.slash_command(
        name="stats",
        description="View the overall combat record of a tracked player",
        guild_ids=REGISTERED_GUILD_IDS,
    )
    async def stats(self, ctx, player_name: Option(str, "Select a tracked player", autocomplete=autocomplete_tracked_players)):
        allowed = ch_id(ctx.guild.id, "arma_stats") if ctx.guild else None
        if not allowed or ctx.channel.id != allowed:
            return await ctx.respond(
                f"❌ Security Protocol: This command can only be executed inside the <#{allowed}> thread.",
                ephemeral=True,
            )

        await ctx.defer()

        player = next(
            (p for p in self.db["tracked_players"]
             if isinstance(p, dict) and p.get("name", "").lower() == player_name.lower()),
            None
        )
        if not player:
            return await ctx.respond(f"❌ Could not find **{player_name}** in the telemetry database.", ephemeral=True)

        pid = player.get("player_id")
        if not pid.startswith("c"):
            pid = await self.resolve_internal_cuid(pid)
            if not pid:
                return await ctx.respond("❌ Network Fault: Could not translate the URL GUID into the Database CUID.")

        api_url = "https://fta.gg/api/trpc/players.getWcsStats"
        payload = {
            "0": {
                "json": {"playerId": pid, "serverId": None},
                "meta": {"values": {"serverId": ["undefined"]}, "v": 1}
            }
        }
        query_params = {"batch": "1", "input": json.dumps(payload, separators=(',', ':'))}

        headers = {}
        if self.db.get("session_cookie"):
            headers["Cookie"] = self.db["session_cookie"]

        try:
            response = await self.client.get(api_url, params=query_params, headers=headers)
            if response.status_code != 200:
                return await ctx.respond(f"❌ **Cloudflare Blocked the Request (HTTP {response.status_code})**")

            data       = response.json()
            stats_json = data[0]["result"]["data"]["json"]

            kills         = stats_json.get("kills", 0)
            deaths        = stats_json.get("deaths", 0)
            headshots     = stats_json.get("headshots", 0)
            longest_kill  = stats_json.get("longestKill", 0)
            avg_kill_dist = stats_json.get("avgKillDistance", 0)
            kd            = round(kills / max(1, deaths), 2)
            hs_pct        = round((headshots / max(1, kills)) * 100, 1)

            top_weapons      = stats_json.get("topWeapons", [])
            fav_weapon       = top_weapons[0].get("weapon", "Unknown") if top_weapons else "Unknown"
            fav_weapon_kills = top_weapons[0].get("kills", 0) if top_weapons else 0

            embed = discord.Embed(title=f"📊 Combat Record | {player['name']}", color=THEME_PRIMARY)
            embed.add_field(name="⚔️ Kills",          value=f"`{kills:,}`",                          inline=True)
            embed.add_field(name="💀 Deaths",          value=f"`{deaths:,}`",                         inline=True)
            embed.add_field(name="🎯 K/D Ratio",       value=f"`{kd}`",                               inline=True)
            embed.add_field(name="🤯 Headshots",       value=f"`{headshots:,}` ({hs_pct}%)",          inline=True)
            embed.add_field(name="📏 Longest Kill",    value=f"`{longest_kill}m`",                    inline=True)
            embed.add_field(name="📏 Avg Kill Dist",   value=f"`{avg_kill_dist}m`",                   inline=True)
            embed.add_field(name="🏆 Favorite Weapon", value=f"**{fav_weapon}** (`{fav_weapon_kills:,}` kills)", inline=False)
            embed.set_thumbnail(url="https://fta.gg/favicon.ico")
            embed.set_footer(text="FTA.gg Global Server Statistics")
            await ctx.respond(embed=embed)

        except Exception as e:
            logger.error(f"Stats fetch error: {e}")
            await ctx.respond(f"💥 **Data Extraction Error:**\n```\n{e}\n```")

    @discord.slash_command(
        name="track_player",
        description="Add a player to the live API watch list",
        guild_ids=REGISTERED_GUILD_IDS,
    )
    async def track_player(self, ctx,
                           player_name: Option(str, "Exact in-game name (e.g., warcrimes)"),
                           profile_url: Option(str, "Required: Paste fta.gg profile link here")):
        if not is_admin(ctx.author):
            return await ctx.respond("⛔ Restricted.", ephemeral=True)

        await ctx.defer(ephemeral=True)

        player_id = extract_player_id(profile_url)
        if not player_id:
            return await ctx.respond("❌ Invalid URL.", ephemeral=True)

        cuid = await self.resolve_internal_cuid(player_id)
        if not cuid:
            return await ctx.respond(
                f"❌ Failed to find the internal database ID for {player_name}. Check the URL.",
                ephemeral=True
            )

        if any(isinstance(p, dict) and p.get("player_id") == cuid for p in self.db["tracked_players"]):
            return await ctx.respond(f"⚠️ **{player_name}** is already tracked.", ephemeral=True)

        self.db["tracked_players"].append({"name": player_name, "player_id": cuid, "profile_url": profile_url})
        self._save()
        await ctx.respond(f"✅ Telemetry locked onto: **{player_name}**", ephemeral=True)

    @discord.slash_command(
        name="untrack_player",
        description="Stop monitoring a player by name",
        guild_ids=REGISTERED_GUILD_IDS,
    )
    async def untrack_player(self, ctx, player_name: Option(str, "Name of the player to remove", autocomplete=autocomplete_tracked_players)):
        if not is_admin(ctx.author):
            return await ctx.respond("⛔ Restricted.", ephemeral=True)

        initial = len(self.db["tracked_players"])
        self.db["tracked_players"] = [
            p for p in self.db["tracked_players"]
            if isinstance(p, dict) and p.get("name", "").lower() != player_name.lower()
        ]

        if len(self.db["tracked_players"]) < initial:
            self._save()
            await ctx.respond(f"🗑️ Released monitor for: **{player_name}**", ephemeral=True)
        else:
            await ctx.respond(f"❓ Player **{player_name}** not found in database.", ephemeral=True)

    @discord.slash_command(
        name="tracker_config",
        description="Set THIS thread/channel for live API broadcasts",
        guild_ids=REGISTERED_GUILD_IDS,
    )
    async def tracker_config(self, ctx):
        if not is_admin(ctx.author):
            return await ctx.respond("⛔ Restricted.", ephemeral=True)
        if not ctx.guild or not is_registered_guild(ctx.guild.id):
            return await ctx.respond("⛔ Unregistered guild.", ephemeral=True)

        threads = self.db.setdefault("target_threads", {})
        threads[str(ctx.guild.id)] = ctx.channel.id
        self._save()
        await ctx.respond("🎯 Output synchronized.", ephemeral=True)
        try:
            await ctx.channel.send("✅ **[System Check]** Telemetry engine is officially linked to this channel. Awaiting live data...")
        except discord.Forbidden:
            await ctx.respond(
                "❌ **ERROR:** The bot does not have 'Send Messages' permissions in this specific thread!",
                ephemeral=True
            )

    @discord.slash_command(
        name="tracker_list",
        description="List all monitored API profiles",
        guild_ids=REGISTERED_GUILD_IDS,
    )
    async def tracker_list(self, ctx):
        players = [p for p in self.db["tracked_players"] if isinstance(p, dict) and "name" in p]
        if not players:
            return await ctx.respond("📝 Monitor list is currently empty.", ephemeral=True)

        desc  = "\n".join([f"• **{p['name']}** ([Link]({p['profile_url']}))" for p in players])
        embed = discord.Embed(title="📑 Active API Watch List", description=desc, color=THEME_PRIMARY)
        await ctx.respond(embed=embed, ephemeral=True)

    @discord.slash_command(
        name="tracker_diagnostics",
        description="Run a deep network test to see why the API is failing",
        guild_ids=REGISTERED_GUILD_IDS,
    )
    async def tracker_diagnostics(self, ctx):
        await ctx.defer()
        if not self.db["tracked_players"]:
            return await ctx.respond("❌ No players tracked. Add one first to test the API.")

        player = self.db["tracked_players"][0]
        pid    = player.get("player_id")

        if not pid.startswith("c"):
            pid = await self.resolve_internal_cuid(pid)
            if not pid:
                return await ctx.respond("❌ Network Check Failed: Could not translate the URL GUID into the Database CUID.")

        api_url      = "https://fta.gg/api/trpc/players.getWcsKills"
        payload      = {
            "0": {
                "json": {"playerId": pid, "serverId": None, "limit": 2},
                "meta": {"values": {"serverId": ["undefined"]}, "v": 1}
            }
        }
        query_params = {"batch": "1", "input": json.dumps(payload, separators=(',', ':'))}

        headers = {}
        if self.db.get("session_cookie"):
            headers["Cookie"] = self.db["session_cookie"]

        try:
            response = await self.client.get(api_url, params=query_params, headers=headers)
            if response.status_code != 200:
                resp_text = response.text[:1000]
                return await ctx.respond(
                    f"❌ **Cloudflare Blocked the Request (HTTP {response.status_code})**\n```html\n{resp_text}\n```"
                )

            data      = response.json()
            data_text = json.dumps(data, indent=2)[:1500]
            await ctx.respond(
                f"✅ **HTTP 200 OK.** Translating ID... Success! Here is exactly what the database returned:\n```json\n{data_text}\n```"
            )

        except Exception as e:
            logger.error(f"Diagnostics error: {e}")
            await ctx.respond(f"💥 **Fatal Network Error:**\n```\n{e}\n```")


def setup(bot):
    bot.add_cog(TrackerCog(bot))
