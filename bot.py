# bot.py — ShadowSyn (Music + Core Only)
#
# === MODULES ===
# 1. Music (Native Search & Play)
# 2. Core (Welcome, Speak, Audit, Roles)
# 3. NO VoiceMaster (Removed as requested)
#
# Env: DISCORD_TOKEN

import os
import re
import json
import asyncio
import tempfile
import time
import traceback
from pathlib import Path
from typing import Optional, Tuple, Union, Dict, List, Set
from datetime import datetime, timezone
from collections import deque

import discord
from discord import app_commands, ButtonStyle, SelectOption, Interaction
from discord.ui import View, Button, Modal, TextInput, Select, button, select
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

# Channel IDs
ARRIVALS_THREAD_ID      = 959629903186259978
ROLE_MINION_ID          = 955600021502431233
ROLE_ADMIN_ID           = 1214794734770323466
ROLE_MEMBER_ID          = 955600320287887400
SPEAK_LOG_THREAD_ID     = 1400048671973703690
DEPARTURES_THREAD_ID    = 960088192177029140
DEFAULT_TARGET_ID       = 1166874144395247757
DEFAULT_AUDIT_THREAD_ID = 961726632249425930

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
    app_commands.Choice(name="English",    value="en"),
    app_commands.Choice(name="Japanese",   value="ja"),
    app_commands.Choice(name="German",     value="de"),
    app_commands.Choice(name="Spanish",    value="es"),
    app_commands.Choice(name="French",     value="fr"),
    app_commands.Choice(name="Italian",    value="it"),
    app_commands.Choice(name="Portuguese", value="pt"),
    app_commands.Choice(name="Russian",    value="ru"),
    app_commands.Choice(name="Korean",     value="ko"),
    app_commands.Choice(name="Chinese",    value="zh-CN"),
    app_commands.Choice(name="Hindi",      value="hi"),
    app_commands.Choice(name="Indonesian", value="id"),
]

# ==================== PERSISTENCE ===================

PERSIST_ROOT = Path(os.getenv("PERSIST_PATH", "/data")).resolve()
try:
    PERSIST_ROOT.mkdir(parents=True, exist_ok=True)
except:
    PERSIST_ROOT = Path(".").resolve()

ROLE_STORE = (PERSIST_ROOT / "role_picker.json")
YT_STORE = (PERSIST_ROOT / "youtube_watch.json")
INVITE_ROLE_STORE = (PERSIST_ROOT / "invite_roles.json")
# ACTIVE_VCS_STORE removed as VoiceMaster is gone

# ==================== MUSIC CONFIG ====================

YTDL_FORMAT_OPTIONS = {
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
}

FFMPEG_OPTIONS = {
    'options': '-vn',
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5' 
}

ytdl = yt_dlp.YoutubeDL(YTDL_FORMAT_OPTIONS)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True):
        loop = loop or asyncio.get_running_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        if 'entries' in data:
            data = data['entries'][0]
        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS), data=data)

# ==================== PERSISTENCE HELPERS ====================

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

# ========================= SAFE HELPERS ==========================

async def safe_defer(inter: discord.Interaction, *, ephemeral: bool = False):
    try:
        if not inter.response.is_done(): await inter.response.defer(ephemeral=ephemeral)
    except: pass

async def safe_reply(inter: discord.Interaction, *args, **kwargs):
    try:
        if not inter.response.is_done(): return await inter.response.send_message(*args, **kwargs)
        else: return await inter.followup.send(*args, **kwargs)
    except: return None

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

# ============================ BOT CORE ===========================

class ShadowSynBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.voice_states = True
        intents.members = True
        intents.message_content = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self._yt_task: Optional[asyncio.Task] = None
        self.audio_queues: Dict[int, deque] = {}
        self.synced = False

    async def setup_hook(self):
        # We hook error here but defer sync to on_ready to see guilds
        self.tree.on_error = self.on_tree_error
        
        if self._yt_task is None:
            self._yt_task = asyncio.create_task(youtube_watch_loop(self))

    async def on_tree_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        traceback.print_exc()
        if interaction.response.is_done():
            await interaction.followup.send(f"⚠️ Command Error: `{error}`", ephemeral=True)
        else:
            await interaction.response.send_message(f"⚠️ Command Error: `{error}`", ephemeral=True)

bot = ShadowSynBot()

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    
    # --- CLEAN SYNC (Removes the Broken Command) ---
    if not bot.synced:
        print("🔄 Performing Cleanup Sync...")
        try:
            # 1. Clear GUILD commands (This removes the duplicate/broken ones)
            for guild in bot.guilds:
                bot.tree.clear_commands(guild=guild)
                await bot.tree.sync(guild=guild)
                await _prime_invites_cache(guild)
            
            # 2. Sync GLOBAL commands (The working ones)
            await bot.tree.sync()
            print("✅ Sync Complete. Broken commands removed.")
            bot.synced = True
        except Exception as e:
            print(f"❌ Sync Error: {e}")

    try: bot.add_view(InviteCopyView())
    except: pass
    
    for g in bot.guilds:
        try: await rehydrate_role_panel(bot, g)
        except: pass

@bot.event
async def on_guild_join(guild: discord.Guild):
    await _prime_invites_cache(guild)
    try: await rehydrate_role_panel(bot, guild)
    except: pass

# ==================== CORE EVENT HANDLING (Audit Only) ====================

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
    # --- NO VOICEMASTER LOGIC HERE ---
    
    # --- SHADOWSYN AUDIT LOGIC ---
    if member.bot: return
    target, _ = await resolve_target(bot, DEFAULT_AUDIT_THREAD_ID)
    if not target: return

    m_name = safe_display_name(member)

    # Moves/Joins/Leaves Logging
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

    # Mute/Deafen (Moderator actions)
    if before.mute != after.mute:
        entry = await _find_audit_action(member.guild, discord.AuditLogAction.member_update, member.id)
        if entry:
            actor = safe_display_name(entry.user)
            try: await target.send(f"{actor} {'muted' if after.mute else 'unmuted'} {m_name}")
            except: pass
            return

    # Deaf/Undeaf (Moderator actions)
    if before.deaf != after.deaf:
        entry = await _find_audit_action(member.guild, discord.AuditLogAction.member_update, member.id)
        if entry:
            actor = safe_display_name(entry.user)
            try: await target.send(f"{actor} {'deafened' if after.deaf else 'undeafened'} {m_name}")
            except: pass
            return

    # Self Toggles
    if before.self_mute != after.self_mute or before.self_deaf != after.self_deaf:
        try: await target.send(f"🎛️ {m_name} toggled mute/deafen")
        except: pass

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

# ===================== MUSIC COMMANDS (NATIVE) ==================

async def ensure_voice_simple(interaction: discord.Interaction):
    if not interaction.user.voice:
        await safe_reply(interaction, "❌ Join a VC first!", ephemeral=True)
        return None
    
    channel = interaction.user.voice.channel
    vc = interaction.guild.voice_client

    try:
        if vc and vc.is_connected():
            if vc.channel.id != channel.id:
                await vc.move_to(channel)
            return vc
        else:
            return await channel.connect(timeout=10, reconnect=True)
    except Exception as e:
        print(f"[DEBUG] Voice Connect Error: {e}")
        await safe_reply(interaction, f"❌ Voice Error: {e}", ephemeral=True)
        return None

class MusicSelect(Select):
    def __init__(self, tracks: List[dict]):
        self.tracks = tracks
        options = []
        for i, t in enumerate(tracks[:5]):
            label = t.get('title', 'Unknown Title')[:95]
            desc = t.get('channel', 'Unknown Artist')[:95]
            options.append(SelectOption(label=f"{i+1}. {label}", description=desc, value=str(i), emoji="🎵"))
        
        super().__init__(placeholder="Select a song to play...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: Interaction):
        await safe_defer(interaction)
        
        idx = int(self.values[0])
        track = self.tracks[idx]
        url = track.get('url') or track.get('webpage_url')
        
        vc = await ensure_voice_simple(interaction)
        if not vc: return

        if vc.is_playing():
            vc.stop()
            if interaction.guild.id in bot.audio_queues:
                bot.audio_queues[interaction.guild.id].clear()

        try:
            player = await YTDLSource.from_url(url, loop=bot.loop, stream=True)
            vc.play(player)
            
            embed = discord.Embed(title="▶️ Now Playing", description=f"[{player.title}]({player.url})", color=THEME_PRIMARY)
            await interaction.edit_original_response(content="", embed=embed, view=None)
        except Exception as e:
            await interaction.followup.send(f"❌ Error playing track: {e}", ephemeral=True)

class MusicSearchView(View):
    def __init__(self, tracks: List[dict]):
        super().__init__(timeout=60)
        self.add_item(MusicSelect(tracks))

@bot.tree.command(name="play", description="Search & Play music")
@app_commands.describe(search="Song name or URL")
async def play(interaction: discord.Interaction, search: str):
    await safe_defer(interaction, ephemeral=True)
    
    try:
        # 1. Direct Link
        if re.match(r'^https?://', search):
            vc = await ensure_voice_simple(interaction)
            if not vc: return
            if vc.is_playing(): vc.stop()
            
            player = await YTDLSource.from_url(search, loop=bot.loop, stream=True)
            vc.play(player)
            await safe_reply(interaction, f"▶️ **Playing:** {player.title}", ephemeral=True)
            return

        # 2. Search
        data = await bot.loop.run_in_executor(None, lambda: ytdl.extract_info(f"ytsearch5:{search}", download=False))
        
        if 'entries' not in data or not data['entries']:
            await safe_reply(interaction, "❌ No results found.", ephemeral=True)
            return
            
        tracks = data['entries']
        view = MusicSearchView(tracks)
        await safe_reply(interaction, f"🔎 Results for **{search}**:", view=view, ephemeral=True)

    except Exception as e:
        print(f"[DEBUG] Play Error: {e}")
        await safe_reply(interaction, f"❌ Error: `{e}`", ephemeral=True)

@bot.tree.command(name="stop", description="Stop music and disconnect")
async def stop(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc:
        await vc.disconnect()
        if interaction.guild.id in bot.audio_queues:
            bot.audio_queues[interaction.guild.id].clear()
        await safe_reply(interaction, "⏹️ Disconnected.", ephemeral=True)
    else:
        await safe_reply(interaction, "ℹ️ Not connected.", ephemeral=True)

# ===================== /SPEAK (TTS QUEUE) ==================

def check_queue(guild_id: int, voice_client: discord.VoiceClient):
    if not voice_client or not voice_client.is_connected():
        return
    q = bot.audio_queues.get(guild_id)
    if q and len(q) > 0:
        next_file = q.popleft()
        if os.path.exists(next_file):
            voice_client.play(
                discord.FFmpegPCMAudio(next_file),
                after=lambda e: check_queue(guild_id, voice_client)
            )
        else:
            check_queue(guild_id, voice_client)

async def log_speak_usage(inter, text, lang):
    target, _ = await resolve_target(bot, SPEAK_LOG_THREAD_ID)
    if target:
        embed = discord.Embed(title="🗣️ /speak used", color=THEME_PRIMARY)
        embed.add_field(name="User", value=str(inter.user), inline=False)
        embed.add_field(name="Language", value=lang, inline=True)
        embed.add_field(name="Text", value=text[:1024], inline=False)
        try: await target.send(embed=embed)
        except: pass

@bot.tree.command(name="speak", description="Speak text in your VC")
@app_commands.describe(text="Message", language="Target language")
@app_commands.choices(language=LANG_CHOICES)
async def speak(interaction: discord.Interaction, text: str, language: app_commands.Choice[str] = None):
    if not isinstance(interaction.user, discord.Member) or not any(r.id == ROLE_MEMBER_ID for r in interaction.user.roles):
        return await safe_reply(interaction, "❌ `/speak` is restricted to Members.", ephemeral=True)

    await safe_defer(interaction, ephemeral=True)
    if not ffmpeg_available(): return await safe_reply(interaction, "❌ FFmpeg missing", ephemeral=True)
    
    vc = await ensure_voice_simple(interaction)
    if not vc: return

    lang_code = (language.value if language else "en").lower()
    loop = asyncio.get_running_loop()

    try:
        to_say = text
        if lang_code != "en":
            try:
                translation = await loop.run_in_executor(None, lambda: translator.translate(text, src="en", dest=lang_code))
                to_say = translation.text
            except: 
                await safe_reply(interaction, "⚠️ Translate failed, using original.", ephemeral=True)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f: 
            tmp_path = f.name
        
        await loop.run_in_executor(None, lambda: gTTS(text=to_say, lang=lang_code).save(tmp_path))

        guild_id = interaction.guild.id
        if guild_id not in bot.audio_queues:
            bot.audio_queues[guild_id] = deque()

        if vc.is_playing():
            bot.audio_queues[guild_id].append(tmp_path)
            await safe_reply(interaction, "✅ Queued text", ephemeral=True)
        else:
            vc.play(
                discord.FFmpegPCMAudio(tmp_path),
                after=lambda e: check_queue(guild_id, vc)
            )
            await safe_reply(interaction, "✅ Spoke text", ephemeral=True)
            
        await log_speak_usage(interaction, text, lang_code)
        
    except Exception as e:
        await safe_reply(interaction, f"❌ Error: `{e}`", ephemeral=True)

# ======================== CUSTOM EMBED MODAL =====================

class CustomEmbedModal(Modal, title="Send Custom Embed"):
    def __init__(self, target_id: int):
        super().__init__(timeout=300)
        self.target_id = target_id
        self.title_input = TextInput(label="Title", max_length=256)
        self.message_input = TextInput(label="Message", style=discord.TextStyle.paragraph, max_length=4000)
        self.add_item(self.title_input)
        self.add_item(self.message_input)

    async def on_submit(self, interaction):
        embed = discord.Embed(title=self.title_input.value, description=self.message_input.value, color=THEME_PRIMARY)
        ch = interaction.client.get_channel(self.target_id)
        if ch:
            try: await ch.send(embed=embed)
            except Exception as e: return await safe_reply(interaction, f"❌ Failed: `{e}`", ephemeral=True)
        await safe_reply(interaction, "✅ Posted", ephemeral=True)

@bot.tree.command(name="send_custom", description="Send a custom embed here")
async def send_custom(interaction: discord.Interaction):
    try: await interaction.response.send_modal(CustomEmbedModal(interaction.channel.id))
    except: await safe_reply(interaction, "❌ Couldn't open modal.", ephemeral=True)

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
        await safe_reply(interaction, content=msg, view=CopyInviteEphemeralView(), ephemeral=True)

def admin_only():
    async def predicate(inter: discord.Interaction) -> bool:
        if not isinstance(inter.user, discord.Member): return False
        return any(r.id == ROLE_ADMIN_ID for r in inter.user.roles)
    return app_commands.check(predicate)

@admin_only()
@bot.tree.command(name="send_welcome", description="Post the welcome card.")
async def send_welcome(interaction: discord.Interaction, target: Union[discord.TextChannel, discord.Thread, None] = None):
    await safe_defer(interaction, ephemeral=True)
    dest = target or interaction.channel
    try:
        view = InviteCopyView()
        msg = await dest.send(embed=welcome_embed(), view=view)
        try: await msg.pin(reason="ShadowSyn Welcome")
        except: pass
        await safe_reply(interaction, f"✅ Posted in {dest.mention}.", ephemeral=True)
    except Exception as e:
        await safe_reply(interaction, f"❌ Failed: `{e}`", ephemeral=True)

@admin_only()
@bot.tree.command(name="welcome_update", description="Update welcome card.")
async def welcome_update(interaction: discord.Interaction, message_id: Optional[str] = None, target: Union[discord.TextChannel, discord.Thread, None] = None):
    await safe_defer(interaction, ephemeral=True)
    dest = target or interaction.channel
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
    if not msg: return await safe_reply(interaction, "❌ Card not found.", ephemeral=True)
    try:
        await msg.edit(embed=welcome_embed(), view=InviteCopyView())
        await safe_reply(interaction, "✅ Updated.", ephemeral=True)
    except Exception as e:
        await safe_reply(interaction, f"❌ Failed: `{e}`", ephemeral=True)

# ====================== INVITE→ROLE ADMIN COMMANDS ======================

invite_role_group = app_commands.Group(name="invite_role", description="Map invite codes to auto-roles on join (admin).")

@invite_role_group.command(name="add", description="Map an invite (code/url/vanity) to a role.")
@app_commands.describe(invite="Invite code, invite URL, or the word 'vanity'", role="Role to auto-assign")
@admin_only()
async def invite_role_add(interaction: discord.Interaction, invite: str, role: discord.Role):
    await safe_defer(interaction, ephemeral=True)
    guild = interaction.guild
    code = normalize_invite_code(invite)
    if not code: return await safe_reply(interaction, "❌ Invalid invite.", ephemeral=True)
    mapping = get_invite_role_map(guild.id)
    mapping[code] = role.id
    set_invite_role_map(guild.id, mapping)
    label = "vanity" if code == "vanity" else f"`{code}`"
    await safe_reply(interaction, f"✅ Mapped {label} → {role.mention}", ephemeral=True)

@invite_role_group.command(name="remove", description="Remove an invite→role mapping.")
@admin_only()
async def invite_role_remove(interaction: discord.Interaction, invite: str):
    await safe_defer(interaction, ephemeral=True)
    guild = interaction.guild
    code = normalize_invite_code(invite)
    if not code: return await safe_reply(interaction, "❌ Invalid invite.", ephemeral=True)
    mapping = get_invite_role_map(guild.id)
    if code not in mapping: return await safe_reply(interaction, "ℹ️ No mapping exists.", ephemeral=True)
    mapping.pop(code, None)
    set_invite_role_map(guild.id, mapping)
    await safe_reply(interaction, f"✅ Removed mapping for {code}.", ephemeral=True)

@invite_role_group.command(name="list", description="List current invite→role mappings.")
@admin_only()
async def invite_role_list(interaction: discord.Interaction):
    await safe_defer(interaction, ephemeral=True)
    guild = interaction.guild
    mapping = get_invite_role_map(guild.id)
    if not mapping: return await safe_reply(interaction, "No invite-role mappings set.", ephemeral=True)
    lines = []
    for code, role_id in sorted(mapping.items(), key=lambda kv: kv[0]):
        role = guild.get_role(int(role_id))
        lines.append(f"- **{code}** → {role.mention if role else role_id}")
    await safe_reply(interaction, "\n".join(lines)[:4000], ephemeral=True)

bot.tree.add_command(invite_role_group)

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
    async def predicate(inter): return isinstance(inter.user, discord.Member) and any(r.id == ROLE_YT_MANAGER_ID for r in inter.user.roles)
    return app_commands.check(predicate)

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

@yt_locked()
@bot.tree.command(name="yt_add", description="Watch a YouTube channel.")
async def yt_add(interaction: discord.Interaction, channel_url_or_id: str):
    await safe_defer(interaction, ephemeral=True)
    ch_id = await normalize_channel_id(channel_url_or_id) if "normalize_channel_id" in globals() else channel_url_or_id
    if not ch_id: return await safe_reply(interaction, "❌ Invalid channel.", ephemeral=True)
    store = _load_yt_store()
    store["channels"].setdefault(ch_id, {"last_video_id": None, "channel_title": ""})
    _save_yt_store(store)
    _add_alias(channel_url_or_id, ch_id)
    await safe_reply(interaction, f"✅ Watching `{ch_id}`.", ephemeral=True)

@yt_locked()
@bot.tree.command(name="yt_remove", description="Stop watching a YouTube channel.")
async def yt_remove(interaction: discord.Interaction, channel_id_or_url: str):
    await safe_defer(interaction, ephemeral=True)
    ch_id = _lookup_alias(channel_id_or_url)
    if not ch_id: ch_id = channel_id_or_url
    store = _load_yt_store()
    if store.get("channels", {}).pop(ch_id, None) is None: return await safe_reply(interaction, "ℹ️ Not watching.", ephemeral=True)
    _save_yt_store(store)
    await safe_reply(interaction, f"✅ Removed `{ch_id}`.", ephemeral=True)

@yt_locked()
@bot.tree.command(name="yt_list", description="List watched YouTube channels.")
async def yt_list(interaction: discord.Interaction):
    await safe_defer(interaction, ephemeral=True)
    store = _load_yt_store()
    channels = store.get("channels", {})
    if not channels: return await safe_reply(interaction, "No channels.", ephemeral=True)
    lines = []
    for ch_id, cfg in channels.items():
        title = cfg.get("channel_title") or "Unknown"
        lines.append(f"- **{title}** (`{ch_id}`)")
    await safe_reply(interaction, "\n".join(lines)[:1990], ephemeral=True)

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
        await safe_defer(interaction)
        if self.page > 0:
            self.page -= 1
            self._refresh_add_select()
            self._update_page_buttons()
            try: await interaction.message.edit(view=self)
            except: pass

    async def _on_next_page(self, interaction: Interaction):
        await safe_defer(interaction)
        if self.page < self._total_pages() - 1:
            self.page += 1
            self._refresh_add_select()
            self._update_page_buttons()
            try: await interaction.message.edit(view=self)
            except: pass

    async def _on_select_toggle(self, interaction: Interaction):
        await safe_defer(interaction, ephemeral=True)
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
        await safe_reply(interaction, embed=embed, ephemeral=True)

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

@admin_only()
@bot.tree.command(name="roles_post", description="Post role panel.")
async def roles_post(interaction: discord.Interaction, target: Union[discord.TextChannel, discord.Thread, None] = None):
    await safe_defer(interaction, ephemeral=True)
    guild = interaction.guild
    cfg = get_guild_role_cfg(guild.id)
    dest = target or interaction.channel
    try:
        view = DualRolePickerView(guild, cfg.get("options", []))
        msg = await dest.send(embed=role_picker_embed(), view=view)
        cfg["panel"] = {"channel_id": dest.id, "message_id": msg.id}
        set_guild_role_cfg(guild.id, cfg)
        try: bot.add_view(view, message_id=msg.id)
        except: pass
        await safe_reply(interaction, f"✅ Posted in {dest.mention}.", ephemeral=True)
    except Exception as e: await safe_reply(interaction, f"❌ Failed: `{e}`", ephemeral=True)

@admin_only()
@bot.tree.command(name="roles_add", description="Add roles to picker.")
async def roles_add(interaction: discord.Interaction, roles: str):
    await safe_defer(interaction, ephemeral=True)
    ids = _parse_role_mentions(roles)
    cfg = get_guild_role_cfg(interaction.guild.id)
    existing = {int(o["role_id"]) for o in cfg.get("options", [])}
    added = []
    for rid in ids:
        if rid in existing: continue
        r = interaction.guild.get_role(rid)
        if r:
            cfg.setdefault("options", []).append({"role_id": r.id, "label": r.name})
            added.append(r.name)
    set_guild_role_cfg(interaction.guild.id, cfg)
    await safe_reply(interaction, f"✅ Added: {', '.join(added)}", ephemeral=True)

@admin_only()
@bot.tree.command(name="roles_remove", description="Remove roles from picker.")
async def roles_remove(interaction: discord.Interaction, roles: str):
    await safe_defer(interaction, ephemeral=True)
    ids = set(_parse_role_mentions(roles))
    cfg = get_guild_role_cfg(interaction.guild.id)
    opts = [o for o in cfg.get("options", []) if int(o["role_id"]) not in ids]
    cfg["options"] = opts
    set_guild_role_cfg(interaction.guild.id, cfg)
    await safe_reply(interaction, "✅ Removed roles.", ephemeral=True)

@admin_only()
@bot.tree.command(name="roles_sync", description="Refresh panel.")
async def roles_sync(interaction: discord.Interaction):
    await safe_defer(interaction, ephemeral=True)
    cfg = get_guild_role_cfg(interaction.guild.id)
    panel = cfg.get("panel")
    if not panel: return await safe_reply(interaction, "No panel.", ephemeral=True)
    try:
        ch = interaction.guild.get_channel(panel["channel_id"])
        msg = await ch.fetch_message(panel["message_id"])
        view = DualRolePickerView(interaction.guild, cfg.get("options", []))
        await msg.edit(embed=role_picker_embed(), view=view)
        try: bot.add_view(view, message_id=msg.id)
        except: pass
        await safe_reply(interaction, "✅ Synced.", ephemeral=True)
    except: await safe_reply(interaction, "❌ Failed to sync.", ephemeral=True)

# =============================== RUN ============================

def main():
    print("FFMPEG PATH:", which("ffmpeg"))
    print("PERSIST_ROOT:", PERSIST_ROOT)
    bot.run(TOKEN)

if __name__ == "__main__":
    main()
