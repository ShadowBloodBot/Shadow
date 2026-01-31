# bot.py — ShadowSyn (Ultimate: Fixed Audio Buffer + Ephemeral)
#
# === FEATURES ===
# 1. VoiceMaster: Join-to-Create VCs + Control Panel
# 2. Music: Queue System, Fast Search, Role Locked
# 3. Clip System: Auto-buffers 30s -> Saves to channel 1467055136609271818
# 4. Core: Audit, Roles, Welcome, TTS, Youtube Watcher
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
from pathlib import Path
from typing import Optional, Tuple, Union, Dict, List, Set
from datetime import datetime, timezone
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
import aiohttp
import xml.etree.ElementTree as ET
from discord.utils import get

# --- NATIVE MUSIC DEPENDENCY ---
import yt_dlp

# =========================== CONSTANTS ===========================

VANITY_INVITE  = "https://discord.gg/shadowsyn"
THEME_PRIMARY  = 0x2B0B35

# Channel & Role IDs
ARRIVALS_THREAD_ID      = 959629903186259978
ROLE_MINION_ID          = 955600021502431233
ROLE_ADMIN_ID           = 1214794734770323466
ROLE_MEMBER_ID          = 955600320287887400
SPEAK_LOG_THREAD_ID     = 1400048671973703690
DEPARTURES_THREAD_ID    = 960088192177029140
DEFAULT_TARGET_ID       = 1166874144395247757
DEFAULT_AUDIT_THREAD_ID = 961726632249425930
CLIPS_TARGET_ID         = 1467055136609271818

# VoiceMaster Config
JOIN_TO_CREATE_CHANNEL_ID = 1398618132788281364
VC_CATEGORY_ID            = 908659586536468542
VC_DEFAULT_BITRATE        = 384000
VC_DEFAULT_USER_LIMIT     = 0
ADMIN_ROLE_NAME           = "SHADOW"

# Music Config
DJ_ROLE_ID              = 955600320287887400

# Youtube Watcher Config
ROLE_YT_MANAGER_ID      = 960088893351415898
YT_POST_TARGET_ID       = 959631286882934784
YT_POLL_SECONDS         = 180
YT_USER_AGENT           = "ShadowSynBot/YouTubeWatcher"

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
YT_STORE = (PERSIST_ROOT / "youtube_watch.json")
INVITE_ROLE_STORE = (PERSIST_ROOT / "invite_roles.json")
ACTIVE_VCS_STORE = (PERSIST_ROOT / "active_vcs.json")

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

        # FIXED: Py-Cord sends (user, data), NOT (data, user)
        def write(self, user, data):
            if user not in self.buffer:
                # 20ms packets * 50 = 1 sec. 
                self.buffer[user] = deque(maxlen=int(self.time_limit * 50))
            self.buffer[user].append(data)

        def cleanup(self):
            self.finished = True

        def get_recent_clips(self):
            files = []
            for user_id, audio_deque in self.buffer.items():
                if not audio_deque: continue
                data = b''.join(audio_deque)
                
                f = io.BytesIO()
                with wave.open(f, 'wb') as wav:
                    wav.setnchannels(2) 
                    wav.setsampwidth(2) 
                    wav.setframerate(48000) 
                    wav.writeframes(data)
                f.seek(0)
                
                files.append(discord.File(f, filename=f"clip_{user_id}_{int(time.time())}.wav"))
            return files
else:
    RingBufferSink = None

def dummy_callback(sink, *args):
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
        if vc and vc.is_connected():
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

def dj_role_check():
    def predicate(ctx):
        if ctx.author.guild_permissions.manage_guild: return True
        if any(role.id == DJ_ROLE_ID for role in ctx.author.roles): return True
        return False
    return commands.check(predicate)

def admin_only():
    def predicate(ctx):
        if not isinstance(ctx.author, discord.Member): return False
        return any(r.id == ROLE_ADMIN_ID for r in ctx.author.roles)
    return commands.check(predicate)

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

def _load_yt_store() -> Dict[str, dict]:
    base = {"channels": {}, "aliases": {}}
    if YT_STORE.exists():
        try:
            data = json.loads(YT_STORE.read_text())
            if isinstance(data, dict): base.update(data)
        except: pass
    base.setdefault("channels", {})
    base.setdefault("aliases", {})
    return base

def _save_yt_store(data: Dict[str, dict]) -> None:
    data.setdefault("channels", {})
    data.setdefault("aliases", {})
    try: YT_STORE.write_text(json.dumps(data, indent=2))
    except: pass

def _alias_key(text: str) -> str:
    s = (text or "").strip().lower().rstrip("/")
    s = re.sub(r"^https?://(www\.)?", "", s)
    return s

def _add_alias(user_input: str, uc_id: str):
    if not user_input or not uc_id: return
    store = _load_yt_store()
    store["aliases"][_alias_key(user_input)] = uc_id
    _save_yt_store(store)

def _lookup_alias(user_input: str) -> Optional[str]:
    return _load_yt_store().get("aliases", {}).get(_alias_key(user_input))

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
        self._yt_task: Optional[asyncio.Task] = None
        self.audio_queues: Dict[int, deque] = {} 
        self.synced = False

bot = ShadowSynBot()

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (Py-Cord)")
    if bot._yt_task is None:
        bot._yt_task = asyncio.create_task(youtube_watch_loop(bot))
    
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
            await interaction.edit_original_response(content=f"▶️ **Playing:** {title}", view=None)
            await play_track(vc, url, title, guild_id)

class MusicSearchView(View):
    def __init__(self, tracks: List[dict]):
        super().__init__(timeout=60)
        self.add_item(MusicSelect(tracks))

@bot.slash_command(name="play", description="Search & Play music (Queue enabled)")
@dj_role_check()
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
@dj_role_check()
async def skip(ctx: discord.ApplicationContext):
    vc = ctx.guild.voice_client
    if vc and vc.is_playing():
        vc.stop()
        await safe_reply(ctx, "⏭️ Skipped.", ephemeral=True)
    else:
        await safe_reply(ctx, "❌ Nothing is playing.", ephemeral=True)

@bot.slash_command(name="queue", description="Show the music queue")
@dj_role_check()
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
@dj_role_check()
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
async def join(ctx: discord.ApplicationContext):
    # EPHEMERAL: Only user sees this
    await safe_defer(ctx, ephemeral=True)
    vc = await ensure_voice_simple(ctx)
    if vc:
        await safe_reply(ctx, f"✅ Joined {vc.channel.mention} and started auto-recording.", ephemeral=True)

@bot.slash_command(name="clip", description="Clip last 30s and save to channel")
async def clip(ctx: discord.ApplicationContext):
    # EPHEMERAL: Only user sees this
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

    files = sink.get_recent_clips()
    if not files:
        return await safe_reply(ctx, "ℹ️ No audio data found in buffer.", ephemeral=True)

    target_id = CLIPS_TARGET_ID
    target_ch, _ = await resolve_target(ctx.bot, target_id)
    
    if target_ch:
        try:
            await target_ch.send(content=f"✂️ **Clip recorded by {ctx.author.mention}**", files=files)
            await safe_reply(ctx, f"✅ Clip saved to {target_ch.mention}.", ephemeral=True)
        except Exception as e:
            await safe_reply(ctx, f"❌ Failed to save to target: {e}. Here it is instead:", files=files)
    else:
        await safe_reply(ctx, f"⚠️ Clip target channel (`{target_id}`) not found. Here is your clip:", files=files)

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
async def speak(
    ctx: discord.ApplicationContext, 
    text: Option(str, "Message"), 
    language: Option(str, "Language", choices=LANG_CHOICES, default="English")
):
    if not isinstance(ctx.author, discord.Member) or not any(r.id == ROLE_MEMBER_ID for r in ctx.author.roles):
        return await safe_reply(ctx, "❌ `/speak` is restricted to Members.", ephemeral=True)

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

# =================== YOUTUBE WATCHER ==================

def yt_locked():
    def predicate(ctx):
        return isinstance(ctx.author, discord.Member) and any(r.id == ROLE_YT_MANAGER_ID for r in ctx.author.roles)
    return commands.check(predicate)

async def fetch_feed_latest(session: aiohttp.ClientSession, channel_id: str) -> Optional[Dict[str, str]]:
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    try:
        async with session.get(url, headers={"User-Agent": YT_USER_AGENT}) as r:
            if r.status != 200: return None
            text = await r.text()
    except: return None
    try:
        ns = {"atom": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015", "media": "http://search.yahoo.com/mrss/"}
        root = ET.fromstring(text)
        entry = root.find("atom:entry", ns)
        if entry is None: return None
        vid = entry.find("yt:videoId", ns).text
        title = entry.find("media:group/media:title", ns).text
        link_el = entry.find("atom:link", ns)
        link = link_el.attrib.get("href") if link_el is not None else f"https://www.youtube.com/watch?v={vid}"
        ch_title = root.find("atom:title", ns).text
        published = entry.find("atom:published", ns).text
        return {"video_id": vid, "title": title, "url": link, "channel_title": ch_title, "published": published}
    except: return None

async def post_video_announcement(client: discord.Client, payload: Dict[str, str]):
    target, _ = await resolve_target(client, YT_POST_TARGET_ID)
    if not target: return
    title = payload.get("title") or "New Video"
    url = payload.get("url")
    channel_title = payload.get("channel_title") or "Creator"
    prefix = f"Hey, **{channel_title}** just posted a video!"
    embed = discord.Embed(title=title, url=url, description=prefix, color=discord.Color.red())
    embed.set_footer(text="YouTube • ShadowSyn")
    try: await target.send(embed=embed)
    except: pass

async def youtube_watch_loop(client: discord.Client):
    await client.wait_until_ready()
    store = _load_yt_store()
    async with aiohttp.ClientSession(headers={"User-Agent": YT_USER_AGENT}) as session:
        for ch_id, cfg in list(store.get("channels", {}).items()):
            latest = await fetch_feed_latest(session, ch_id)
            if latest:
                cfg["last_video_id"] = latest["video_id"]
                store["channels"][ch_id] = cfg
        _save_yt_store(store)
    
    while not client.is_closed():
        try:
            store = _load_yt_store()
            channels = store.get("channels", {})
            if not channels:
                await asyncio.sleep(YT_POLL_SECONDS)
                continue
            async with aiohttp.ClientSession(headers={"User-Agent": YT_USER_AGENT}) as session:
                for ch_id, cfg in list(channels.items()):
                    latest = await fetch_feed_latest(session, ch_id)
                    if not latest:
                        await asyncio.sleep(1.0); continue
                    last = cfg.get("last_video_id")
                    if latest["video_id"] != last:
                        await post_video_announcement(client, latest)
                        cfg["last_video_id"] = latest["video_id"]
                        store["channels"][ch_id] = cfg
                        _save_yt_store(store)
                    await asyncio.sleep(1.0)
        except: pass
        await asyncio.sleep(YT_POLL_SECONDS)

# =================== YOUTUBE COMMANDS ==================

@bot.slash_command(name="yt_add", description="Watch a YouTube channel.")
@yt_locked()
async def yt_add(ctx: discord.ApplicationContext, channel_url_or_id: str):
    await safe_defer(ctx, ephemeral=True)
    ch_id = await normalize_channel_id(channel_url_or_id) if "normalize_channel_id" in globals() else channel_url_or_id
    if not ch_id: return await safe_reply(ctx, "❌ Invalid channel.", ephemeral=True)
    store = _load_yt_store()
    store["channels"].setdefault(ch_id, {"last_video_id": None, "channel_title": ""})
    _save_yt_store(store)
    _add_alias(channel_url_or_id, ch_id)
    await safe_reply(ctx, f"✅ Watching `{ch_id}`.", ephemeral=True)

@bot.slash_command(name="yt_remove", description="Stop watching a YouTube channel.")
@yt_locked()
async def yt_remove(ctx: discord.ApplicationContext, channel_id_or_url: str):
    await safe_defer(ctx, ephemeral=True)
    ch_id = _lookup_alias(channel_id_or_url)
    if not ch_id: ch_id = channel_id_or_url
    store = _load_yt_store()
    if store.get("channels", {}).pop(ch_id, None) is None: return await safe_reply(ctx, "ℹ️ Not watching.", ephemeral=True)
    _save_yt_store(store)
    await safe_reply(ctx, f"✅ Removed `{ch_id}`.", ephemeral=True)

@bot.slash_command(name="yt_list", description="List watched YouTube channels.")
@yt_locked()
async def yt_list(ctx: discord.ApplicationContext):
    await safe_defer(ctx, ephemeral=True)
    store = _load_yt_store()
    channels = store.get("channels", {})
    if not channels: return await safe_reply(ctx, "No channels.", ephemeral=True)
    lines = []
    for ch_id, cfg in channels.items():
        title = cfg.get("channel_title") or "Unknown"
        lines.append(f"- **{title}** (`{ch_id}`)")
    await safe_reply(ctx, "\n".join(lines)[:1990], ephemeral=True)

async def normalize_channel_id(inp: str) -> Optional[str]:
    if re.fullmatch(r"UC[0-9A-Za-z_-]{10,}", (inp or "").strip()): return inp.strip()
    return None

# =================== ROLE PICKER (DUAL VIEW) ==================

def _sorted_opts(options: List[dict]) -> List[dict]:
    return sorted(options, key=lambda o: str(o.get("label", "")).casefold())

class DualRolePickerView(View):
    def __init__(self, guild: discord.Guild, options: List[dict]):
        super().__init__(timeout=None)
        self.guild = guild
        self.options = _sorted_opts(options)
        self.page: int = 0
        self.page_size: int = 25
        self.add_select = Select(placeholder="Select your game roles…", min_values=0, max_values=0, options=[], custom_id=f"ss:roles:toggle:g{guild.id}")
        self._refresh_add_select()
        self.add_select.callback = self._on_select_toggle
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
            self.add_select.max_values = 0
        else:
            self.add_select.options = [SelectOption(label=o["label"], value=str(o["role_id"])) for o in chunk]
            self.add_select.max_values = len(chunk)

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
