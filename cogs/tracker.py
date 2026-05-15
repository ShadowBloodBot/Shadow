# cogs/tracker.py
import os
import json
import asyncio
import traceback
import re
from pathlib import Path
from datetime import datetime

import discord
import httpx
from bs4 import BeautifulSoup
from discord import Option, Interaction
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

TRACKER_STORE = (PERSIST_ROOT / "kill_tracker.json")
tracker_db = {
    "target_thread_id": None,
    "tracked_players": [],  # List of dicts: {"name": str, "profile_url": str}
    "last_seen_ids": {},
    "server_map": {
        "Server 1": "https://fta.gg/servers/cmmhhqso80000p1h6vkd35n7x",
        "Server 2": "https://fta.gg/servers/cmmisvn1j0000rr959s5dbvet",
        "Server 3": "https://fta.gg/servers/cmmit0zmm0009rr953nn0mkwo",
        "Server 4": "https://fta.gg/servers/cmmiwb0fa000wrr959azzr5my"
    }
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

# --- TELEMETRY COG ---
class TrackerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._load_data()
        self.client = httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers={
            "User-Agent": "ShadowSyn Systems Architect/3.2 (Production Telemetry)"
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

    async def _extract_player_name(self, profile_url: str):
        """Resolves an fta.gg profile URL to a case-sensitive in-game name."""
        try:
            response = await self.client.get(profile_url)
            if response.status_code != 200:
                return None
            
            soup = BeautifulSoup(response.text, "html.parser")
            # Strategy: Find the main heading or meta titles where FTA stores character names
            name_tag = soup.find("h1")
            if name_tag:
                return name_tag.get_text().strip()
            
            meta_title = soup.find("meta", property="og:title")
            if meta_title:
                return meta_title["content"].split("-")[0].strip()
                
            return None
        except:
            return None

    @tasks.loop(minutes=1)
    async def feed_monitor(self):
        if not tracker_db["target_thread_id"]:
            return

        tracked_names = [p["name"].lower() for p in tracker_db["tracked_players"]]

        for server_name, url in tracker_db["server_map"].items():
            try:
                response = await self.client.get(url)
                if response.status_code != 200:
                    continue

                soup = BeautifulSoup(response.text, "html.parser")
                # Detect activity elements (divs, table rows, or paragraphs containing 'killed')
                activity_rows = soup.find_all(lambda tag: tag.name in ["div", "tr", "p"] and "killed" in tag.text.lower())
                
                new_events = []
                for row in activity_rows:
                    full_text = row.get_text(separator=" ").strip()
                    text = " ".join(full_text.split()) # Normalize whitespace
                    
                    if "killed" not in text.lower():
                        continue

                    # Create unique anchor for this kill event
                    event_id = str(hash(f"{server_name}_{text}"))
                    if event_id == tracker_db["last_seen_ids"].get(server_name):
                        break
                    
                    # Pattern matching: [Killer] killed [Victim] [KD: X.X]
                    match = re.search(r"^(.*?)\s+killed\s+(.*?)(?:\s+\[KD:\s*([\d\.]+)\])?.*$", text, re.IGNORECASE)
                    
                    if not match:
                        continue
                        
                    killer_name = match.group(1).strip()
                    victim_part = match.group(2).strip()
                    # Isolate victim name from potential trailing text
                    victim_name = victim_part.split(" ")[0].strip()
                    kd = match.group(3) if match.group(3) else "N/A"

                    # Filtration logic
                    is_relevant = False
                    if not tracked_names:
                        is_relevant = True # Global mode
                    else:
                        if killer_name.lower() in tracked_names or victim_name.lower() in tracked_names:
                            is_relevant = True

                    if is_relevant:
                        new_events.append({
                            "killer": killer_name,
                            "victim": victim_name,
                            "kd": kd,
                            "server": server_name,
                            "event_id": event_id
                        })

                if new_events:
                    tracker_db["last_seen_ids"][server_name] = new_events[0]["event_id"]
                    _save_tracker()
                    await self.broadcast_kills(new_events[::-1])

            except Exception:
                print(f"📡 Telemetry Fault [{server_name}]: {traceback.format_exc()}")

    async def broadcast_kills(self, events):
        channel = self.bot.get_channel(tracker_db["target_thread_id"])
        if not channel:
            return

        tracked_names = [p["name"].lower() for p in tracker_db["tracked_players"]]

        for event in events:
            # Color logic based on friend/foe outcome
            is_killer_tracked = event["killer"].lower() in tracked_names
            is_victim_tracked = event["victim"].lower() in tracked_names
            
            if is_killer_tracked:
                color = THEME_WIN
            elif is_victim_tracked:
                color = THEME_LOSS
            else:
                color = THEME_PRIMARY

            embed = discord.Embed(
                title=f"⚔️ Kill Feed | {event['server']}",
                description=f"**{event['killer']}** eliminated **{event['victim']}**",
                color=color,
                timestamp=datetime.utcnow()
            )
            embed.add_field(name="Current KD", value=f"📊 `{event['kd']}`", inline=True)
            embed.set_footer(text="FTA.gg Live Analysis")
            
            try:
                await channel.send(embed=embed)
                await asyncio.sleep(1.2)
            except:
                break

    # --- SLASH COMMANDS ---

    @discord.slash_command(name="track_profile", description="Track a player using their fta.gg profile URL")
    async def track_profile(self, ctx, profile_url: Option(str, "Full player profile link from fta.gg")):
        await ctx.defer(ephemeral=True)
        
        if "fta.gg" not in profile_url:
            return await ctx.respond("❌ Invalid URL. Please provide a link from fta.gg", ephemeral=True)

        name = await self._extract_player_name(profile_url)
        if not name:
            return await ctx.respond("❌ Could not resolve player name. Is the profile public?", ephemeral=True)

        if any(p["name"].lower() == name.lower() for p in tracker_db["tracked_players"]):
            return await ctx.respond(f"⚠️ **{name}** is already being monitored.", ephemeral=True)

        tracker_db["tracked_players"].append({"name": name, "profile_url": profile_url})
        _save_tracker()
        await ctx.respond(f"✅ Telemetry locked onto: **{name}**", ephemeral=True)

    @discord.slash_command(name="untrack_player", description="Stop monitoring a player by name")
    async def untrack_player(self, ctx, player_name: Option(str, "Name of the player to remove")):
        initial = len(tracker_db["tracked_players"])
        tracker_db["tracked_players"] = [p for p in tracker_db["tracked_players"] if p["name"].lower() != player_name.lower()]
        
        if len(tracker_db["tracked_players"]) < initial:
            _save_tracker()
            await ctx.respond(f"🗑️ Released monitor for: **{player_name}**", ephemeral=True)
        else:
            await ctx.respond(f"❓ Player **{player_name}** not found in database.", ephemeral=True)

    @discord.slash_command(name="tracker_config", description="Set THIS thread/channel for live fta.gg broadcasts")
    async def tracker_config(self, ctx):
        # UI Bypass: Automatically grabs the channel ID of wherever the command is executed.
        tracker_db["target_thread_id"] = ctx.channel.id
        _save_tracker()
        await ctx.respond(f"🎯 Output thread synchronized to: {ctx.channel.mention}", ephemeral=True)

    @discord.slash_command(name="tracker_list", description="List all monitored FTA profiles")
    async def tracker_list(self, ctx):
        players = tracker_db["tracked_players"]
        if not players:
            return await ctx.respond("📝 Monitor list empty. Currently in Global Server Mode.", ephemeral=True)
        
        desc = "\n".join([f"• **{p['name']}** ([Profile]({p['profile_url']}))" for p in players])
        embed = discord.Embed(title="📑 Current Watch List", description=desc, color=THEME_PRIMARY)
        await ctx.respond(embed=embed, ephemeral=True)

def setup(bot):
    bot.add_cog(TrackerCog(bot))
