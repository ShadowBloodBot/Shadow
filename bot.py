# bot.py — ShadowSyn (Final: Owner-Only Economy Control)
#
# === FEATURES ===
# 1. VoiceMaster: Join-to-Create VCs + Control Panel
# 2. Music: Crash-Proof Playback + Zombie Connection Fix
# 3. Clip System: Force Recording (Records "Unknown" users too)
# 4. Haste Facts: /haste (Public) + /morehaste (Admin)
# 5. Scoins Economy: /pull, /bet (Visuals), /wallet, /leaderboard
#
# LIBRARY REQUIREMENT: py-cord[voice] (NOT discord.py)

import os
import re
import json
import asyncio
import tempfile
import time
import traceback
import wave
import io
import subprocess
import random
from pathlib import Path
from typing import Optional, Tuple, Union, Dict, List, Set
from datetime import datetime, timezone, timedelta
from collections import deque

import discord
from discord import Option, ButtonStyle, SelectOption, Interaction
from discord.ui import View, Button, Modal, TextInput, Select
from discord.ext import commands

# --- AUDIO SINK (Native to Py-Cord) ---
try:
    from discord.sinks import Sink, Filters, default_filters
    HAS_SINKS = True
except ImportError:
    HAS_SINKS = False
    print("⚠️ WARNING: 'discord.sinks' not found. Ensure you are using py-cord.")
    class Sink: pass

from gtts import gTTS
from shutil import which
from googletrans import Translator
from discord.utils import get

# --- NATIVE MUSIC DEPENDENCY ---
import yt_dlp

# =========================== CONSTANTS ===========================

VANITY_INVITE  = "https://discord.gg/shadowsyn"
THEME_PRIMARY  = 0x2B0B35
THEME_WIN      = 0x43B581 # Green
THEME_LOSS     = 0xF04747 # Red
THEME_GOLD     = 0xFFD700 # Gold

# Channel & Role IDs
ARRIVALS_THREAD_ID      = 959629903186259978
ROLE_MINION_ID          = 955600021502431233
SPEAK_LOG_THREAD_ID     = 1400048671973703690
DEPARTURES_THREAD_ID    = 960088192177029140
DEFAULT_TARGET_ID       = 1166874144395247757
DEFAULT_AUDIT_THREAD_ID = 961726632249425930
CLIPS_TARGET_ID         = 1467055136609271818

# --- PERMISSION ROLES & USERS ---
ROLE_ADMIN_ID           = 1214794734770323466 
ROLE_DJ_ID              = 955600320287887400
OWNER_ID                = 482463400929263627 

# VoiceMaster Config
JOIN_TO_CREATE_CHANNEL_ID = 1398618132788281364
VC_CATEGORY_ID            = 908659586536468542
VC_DEFAULT_BITRATE        = 384000
VC_DEFAULT_USER_LIMIT     = 0
ADMIN_ROLE_NAME           = "SHADOW"

# Economy Config
SCOIN_PULL_AMOUNT = 5
SCOIN_COOLDOWN_HOURS = 24

# Default Haste Facts
DEFAULT_HASTE_FACTS = [
    "Haste is a man lover",
    "Haste feeds knights to spearmen",
    "Haste is the potato peeler",
    "Haste hates women",
    "Haste loves fat chicks",
    "Haste would die for brightwood, bro",
    "Haste is a fitzroy enjoyer",
    "Haste used to get feudal in 3mins... used to",
    "Haste goes Pro scout",
    "Haste is in a good mood. Jks.",
    "Haste loves dating paki protestors",
    "Haste is a lefty greeny",
    "Haste has no dps",
    "Haste has beef with a dev of a game with sub 1000 players",
    "Haste cant afford ranger gear so he blames the dev",
    "Haste thinks Maya is fat",
    "Haste was MIA in Shadow Until Jed showed up",
    "Everyone prefers Haste over Boet",
    "Everyone likes it when Haste has a break down",
    "Everyone is scared Haste might get bashed at his restaurant",
    "Haste earns 70k a year and that gives Blood anxiety",
    "Haste Likes using a bow",
    "Haste doesn't have the muscle mass to carry a real life weapon. That's why he hates Military Sim Games.",
    "Haste never let go of New world, and it affects all of his current relationships.",
    "Haste only played Vrising cause he thought the outfits were cute."
]

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise SystemExit("❌ DISCORD_TOKEN is not set.")

translator = Translator()

LANG_CHOICES = [
    "English", "Japanese", "German", "Spanish", "French", 
    "Italian", "Portuguese", "Russian", "Korean", "Chinese", "Hindi", "Indonesian"
]
LANG_CODES = {
    "English": "en", "Japanese": "ja", "German": "de", "Spanish": "es", 
    "French": "fr", "Italian": "it", "Portuguese": "pt", "Russian": "ru",
    "Korean": "ko", "Chinese": "zh-CN", "Hindi": "hi", "Indonesian": "id"
}

# ==================== PERSISTENCE ===================

PERSIST_ROOT = Path(os.getenv("PERSIST_PATH", "/data")).resolve()
try:
    PERSIST_ROOT.mkdir(parents=True, exist_ok=True)
except:
    PERSIST_ROOT = Path(".").resolve()

ROLE_STORE = (PERSIST_ROOT / "role_picker.json")
INVITE_ROLE_STORE = (PERSIST_ROOT / "invite_roles.json")
ACTIVE_VCS_STORE = (PERSIST_ROOT / "active_vcs.json")
HASTE_FACTS_STORE = (PERSIST_ROOT / "haste_facts.json")
SCOINS_STORE = (PERSIST_ROOT / "scoins.json")

# Global Variables
active_haste_facts = []
scoins_db = {} # {user_id: {"balance": int, "last_pull": float}}

def _load_persistence():
    global active_haste_facts, scoins_db
    
    # Haste Facts
    if HASTE_FACTS_STORE.exists():
        try: active_haste_facts = json.loads(HASTE_FACTS_STORE.read_text())
        except: active_haste_facts = list(DEFAULT_HASTE_FACTS)
    else:
        active_haste_facts = list(DEFAULT_HASTE_FACTS)
        
    # Scoins
    if SCOINS_STORE.exists():
        try: scoins_db = json.loads(SCOINS_STORE.read_text())
        except: scoins_db = {}
    else:
        scoins_db = {}

def _save_haste_facts():
    try: HASTE_FACTS_STORE.write_text(json.dumps(active_haste_facts))
    except: pass

def _save_scoins():
    try: SCOINS_STORE.write_text(json.dumps(scoins_db))
    except: pass

# --- SCOINS HELPERS ---
def get_balance(user_id: str) -> int:
    return scoins_db.get(user_id, {}).get("balance", 0)

def update_balance(user_id: str, amount: int):
    user_id = str(user_id)
    if user_id not in scoins_db:
        scoins_db[user_id] = {"balance": 0, "last_pull": 0}
    scoins_db[user_id]["balance"] += amount
    _save_scoins()

# ==================== PERMISSION DECORATORS ====================

def admin_only():
    def predicate(ctx):
        if not isinstance(ctx.author, discord.Member): return False
        return any(r.id == ROLE_ADMIN_ID for r in ctx.author.roles)
    return commands.check(predicate)

def dj_or_admin():
    def predicate(ctx):
        if not isinstance(ctx.author, discord.Member): return False
        # Allow if Admin OR DJ
        if any(r.id == ROLE_ADMIN_ID for r in ctx.author.roles): return True
        if any(r.id == ROLE_DJ_ID for r in ctx.author.roles): return True
        return False
    return commands.check(predicate)

def owner_only():
    def predicate(ctx):
        return ctx.author.id == OWNER_ID
    return commands.check(predicate)

# ==================== MUSIC ENGINE CONFIG ====================

YTDL_PLAY_OPTIONS = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'socket_timeout': 10,
    'retries': 5,
}

YTDL_SEARCH_OPTIONS = YTDL_PLAY_OPTIONS.copy()
YTDL_SEARCH_OPTIONS.update({
    'extract_flat': True,
    'skip_download': True,
})

FFMPEG_OPTIONS = {
    'options': '-vn',
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
}

ytdl_play = yt_dlp.YoutubeDL(YTDL_PLAY_OPTIONS)
ytdl_search = yt_dlp.YoutubeDL(YTDL_SEARCH_OPTIONS)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True):
        loop = loop or asyncio.get_running_loop()
        data = await loop.run_in_executor(None, lambda: ytdl_play.extract_info(url, download=not stream))
        if 'entries' in data:
            data = data['entries'][0]
        filename = data['url'] if stream else ytdl_play.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS), data=data)

# ==================== AUTO-CLIP SYSTEM ====================

if HAS_SINKS:
    class RingBufferSink(Sink):
        """Captures the last N seconds of audio in a rolling buffer."""
        def __init__(self, time_limit=30):
            super().__init__()
            self.time_limit = time_limit
            self.buffer = {} # user_id -> deque of bytes
            self._debug_log_counter = 0

        def write(self, user, data):
            if hasattr(user, "data") or isinstance(user, (bytes, bytearray)):
                user, data = data, user

            user_id = "unknown"
            if user and hasattr(user, 'id'):
                user_id = user.id

            if user_id not in self.buffer:
                self.buffer[user_id] = deque(maxlen=int(self.time_limit * 50))
            
            audio_bytes = getattr(data, "pcm", None) or getattr(data, "data", None)
            if not audio_bytes and isinstance(data, (bytes, bytearray)):
                audio_bytes = data
            
            if audio_bytes and isinstance(audio_bytes, (bytes, bytearray)):
                self.buffer[user_id].append(audio_bytes)

        def cleanup(self):
            self.finished = True

else:
    RingBufferSink = None

async def dummy_callback(sink, *args):
    pass

# ==================== UTILS ====================

def _load_active_vcs() -> Set[int]:
    if ACTIVE_VCS_STORE.exists():
        try: return set(json.loads(ACTIVE_VCS_STORE.read_text()))
        except: return set()
    return set()

def _save_active_vcs(vcs: Set[int]) -> None:
    try: ACTIVE_VCS_STORE.write_text(json.dumps(list(vcs)))
    except: pass

active_temp_vcs: Set[int] = _load_active_vcs()

def _to_sans_bold_italic(text: str) -> str:
    _map = {
        "A": "𝘼", "B": "𝘽", "C": "𝘾", "D": "𝘿", "E": "𝙀", "F": "𝙁", "G": "𝙂",
        "H": "𝙃", "I": "𝙄", "J": "𝙅", "K": "𝙆", "L": "𝙇", "M": "𝙈", "N": "𝙉",
        "O": "𝙊", "P": "𝙋", "Q": "𝙌", "R": "𝙍", "S": "𝙎", "T": "𝙏", "U": "𝙐",
        "V": "𝙑", "W": "𝙒", "X": "𝙓", "Y": "𝙔", "Z": "𝙕",
        "a": "𝙖", "b": "𝙗", "c": "𝙘", "d": "𝙙", "e": "𝙚", "f": "𝙛", "g": "𝙜",
        "h": "𝙝", "i": "𝙞", "j": "𝙟", "k": "𝙠", "l": "𝙡", "m": "𝙢", "n": "𝙣",
        "o": "𝙤", "p": "𝙥", "q": "𝙦", "r": "𝙧", "s": "𝙨", "t": "𝙩", "u": "𝙪",
        "v": "𝙫", "w": "𝙬", "x": "𝙭", "y": "𝙮", "z": "𝙯",
    }
    return "".join(_map.get(ch, ch) for ch in text)

def _limit_channel_name(name: str, limit: int = 100) -> str:
    return name[:limit] if len(name) > limit else name

async def safe_reply(ctx_or_inter, *args, **kwargs):
    try:
        if hasattr(ctx_or_inter, 'respond'):
            return await ctx_or_inter.respond(*args, **kwargs)
        elif hasattr(ctx_or_inter, 'response'):
            if not ctx_or_inter.response.is_done():
                return await ctx_or_inter.response.send_message(*args, **kwargs)
            else:
                return await ctx_or_inter.followup.send(*args, **kwargs)
    except: return None

async def safe_defer(ctx, ephemeral=False):
    try:
        await ctx.defer(ephemeral=ephemeral)
    except: pass

async def resolve_target(client: discord.Client, target_id: int):
    ch = client.get_channel(target_id)
    if ch is None:
        try: ch = await client.fetch_channel(target_id)
        except: return None, None
    if isinstance(ch, discord.TextChannel): return ch, ch
    if isinstance(ch, discord.Thread):
        try:
            if ch.archived or ch.locked: await ch.edit(archived=False, locked=False)
            await ch.join()
        except: pass
        parent = ch.parent if isinstance(ch.parent, discord.TextChannel) else None
        return ch, parent
    return None, None

async def ensure_voice_simple(ctx):
    user = ctx.user if isinstance(ctx, discord.Interaction) else ctx.author
    if not user.voice:
        await safe_reply(ctx, "❌ Join a VC first!", ephemeral=True)
        return None
    
    channel = user.voice.channel
    vc = ctx.guild.voice_client

    try:
        if vc and not vc.is_connected():
            try: await vc.disconnect(force=True)
            except: pass
            vc = None

        if vc:
            if vc.channel.id != channel.id:
                await vc.move_to(channel)
        else:
            vc = await channel.connect(timeout=10, reconnect=True)
        
        if HAS_SINKS and vc and vc.is_connected():
            if not vc.recording:
                try:
                    vc.start_recording(RingBufferSink(time_limit=30), dummy_callback)
                    print(f"🎙️ Auto-recording started in {channel.name}")
                except Exception as e:
                    print(f"⚠️ Auto-recording failed: {e}")
        
        return vc
    except Exception as e:
        await safe_reply(ctx, f"❌ Voice Error: {e}", ephemeral=True)
        return None

# ==================== VOICEMASTER COMPONENTS =================

class VCNameModal(Modal):
    def __init__(self, vc):
        super().__init__(title="Rename Voice Channel")
        self.vc = vc
        self.add_item(TextInput(label="New VC Name", placeholder="Enter name...", required=True, max_length=50))

    async def callback(self, interaction: Interaction):
        new_name = self.children[0].value
        try:
            await self.vc.edit(name=new_name)
            await interaction.response.send_message(f"✅ Renamed to **{new_name}**", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed: {e}", ephemeral=True)

class KickMemberDropdown(Select):
    def __init__(self, vc, members):
        options = [SelectOption(label=m.display_name, value=str(m.id)) for m in members]
        super().__init__(placeholder="Select member to kick...", options=options, min_values=1, max_values=1)
        self.vc = vc

    async def callback(self, interaction: Interaction):
        try:
            member_id = int(self.values[0])
            member = self.vc.guild.get_member(member_id)
            if member and member in self.vc.members:
                await member.move_to(None)
                await interaction.response.send_message(f"👢 Kicked {member.display_name}.", ephemeral=True)
            else:
                await interaction.response.send_message("⚠️ Member no longer in VC.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed: {e}", ephemeral=True)

class KickMemberView(View):
    def __init__(self, vc: discord.VoiceChannel, members):
        super().__init__(timeout=30)
        self.add_item(KickMemberDropdown(vc, members))

class RoleRestrictSelect(Select):
    def __init__(self, vc: discord.VoiceChannel, creator: discord.Member):
        self.vc = vc
        self.creator = creator
        options = [SelectOption(label="Everyone (default)", value="everyone", description="Allow all members")]
        roles = [r for r in vc.guild.roles if r != vc.guild.default_role and not r.managed]
        roles_sorted = sorted(roles, key=lambda r: r.position, reverse=True)[:24]
        for r in roles_sorted:
            label = (r.name or f"Role {r.id}")[:100]
            options.append(SelectOption(label=label, value=str(r.id)))
        super().__init__(placeholder="Restrict VC to a role…", options=options, min_values=1, max_values=1, custom_id="restrict_role_select")

    async def callback(self, interaction: Interaction):
        if interaction.user.id != self.creator.id:
            return await interaction.response.send_message("🚫 Only the VC creator can use this.", ephemeral=True)
        guild = interaction.guild
        admin_role = discord.utils.get(guild.roles, name=ADMIN_ROLE_NAME)
        try:
            sel = self.values[0]
            if sel == "everyone":
                await self.vc.set_permissions(guild.default_role, connect=True)
                await self.vc.set_permissions(self.creator, connect=True)
                if admin_role: await self.vc.set_permissions(admin_role, connect=True)
                await interaction.response.send_message("✅ Restriction cleared.", ephemeral=True)
                return
            role_id = int(sel)
            selected_role = guild.get_role(role_id)
            if not selected_role:
                return await interaction.response.send_message("⚠️ Role not found.", ephemeral=True)
            await self.vc.set_permissions(guild.default_role, connect=False)
            await self.vc.set_permissions(selected_role, connect=True)
            await self.vc.set_permissions(self.creator, connect=True)
            if admin_role: await self.vc.set_permissions(admin_role, connect=True)
            await interaction.response.send_message(f"🔐 Restricted to: **{selected_role.name}**.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed: {e}", ephemeral=True)

class VCControlPanel(View):
    def __init__(self, vc: discord.VoiceChannel, creator: discord.Member):
        super().__init__(timeout=None)
        self.vc = vc
        self.creator = creator
        try: self.add_item(RoleRestrictSelect(vc, creator))
        except: pass

    async def _check_perm(self, interaction: Interaction) -> bool:
        if interaction.user.id == self.creator.id: return True
        if interaction.data.get("custom_id") == "delete_vc":
            if any(r.name == ADMIN_ROLE_NAME or r.id == ROLE_ADMIN_ID for r in interaction.user.roles): return True
        await interaction.response.send_message("🚫 Only the VC creator can use this.", ephemeral=True)
        return False

    @discord.ui.button(label="🔒 Lock", style=ButtonStyle.danger, custom_id="lock_vc")
    async def lock(self, button: Button, interaction: Interaction):
        if not await self._check_perm(interaction): return
        try:
            overwrites = {interaction.guild.default_role: discord.PermissionOverwrite(connect=False), self.creator: discord.PermissionOverwrite(connect=True)}
            ar = discord.utils.get(interaction.guild.roles, name=ADMIN_ROLE_NAME)
            if ar: overwrites[ar] = discord.PermissionOverwrite(connect=True)
            await self.vc.edit(overwrites=overwrites)
            await interaction.response.send_message("🔒 VC locked.", ephemeral=True)
        except Exception as e: await interaction.response.send_message(f"❌ Failed: {e}", ephemeral=True)

    @discord.ui.button(label="🔓 Unlock", style=ButtonStyle.success, custom_id="unlock_vc")
    async def unlock(self, button: Button, interaction: Interaction):
        if not await self._check_perm(interaction): return
        try:
            await self.vc.set_permissions(interaction.guild.default_role, connect=True)
            await interaction.response.send_message("🔓 VC unlocked.", ephemeral=True)
        except: pass

    @discord.ui.button(label="❌ Delete", style=ButtonStyle.red, custom_id="delete_vc")
    async def delete(self, button: Button, interaction: Interaction):
        if not await self._check_perm(interaction): return
        try:
            await self.vc.delete()
            await interaction.response.send_message("🗑️ Deleted.", ephemeral=True)
        except: pass

    @discord.ui.button(label="✏️ Rename", style=ButtonStyle.blurple, custom_id="rename_vc")
    async def rename(self, button: Button, interaction: Interaction):
        if not await self._check_perm(interaction): return
        await interaction.response.send_modal(VCNameModal(self.vc))

    @discord.ui.button(label="👢 Kick", style=ButtonStyle.gray, custom_id="kick_members")
    async def kick(self, button: Button, interaction: Interaction):
        if not await self._check_perm(interaction): return
        members = [m for m in self.vc.members if m != interaction.guild.me]
        if not members: return await interaction.response.send_message("⚠️ No members to kick.", ephemeral=True)
        await interaction.response.send_message("Select member:", view=KickMemberView(self.vc, members), ephemeral=True)

    @discord.ui.select(placeholder="Bitrate", options=[SelectOption(label="64 kbps", value="64000"), SelectOption(label="96 kbps", value="96000"), SelectOption(label="128 kbps", value="128000"), SelectOption(label="256 kbps", value="256000"), SelectOption(label="384 kbps", value="384000")], custom_id="bitrate_select")
    async def bitrate(self, select: Select, interaction: Interaction):
        if not await self._check_perm(interaction): return
        try:
            await self.vc.edit(bitrate=int(select.values[0]))
            await interaction.response.send_message(f"📶 Bitrate: {int(select.values[0])//1000} kbps.", ephemeral=True)
        except Exception as e: await interaction.response.send_message(f"❌ Failed: {e}", ephemeral=True)

    @discord.ui.select(placeholder="User Limit", options=[SelectOption(label="Unlimited", value="0"), SelectOption(label="2", value="2"), SelectOption(label="5", value="5"), SelectOption(label="10", value="10"), SelectOption(label="25", value="25")], custom_id="limit_select")
    async def limit(self, select: Select, interaction: Interaction):
        if not await self._check_perm(interaction): return
        try:
            await self.vc.edit(user_limit=int(select.values[0]))
            await interaction.response.send_message(f"👥 Limit: {select.values[0]}.", ephemeral=True)
        except Exception as e: await interaction.response.send_message(f"❌ Failed: {e}", ephemeral=True)

async def send_control_panel(vc: discord.VoiceChannel, creator: discord.Member):
    try:
        await asyncio.sleep(2.0)
        await vc.send(content=f"{creator.mention}, here is your **VoiceMaster** controls:", view=VCControlPanel(vc, creator))
    except: pass

# ==================== GENERAL LOADERS ====================

def _load_role_store() -> Dict[str, dict]:
    if ROLE_STORE.exists():
        try: return json.loads(ROLE_STORE.read_text())
        except: return {}
    return {}

def _save_role_store(data: Dict[str, dict]) -> None:
    try: ROLE_STORE.write_text(json.dumps(data, indent=2))
    except: pass

def get_guild_role_cfg(gid: int) -> dict:
    store = _load_role_store()
    cfg = store.get(str(gid), {"panel": None, "options": []})
    cfg["options"] = sorted(cfg.get("options", []), key=lambda o: str(o.get("label", "")).casefold())
    return cfg

def set_guild_role_cfg(gid: int, cfg: dict) -> None:
    cfg["options"] = sorted(cfg.get("options", []), key=lambda o: str(o.get("label", "")).casefold())
    store = _load_role_store()
    store[str(gid)] = cfg
    _save_role_store(store)

def _load_invite_role_store() -> Dict[str, dict]:
    if INVITE_ROLE_STORE.exists():
        try: return json.loads(INVITE_ROLE_STORE.read_text())
        except: return {}
    return {}

def _save_invite_role_store(data: Dict[str, dict]) -> None:
    try: INVITE_ROLE_STORE.write_text(json.dumps(data, indent=2))
    except: pass

def get_invite_role_map(guild_id: int) -> Dict[str, int]:
    store = _load_invite_role_store()
    raw = store.get(str(guild_id), {})
    return {str(k).lower(): int(v) for k, v in raw.items()} if isinstance(raw, dict) else {}

def set_invite_role_map(guild_id: int, mapping: Dict[str, int]) -> None:
    store = _load_invite_role_store()
    store[str(guild_id)] = {str(k).lower(): int(v) for k, v in (mapping or {}).items()}
    _save_invite_role_store(store)

_INVITE_CODE_RX = re.compile(r"(?:discord\.gg/|discord\.com/invite/)(?P<code>[A-Za-z0-9-]+)", re.I)
def normalize_invite_code(text: str) -> Optional[str]:
    s = (text or "").strip()
    if not s: return None
    low = s.lower()
    if low in {"vanity", "vanity_url", "vanityurl"}: return "vanity"
    m = _INVITE_CODE_RX.search(s)
    if m: return m.group("code").lower()
    if re.fullmatch(r"[A-Za-z0-9-]{2,}", s): return s.lower()
    return None

def safe_avatar_url(member: Union[discord.Member, discord.User]) -> Optional[str]:
    try: return member.display_avatar.url
    except: return None

def utcnow(): return datetime.now(timezone.utc)
def ffmpeg_available() -> bool: return which("ffmpeg") is not None

async def resolve_target(client: discord.Client, target_id: int):
    ch = client.get_channel(target_id)
    if ch is None:
        try: ch = await client.fetch_channel(target_id)
        except: return None, None
    if isinstance(ch, discord.TextChannel): return ch, ch
    if isinstance(ch, discord.Thread):
        try:
            if ch.archived or ch.locked: await ch.edit(archived=False, locked=False)
            await ch.join()
        except: pass
        parent = ch.parent if isinstance(ch.parent, discord.TextChannel) else None
        return ch, parent
    return None, None

def human_ago(dt: Optional[datetime]) -> str:
    if not isinstance(dt, datetime): return "Unknown"
    if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
    delta = utcnow() - dt
    s = int(max(delta.total_seconds(), 0))
    if s < 60: return "just now"
    units = [("year", 31536000), ("month", 2629800), ("day", 86400), ("hour", 3600), ("minute", 60)]
    for name, secs in units:
        if s >= secs:
            v = s // secs
            return f"{v} {name}{'' if v == 1 else 's'} ago"
    return "just now"

def safe_display_name(obj):
    try: return obj.display_name if isinstance(obj, discord.Member) else (obj.global_name or obj.name)
    except: return str(obj)

# ======================= INVITE ATTRIBUTION ======================

_INVITES_CACHE: Dict[int, Dict[str, int]] = {}

def _can_track_invites(guild: discord.Guild) -> bool:
    return bool(guild.me and guild.me.guild_permissions.manage_guild)

async def _prime_invites_cache(guild: discord.Guild):
    if not _can_track_invites(guild):
        _INVITES_CACHE[guild.id] = {}
        return
    try:
        invites = await guild.invites()
        _INVITES_CACHE[guild.id] = {inv.code: (inv.uses or 0) for inv in invites}
    except: _INVITES_CACHE[guild.id] = {}

async def _detect_join_source(member: discord.Member) -> Optional[str]:
    guild = member.guild
    if not guild: return None
    if not _can_track_invites(guild):
        try: return f"Joined via Vanity: `{guild.vanity_url_code}`" if guild.vanity_url_code else None
        except: return None
    try:
        before = _INVITES_CACHE.get(guild.id, {})
        current = await guild.invites()
        increased = None
        for inv in current:
            if (inv.uses or 0) > before.get(inv.code, 0):
                increased = inv
                break
        _INVITES_CACHE[guild.id] = {inv.code: (inv.uses or 0) for inv in current}
        if increased:
            return f"Joined via `{increased.code}`, invited by **{increased.inviter or 'Unknown'}**"
        try: return f"Joined via Vanity: `{guild.vanity_url_code}`" if guild.vanity_url_code else None
        except: return None
    except: return None

async def _detect_used_invite_code(member: discord.Member) -> Optional[str]:
    guild = member.guild
    if not guild: return None
    if not _can_track_invites(guild):
        try: return "vanity" if guild.vanity_url_code else None
        except: return None
    try:
        before = _INVITES_CACHE.get(guild.id, {})
        current = await guild.invites()
        increased = None
        for inv in current:
            if (inv.uses or 0) > before.get(inv.code, 0):
                increased = inv
                break
        _INVITES_CACHE[guild.id] = {inv.code: (inv.uses or 0) for inv in current}
        if increased: return increased.code.lower()
        try: return "vanity" if guild.vanity_url_code else None
        except: return None
    except: return None

async def _apply_invite_role(member: discord.Member, used_code: Optional[str]) -> Tuple[bool, str]:
    if not member.guild or not used_code: return False, "Unknown"
    mapping = get_invite_role_map(member.guild.id)
    role_id = mapping.get(used_code.lower())
    if not role_id: return False, "No mapping"
    role = member.guild.get_role(role_id)
    if not role: return False, "Role missing"
    try:
        await member.add_roles(role, reason=f"Auto role via {used_code}")
        return True, role.name
    except Exception as e: return False, str(e)

# ============================ BOT CORE (Py-Cord) ===========================

class ShadowSynBot(discord.Bot):
    def __init__(self):
        super().__init__(intents=discord.Intents.all())
        self.audio_queues: Dict[int, deque] = {} 
        self.synced = False

bot = ShadowSynBot()

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (Py-Cord)")
    
    # Load persistence
    _load_persistence()

    # Primes invitation cache
    for guild in bot.guilds:
        await _prime_invites_cache(guild)
        try: await rehydrate_role_panel(bot, guild)
        except: pass
    
    print(f"Active Temp VCs: {len(active_temp_vcs)} loaded from disk.")

@bot.event
async def on_guild_join(guild: discord.Guild):
    await _prime_invites_cache(guild)
    try: await rehydrate_role_panel(bot, guild)
    except: pass

# ==================== UNIFIED EVENT HANDLING ====================

async def _find_audit_action(guild, action, target_id, window_seconds=30):
    if not (guild.me and guild.me.guild_permissions.view_audit_log): return None
    try:
        async for entry in guild.audit_logs(limit=10, action=action):
            if entry.target and entry.target.id == target_id:
                if (utcnow() - entry.created_at.replace(tzinfo=timezone.utc)).total_seconds() <= window_seconds:
                    return entry
    except: pass
    return None

@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    guild = member.guild
    
    # --- VOICEMASTER LOGIC ---
    if after.channel and after.channel.id == JOIN_TO_CREATE_CHANNEL_ID:
        try:
            print(f"[JTC Debug] {member.display_name} joined JTC channel.")
            category = get(guild.categories, id=VC_CATEGORY_ID) or after.channel.category
            
            base = member.nick or member.name
            styled = _to_sans_bold_italic(f"{base}'s Room")
            final_name = _limit_channel_name(styled)
            
            new_vc = await guild.create_voice_channel(
                name=final_name,
                category=category,
                user_limit=VC_DEFAULT_USER_LIMIT,
                bitrate=VC_DEFAULT_BITRATE
            )
            
            active_temp_vcs.add(new_vc.id)
            _save_active_vcs(active_temp_vcs)
            await member.move_to(new_vc)
            print(f"[JTC Success] Created {new_vc.name} and moved member.")
            
            asyncio.create_task(send_control_panel(new_vc, member))
            
        except Exception as e:
            print(f"[JTC Error] {e}")
            traceback.print_exc()

    # --- AUTO-DELETE LOGIC ---
    if before.channel and before.channel.id != JOIN_TO_CREATE_CHANNEL_ID:
        if before.channel.id in active_temp_vcs:
            if len(before.channel.members) == 0:
                try:
                    await before.channel.delete()
                    active_temp_vcs.discard(before.channel.id)
                    _save_active_vcs(active_temp_vcs)
                    print(f"[JTC Info] Deleted empty channel {before.channel.id}")
                except Exception as e:
                    print(f"[JTC Delete Error] {e}")

    # --- AUDIT LOGIC ---
    if member.bot: return
    target, _ = await resolve_target(bot, DEFAULT_AUDIT_THREAD_ID)
    if not target: return

    m_name = safe_display_name(member)

    if before.channel != after.channel:
        entry = await _find_audit_action(member.guild, discord.AuditLogAction.member_move, member.id)
        if entry:
            actor = safe_display_name(entry.user)
            if before.channel and after.channel: msg = f"🔀 {actor} moved {m_name} {before.channel.name} → {after.channel.name}"
            elif before.channel: msg = f"⏏️ {actor} disconnected {m_name} from {before.channel.name}"
            else: msg = f"📥 {actor} moved {m_name} into {after.channel.name}"
        else:
            if before.channel and not after.channel: msg = f"📤 {m_name} left {before.channel.name}"
            elif not before.channel and after.channel: msg = f"📥 {m_name} joined {after.channel.name}"
            else: msg = f"🔀 {m_name} moved {before.channel.name} → {after.channel.name}"
        try: await target.send(msg)
        except: pass
        return

# ================== WELCOME (Minion quick-grant) =================

def setup_welcome(client: discord.Client):
    class MinionView(View):
        def __init__(self, target_member_id: int):
            super().__init__(timeout=86400)
            self.target_member_id = target_member_id
            btn = Button(label="Minion", style=ButtonStyle.success)
            btn.callback = self._grant_minion
            self.add_item(btn)

        async def _grant_minion(self, interaction: Interaction):
            if not interaction.guild: return
            member = interaction.guild.get_member(self.target_member_id)
            role = interaction.guild.get_role(ROLE_MINION_ID)
            if member and role:
                try:
                    await member.add_roles(role, reason=f"Granted by {interaction.user}")
                    await safe_reply(interaction, f"✅ Gave {role.name} to {member.mention}", ephemeral=True)
                except Exception as e:
                    await safe_reply(interaction, f"❌ Failed: `{e}`", ephemeral=True)

    async def _send_arrival_card(member: discord.Member):
        if member.bot: return
        dest = client.get_channel(ARRIVALS_THREAD_ID)
        if not dest: return
        invite_line = await _detect_join_source(member)
        icon = safe_avatar_url(member)
        embed = discord.Embed(description=f"{member.mention} joined **{member.guild.name}**", color=discord.Color.dark_theme())
        embed.set_author(name=str(member), icon_url=icon)
        if invite_line: embed.add_field(name="Joined Via", value=invite_line, inline=False)
        embed.set_footer(text="Tap to grant Minion")
        await dest.send(embed=embed, view=MinionView(member.id))

    @bot.event
    async def on_member_join(member: discord.Member):
        try:
            used_code = await _detect_used_invite_code(member)
            if used_code: await _apply_invite_role(member, used_code)
        except: pass
        await _send_arrival_card(member)

setup_welcome(bot)

# ===================== MUSIC: QUEUE & ROLE LOCK ==================

def check_queue(guild_id: int, vc: discord.VoiceClient):
    if not vc or not vc.is_connected():
        return
    
    if guild_id in bot.audio_queues and bot.audio_queues[guild_id]:
        next_track = bot.audio_queues[guild_id].popleft()
        url, title = next_track
        future = asyncio.run_coroutine_threadsafe(play_track(vc, url, title, guild_id), bot.loop)
        try: future.result()
        except: pass

async def play_track(vc: discord.VoiceClient, url: str, title: str, guild_id: int):
    try:
        player = await YTDLSource.from_url(url, loop=bot.loop, stream=True)
        vc.play(player, after=lambda e: check_queue(guild_id, vc))
    except Exception as e:
        print(f"Error playing track {title}: {e}")
        check_queue(guild_id, vc)

class MusicSelect(Select):
    def __init__(self, tracks: List[dict]):
        self.tracks = tracks
        options = []
        for i, t in enumerate(tracks[:5]):
            label = t.get('title', 'Unknown Title')[:95]
            desc = t.get('channel', 'Unknown Artist')[:95]
            options.append(SelectOption(label=f"{i+1}. {label}", description=desc, value=str(i), emoji="🎵"))
        
        super().__init__(placeholder="Select a song...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: Interaction):
        await safe_defer(interaction)
        idx = int(self.values[0])
        track = self.tracks[idx]
        url = track.get('url') or track.get('webpage_url')
        title = track.get('title', 'Unknown')
        
        vc = await ensure_voice_simple(interaction)
        if not vc: return

        guild_id = interaction.guild.id
        if guild_id not in bot.audio_queues:
            bot.audio_queues[guild_id] = deque()

        if vc.is_playing():
            bot.audio_queues[guild_id].append((url, title))
            await interaction.followup.send(f"📝 **Queued:** {title}", ephemeral=True)
        else:
            try:
                await interaction.edit_original_response(content=f"▶️ **Playing:** {title}", view=None)
            except: pass 
            
            await play_track(vc, url, title, guild_id)

class MusicSearchView(View):
    def __init__(self, tracks: List[dict]):
        super().__init__(timeout=60)
        self.add_item(MusicSelect(tracks))

@bot.slash_command(name="play", description="Search & Play music (Queue enabled)")
@dj_or_admin()
async def play(ctx: discord.ApplicationContext, search: Option(str, description="Song name or URL")):
    await safe_defer(ctx)
    
    try:
        if re.match(r'^https?://', search):
            vc = await ensure_voice_simple(ctx)
            if not vc: return
            
            guild_id = ctx.guild.id
            if guild_id not in bot.audio_queues:
                bot.audio_queues[guild_id] = deque()

            info = await bot.loop.run_in_executor(None, lambda: ytdl_search.extract_info(search, download=False))
            title = info.get('title', 'Unknown Track')

            if vc.is_playing():
                bot.audio_queues[guild_id].append((search, title))
                await safe_reply(ctx, f"📝 **Queued:** {title}", ephemeral=True)
            else:
                await safe_reply(ctx, f"▶️ **Playing:** {title}", ephemeral=True)
                await play_track(vc, search, title, guild_id)
            return

        data = await bot.loop.run_in_executor(None, lambda: ytdl_search.extract_info(f"ytsearch5:{search}", download=False))
        if 'entries' not in data or not data['entries']:
            await safe_reply(ctx, "❌ No results found.", ephemeral=True)
            return
            
        tracks = data['entries']
        view = MusicSearchView(tracks)
        await safe_reply(ctx, f"🔎 Results for **{search}**:", view=view, ephemeral=True)

    except Exception as e:
        print(f"[DEBUG] Play Error: {e}")
        await safe_reply(ctx, f"❌ Error: `{e}`", ephemeral=True)

@bot.slash_command(name="skip", description="Skip the current song")
@dj_or_admin()
async def skip(ctx: discord.ApplicationContext):
    vc = ctx.guild.voice_client
    if vc and vc.is_playing():
        vc.stop()
        await safe_reply(ctx, "⏭️ Skipped.", ephemeral=True)
    else:
        await safe_reply(ctx, "❌ Nothing is playing.", ephemeral=True)

@bot.slash_command(name="queue", description="Show the music queue")
@dj_or_admin()
async def queue(ctx: discord.ApplicationContext):
    gid = ctx.guild.id
    if gid not in bot.audio_queues or not bot.audio_queues[gid]:
        return await safe_reply(ctx, "ℹ️ Queue is empty.", ephemeral=True)
    
    lines = []
    for i, (url, title) in enumerate(list(bot.audio_queues[gid])[:10]):
        lines.append(f"`{i+1}.` {title}")
    
    embed = discord.Embed(title="🎵 Music Queue", description="\n".join(lines), color=THEME_PRIMARY)
    if len(bot.audio_queues[gid]) > 10:
        embed.set_footer(text=f"...and {len(bot.audio_queues[gid])-10} more")
    
    await safe_reply(ctx, embed=embed, ephemeral=True)

@bot.slash_command(name="stop", description="Stop music and clear queue")
@dj_or_admin()
async def stop(ctx: discord.ApplicationContext):
    vc = ctx.guild.voice_client
    if vc:
        if ctx.guild.id in bot.audio_queues:
            bot.audio_queues[ctx.guild.id].clear()
        
        await vc.disconnect()
        await safe_reply(ctx, "⏹️ Stopped & Cleared.", ephemeral=True)
    else:
        await safe_reply(ctx, "ℹ️ Not connected.", ephemeral=True)

# ===================== CLIPPING COMMANDS =====================

@bot.slash_command(name="join", description="Join VC and start Auto-Recording")
@dj_or_admin()
async def join(ctx: discord.ApplicationContext):
    # EPHEMERAL: Only user sees this
    await safe_defer(ctx, ephemeral=True)
    vc = await ensure_voice_simple(ctx)
    if vc:
        await safe_reply(ctx, f"✅ Joined {vc.channel.mention} and started auto-recording.", ephemeral=True)

@bot.slash_command(name="clip", description="Clip last 30s and save to channel")
@dj_or_admin()
async def clip(ctx: discord.ApplicationContext):
    await safe_defer(ctx, ephemeral=True)
    vc = ctx.guild.voice_client
    if not vc or not vc.is_connected():
        return await safe_reply(ctx, "❌ I am not in a voice channel.", ephemeral=True)

    if not HAS_SINKS:
        return await safe_reply(ctx, "❌ Clipping not supported (Missing Py-Cord).", ephemeral=True)

    if not hasattr(vc, "recording") or not vc.recording:
        try:
            vc.start_recording(RingBufferSink(time_limit=30), dummy_callback)
            return await safe_reply(ctx, "⚠️ Recording started now. Try again in 30s.", ephemeral=True)
        except:
            return await safe_reply(ctx, "❌ Could not access recording stream.", ephemeral=True)

    sink = vc.sink
    if not isinstance(sink, RingBufferSink):
        return await safe_reply(ctx, "❌ Current recording format does not support clipping.", ephemeral=True)

    # --- MIXING LOGIC: Combine all users into ONE file ---
    input_files = []
    temp_files_to_cleanup = []

    try:
        # 1. Write separate WAVs for each user
        for user_id, audio_deque in sink.buffer.items():
            if not audio_deque: continue
            data = b''.join(audio_deque)
            # ZERO FILTER: Capture everything > 0 bytes
            if len(data) == 0: continue

            f_path = f"temp_{user_id}_{int(time.time())}.wav"
            with wave.open(f_path, 'wb') as wav:
                wav.setnchannels(2) 
                wav.setsampwidth(2) 
                wav.setframerate(48000) 
                wav.writeframes(data)
            
            input_files.append(f_path)
            temp_files_to_cleanup.append(f_path)

        if not input_files:
            return await safe_reply(ctx, "ℹ️ No recent audio found (Buffer empty). Speak for 5 seconds and try again.", ephemeral=True)

        final_file = None
        
        # 2. Use FFmpeg to Mix
        if len(input_files) == 1:
            # Only one person spoke? Just convert that one file.
            final_file = discord.File(input_files[0], filename=f"clip_{int(time.time())}.wav")
        else:
            # Mix multiple inputs
            output_filename = f"mixed_clip_{int(time.time())}.mp3"
            cmd = ['ffmpeg', '-y']
            for f in input_files:
                cmd.extend(['-i', f])
            
            # Complex filter: 'amix' mixes inputs. duration=longest means keep clip going until last person stops.
            cmd.extend(['-filter_complex', f'amix=inputs={len(input_files)}:duration=longest', output_filename])
            
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            if os.path.exists(output_filename):
                final_file = discord.File(output_filename)
                temp_files_to_cleanup.append(output_filename)
            else:
                return await safe_reply(ctx, "❌ Failed to mix audio.", ephemeral=True)

        # 3. Send to Clip Channel
        target_id = CLIPS_TARGET_ID
        target_ch, _ = await resolve_target(ctx.bot, target_id)
        
        if target_ch and final_file:
            await target_ch.send(content=f"✂️ **Clip recorded by {ctx.author.mention}**", file=final_file)
            await safe_reply(ctx, f"✅ Clip saved to {target_ch.mention}.", ephemeral=True)
        else:
            await safe_reply(ctx, "⚠️ Target channel not found.", file=final_file, ephemeral=True)

    except Exception as e:
        print(f"Clip Error: {e}")
        await safe_reply(ctx, f"❌ Error processing clip: {e}", ephemeral=True)
    
    finally:
        # Cleanup temp files
        for f in temp_files_to_cleanup:
            try: os.remove(f)
            except: pass

# ===================== /SPEAK (TTS) ==================

async def log_speak_usage(user, text, lang):
    target, _ = await resolve_target(bot, SPEAK_LOG_THREAD_ID)
    if target:
        embed = discord.Embed(title="🗣️ /speak used", color=THEME_PRIMARY)
        embed.add_field(name="User", value=str(user), inline=False)
        embed.add_field(name="Language", value=lang, inline=True)
        embed.add_field(name="Text", value=text[:1024], inline=False)
        try: await target.send(embed=embed)
        except: pass

@bot.slash_command(name="speak", description="Speak text in your VC")
@dj_or_admin()
async def speak(
    ctx: discord.ApplicationContext, 
    text: Option(str, "Message"), 
    language: Option(str, "Language", choices=LANG_CHOICES, default="English")
):
    await safe_defer(ctx, ephemeral=True)
    if not ffmpeg_available(): return await safe_reply(ctx, "❌ FFmpeg missing", ephemeral=True)
    
    vc = await ensure_voice_simple(ctx)
    if not vc: return

    lang_code = LANG_CODES.get(language, "en")
    try:
        to_say = text
        if lang_code != "en":
            try: to_say = translator.translate(text, src="en", dest=lang_code).text
            except: pass

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f: tmp = f.name
        gTTS(text=to_say, lang=lang_code).save(tmp)
        vc.play(discord.FFmpegPCMAudio(tmp))
        
        await log_speak_usage(ctx.author, text, lang_code)
        await safe_reply(ctx, "✅ Spoke text", ephemeral=True)
    except Exception as e:
        await safe_reply(ctx, f"❌ Error: `{e}`", ephemeral=True)

# ======================== SCOINS ECONOMY =====================

@bot.slash_command(name="pull", description="Get your daily Scoins (24h Cooldown)")
async def pull(ctx: discord.ApplicationContext):
    user_id = str(ctx.author.id)
    user_data = scoins_db.get(user_id, {"balance": 0, "last_pull": 0})
    last = user_data["last_pull"]
    now = time.time()
    
    # 24h = 86400 seconds
    if now - last < (SCOIN_COOLDOWN_HOURS * 3600):
        remaining = (SCOIN_COOLDOWN_HOURS * 3600) - (now - last)
        hours = int(remaining // 3600)
        mins = int((remaining % 3600) // 60)
        embed = discord.Embed(description=f"⏳ **Cooldown:** Return in `{hours}h {mins}m`.", color=discord.Color.red())
        return await safe_reply(ctx, embed=embed, ephemeral=True)
    
    new_bal = user_data["balance"] + SCOIN_PULL_AMOUNT
    scoins_db[user_id] = {"balance": new_bal, "last_pull": now}
    _save_scoins()
    
    embed = discord.Embed(description=f"💰 **Payday!** Received **{SCOIN_PULL_AMOUNT} Scoins**.\n💳 Balance: `{new_bal}`", color=THEME_WIN)
    await safe_reply(ctx, embed=embed)

@bot.slash_command(name="wallet", description="Check your Scoins balance")
async def wallet(ctx: discord.ApplicationContext, user: Option(discord.User, required=False)):
    target = user or ctx.author
    bal = get_balance(str(target.id))
    embed = discord.Embed(description=f"💳 **{target.display_name}** has `{bal}` Scoins.", color=THEME_PRIMARY)
    await safe_reply(ctx, embed=embed)

@bot.slash_command(name="bet", description="Gamble Scoins (Double or Nothing)")
async def bet(ctx: discord.ApplicationContext, amount: Option(str, "Amount to bet (or 'all')")):
    user_id = str(ctx.author.id)
    bal = get_balance(user_id)
    
    # Parse amount
    if amount.lower() == "all":
        bet_amount = bal
    else:
        try: bet_amount = int(amount)
        except: return await safe_reply(ctx, "❌ Invalid amount.", ephemeral=True)
    
    if bet_amount <= 0: return await safe_reply(ctx, "❌ Must bet at least 1.", ephemeral=True)
    if bet_amount > bal: return await safe_reply(ctx, "❌ Insufficient funds.", ephemeral=True)
    
    # 1. VISUAL: Rolling Animation
    roll_embed = discord.Embed(description="🎲 **Rolling the bones...**", color=THEME_PRIMARY)
    interaction = await ctx.respond(embed=roll_embed)
    if hasattr(interaction, 'message'): msg = interaction.message
    else: msg = await interaction.original_response()
    
    await asyncio.sleep(1.5) # Suspense
    
    # 2. LOGIC: Roll
    roll = random.randint(1, 100)
    
    if roll == 100: # JACKPOT 5x
        winnings = bet_amount * 5
        update_balance(user_id, winnings)
        res_embed = discord.Embed(title="🎰 JACKPOT! 🎰", description=f"🎲 Rolled: **{roll}**\n💸 Won: **{winnings}** Scoins!", color=THEME_GOLD)
    elif roll > 50: # WIN 2x (Profit = Amount)
        update_balance(user_id, bet_amount)
        res_embed = discord.Embed(title="✅ YOU WIN", description=f"🎲 Rolled: **{roll}**\n💸 Won: **{bet_amount}** Scoins", color=THEME_WIN)
    else: # LOSS
        update_balance(user_id, -bet_amount)
        res_embed = discord.Embed(title="❌ YOU LOSE", description=f"🎲 Rolled: **{roll}**\n💸 Lost: **{bet_amount}** Scoins", color=THEME_LOSS)
        
    res_embed.set_footer(text=f"New Balance: {get_balance(user_id)}")
    try: await msg.edit(embed=res_embed)
    except: await ctx.send(embed=res_embed)

@bot.slash_command(name="leaderboard", description="Top 10 Scoin Rich List")
async def leaderboard(ctx: discord.ApplicationContext):
    # Sort by balance descending
    sorted_users = sorted(scoins_db.items(), key=lambda x: x[1].get("balance", 0), reverse=True)
    top_10 = sorted_users[:10]
    
    lines = []
    for i, (uid, data) in enumerate(top_10):
        try: member = ctx.guild.get_member(int(uid)) or await ctx.guild.fetch_member(int(uid))
        except: member = None
        name = member.display_name if member else "Unknown"
        bal = data.get("balance", 0)
        lines.append(f"`{i+1}.` **{name}** — {bal} 💰")
        
    if not lines: lines = ["No data yet."]
    
    embed = discord.Embed(title="🏆 Scoin Leaderboard", description="\n".join(lines), color=THEME_GOLD)
    await safe_reply(ctx, embed=embed)

@bot.slash_command(name="give_scoins", description="Owner Only: Add/Remove Scoins")
@owner_only()
async def give_scoins(ctx: discord.ApplicationContext, user: discord.Member, amount: int):
    update_balance(str(user.id), amount)
    new_bal = get_balance(str(user.id))
    await safe_reply(ctx, f"✅ Adjusted **{user.display_name}** by `{amount}`.\nNew Balance: `{new_bal}`", ephemeral=True)

# ======================== HASTE FACTS COMMANDS =====================

@bot.slash_command(name="haste", description="Get a random fact about Haste")
async def haste(ctx: discord.ApplicationContext):
    fact = random.choice(active_haste_facts)
    await safe_reply(ctx, fact)

@bot.slash_command(name="morehaste", description="Add a new Haste fact")
@admin_only()
async def morehaste(ctx: discord.ApplicationContext, fact: Option(str, "The fact to add")):
    active_haste_facts.append(fact)
    _save_haste_facts()
    await safe_reply(ctx, f"✅ Added fact: \"{fact}\"")

# ======================== CUSTOM EMBED MODAL =====================

class CustomEmbedModal(Modal):
    def __init__(self, target_id: int, bot_ref):
        super().__init__(title="Send Custom Embed")
        self.target_id = target_id
        self.bot_ref = bot_ref
        self.add_item(TextInput(label="Title", max_length=256))
        self.add_item(TextInput(label="Message", style=discord.InputTextStyle.paragraph, max_length=4000))

    async def callback(self, interaction: Interaction):
        title = self.children[0].value
        desc = self.children[1].value
        embed = discord.Embed(title=title, description=desc, color=THEME_PRIMARY)
        ch = self.bot_ref.get_channel(self.target_id)
        if ch:
            try: await ch.send(embed=embed)
            except Exception as e: return await interaction.response.send_message(f"❌ Failed: `{e}`", ephemeral=True)
        await interaction.response.send_message("✅ Posted", ephemeral=True)

@bot.slash_command(name="send_custom", description="Send a custom embed here")
@admin_only()
async def send_custom(ctx: discord.ApplicationContext):
    await ctx.send_modal(CustomEmbedModal(ctx.channel.id, ctx.bot))

# ====================== DURABLE WELCOME COMMANDS =================

def welcome_embed() -> discord.Embed:
    return discord.Embed(
        title="Welcome to ShadowSyn",
        color=THEME_PRIMARY,
        description=(
            "👋 **Welcome to ShadowSyn**\n"
            "You're in OCE's most toxic (Fun) enviroment.\n\n"
            "🪪 **Game roles**\n"
            "Go to **#self-roles** and pick the **game roles** you actually play.\n\n"
            "🚫 **Rules**\n"
            "No spam, no drama, no random DMs. Use common sense.\n\n"
            f"🔗 **Invite**\n{VANITY_INVITE}"
        ),
    )

class CopyInviteEphemeralView(View):
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(Button(label="Open Link", style=ButtonStyle.link, url=VANITY_INVITE))

class InviteCopyView(View):
    def __init__(self):
        super().__init__(timeout=None)
        btn = Button(label="Invite Friends", style=ButtonStyle.primary, emoji="🔗", custom_id="shadowsyn:welcome_invite_copy:v1")
        btn.callback = self._send_copyable
        self.add_item(btn)

    async def _send_copyable(self, interaction: discord.Interaction):
        msg = f"✅ Invite ready:\n```text\n{VANITY_INVITE}\n```"
        await interaction.response.send_message(content=msg, view=CopyInviteEphemeralView(), ephemeral=True)

@bot.slash_command(name="send_welcome", description="Post the welcome card.")
@admin_only()
async def send_welcome(ctx: discord.ApplicationContext, target: Option(discord.TextChannel, required=False)):
    await safe_defer(ctx, ephemeral=True)
    dest = target or ctx.channel
    try:
        view = InviteCopyView()
        msg = await dest.send(embed=welcome_embed(), view=view)
        try: await msg.pin(reason="ShadowSyn Welcome")
        except: pass
        await safe_reply(ctx, f"✅ Posted in {dest.mention}.", ephemeral=True)
    except Exception as e:
        await safe_reply(ctx, f"❌ Failed: `{e}`", ephemeral=True)

@bot.slash_command(name="welcome_update", description="Update welcome card.")
@admin_only()
async def welcome_update(ctx: discord.ApplicationContext, message_id: Option(str, required=False), target: Option(discord.TextChannel, required=False)):
    await safe_defer(ctx, ephemeral=True)
    dest = target or ctx.channel
    msg = None
    if message_id:
        try: msg = await dest.fetch_message(int(message_id))
        except: pass
    else:
        try:
            pins = await dest.pins()
            for m in pins:
                if m.author.id == bot.user.id and m.embeds and "welcome" in (m.embeds[0].title or "").lower():
                    msg = m
                    break
        except: pass
    if not msg: return await safe_reply(ctx, "❌ Card not found.", ephemeral=True)
    try:
        await msg.edit(embed=welcome_embed(), view=InviteCopyView())
        await safe_reply(ctx, "✅ Updated.", ephemeral=True)
    except Exception as e:
        await safe_reply(ctx, f"❌ Failed: `{e}`", ephemeral=True)

# ====================== INVITE→ROLE ADMIN COMMANDS ======================

invite_role_group = bot.create_group("invite_role", "Map invite codes to auto-roles on join (admin).")

@invite_role_group.command(name="add", description="Map an invite (code/url/vanity) to a role.")
@admin_only()
async def invite_role_add(ctx: discord.ApplicationContext, invite: str, role: discord.Role):
    await safe_defer(ctx, ephemeral=True)
    guild = ctx.guild
    code = normalize_invite_code(invite)
    if not code: return await safe_reply(ctx, "❌ Invalid invite.", ephemeral=True)
    mapping = get_invite_role_map(guild.id)
    mapping[code] = role.id
    set_invite_role_map(guild.id, mapping)
    label = "vanity" if code == "vanity" else f"`{code}`"
    await safe_reply(ctx, f"✅ Mapped {label} → {role.mention}", ephemeral=True)

@invite_role_group.command(name="remove", description="Remove an invite→role mapping.")
@admin_only()
async def invite_role_remove(ctx: discord.ApplicationContext, invite: str):
    await safe_defer(ctx, ephemeral=True)
    guild = ctx.guild
    code = normalize_invite_code(invite)
    if not code: return await safe_reply(ctx, "❌ Invalid invite.", ephemeral=True)
    mapping = get_invite_role_map(guild.id)
    if code not in mapping: return await safe_reply(ctx, "ℹ️ No mapping exists.", ephemeral=True)
    mapping.pop(code, None)
    set_invite_role_map(guild.id, mapping)
    await safe_reply(ctx, f"✅ Removed mapping for {code}.", ephemeral=True)

@invite_role_group.command(name="list", description="List current invite→role mappings.")
@admin_only()
async def invite_role_list(ctx: discord.ApplicationContext):
    await safe_defer(ctx, ephemeral=True)
    guild = ctx.guild
    mapping = get_invite_role_map(guild.id)
    if not mapping: return await safe_reply(ctx, "No invite-role mappings set.", ephemeral=True)
    lines = []
    for code, role_id in sorted(mapping.items(), key=lambda kv: kv[0]):
        role = guild.get_role(int(role_id))
        lines.append(f"- **{code}** → {role.mention if role else role_id}")
    await safe_reply(ctx, "\n".join(lines)[:4000], ephemeral=True)

# ============================ AUDIT & DEPARTURES ==========================

_last_departures: Dict[int, float] = {}

def _build_departure_embed(subject, reason_text, executor=None, moderator_reason=None):
    rt = reason_text.lower()
    title = "⛔ Member Banned" if rt == "banned" else ("👢 Member Kicked" if rt == "kicked" else "👋 Member Left")
    embed = discord.Embed(title=title, color=discord.Color.orange(), timestamp=utcnow())
    if safe_avatar_url(subject): embed.set_thumbnail(url=safe_avatar_url(subject))
    embed.add_field(name="User", value=f"{subject.mention}\n{discord.utils.escape_markdown(str(subject))}", inline=False)
    if isinstance(subject, discord.Member):
        embed.add_field(name="Joined", value=human_ago(subject.joined_at), inline=True)
    embed.add_field(name="Account Age", value=human_ago(subject.created_at), inline=True)
    details = [f"{subject.mention} {rt} the server."]
    if executor: details.append(f"By: **{executor}**")
    if moderator_reason: details.append(f"Reason: {moderator_reason}")
    embed.add_field(name="Details", value="\n".join(details), inline=False)
    return embed

async def _send_departure_embed(user_id, embed):
    target, _ = await resolve_target(bot, DEPARTURES_THREAD_ID)
    if not target: return
    now = time.time()
    if now - _last_departures.get(user_id, 0) < 5: return
    _last_departures[user_id] = now
    try: await target.send(embed=embed)
    except: pass

async def _find_recent_audit(guild, action, target_id, window_seconds=300):
    if not (guild.me and guild.me.guild_permissions.view_audit_log): return None
    try:
        async for entry in guild.audit_logs(limit=20, action=action):
            if entry.target and entry.target.id == target_id:
                if abs((utcnow() - entry.created_at.replace(tzinfo=timezone.utc)).total_seconds()) <= window_seconds:
                    return entry
    except: pass
    return None

@bot.event
async def on_member_remove(member: discord.Member):
    await asyncio.sleep(1.0)
    ban = await _find_recent_audit(member.guild, discord.AuditLogAction.ban, member.id, 180)
    if ban: return
    kick = await _find_recent_audit(member.guild, discord.AuditLogAction.kick, member.id, 300)
    if kick:
        await _send_departure_embed(member.id, _build_departure_embed(member, "Kicked", kick.user, kick.reason))
        return
    await _send_departure_embed(member.id, _build_departure_embed(member, "Left"))

@bot.event
async def on_member_ban(guild, user):
    executor, reason = None, None
    entry = await _find_recent_audit(guild, discord.AuditLogAction.ban, user.id, 300)
    if entry: executor, reason = entry.user, entry.reason
    await _send_departure_embed(user.id, _build_departure_embed(user, "Banned", executor, reason))

# =================== ROLE PICKER (DUAL VIEW RESTORED) ==================

def _sorted_opts(options: List[dict]) -> List[dict]:
    return sorted(options, key=lambda o: str(o.get("label", "")).casefold())

class DualRolePickerView(View):
    def __init__(self, guild: discord.Guild, options: List[dict]):
        super().__init__(timeout=None)
        self.guild = guild
        self.options = _sorted_opts(options)
        self.page: int = 0
        self.page_size: int = 25
        
        self.add_select = Select(
            placeholder="Select your game roles…",
            min_values=0,
            max_values=1, # Updated dynamically
            options=[],
            custom_id=f"ss:roles:toggle:g{guild.id}"
        )
        self.add_select.callback = self._on_select_toggle
        
        self._refresh_add_select()
        self.add_item(self.add_select)

        if self._total_pages() > 1:
            self.btn_prev = Button(emoji="⬅️", style=ButtonStyle.secondary, row=1, custom_id=f"ss:roles:page_prev:g{guild.id}")
            self.btn_prev.callback = self._on_prev_page
            self.add_item(self.btn_prev)
            
            self.btn_next = Button(emoji="➡️", style=ButtonStyle.secondary, row=1, custom_id=f"ss:roles:page_next:g{guild.id}")
            self.btn_next.callback = self._on_next_page
            self.add_item(self.btn_next)
            
            self._update_page_buttons()

    def _total_pages(self) -> int:
        return 1 if not self.options else (len(self.options) - 1) // self.page_size + 1

    def _current_slice(self) -> List[dict]:
        start = self.page * self.page_size
        return self.options[start:start + self.page_size]

    def _refresh_add_select(self):
        chunk = self._current_slice()
        if not chunk:
            self.add_select.options = []
            self.add_select.max_values = 1
            self.add_select.disabled = True
        else:
            self.add_select.options = [SelectOption(label=o["label"], value=str(o["role_id"])) for o in chunk]
            self.add_select.max_values = len(chunk)
            self.add_select.disabled = False

    def _update_page_buttons(self):
        if not hasattr(self, "btn_prev"): return
        self.btn_prev.disabled = self.page <= 0
        self.btn_next.disabled = self.page >= (self._total_pages() - 1)

    async def _on_prev_page(self, interaction: Interaction):
        await interaction.response.defer()
        if self.page > 0:
            self.page -= 1
            self._refresh_add_select()
            self._update_page_buttons()
            try: await interaction.message.edit(view=self)
            except: pass

    async def _on_next_page(self, interaction: Interaction):
        await interaction.response.defer()
        if self.page < self._total_pages() - 1:
            self.page += 1
            self._refresh_add_select()
            self._update_page_buttons()
            try: await interaction.message.edit(view=self)
            except: pass

    async def _on_select_toggle(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild: return
        member = interaction.guild.get_member(interaction.user.id)
        bot_member = interaction.guild.me
        page_roles = self._current_slice()
        page_ids = {int(o["role_id"]) for o in page_roles}
        allowed = {int(o["role_id"]) for o in self.options}
        current = {r.id for r in member.roles if r.id in allowed}
        selected = {int(v) for v in (self.add_select.values or [])}
        to_add = (selected - (current & page_ids)) & page_ids
        to_remove = ((current & page_ids) - selected)
        
        added, removed = [], []
        for rid in to_add:
            r = interaction.guild.get_role(rid)
            if r and bot_member.top_role > r:
                try: await member.add_roles(r); added.append(r.name)
                except: pass
        for rid in to_remove:
            r = interaction.guild.get_role(rid)
            if r and bot_member.top_role > r:
                try: await member.remove_roles(r); removed.append(r.name)
                except: pass

        embed = discord.Embed(title="✅ Roles Updated", color=THEME_PRIMARY)
        if added: embed.add_field(name="Added", value=", ".join(added), inline=False)
        if removed: embed.add_field(name="Removed", value=", ".join(removed), inline=False)
        if not added and not removed: embed.description = "No changes."
        await interaction.followup.send(embed=embed, ephemeral=True)

def role_picker_embed() -> discord.Embed:
    return discord.Embed(title="SELECT ROLES", description="Select items to instantly add/remove roles.", color=THEME_PRIMARY)

async def rehydrate_role_panel(client: discord.Client, guild: discord.Guild):
    cfg = get_guild_role_cfg(guild.id)
    if not cfg or not cfg.get("panel"): return
    panel = cfg["panel"]
    channel = guild.get_channel(panel.get("channel_id"))
    if not channel:
        try: channel = await client.fetch_channel(panel.get("channel_id"))
        except: return
    try:
        msg = await channel.fetch_message(panel.get("message_id"))
        client.add_view(DualRolePickerView(guild, cfg.get("options", [])), message_id=msg.id)
    except: pass

ROLE_MENTION_RE = re.compile(r"<@&(\d+)>")
def _parse_role_mentions(text: str) -> List[int]:
    return [int(m) for m in ROLE_MENTION_RE.findall(text or "")]

@bot.slash_command(name="roles_post", description="Post role panel.")
@admin_only()
async def roles_post(ctx: discord.ApplicationContext, target: Option(discord.TextChannel, required=False)):
    await safe_defer(ctx, ephemeral=True)
    guild = ctx.guild
    cfg = get_guild_role_cfg(guild.id)
    dest = target or ctx.channel
    try:
        view = DualRolePickerView(guild, cfg.get("options", []))
        msg = await dest.send(embed=role_picker_embed(), view=view)
        cfg["panel"] = {"channel_id": dest.id, "message_id": msg.id}
        set_guild_role_cfg(guild.id, cfg)
        try: bot.add_view(view, message_id=msg.id)
        except: pass
        await safe_reply(ctx, f"✅ Posted in {dest.mention}.", ephemeral=True)
    except Exception as e: await safe_reply(ctx, f"❌ Failed: `{e}`", ephemeral=True)

@bot.slash_command(name="roles_add", description="Add roles to picker.")
@admin_only()
async def roles_add(ctx: discord.ApplicationContext, roles: str):
    await safe_defer(ctx, ephemeral=True)
    ids = _parse_role_mentions(roles)
    cfg = get_guild_role_cfg(ctx.guild.id)
    existing = {int(o["role_id"]) for o in cfg.get("options", [])}
    added = []
    for rid in ids:
        if rid in existing: continue
        r = ctx.guild.get_role(rid)
        if r:
            cfg.setdefault("options", []).append({"role_id": r.id, "label": r.name})
            added.append(r.name)
    set_guild_role_cfg(ctx.guild.id, cfg)
    await safe_reply(ctx, f"✅ Added: {', '.join(added)}", ephemeral=True)

@bot.slash_command(name="roles_remove", description="Remove roles from picker.")
@admin_only()
async def roles_remove(ctx: discord.ApplicationContext, roles: str):
    await safe_defer(ctx, ephemeral=True)
    ids = set(_parse_role_mentions(roles))
    cfg = get_guild_role_cfg(ctx.guild.id)
    opts = [o for o in cfg.get("options", []) if int(o["role_id"]) not in ids]
    cfg["options"] = opts
    set_guild_role_cfg(ctx.guild.id, cfg)
    await safe_reply(ctx, "✅ Removed roles.", ephemeral=True)

@bot.slash_command(name="roles_sync", description="Refresh panel.")
@admin_only()
async def roles_sync(ctx: discord.ApplicationContext):
    await safe_defer(ctx, ephemeral=True)
    cfg = get_guild_role_cfg(ctx.guild.id)
    panel = cfg.get("panel")
    if not panel: return await safe_reply(ctx, "No panel.", ephemeral=True)
    try:
        ch = ctx.guild.get_channel(panel["channel_id"])
        msg = await ch.fetch_message(panel["message_id"])
        view = DualRolePickerView(ctx.guild, cfg.get("options", []))
        await msg.edit(embed=role_picker_embed(), view=view)
        try: bot.add_view(view, message_id=msg.id)
        except: pass
        await safe_reply(ctx, "✅ Synced.", ephemeral=True)
    except: await safe_reply(ctx, "❌ Failed to sync.", ephemeral=True)

# =============================== RUN ============================

def main():
    print("FFMPEG PATH:", which("ffmpeg"))
    print("PERSIST_ROOT:", PERSIST_ROOT)
    bot.run(TOKEN)

if __name__ == "__main__":
    main()
