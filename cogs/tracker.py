# cogs/tracker.py
import os
import json
import asyncio
import traceback
import re
import time
import urllib.parse
from pathlib import Path
from datetime import datetime, timezone

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
    "session_cookie": None,  
    "tracked_players": [],   # Format: {"name": str, "player_id": str, "profile_url": str}
    "processed_kills": []    
}

def _atomic_write(file_path: Path, data):
    try:
        content = json.dumps(list(data) if isinstance(data, set) else data, indent=2)
        temp_path = file_path.with_suffix(".tmp")
        temp_path.write_text(content, encoding='utf-8')
        temp_path.replace(file_path)
    except Exception as e:
        print(f"⚠️ Persistence Error [{file_path.name}]: {e}")

def _save_tracker():
    _atomic_write(TRACKER_STORE, tracker_db)

def extract_player_id(url: str):
    """Extracts the raw database UUID from an fta.gg profile link."""
    if not url or not isinstance(url, str):
        return None
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
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept": "application/json",
            "Referer": "https://fta.gg/",
            "Cache-Control": "no-cache"
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
                
        sanitized_players = []
        patched = False
        for p in tracker_db["tracked_players"]:
            if isinstance(p, dict):
                if not p.get("player_id") and p.get("profile_url"):
                    p["player_id"] = extract_player_id(p["profile_url"])
                    patched = True
                if p.get("name") and p.get("player_id"):
                    sanitized_players.append(p)
            else:
                patched = True

        tracker_db["tracked_players"] = sanitized_players
        if patched:
            _save_tracker()

    @tasks.loop(seconds=45)
    async def feed_monitor(self):
        if not tracker_db.get("target_thread_id"):
            return

        new_events = []
        
        # We track both IDs (Primary) and Names (Fallback)
        tracked_ids = [p["player_id"] for p in tracker_db["tracked_players"] if isinstance(p, dict) and p.get("player_id")]
        tracked_names = [p["name"].lower() for p in tracker_db["tracked_players"] if isinstance(p, dict) and p.get("name")]

        headers = {}
        if tracker_db.get("session_cookie"):
            headers["Cookie"] = tracker_db["session_cookie"]

        for player in tracker_db["tracked_players"]:
            if not isinstance(player, dict):
                continue
                
            pid = player.get("player_id")
            if not pid:
                continue

            # Fully constructed SuperJSON Payload (Matches frontend exact architecture)
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
                        },
                        "v": 1
                    }
                }
            }
            
            encoded_payload = urllib.parse.quote(json.dumps(payload))
            cache_buster = int(time.time() * 1000)
            url = f"https://fta.gg/api/trpc/players.getWcsKills?batch=1&input={encoded_payload}&_cb={cache_buster}"

            try:
                response = await self.client.get(url, headers=headers)
                if response.status_code != 200:
                    continue

                data = response.json()
                
                if not data or not isinstance(data, list) or "result" not in data[0]:
                    continue
                    
                json_data = data[0]["result"]["data"]["json"]
                
                # Infinite Query Parser: Safely extracts the array whether it's named 'items', 'data', or just a raw list
                kills_array = []
                if isinstance(json_data, list):
                    kills_array = json_data
                elif isinstance(json_data, dict):
                    for val in json_data.values():
                        if isinstance(val, list):
                            kills_array = val
                            break
                
                if not kills_array:
                    continue
                
                for event in kills_array:
                    if not isinstance(event, dict):
                        continue
                        
                    kill_id = event.get("id")
                    if not kill_id or kill_id in tracker_db["processed_kills"]:
                        continue
                        
                    # Register to memory to prevent duplicates
                    tracker_db["processed_kills"].insert(0, kill_id)
                    
                    # Spam Filter: If a kill is older than 2 hours, we skip broadcasting it 
                    # This prevents the bot from dumping 50 historical kills when you track a new friend
                    try:
                        if event.get("timestamp"):
                            event_time = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
                            if (datetime.now(timezone.utc) - event_time).total_seconds() > 7200:
                                continue
                    except:
                        pass
                        
                    new_events.append(event)
                    
            except Exception as e:
                print(f"📡 API Telemetry Fault [{player.get('name', 'Unknown')}]: {traceback.format_exc()}")

        if new_events:
            # Memory Management: Keep array lean
            if len(tracker_db["processed_kills"]) > 600:
                tracker_db["processed_kills"] = tracker_db["processed_kills"][:600]
            _save_tracker()
            
            # Sort events chronologically so the Discord feed reads top-to-bottom accurately
            new_events.sort(key=lambda x: x.get("timestamp", ""))
            await self.broadcast_kills(new_events, tracked_ids, tracked_names)

    async def broadcast_kills(self, events, tracked_ids, tracked_names):
        channel_id = tracker_db.get("target_thread_id")
        if not channel_id:
            return

        # Hard-Fetch Fallback: Ensures private channels don't get dropped from bot cache
        channel = self.bot.get_channel(int(channel_id))
        if not channel:
            try:
                channel = await self.bot.fetch_channel(int(channel_id))
            except Exception as e:
                print(f"⚠️ Broadcast Error: Could not fetch channel {channel_id} - {e}")
                return

        for event in events:
            killer_id = event.get("killerId")
            victim_id = event.get("victimId")
            killer_name = event.get("killerName", "Unknown")
            victim_name = event.get("victimName", "Unknown")
            weapon = event.get("weapon", "Unknown Weapon")
            distance = event.get("distance", 0)
            server_name = event.get("server", {}).get("shortName", "Unknown Server")
            
            # Strict validation using UUIDs first, falling back to name checks
            is_killer_tracked = (killer_id in tracked_ids) or (killer_name.lower() in tracked_names)
            is_victim_tracked = (victim_id in tracked_ids) or (victim_name.lower() in tracked_names)
            
            if is_killer_tracked:
                color = THEME_WIN
            elif is_victim_tracked:
                color = THEME_LOSS
            else:
                color = THEME_PRIMARY

            event_time = datetime.now(timezone.utc)
            try:
                if event.get("timestamp"):
                    event_time = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
            except:
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
            except:
                embed.add_field(name="📏 Distance", value=f"`{distance}m`", inline=True)
                
            embed.set_footer(text="FTA.gg API Telemetry")
            
            try:
                await channel.send(embed=embed)
                await asyncio.sleep(1.2)
            except Exception as e:
                print(f"⚠️ Failed to send message to Discord: {e}")
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

        if any(isinstance(p, dict) and p.get("player_id") == player_id for p in tracker_db["tracked_players"]):
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
        tracker_db["tracked_players"] = [p for p in tracker_db["tracked_players"] if isinstance(p, dict) and p.get("name", "").lower() != player_name.lower()]
        
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

    @discord.slash_command(name="tracker_session", description="Set or clear the authorization raw cookie value (Admin Only)")
    async def tracker_session(self, ctx, cookie_string: Option(str, "Paste raw cookie headers string from DevTools or type 'clear'", required=True)):
        if cookie_string.lower().strip() == "clear":
            tracker_db["session_cookie"] = None
            _save_tracker()
            return await ctx.respond("🧹 Cleared session cookies from the telemetry engine database.", ephemeral=True)
            
        tracker_db["session_cookie"] = cookie_string
        _save_tracker()
        await ctx.respond("🔒 Session cookie headers updated successfully.", ephemeral=True)

    @discord.slash_command(name="tracker_list", description="List all monitored API profiles")
    async def tracker_list(self, ctx):
        players = tracker_db["tracked_players"]
        valid_players = [p for p in players if isinstance(p, dict) and "name" in p]
        if not valid_players:
            return await ctx.respond("📝 Monitor list is currently empty.", ephemeral=True)
        
        desc = ""
        for p in valid_players:
            desc += f"• **{p['name']}** ([Link]({p['profile_url']}))\n"
                
        embed = discord.Embed(title="📑 Active API Watch List", description=desc, color=THEME_PRIMARY)
        await ctx.respond(embed=embed, ephemeral=True)

def setup(bot):
    bot.add_cog(TrackerCog(bot))
