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
    "tracked_players": [],   
    "processed_kills": []    
}

def _atomic_write(file_path: Path, data):
    try:
        content = json.dumps(list(data) if isinstance(data, set) else data, indent=2)
        temp_path = file_path.with_suffix(".tmp")
        temp_path.write_text(content, encoding='utf-8')
        temp_path.replace(file_path)
    except Exception as e:
        print(f"⚠️ Persistence Error: {e}")

def _save_tracker():
    _atomic_write(TRACKER_STORE, tracker_db)

def extract_player_id(url: str):
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
            "Referer": "https://fta.gg/"
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

        tracker_db["tracked_players"] = sanitized_players
        if patched:
            _save_tracker()

    # THE TRANSLATOR: Converts Public URL GUIDs to Internal Database CUIDs
    async def resolve_internal_cuid(self, guid: str):
        # Database CUIDs always start with 'c'. If it already has it, skip the check.
        if guid.startswith("c") and len(guid) > 15:
            return guid
            
        payload = {"0": {"json": {"id": guid}}}
        encoded = urllib.parse.quote(json.dumps(payload, separators=(',', ':')))
        url = f"https://fta.gg/api/trpc/players.getProfile?batch=1&input={encoded}"
        try:
            res = await self.client.get(url)
            if res.status_code == 200:
                data = res.json()
                cuid = data[0]["result"]["data"]["json"].get("id")
                if cuid:
                    return cuid
        except Exception as e:
            print(f"⚠️ CUID Resolve Error for {guid}: {e}")
        return None

    @tasks.loop(seconds=45)
    async def feed_monitor(self):
        if not tracker_db.get("target_thread_id"):
            return

        new_events = []
        tracked_names = [p["name"].lower() for p in tracker_db["tracked_players"] if isinstance(p, dict) and p.get("name")]
        
        headers = {}
        if tracker_db.get("session_cookie"):
            headers["Cookie"] = tracker_db["session_cookie"]

        api_url = "https://fta.gg/api/trpc/players.getWcsKills"

        for player in tracker_db["tracked_players"]:
            if not isinstance(player, dict):
                continue
                
            pid = player.get("player_id")
            if not pid:
                continue

            # Auto-Heal: If the bot detects an old URL GUID, it silently upgrades it to the database CUID.
            if not pid.startswith("c"):
                new_pid = await self.resolve_internal_cuid(pid)
                if new_pid:
                    player["player_id"] = new_pid
                    pid = new_pid
                    _save_tracker()
                else:
                    continue

            payload = {
                "0": {
                    "json": {
                        "playerId": pid,
                        "serverId": None,
                        "limit": 15
                    },
                    "meta": {
                        "values": {"serverId": ["undefined"]},
                        "v": 1
                    }
                }
            }
            
            query_params = {
                "batch": "1",
                "input": json.dumps(payload, separators=(',', ':')),
                "_cb": str(int(time.time() * 1000))
            }

            try:
                response = await self.client.get(api_url, params=query_params, headers=headers)
                if response.status_code != 200:
                    continue

                data = response.json()
                if not data or not isinstance(data, list) or "result" not in data[0]:
                    continue
                    
                json_data = data[0]["result"]["data"]["json"]
                
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
                        
                    tracker_db["processed_kills"].insert(0, kill_id)
                    new_events.append(event)
                    
            except Exception as e:
                print(f"📡 Background Loop Fault: {e}")

        if new_events:
            if len(tracker_db["processed_kills"]) > 600:
                tracker_db["processed_kills"] = tracker_db["processed_kills"][:600]
            _save_tracker()
            
            # Rebuild tracked IDs list with the newly resolved internal CUIDs
            tracked_ids = [p["player_id"] for p in tracker_db["tracked_players"] if isinstance(p, dict) and p.get("player_id")]
            new_events.sort(key=lambda x: x.get("timestamp", ""))
            await self.broadcast_kills(new_events, tracked_ids, tracked_names)

    @feed_monitor.before_loop
    async def before_feed_monitor(self):
        await self.bot.wait_until_ready()

    async def broadcast_kills(self, events, tracked_ids, tracked_names):
        channel_id = tracker_db.get("target_thread_id")
        if not channel_id:
            return

        channel = self.bot.get_channel(int(channel_id))
        if not channel:
            try:
                channel = await self.bot.fetch_channel(int(channel_id))
            except Exception as e:
                return

        for event in events:
            killer_id = event.get("killerId")
            victim_id = event.get("victimId")
            killer_name = event.get("killerName", "Unknown")
            victim_name = event.get("victimName", "Unknown")
            weapon = event.get("weapon", "Unknown Weapon")
            distance = event.get("distance", 0)
            server_name = event.get("server", {}).get("shortName", "Unknown Server")
            
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
                break

    # --- SLASH COMMANDS ---

    @discord.slash_command(name="track_player", description="Add a player to the live API watch list")
    async def track_player(self, ctx, 
                           player_name: Option(str, "Exact in-game name (e.g., warcrimes)"), 
                           profile_url: Option(str, "Required: Paste fta.gg profile link here")):
        await ctx.defer(ephemeral=True)
        player_id = extract_player_id(profile_url)
        if not player_id:
            return await ctx.respond("❌ Invalid URL.", ephemeral=True)
            
        cuid = await self.resolve_internal_cuid(player_id)
        if not cuid:
            return await ctx.respond(f"❌ Failed to find the internal database ID for {player_name}. Check the URL.", ephemeral=True)

        if any(isinstance(p, dict) and p.get("player_id") == cuid for p in tracker_db["tracked_players"]):
            return await ctx.respond(f"⚠️ **{player_name}** is already tracked.", ephemeral=True)

        tracker_db["tracked_players"].append({"name": player_name, "player_id": cuid, "profile_url": profile_url})
        _save_tracker()
        await ctx.respond(f"✅ Telemetry locked onto: **{player_name}**", ephemeral=True)

    @discord.slash_command(name="tracker_config", description="Set THIS thread/channel for live API broadcasts")
    async def tracker_config(self, ctx):
        tracker_db["target_thread_id"] = ctx.channel.id
        _save_tracker()
        await ctx.respond(f"🎯 Output synchronized.", ephemeral=True)
        try:
            await ctx.channel.send("✅ **[System Check]** Telemetry engine is officially linked to this channel. Awaiting live data...")
        except discord.Forbidden:
            await ctx.respond("❌ **ERROR:** The bot does not have 'Send Messages' permissions in this specific thread!", ephemeral=True)

    @discord.slash_command(name="tracker_list", description="List all monitored API profiles")
    async def tracker_list(self, ctx):
        players = [p for p in tracker_db["tracked_players"] if isinstance(p, dict) and "name" in p]
        if not players:
            return await ctx.respond("📝 Monitor list is currently empty.", ephemeral=True)
        
        desc = "\n".join([f"• **{p['name']}** ([Link]({p['profile_url']}))" for p in players])
        embed = discord.Embed(title="📑 Active API Watch List", description=desc, color=THEME_PRIMARY)
        await ctx.respond(embed=embed, ephemeral=True)

    @discord.slash_command(name="tracker_diagnostics", description="Run a deep network test to see why the API is failing")
    async def tracker_diagnostics(self, ctx):
        await ctx.defer()
        if not tracker_db["tracked_players"]:
            return await ctx.respond("❌ No players tracked. Add one first to test the API.")
            
        player = tracker_db["tracked_players"][0]
        pid = player.get("player_id")
        
        # Resolve to internal CUID first to test real payload
        if not pid.startswith("c"):
            pid = await self.resolve_internal_cuid(pid)
            if not pid:
                return await ctx.respond("❌ Network Check Failed: Could not translate the URL GUID into the Database CUID.")
        
        api_url = "https://fta.gg/api/trpc/players.getWcsKills"
        payload = {
            "0": {
                "json": {"playerId": pid, "serverId": None, "limit": 2},
                "meta": {"values": {"serverId": ["undefined"]}, "v": 1}
            }
        }
        
        query_params = {
            "batch": "1",
            "input": json.dumps(payload, separators=(',', ':'))
        }
        
        headers = {}
        if tracker_db.get("session_cookie"):
            headers["Cookie"] = tracker_db["session_cookie"]

        try:
            response = await self.client.get(api_url, params=query_params, headers=headers)
            if response.status_code != 200:
                resp_text = response.text[:1000]
                error_msg = f"❌ **Cloudflare Blocked the Request (HTTP {response.status_code})**\n```html\n{resp_text}\n```"
                return await ctx.respond(error_msg)
                
            data = response.json()
            data_text = json.dumps(data, indent=2)[:1500]
            success_msg = f"✅ **HTTP 200 OK.** Translating ID... Success! Here is exactly what the database returned:\n```json\n{data_text}\n```"
            await ctx.respond(success_msg)
            
        except Exception as e:
            err_msg = f"💥 **Fatal Network Error:**\n```\n{e}\n```"
            await ctx.respond(err_msg)

def setup(bot):
    bot.add_cog(TrackerCog(bot))
