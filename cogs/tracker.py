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
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Referer": "[https://fta.gg/](https://fta.gg/)"
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

    @tasks.loop(seconds=45)
    async def feed_monitor(self):
        if not tracker_db.get("target_thread_id"):
            return

        new_events = []
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
            
            encoded_payload = urllib.parse.quote(json.dumps(payload, separators=(',', ':')))
            url = f"[https://fta.gg/api/trpc/players.getWcsKills?batch=1&input=](https://fta.gg/api/trpc/players.getWcsKills?batch=1&input=){encoded_payload}"

            try:
                response = await self.client.get(url, headers=headers)
                if response.status_code != 200:
                    print(f"📡 HTTP {response.status_code} Error from FTA for {player.get('name')}")
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
            
            new_events.sort(key=lambda x: x.get("timestamp", ""))
            await self.broadcast_kills(new_events, tracked_ids, tracked_names)

    async def broadcast_kills(self, events, tracked_ids, tracked_names):
        channel_id = tracker_db.get("target_thread_id")
        if not channel_id:
            return

        channel = self.bot.get_channel(int(channel_id))
        if not channel:
            try:
                channel = await self.bot.fetch_channel(int(channel_id))
            except Exception as e:
                print(f"⚠️ Discord Fetch Error: {e}")
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
                print(f"⚠️ Discord Send Error (Permissions?): {e}")
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
        if any(isinstance(p, dict) and p.get("player_id") == player_id for p in tracker_db["tracked_players"]):
            return await ctx.respond(f"⚠️ **{player_name}** is already tracked.", ephemeral=True)

        tracker_db["tracked_players"].append({"name": player_name, "player_id": player_id, "profile_url": profile_url})
        _save_tracker()
        await ctx.respond(f"✅ Telemetry locked onto: **{player_name}**", ephemeral=True)

    @discord.slash_command(name="tracker_config", description="Set THIS thread/channel for live API broadcasts")
    async def tracker_config(self, ctx):
        tracker_db["target_thread_id"] = ctx.channel.id
        _save_tracker()
        await ctx.respond(f"🎯 Output synchronized.", ephemeral=True)
        # Validation test message
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
        
        payload = {
            "0": {
                "json": {"playerId": pid, "serverId": None, "limit": 2},
                "meta": {"values": {"serverId": ["undefined"]}, "v": 1}
            }
        }
        encoded = urllib.parse.quote(json.dumps(payload, separators=(',', ':')))
        url = f"[https://fta.gg/api/trpc/players.getWcsKills?batch=1&input=](https://fta.gg/api/trpc/players.getWcsKills?batch=1&input=){encoded}"
        
        try:
            response = await self.client.get(url)
            if response.status_code != 200:
                resp_text = response.text[:1000]
                error_msg = f"❌ **Cloudflare Blocked the Request (HTTP {response.status_code})**\n```html\n{resp_text}\n```"
                return await ctx.respond(error_msg)
                
            data = response.json()
            data_text = json.dumps(data, indent=2)[:1500]
            success_msg = f"✅ **HTTP 200 OK.** The server replied! Here is exactly what it gave the bot:\n```json\n{data_text}\n```"
            await ctx.respond(success_msg)
            
        except Exception as e:
            err_msg = f"💥 **Fatal Network Error:**\n```\n{e}\n```"
            await ctx.respond(err_msg)

def setup(bot):
    bot.add_cog(TrackerCog(bot))
