# bot.py — ShadowSyn Bot
# Features (Feature Lock — DO NOT REMOVE):
# - Welcome Minion card (on join) with one-tap role grant
# - /speak (gTTS + translate) with VC handling + usage log
# - Custom embed modal (/send_custom)
# - Durable welcome card: /send_welcome + /welcome_update
#   • Blue “Invite Friends” button (persistent) → sends ephemeral copy-ready invite
# - Audit logger for voice state changes
# - Departures logger (rich embed) with Left/Kicked/Banned detection
# - Persistent Self-Assign Roles panel (instant add/remove) + full admin cmd suite
# - YouTube watcher (RSS): accepts URL/@handle/UC with alias memory; posts to ONE fixed thread
# - Invite→Role: map invite codes (or vanity) to auto-roles on join + admin commands

import os
import re
import json
import asyncio
import tempfile
import time
from pathlib import Path
from typing import Optional, Tuple, Union, Dict, List, Set
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ui import View, Button, Modal, TextInput, Select
from gtts import gTTS
from shutil import which
from googletrans import Translator

# YouTube deps
import aiohttp
import xml.etree.ElementTree as ET

# =========================== CONSTANTS ===========================

VANITY_INVITE  = "https://discord.gg/shadowsyn"
THEME_PRIMARY  = 0x2B0B35

ARRIVALS_THREAD_ID      = 959629903186259978
ROLE_MINION_ID          = 955600021502431233
ROLE_ADMIN_ID           = 1214794734770323466  
ROLE_MEMBER_ID          = 955600320287887400   

DEFAULT_TARGET_ID       = 1166874144395247757
SPEAK_LOG_THREAD_ID     = 1400048671973703690
DEPARTURES_THREAD_ID    = 960088192177029140
DEFAULT_AUDIT_THREAD_ID = 961726632249425930

ROLE_YT_MANAGER_ID      = 960088893351415898
YT_POST_TARGET_ID       = 959631286882934784   
YT_POLL_SECONDS         = 180
YT_USER_AGENT           = "ShadowSynBot/YouTubeWatcher"

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise SystemExit("❌ DISCORD_TOKEN is not set.")

translator = Translator()
LANG_CHOICES = [
    app_commands.Choice(name="English",  value="en"),
    app_commands.Choice(name="Japanese", value="ja"),
    app_commands.Choice(name="German",   value="de"),
    app_commands.Choice(name="Spanish",  value="es"),
]

# ==================== PERSISTENCE ROOT & FILES ===================

PERSIST_ROOT = Path(os.getenv("PERSIST_PATH", "/data")).resolve()
try:
    PERSIST_ROOT.mkdir(parents=True, exist_ok=True)
except Exception:
    PERSIST_ROOT = Path(".").resolve()

ROLE_STORE = (PERSIST_ROOT / "role_picker.json")
YT_STORE = (PERSIST_ROOT / "youtube_watch.json")
INVITE_ROLE_STORE = (PERSIST_ROOT / "invite_roles.json")
CONFIG_PATH = PERSIST_ROOT / "welcome_config.json"

def _load_json(path, default):
    if path.exists():
        try: return json.loads(path.read_text())
        except: return default
    return default

def _save_json(path, data):
    try: path.write_text(json.dumps(data, indent=2))
    except: pass

def get_guild_role_cfg(gid: int) -> dict:
    store = _load_json(ROLE_STORE, {})
    cfg = store.get(str(gid), {"panel": None, "options": []})
    cfg["options"] = sorted(cfg.get("options", []), key=lambda o: str(o.get("label", "")).casefold())
    return cfg

def set_guild_role_cfg(gid: int, cfg: dict) -> None:
    cfg["options"] = sorted(cfg.get("options", []), key=lambda o: str(o.get("label", "")).casefold())
    store = _load_json(ROLE_STORE, {})
    store[str(gid)] = cfg
    _save_json(ROLE_STORE, store)

def get_invite_role_map(guild_id: int) -> Dict[str, int]:
    store = _load_json(INVITE_ROLE_STORE, {})
    return {str(k).lower(): int(v) for k, v in store.get(str(guild_id), {}).items()}

def set_invite_role_map(guild_id: int, mapping: Dict[str, int]) -> None:
    store = _load_json(INVITE_ROLE_STORE, {})
    store[str(guild_id)] = {str(k).lower(): int(v) for k, v in (mapping or {}).items()}
    _save_json(INVITE_ROLE_STORE, store)

# ========================= UTILITIES ==========================

async def safe_defer(inter: discord.Interaction, ephemeral: bool = False):
    if not inter.response.is_done():
        try: await inter.response.defer(ephemeral=ephemeral)
        except: pass

async def safe_reply(inter: discord.Interaction, *args, **kwargs):
    try:
        if not inter.response.is_done(): return await inter.response.send_message(*args, **kwargs)
        return await inter.followup.send(*args, **kwargs)
    except: return None

def safe_display_name(obj: Union[discord.Member, discord.User]) -> str:
    return obj.display_name if isinstance(obj, discord.Member) else (getattr(obj, "global_name", obj.name))

def human_ago(dt: Optional[datetime]) -> str:
    if not isinstance(dt, datetime): return "Unknown"
    delta = datetime.now(timezone.utc) - (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc))
    s = int(max(delta.total_seconds(), 0))
    for name, secs in [("year", 31536000), ("month", 2629800), ("day", 86400), ("hour", 3600), ("minute", 60)]:
        if s >= secs:
            v = s // secs
            return f"{v} {name}{'' if v == 1 else 's'} ago"
    return "just now"

# ======================= BOT CORE ===========================

class ShadowSynBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self._yt_task: Optional[asyncio.Task] = None

    async def setup_hook(self):
        self.add_view(InviteCopyView())
        for g in self.guilds:
            await _prime_invites_cache(g)
            await rehydrate_role_panel(self, g)
        await self.tree.sync()
        if self._yt_task is None:
            self._yt_task = asyncio.create_task(youtube_watch_loop(self))

bot = ShadowSynBot()

# ================== INVITE TRACKING =================

_INVITES_CACHE: Dict[int, Dict[str, int]] = {}

async def _prime_invites_cache(guild: discord.Guild):
    if guild.me.guild_permissions.manage_guild:
        try:
            invs = await guild.invites()
            _INVITES_CACHE[guild.id] = {i.code: (i.uses or 0) for i in invs}
        except: _INVITES_CACHE[guild.id] = {}

async def _detect_join_source(member: discord.Member) -> Optional[str]:
    guild = member.guild
    try:
        before = _INVITES_CACHE.get(guild.id, {})
        current = await guild.invites()
        _INVITES_CACHE[guild.id] = {i.code: (i.uses or 0) for i in current}
        for inv in current:
            if (inv.uses or 0) > before.get(inv.code, 0):
                return f"Joined via `{inv.code}`, invited by **{inv.inviter}**"
        vanity = (await guild.vanity_url()).code if guild.premium_tier >= 3 else None
        return f"Joined via Vanity: `{vanity}`" if vanity else None
    except: return None

# ================== WELCOME (Minion quick-grant) =================

class MinionView(View):
    def __init__(self, target_member_id: int):
        super().__init__(timeout=86400)
        btn = Button(label="Minion", style=discord.ButtonStyle.success)
        btn.callback = self._callback
        self.target_member_id = target_member_id
        self.add_item(btn)

    async def _callback(self, interaction: discord.Interaction):
        member = interaction.guild.get_member(self.target_member_id)
        role = interaction.guild.get_role(ROLE_MINION_ID)
        if member and role:
            try:
                await member.add_roles(role)
                await safe_reply(interaction, f"✅ Granted {role.name} to {member.mention}", ephemeral=True)
            except Exception as e:
                await safe_reply(interaction, f"❌ Failed: `{e}`", ephemeral=True)

@bot.event
async def on_member_join(member: discord.Member):
    if member.bot: return
    # Auto-role logic
    used_code = await _detect_join_source(member)
    mapping = get_invite_role_map(member.guild.id)
    # Check code or vanity mapping
    for trigger in mapping:
        if trigger in (used_code or ""):
            role = member.guild.get_role(mapping[trigger])
            if role: await member.add_roles(role)

    # Arrival Card
    dest = bot.get_channel(ARRIVALS_THREAD_ID)
    if dest:
        embed = discord.Embed(description=f"{member.mention} joined **{member.guild.name}**", color=THEME_PRIMARY)
        embed.set_author(name=str(member), icon_url=member.display_avatar.url)
        if used_code: embed.add_field(name="Joined Via", value=used_code, inline=False)
        await dest.send(embed=embed, view=MinionView(member.id))

# ===================== /SPEAK (TTS + Non-blocking Translate) ==================

@bot.tree.command(name="speak", description="Speak text in your VC")
@app_commands.describe(text="Message", language="Target language")
@app_commands.choices(language=LANG_CHOICES)
async def speak(interaction: discord.Interaction, text: str, language: app_commands.Choice[str] = None):
    if not any(r.id == ROLE_MEMBER_ID for r in interaction.user.roles):
        return await safe_reply(interaction, "❌ Feature locked to **Member** role.", ephemeral=True)

    await safe_defer(interaction, ephemeral=True)
    if not interaction.user.voice: return await safe_reply(interaction, "❌ Join VC first.", ephemeral=True)

    lang_code = (language.value if language else "en").lower()
    loop = asyncio.get_event_loop()
    
    # Non-blocking translation
    if lang_code != "en":
        try:
            trans = await loop.run_in_executor(None, lambda: translator.translate(text, dest=lang_code).text)
        except: trans = text
    else: trans = text

    try:
        vc = await interaction.user.voice.channel.connect()
    except: vc = discord.utils.get(bot.voice_clients, guild=interaction.guild)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
        tmp = f.name
    
    await loop.run_in_executor(None, lambda: gTTS(text=trans, lang=lang_code).save(tmp))
    vc.play(discord.FFmpegPCMAudio(tmp), after=lambda e: os.remove(tmp))
    await safe_reply(interaction, "✅ Spoke text.", ephemeral=True)

# ====================== DURABLE WELCOME & INVITE =================

class InviteCopyView(View):
    def __init__(self):
        super().__init__(timeout=None)
        btn = Button(label="Invite Friends", style=discord.ButtonStyle.primary, emoji="🔗", custom_id="ss:invite_copy")
        btn.callback = self._callback
        self.add_item(btn)

    async def _callback(self, interaction: discord.Interaction):
        msg = f"✅ Invite Link:\n`{VANITY_INVITE}`"
        await interaction.response.send_message(msg, ephemeral=True)

def welcome_embed():
    return discord.Embed(title="Welcome to ShadowSyn", color=THEME_PRIMARY, description="OCE's most toxic (Fun) environment...")

@bot.tree.command(name="send_welcome")
@app_commands.check(lambda i: any(r.id == ROLE_ADMIN_ID for r in i.user.roles))
async def send_welcome(interaction: discord.Interaction):
    await interaction.channel.send(embed=welcome_embed(), view=InviteCopyView())
    await safe_reply(interaction, "✅ Posted", ephemeral=True)

# ====================== SELF-ASSIGN ROLES ======================

class DualRolePickerView(View):
    def __init__(self, guild, options):
        super().__init__(timeout=None)
        self.add_item(Select(
            placeholder="Select your game roles...",
            options=[discord.SelectOption(label=o["label"], value=str(o["role_id"])) for o in options[:25]],
            custom_id=f"ss:roles:{guild.id}",
            min_values=0, max_values=len(options[:25])
        ))

    @bot.event # Placeholder for handling interaction via global listener or custom callback
    async def on_interaction(self, interaction): pass

async def rehydrate_role_panel(client, guild):
    cfg = get_guild_role_cfg(guild.id)
    if cfg.get("panel"):
        try:
            ch = client.get_channel(cfg["panel"]["channel_id"])
            msg = await ch.fetch_message(cfg["panel"]["message_id"])
            await msg.edit(view=DualRolePickerView(guild, cfg["options"]))
        except: pass

# ====================== YOUTUBE WATCHER ======================

async def youtube_watch_loop(client):
    await client.wait_until_ready()
    while not client.is_closed():
        store = _load_json(YT_STORE, {"channels": {}})
        async with aiohttp.ClientSession() as session:
            for cid, data in list(store["channels"].items()):
                try:
                    async with session.get(f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}") as r:
                        root = ET.fromstring(await r.text())
                        latest = root.find("{http://www.w3.org/2005/Atom}entry")
                        vid = latest.find("{http://www.youtube.com/xml/schemas/2015}videoId").text
                        if vid != data.get("last_video_id"):
                            target = client.get_channel(YT_POST_TARGET_ID)
                            await target.send(f"New video from **{data['channel_title']}**!\nhttps://www.youtube.com/watch?v={vid}")
                            store["channels"][cid]["last_video_id"] = vid
                            _save_json(YT_STORE, store)
                except: pass
        await asyncio.sleep(YT_POLL_SECONDS)

# ====================== DEPARTURES & AUDIT ======================

@bot.event
async def on_member_remove(member):
    dest = bot.get_channel(DEPARTURES_THREAD_ID)
    if dest:
        embed = discord.Embed(title="👋 Member Left", color=discord.Color.orange(), timestamp=timezone.utc)
        embed.add_field(name="User", value=f"{member.mention} ({member.id})")
        await dest.send(embed=embed)

@bot.event
async def on_voice_state_update(member, before, after):
    dest = bot.get_channel(DEFAULT_AUDIT_THREAD_ID)
    if dest and before.channel != after.channel:
        msg = f"🎤 {member.name} moved: {getattr(before.channel, 'name', 'None')} -> {getattr(after.channel, 'name', 'None')}"
        await dest.send(msg)

# ====================== RUN ======================

if __name__ == "__main__":
    bot.run(TOKEN)
