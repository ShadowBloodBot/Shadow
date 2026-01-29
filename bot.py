# bot.py — ShadowSyn Unified System
#
# === MODULES INCLUDED ===
# 1. ShadowSyn Core (Welcome, Speak, Audit, Departures, Roles)
# 2. VoiceMaster (Join-to-Create, Dynamic VCs, Control Panel)
#
# Env: DISCORD_TOKEN
# Persistence: role_picker.json, youtube_watch.json, invite_roles.json, active_vcs.json

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
from discord import app_commands, ButtonStyle, SelectOption, Interaction
from discord.ui import View, Button, Modal, TextInput, Select, button, select
from gtts import gTTS
from shutil import which
from googletrans import Translator
import aiohttp
import xml.etree.ElementTree as ET
from discord.utils import get

# =========================== CONSTANTS ===========================

# --- ShadowSyn Config ---
VANITY_INVITE  = "https://discord.gg/shadowsyn"
THEME_PRIMARY  = 0x2B0B35

ARRIVALS_THREAD_ID      = 959629903186259978
ROLE_MINION_ID          = 955600021502431233
ROLE_ADMIN_ID           = 1214794734770323466
ROLE_MEMBER_ID          = 955600320287887400
SPEAK_LOG_THREAD_ID     = 1400048671973703690
DEPARTURES_THREAD_ID    = 960088192177029140

# --- FIX: Restored Missing Constants ---
DEFAULT_TARGET_ID       = 1166874144395247757
DEFAULT_AUDIT_THREAD_ID = 961726632249425930

ROLE_YT_MANAGER_ID      = 960088893351415898
YT_POST_TARGET_ID       = 959631286882934784
YT_POLL_SECONDS         = 180
YT_USER_AGENT           = "ShadowSynBot/YouTubeWatcher"

# --- VoiceMaster Config ---
JOIN_TO_CREATE_CHANNEL_ID = 1398618132788281364
VC_CATEGORY_ID            = 908659586536468542
VC_DEFAULT_BITRATE        = 384000
VC_DEFAULT_USER_LIMIT     = 0
ADMIN_ROLE_NAME           = "SHADOW"

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

# ==================== PERSISTENCE ROOT & FILES ===================

PERSIST_ROOT = Path(os.getenv("PERSIST_PATH", "/data")).resolve()
try:
    PERSIST_ROOT.mkdir(parents=True, exist_ok=True)
except Exception:
    PERSIST_ROOT = Path(".").resolve()

# --- Files ---
ROLE_STORE = (PERSIST_ROOT / "role_picker.json")
YT_STORE = (PERSIST_ROOT / "youtube_watch.json")
INVITE_ROLE_STORE = (PERSIST_ROOT / "invite_roles.json")
ACTIVE_VCS_STORE = (PERSIST_ROOT / "active_vcs.json")
CONFIG_PATH = Path("welcome_config.json")

# ==================== VOICEMASTER UTILS & PERSISTENCE =================

_SANS_BOLD_ITALIC_MAP = {
    "A": "𝘼", "B": "𝘽", "C": "𝘾", "D": "𝘿", "E": "𝙀", "F": "𝙁", "G": "𝙂",
    "H": "𝙃", "I": "𝙄", "J": "𝙅", "K": "𝙆", "L": "𝙇", "M": "𝙈", "N": "𝙉",
    "O": "𝙊", "P": "𝙋", "Q": "𝙌", "R": "𝙍", "S": "𝙎", "T": "𝙏", "U": "𝙐",
    "V": "𝙑", "W": "𝙒", "X": "𝙓", "Y": "𝙔", "Z": "𝙕",
    "a": "𝙖", "b": "𝙗", "c": "𝙘", "d": "𝙙", "e": "𝙚", "f": "𝙛", "g": "𝙜",
    "h": "𝙝", "i": "𝙞", "j": "𝙟", "k": "𝙠", "l": "𝙡", "m": "𝙢", "n": "𝙣",
    "o": "𝙤", "p": "𝙥", "q": "𝙦", "r": "𝙧", "s": "𝙨", "t": "𝙩", "u": "𝙪",
    "v": "𝙫", "w": "𝙬", "x": "𝙭", "y": "𝙮", "z": "𝙯",
}

def _to_sans_bold_italic(text: str) -> str:
    return "".join(_SANS_BOLD_ITALIC_MAP.get(ch, ch) for ch in text)

def _limit_channel_name(name: str, limit: int = 100) -> str:
    return name[:limit] if len(name) > limit else name

def _load_active_vcs() -> Set[int]:
    if ACTIVE_VCS_STORE.exists():
        try:
            data = json.loads(ACTIVE_VCS_STORE.read_text())
            return set(data)
        except Exception:
            return set()
    return set()

def _save_active_vcs(vcs: Set[int]) -> None:
    try:
        ACTIVE_VCS_STORE.write_text(json.dumps(list(vcs)))
    except Exception:
        pass

# Global runtime registry (synced to disk)
active_temp_vcs: Set[int] = _load_active_vcs()

# ==================== VOICEMASTER UI COMPONENTS =================

class VCNameModal(Modal, title="Rename Voice Channel"):
    def __init__(self, vc):
        super().__init__()
        self.vc = vc
        self.new_name = TextInput(label="New VC Name", placeholder="Enter name...", required=True, max_length=50)
        self.add_item(self.new_name)

    async def on_submit(self, interaction: Interaction):
        try:
            await self.vc.edit(name=self.new_name.value)
            await interaction.response.send_message(f"✅ Renamed to **{self.new_name.value}**", ephemeral=True)
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
        # Sort by position, take top 24
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
        try:
            self.add_item(RoleRestrictSelect(vc, creator))
        except Exception:
            pass

    async def _check_perm(self, interaction: Interaction) -> bool:
        if interaction.user.id == self.creator.id:
            return True
        # Allow admins to delete
        if interaction.data.get("custom_id") == "delete_vc":
            if any(r.name == ADMIN_ROLE_NAME or r.id == ROLE_ADMIN_ID for r in interaction.user.roles):
                return True
        await interaction.response.send_message("🚫 Only the VC creator can use this.", ephemeral=True)
        return False

    @button(label="🔒 Lock", style=ButtonStyle.danger, custom_id="lock_vc")
    async def lock(self, interaction: Interaction, button: Button):
        if not await self._check_perm(interaction): return
        try:
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(connect=False),
                self.creator: discord.PermissionOverwrite(connect=True),
            }
            ar = discord.utils.get(interaction.guild.roles, name=ADMIN_ROLE_NAME)
            if ar: overwrites[ar] = discord.PermissionOverwrite(connect=True)
            await self.vc.edit(overwrites=overwrites)
            await interaction.response.send_message("🔒 VC locked.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed: {e}", ephemeral=True)

    @button(label="🔓 Unlock", style=ButtonStyle.success, custom_id="unlock_vc")
    async def unlock(self, interaction: Interaction, button: Button):
        if not await self._check_perm(interaction): return
        try:
            await self.vc.set_permissions(interaction.guild.default_role, connect=True)
            await interaction.response.send_message("🔓 VC unlocked.", ephemeral=True)
        except Exception:
            pass

    @button(label="❌ Delete", style=ButtonStyle.red, custom_id="delete_vc")
    async def delete(self, interaction: Interaction, button: Button):
        if not await self._check_perm(interaction): return
        try:
            await self.vc.delete()
            await interaction.response.send_message("🗑️ Deleted.", ephemeral=True)
        except Exception:
            pass

    @button(label="✏️ Rename", style=ButtonStyle.blurple, custom_id="rename_vc")
    async def rename(self, interaction: Interaction, button: Button):
        if not await self._check_perm(interaction): return
        await interaction.response.send_modal(VCNameModal(self.vc))

    @button(label="👢 Kick", style=ButtonStyle.gray, custom_id="kick_members")
    async def kick(self, interaction: Interaction, button: Button):
        if not await self._check_perm(interaction): return
        members = [m for m in self.vc.members if m != interaction.guild.me]
        if not members:
            return await interaction.response.send_message("⚠️ No members to kick.", ephemeral=True)
        await interaction.response.send_message("Select member:", view=KickMemberView(self.vc, members), ephemeral=True)

    @select(
        placeholder="Bitrate",
        options=[
            SelectOption(label="64 kbps", value="64000"),
            SelectOption(label="96 kbps", value="96000"),
            SelectOption(label="128 kbps", value="128000"),
            SelectOption(label="256 kbps", value="256000"),
            SelectOption(label="384 kbps", value="384000"),
        ],
        custom_id="bitrate_select"
    )
    async def bitrate(self, interaction: Interaction, select: Select):
        if not await self._check_perm(interaction): return
        try:
            val = int(select.values[0])
            await self.vc.edit(bitrate=val)
            await interaction.response.send_message(f"📶 Bitrate: {val//1000} kbps.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed: {e}", ephemeral=True)

    @select(
        placeholder="User Limit",
        options=[
            SelectOption(label="Unlimited", value="0"),
            SelectOption(label="2", value="2"),
            SelectOption(label="5", value="5"),
            SelectOption(label="10", value="10"),
            SelectOption(label="25", value="25"),
        ],
        custom_id="limit_select"
    )
    async def limit(self, interaction: Interaction, select: Select):
        if not await self._check_perm(interaction): return
        try:
            val = int(select.values[0])
            await self.vc.edit(user_limit=val)
            await interaction.response.send_message(f"👥 Limit: {val if val else 'Unlimited'}.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed: {e}", ephemeral=True)

async def send_control_panel(vc: discord.VoiceChannel, creator: discord.Member):
    try:
        await asyncio.sleep(2.0) # wait for connection
        # Important: use vc.send() to message the Voice Text Channel
        await vc.send(
            content=f"{creator.mention}, here is your **VoiceMaster** controls:",
            view=VCControlPanel(vc, creator)
        )
    except Exception as e:
        print(f"JTC Error: {e}")

# ==================== GENERAL PERSISTENCE LOADERS ====================

def load_config() -> dict:
    base = {"welcome_target_id": DEFAULT_TARGET_ID, "audit_channel_id": DEFAULT_AUDIT_THREAD_ID}
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text())
            if isinstance(data, dict): base.update(data)
        except: pass
    return base

config = load_config()

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
        intents = discord.Intents.all()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self._yt_task: Optional[asyncio.Task] = None

    async def setup_hook(self):
        for g in self.guilds:
            await _prime_invites_cache(g)
        try: self.add_view(InviteCopyView())
        except: pass
        await self.tree.sync()
        for g in self.guilds:
            try: await rehydrate_role_panel(self, g)
            except: pass
        if self._yt_task is None:
            self._yt_task = asyncio.create_task(youtube_watch_loop(self))

bot = ShadowSynBot()

@bot.event
async def on_ready():
    try: bot.add_view(InviteCopyView())
    except: pass
    print(f"✅ Logged in as {bot.user}")
    print(f"Active Temp VCs: {len(active_temp_vcs)} loaded from disk.")

@bot.event
async def on_guild_join(guild: discord.Guild):
    await _prime_invites_cache(guild)
    try: await rehydrate_role_panel(bot, guild)
    except: pass

# ==================== UNIFIED EVENT HANDLING ====================
# Merges VoiceMaster (Creation/Cleanup) + ShadowSyn (Audit)

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
    
    # -----------------------------------------------
    # 1. VOICEMASTER LOGIC (Join to Create)
    # -----------------------------------------------
    
    # CASE A: User Joined Master Channel
    if after.channel and after.channel.id == JOIN_TO_CREATE_CHANNEL_ID:
        try:
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
            
            # Register & Move
            active_temp_vcs.add(new_vc.id)
            _save_active_vcs(active_temp_vcs) # Persist immediately
            await member.move_to(new_vc)
            
            # Send Control Panel
            asyncio.create_task(send_control_panel(new_vc, member))
            
        except Exception as e:
            print(f"[JTC Error] {e}")

    # CASE B: User Left a Temp Channel (Auto-Delete)
    if before.channel and before.channel.id != JOIN_TO_CREATE_CHANNEL_ID:
        if before.channel.id in active_temp_vcs:
            if len(before.channel.members) == 0:
                try:
                    await before.channel.delete()
                    active_temp_vcs.discard(before.channel.id)
                    _save_active_vcs(active_temp_vcs) # Update persistence
                except Exception as e:
                    print(f"[JTC Delete Error] {e}")
            elif before.channel != after.channel:
                 # Optional: If creator left, maybe transfer ownership? (Logic omitted for simplicity)
                 pass

    # -----------------------------------------------
    # 2. SHADOWSYN LOGIC (Audit Logging)
    # -----------------------------------------------
    if member.bot: return
    target, _ = await resolve_target(bot, DEFAULT_AUDIT_THREAD_ID)
    if not target: return

    m_name = safe_display_name(member)

    # Moves/Joins/Leaves
    if before.channel != after.channel:
        # Avoid logging the "Move to temp VC" spam if desired, 
        # but technically it is a move, so we keep logging it.
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

# ===================== /SPEAK (TTS + translate) ==================

async def ensure_voice(inter: discord.Interaction):
    try:
        if not inter.guild or not isinstance(inter.user, discord.Member):
            await safe_reply(inter, "❌ No guild/member", ephemeral=True)
            return None
        state = inter.user.voice
        if not state or not state.channel:
            await safe_reply(inter, "❌ Join a VC first.", ephemeral=True)
            return None
        vc = discord.utils.get(bot.voice_clients, guild=inter.guild)
        if vc and vc.is_connected():
            if vc.channel.id == state.channel.id: return vc
            await vc.move_to(state.channel)
            return vc
        return await state.channel.connect(reconnect=True, timeout=15)
    except Exception as e:
        await safe_reply(inter, f"❌ VC error: `{e}`", ephemeral=True)
        return None

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
    vc = await ensure_voice(interaction)
    if vc is None: return

    lang_code = (language.value if language else "en").lower()
    to_say = text
    if lang_code != "en":
        try: to_say = translator.translate(text, src="en", dest=lang_code).text
        except: await safe_reply(interaction, "⚠️ Translate failed, using original.", ephemeral=True)

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f: tmp = f.name
        gTTS(text=to_say, lang=lang_code).save(tmp)
        vc.play(discord.FFmpegPCMAudio(tmp))
        await log_speak_usage(interaction, text, lang_code)
        await safe_reply(interaction, "✅ Spoke text", ephemeral=True)
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
        msg = await dest.send(embed
