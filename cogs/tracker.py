# cogs/tracker.py
import os
import json
import asyncio
import traceback
import re
import time
import urllib.parse
from pathlib import Path
from datetime import datetime

import discord
import httpx
from discord import Option
from discord.ext import commands, tasks

# --- CONSTANTS ---
THEME_PRIMARY = 0x2B0B35
THEME_WIN = 0x43B581 
THEME_LOSS = 0xF04747 

# --- PERSISTENCE ---
PERSIST_ROOT = Path(os.getenv("PERSIST_PATH", "/data")).resolve()
try:
    PERSIST_ROOT.mkdir(parents=True, exist_ok=True)
except:
    PERSIST_ROOT = Path(".").resolve()

TRACKER_STORE = (PERSIST_ROOT / "kill_tracker_api.json")
tracker_db = {
    "target_thread_id": None,
    "tracked_players": [],  # Format: {"name": str, "player_id": str, "profile_url": str}
    "processed_kills": []   # Array of raw kill IDs to prevent duplicates
}

def _atomic_write(file_path: Path, data):
    try:
        content = json.dumps(data, indent=2)
        temp_path = file_path.with_suffix(".tmp")
        temp_path.write_text(content, encoding='utf-8')
        temp_path.replace(file_path)
    except Exception as e:
        print(f"⚠️ Persistence Error [{file_path.name}]: {e}")

def _save_tracker():
    _atomic_write(TRACKER_STORE, tracker_db)

def extract_player_id(url: str):
    """Extracts the raw database UUID from an fta.gg profile link."""
    match = re.search(r"/players/([^/?]+)", url)
    if match:
        return match.group(1)
    return None

# --- TELEMETRY COG ---
class TrackerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._load_data()
        self.client = httpx.AsyncClient(timeout=30.0, headers={
            "User-Agent": "ShadowSyn Systems Architect/4.1 (Cache-Busting API Telemetry)",
            "Accept": "application/json"
        })
        self.feed_monitor.start()

    def cog_unload(self):
        self.feed_monitor.cancel()
        asyncio.create_task(self.client.aclose())

    def _load_data(self):
        global tracker_db
        if TRACKER_STORE.exists():
            try:
                loaded = json.loads(TRACKER_STORE.read_text())
                for k, v in loaded.items():
                    if k in tracker_db:
                        tracker_db[k] = v
            except:
                pass
                
        # Auto-patch legacy entries to ensure they have the extracted player_id
        patched = False
        for p in tracker_db["tracked_players"]:
            if not p.get("player_id") and p.get("profile_url"):
                p["player_id"] = extract_player_id(p["profile_url"])
                patched = True
        if patched:
            _save_tracker()

    @tasks.loop(seconds=45)
    async def feed_monitor(self):
        if not tracker_db["target_thread_id"]:
            return

        new_events = []

        for player in tracker_db["tracked_players"]:
            pid = player.get("player_id")
            if not pid:
                continue

            # Constructing the exact tRPC payload intercepted from the network
            payload = {
                "0": {
                    "json": {
                        "playerId": pid,
                        "serverId": None,
                        "limit": 50
                    },
                    "meta": {
                        "values": {
                            "serverId": ["undefined"]
                        }
                    }
                }
            }
            
            encoded_payload = urllib.parse.quote(json.dumps(payload))
            
            # Cryptographic Cache Buster: Forces Cloudflare to treat this as a brand new request
            cache_buster = int(time.time() * 1000)
            url = f"https://fta.gg/api/trpc/players.getWcsKills?batch=1&input={encoded_payload}&_cb={cache_buster}"

            try:
                response = await self.client.get(url)
                if response.status_code != 200:
                    continue

                data = response.json()
                
                # Navigate the tRPC JSON architecture
                kills_array = data[0]["result"]["data"]["json"]
                
                for event in kills_array:
                    kill_id = event.get("id")
                    
                    # Deduplication Engine
                    if not kill_id or kill_id in tracker_db["processed_kills"]:
                        continue
                        
                    # Register new kill
                    tracker_db["processed_kills"].insert(0, kill_id)
                    new_events.append(event)
                    
            except Exception as e:
                print(f"📡 API Telemetry Fault [{player['name']}]: {e}")

        if new_events:
            # Memory Management: Keep deduplication array at 500 to prevent bloat
            if len(tracker_db["processed_kills"]) > 500:
                tracker_db["processed_kills"] = tracker_db["processed_kills"][:500]
            _save_tracker()
            
            # Sort events by timestamp so they broadcast in chronological order
            new_events.sort(key=lambda x: x.get("timestamp", ""))
            await self.broadcast_kills(new_events)

    async def broadcast_kills(self, events):
        channel = self.bot.get_channel(tracker_db["target_thread_id"])
        if not channel:
            return

        tracked_names = [p["name"].lower() for p in tracker_db["tracked_players"]]

        for event in events:
            killer = event.get("killerName", "Unknown")
            victim = event.get("victimName", "Unknown")
            weapon = event.get("weapon", "Unknown Weapon")
            distance = event.get("distance", 0)
            server_name = event.get("server", {}).get("shortName", "Unknown Server")
            
            # Color logic based on friend/foe outcome
            is_killer_tracked = killer.lower() in tracked_names
            is_victim_tracked = victim.lower() in tracked_names
            
            if is_killer_tracked:
                color = THEME_WIN
            elif is_victim_tracked:
                color = THEME_LOSS
            else:
                color = THEME_PRIMARY

            embed = discord.Embed(
                title=f"⚔️ Kill Feed | {server_name}",
                description=f"**{killer}** eliminated **{victim}**",
                color=color,
                timestamp=datetime.utcnow()
            )
            
            # Injecting the precise data mined from the JSON payload
            embed.add_field(name="🔫 Weapon", value=f"`{weapon}`", inline=True)
            embed.add_field(name="📏 Distance", value=f"`{distance:.1f}m`", inline=True)
            embed.set_footer(text="FTA.gg Live Telemetry")
            
            try:
                await channel.send(embed=embed)
                await asyncio.sleep(1.2)
            except:
                break

    # --- SLASH COMMANDS ---

    @discord.slash_command(name="track_player", description="Add a player to the live API watch list")
    async def track_player(self, ctx, 
                           player_name: Option(str, "Exact in-game name (e.g., warcrimes)"), 
                           profile_url: Option(str, "Required: Paste fta.gg profile link here to extract their ID")):
        await ctx.defer(ephemeral=True)
        
        player_id = extract_player_id(profile_url)
        if not player_id:
            return await ctx.respond("❌ Invalid URL. I could not extract the database ID from that link.", ephemeral=True)

        if any(p["player_id"] == player_id for p in tracker_db["tracked_players"]):
            return await ctx.respond(f"⚠️ **{player_name}** is already locked into the telemetry array.", ephemeral=True)

        tracker_db["tracked_players"].append({
            "name": player_name, 
            "player_id": player_id,
            "profile_url": profile_url
        })
        _save_tracker()
        await ctx.respond(f"✅ Direct API Telemetry locked onto: **{player_name}** (`{player_id}`)", ephemeral=True)

    @discord.slash_command(name="untrack_player", description="Stop monitoring a player by name")
    async def untrack_player(self, ctx, player_name: Option(str, "Name of the player to remove")):
        initial = len(tracker_db["tracked_players"])
        tracker_db["tracked_players"] = [p for p in tracker_db["tracked_players"] if p["name"].lower() != player_name.lower()]
        
        if len(tracker_db["tracked_players"]) < initial:
            _save_tracker()
            await ctx.respond(f"🗑️ Released monitor for: **{player_name}**", ephemeral=True)
        else:
            await ctx.respond(f"❓ Player **{player_name}** not found in database.", ephemeral=True)

    @discord.slash_command(name="tracker_config", description="Set THIS thread/channel for live API broadcasts")
    async def tracker_config(self, ctx):
        tracker_db["target_thread_id"] = ctx.channel.id
        _save_tracker()
        await ctx.respond(f"🎯 API Output synchronized to: {ctx.channel.mention}", ephemeral=True)

    @discord.slash_command(name="tracker_list", description="List all monitored API profiles")
    async def tracker_list(self, ctx):
        players = tracker_db["tracked_players"]
        if not players:
            return await ctx.respond("📝 Monitor list is currently empty.", ephemeral=True)
        
        desc = ""
        for p in players:
            desc += f"• **{p['name']}** ([Link]({p['profile_url']}))\n"
                
        embed = discord.Embed(title="📑 Active API Watch List", description=desc, color=THEME_PRIMARY)
        await ctx.respond(embed=embed, ephemeral=True)

def setup(bot):
    bot.add_cog(TrackerCog(bot))
