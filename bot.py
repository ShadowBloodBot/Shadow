# bot.py — ShadowSyn (Master: v6.9 - Speak Command Overhaul & Error Handler)
#
# === FEATURES ===
# [x] ⚔️ WAR ROSTER: "Not Attending" status and category.
# [x] 🎰 CASINO: Slots, Chicken, Dice, Duel, Wallet, Dashboard.
# [x] 🎒 RPG: Tower, Inventory, Loot, Shop, Stats, Capture, Revive, Leaderboard.
# [x] 🎛️ VOICEMASTER & MUSIC: JTC Control Panel & Music Playback.
# [x] 🗣️ TTS (Speak): Fixed file-locking, coroutine handling, and async timeouts.
# [x] 🛡️ STABILITY: Global Error Handler added to catch silent CheckFailures.
#
# LIBRARY: py-cord[voice]

import os
import re
import json
import asyncio
import tempfile
import time
import traceback
import random
import shutil
import uuid
from pathlib import Path
from typing import Optional, List, Set, Union
from datetime import datetime, timezone, timedelta
from collections import deque

import discord
from discord import Option, ButtonStyle, SelectOption, Interaction, AuditLogAction
from discord.ui import View, Button, Modal, TextInput, Select
from discord.ext import commands, tasks

from gtts import gTTS
from shutil import which
from googletrans import Translator
from discord.utils import get
import yt_dlp

# =========================== CONSTANTS ===========================

THEME_PRIMARY   = 0x2B0B35
THEME_WIN       = 0x43B581 
THEME_LOSS      = 0xF04747 
THEME_GOLD      = 0xFFD700 
THEME_COMBAT    = 0xE67E22 

# --- RPG CONFIG ---
RARITY_COLORS = {
    "Common": 0x95A5A6,
    "Uncommon": 0x2ECC71,
    "Rare": 0x3498DB,
    "Epic": 0x9B59B6,
    "Legendary": 0xE67E22
}

ITEM_SLOTS = ["Main Hand", "Off Hand", "Armor", "Accessory"]

# --- CONFIGURATION IDs ---
ARRIVALS_THREAD_ID      = 959629903186259978
ROLE_MINION_ID          = 955600021502431233
SPEAK_LOG_THREAD_ID     = 1400048671973703690
DEPARTURES_THREAD_ID    = 960088192177029140
DEFAULT_TARGET_ID       = 1166874144395247757
DEFAULT_AUDIT_THREAD_ID = 961726632249425930
CASINO_CHANNEL_ID       = 1468766727134249091

# --- PERMISSIONS ---
ROLE_ADMIN_ID           = 1214794734770323466 
ROLE_DJ_ID              = 955600320287887400
OWNER_ID                = 482463400929263627
GAMBLER_ROLE_ID         = 955600320287887400  
WAR_ROLE_ID             = 955600320287887400

# --- VOICEMASTER ---
JOIN_TO_CREATE_CHANNEL_ID = 1398618132788281364
VC_CATEGORY_ID            = 908659586536468542
VC_DEFAULT_BITRATE        = 64000 
VC_DEFAULT_USER_LIMIT     = 0
ADMIN_ROLE_NAME           = "SHADOW"

# --- ECONOMY ---
SCOIN_PULL_AMOUNT = 5
SCOIN_COOLDOWN_HOURS = 3

# --- TTS CONFIG ---
translator = Translator()
LANG_CHOICES = ["English", "Japanese", "German", "Spanish", "French", "Italian", "Portuguese", "Russian", "Korean", "Chinese", "Hindi", "Indonesian", "Thai", "Vietnamese", "Tagalog"]
LANG_CODES = {
    "English": "en", "Japanese": "ja", "German": "de", "Spanish": "es", "French": "fr", 
    "Italian": "it", "Portuguese": "pt", "Russian": "ru", "Korean": "ko", "Chinese": "zh-CN", 
    "Hindi": "hi", "Indonesian": "id", "Thai": "th", "Vietnamese": "vi", "Tagalog": "tl"
}

# --- TOWER CONTENT ---
MONSTERS = {
    1: ["Sewer Rat", "Slime Blob", "Wild Dog", "Angry Bat", "Kobold Runt"],
    5: ["Goblin Scout", "Skeleton Warrior", "Bandit", "Giant Spider", "Orc Grunt"],
    15: ["Troll", "Ogre", "Gargoyle", "Vampire Spawn", "Cursed Armor", "Dark Elf"],
    30: ["Lich", "Demon Soldier", "Shadow Stalker", "Bone Golem", "Hellhound"],
    50: ["Void Walker", "Abyssal Horror", "Fallen Angel", "Dragon Whelp", "Void Titan"]
}

BIOMES = {
    "Sewers": {"range": (1, 20), "color": 0x2ECC71, "emoji": "🤢", "effect": "Toxic: 5% Poison Dmg every 5 turns."},
    "Catacombs": {"range": (21, 40), "color": 0x95A5A6, "emoji": "💀", "effect": "Darkness: 20% Miss Chance."},
    "Magma Core": {"range": (41, 60), "color": 0xE74C3C, "emoji": "🌋", "effect": "Heat: Skills cost 5 HP."},
    "Void": {"range": (61, 999), "color": 0x8E44AD, "emoji": "🔮", "effect": "Void: Enemies deal True Damage."}
}

# --- WAR ROSTER CONFIG ---
WAR_THREAD_ID = 1475981718904242309
QUINFALL_CLASSES = [
    ("Sword / Shield", "🛡️"), ("Life Staff", "🪄"), ("Two-Handed Sword", "🗡️"), ("Spear", "🍢"),
    ("Dual Axe", "🪓"), ("Dual Dagger", "⚔️"), ("War Hammer", "🔨"), ("Bow", "🏹"),
    ("Dual Crossbow", "🎯"), ("Arcane Staff", "🔮")
]

DEFAULT_HASTE_FACTS = [
    "Haste is a man lover", "Haste feeds knights to spearmen", "Haste is the potato peeler",
    "Haste hates women", "Haste loves fat chicks", "Haste would die for brightwood, bro",
    "Haste is a fitzroy enjoyer", "Haste used to get feudal in 3mins... used to",
    "Haste goes Pro scout", "Haste is in a good mood. Jks.", "Haste loves dating paki protestors",
    "Haste is a lefty greeny", "Haste has no dps", "Haste has beef with a dev of a game with sub 1000 players",
    "Haste cant afford ranger gear so he blames the dev", "Haste thinks Maya is fat",
    "Haste was MIA in Shadow Until Jed showed up", "Everyone prefers Haste over Boet",
    "Everyone likes it when Haste has a break down", "Everyone is scared Haste might get bashed at his restaurant",
    "Haste earns 70k a year and that gives Blood anxiety", "Haste Likes using a bow",
    "Haste doesn't have the muscle mass to carry a real life weapon.",
    "Haste never let go of New world.", "Haste only played Vrising cause he thought the outfits were cute."
]

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN: raise SystemExit("❌ DISCORD_TOKEN is not set.")

# ==================== PERSISTENCE ===================

PERSIST_ROOT = Path(os.getenv("PERSIST_PATH", "/data")).resolve()
try: PERSIST_ROOT.mkdir(parents=True, exist_ok=True)
except: PERSIST_ROOT = Path(".").resolve()

INVITE_ROLE_STORE = (PERSIST_ROOT / "invite_roles.json")
ACTIVE_VCS_STORE = (PERSIST_ROOT / "active_vcs.json")
HASTE_FACTS_STORE = (PERSIST_ROOT / "haste_facts.json")
SCOINS_STORE = (PERSIST_ROOT / "scoins.json")
TOWER_STORE = (PERSIST_ROOT / "tower_v6.json")
WAR_STORE = (PERSIST_ROOT / "wars.json")

active_haste_facts = []
scoins_db = {}
tower_db = {}
war_db = {}

def _atomic_write(file_path: Path, data: Union[dict, list, set]):
    try:
        content = json.dumps(list(data) if isinstance(data, set) else data, indent=2)
        temp_path = file_path.with_suffix(".tmp")
        temp_path.write_text(content, encoding='utf-8')
        temp_path.replace(file_path)
    except Exception as e:
        print(f"⚠️ Persistence Error [{file_path.name}]: {e}")

def _load_persistence():
    global active_haste_facts, scoins_db, tower_db, war_db
    if HASTE_FACTS_STORE.exists():
        try: active_haste_facts = json.loads(HASTE_FACTS_STORE.read_text())
        except: active_haste_facts = list(DEFAULT_HASTE_FACTS)
    else: active_haste_facts = list(DEFAULT_HASTE_FACTS)

    if SCOINS_STORE.exists():
        try: scoins_db = json.loads(SCOINS_STORE.read_text())
        except: scoins_db = {}

    if TOWER_STORE.exists():
        try: tower_db = json.loads(TOWER_STORE.read_text())
        except: tower_db = {}
        
    if WAR_STORE.exists():
        try: war_db = json.loads(WAR_STORE.read_text())
        except: war_db = {}

def _save_haste_facts(): _atomic_write(HASTE_FACTS_STORE, active_haste_facts)
def _save_scoins(): _atomic_write(SCOINS_STORE, scoins_db)
def _save_tower(): _atomic_write(TOWER_STORE, tower_db)
def _save_wars(): _atomic_write(WAR_STORE, war_db)

def get_balance(user_id: str) -> int:
    return scoins_db.get(str(user_id), {}).get("balance", 0)

def update_balance(user_id: str, amount: int):
    user_id = str(user_id)
    if user_id not in scoins_db: scoins_db[user_id] = {"balance": 0, "last_pull": 0}
    scoins_db[user_id]["balance"] += amount
    _save_scoins()

# ==================== PERMISSIONS & HELPERS ====================

def admin_only():
    def predicate(ctx):
        if not isinstance(ctx.author, discord.Member): return False
        return any(r.id == ROLE_ADMIN_ID for r in ctx.author.roles)
    return commands.check(predicate)

def dj_or_admin():
    def predicate(ctx):
        if not isinstance(ctx.author, discord.Member): return False
        if any(r.id == ROLE_ADMIN_ID for r in ctx.author.roles): return True
        if any(r.id == ROLE_DJ_ID for r in ctx.author.roles): return True
        return False
    return commands.check(predicate)

def owner_only():
    def predicate(ctx): return ctx.author.id == OWNER_ID
    return commands.check(predicate)

def is_gambler(user):
    if not isinstance(user, discord.Member): return False
    return any(r.id == GAMBLER_ROLE_ID for r in user.roles)
    
def is_war_role(user):
    if not isinstance(user, discord.Member): return False
    return any(r.id == WAR_ROLE_ID for r in user.roles)

def _load_active_vcs() -> Set[int]:
    if ACTIVE_VCS_STORE.exists():
        try: return set(json.loads(ACTIVE_VCS_STORE.read_text()))
        except: return set()
    return set()

def _save_active_vcs(vcs: Set[int]) -> None:
    _atomic_write(ACTIVE_VCS_STORE, vcs)

active_temp_vcs: Set[int] = _load_active_vcs()

def _to_sans_bold_italic(text: str) -> str:
    _map = {"A": "𝘼", "B": "𝘽", "C": "𝘾", "D": "𝘿", "E": "𝙀", "F": "𝙁", "G": "𝙂", "H": "𝙃", "I": "𝙄", "J": "𝙅", "K": "𝙆", "L": "𝙇", "M": "𝙈", "N": "𝙉", "O": "𝙊", "P": "𝙋", "Q": "𝙌", "R": "𝙍", "S": "𝙎", "T": "𝙏", "U": "𝙐", "V": "𝙑", "W": "𝙒", "X": "𝙓", "Y": "𝙔", "Z": "𝙕", "a": "𝙖", "b": "𝙗", "c": "𝙘", "d": "𝙙", "e": "𝙚", "f": "𝙛", "g": "𝙜", "h": "𝙝", "i": "𝙞", "j": "𝙟", "k": "𝙠", "l": "𝙡", "m": "𝙢", "n": "𝙣", "o": "𝙤", "p": "𝙥", "q": "𝙦", "r": "𝙧", "s": "𝙨", "t": "𝙩", "u": "𝙪", "v": "𝙫", "w": "𝙬", "x": "𝙭", "y": "𝙮", "z": "𝙯"}
    return "".join(_map.get(ch, ch) for ch in text)

def _limit_channel_name(name: str, limit: int = 100) -> str:
    return name[:limit] if len(name) > limit else name

async def safe_reply(ctx_or_inter, *args, **kwargs):
    try:
        if hasattr(ctx_or_inter, 'respond'): return await ctx_or_inter.respond(*args, **kwargs)
        elif hasattr(ctx_or_inter, 'response'):
            if not ctx_or_inter.response.is_done(): return await ctx_or_inter.response.send_message(*args, **kwargs)
            else: return await ctx_or_inter.followup.send(*args, **kwargs)
    except: return None

async def safe_defer(ctx, ephemeral=False):
    try: await ctx.defer(ephemeral=ephemeral)
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
            if vc.channel.id != channel.id: await vc.move_to(channel)
        else: vc = await channel.connect(timeout=10, reconnect=True)
        return vc
    except Exception as e:
        await safe_reply(ctx, f"❌ Voice Error: {e}", ephemeral=True)
        return None

def safe_avatar_url(member):
    try: return member.display_avatar.url
    except: return None

def format_age(dt):
    if not dt: return "Unknown"
    delta = utcnow() - dt
    if delta.days > 365:
        return f"{delta.days // 365} years ago"
    return f"{delta.days} days ago"

# ==================== DATA LOADERS ====================

def _load_invite_role_store():
    if INVITE_ROLE_STORE.exists():
        try: return json.loads(INVITE_ROLE_STORE.read_text())
        except: return {}
    return {}

def _save_invite_role_store(data):
    try: INVITE_ROLE_STORE.write_text(json.dumps(data, indent=2))
    except: pass

def get_invite_role_map(guild_id):
    store = _load_invite_role_store()
    raw = store.get(str(guild_id), {})
    return {str(k).lower(): int(v) for k, v in raw.items()}

def set_invite_role_map(guild_id, mapping):
    store = _load_invite_role_store()
    store[str(guild_id)] = {str(k).lower(): int(v) for k, v in (mapping or {}).items()}
    _save_invite_role_store(store)

_INVITE_CODE_RX = re.compile(r"(?:discord\.gg/|discord\.com/invite/)(?P<code>[A-Za-z0-9-]+)", re.I)
def normalize_invite_code(text):
    s = (text or "").strip()
    if not s: return None
    low = s.lower()
    if low in {"vanity", "vanity_url", "vanityurl"}: return "vanity"
    m = _INVITE_CODE_RX.search(s)
    if m: return m.group("code").lower()
    if re.fullmatch(r"[A-Za-z0-9-]{2,}", s): return s.lower()
    return None

_INVITES_CACHE = {}
def _can_track_invites(guild): return bool(guild.me and guild.me.guild_permissions.manage_guild)

async def _prime_invites_cache(guild):
    if not _can_track_invites(guild):
        _INVITES_CACHE[guild.id] = {}
        return
    try:
        invites = await guild.invites()
        _INVITES_CACHE[guild.id] = {inv.code: (inv.uses or 0) for inv in invites}
    except: _INVITES_CACHE[guild.id] = {}

async def _detect_join_source(member):
    guild = member.guild
    if not _can_track_invites(guild):
        try: return f"Joined via Vanity" if guild.vanity_url_code else None
        except: return None
    try:
        before = _INVITES_CACHE.get(guild.id, {})
        current = await guild.invites()
        increased = None
        for inv in current:
            if (inv.uses or 0) > before.get(inv.code, 0):
                increased = inv; break
        _INVITES_CACHE[guild.id] = {inv.code: (inv.uses or 0) for inv in current}
        if increased: return f"Joined via `{increased.code}`, invited by **{increased.inviter or 'Unknown'}**"
        try: return f"Joined via Vanity" if guild.vanity_url_code else None
        except: return None
    except: return None

async def _detect_used_invite_code(member):
    guild = member.guild
    if not _can_track_invites(guild):
        try: return "vanity" if guild.vanity_url_code else None
        except: return None
    try:
        before = _INVITES_CACHE.get(guild.id, {})
        current = await guild.invites()
        increased = None
        for inv in current:
            if (inv.uses or 0) > before.get(inv.code, 0):
                increased = inv; break
        _INVITES_CACHE[guild.id] = {inv.code: (inv.uses or 0) for inv in current}
        if increased: return increased.code.lower()
        try: return "vanity" if guild.vanity_url_code else None
        except: return None
    except: return None

async def _apply_invite_role(member, used_code):
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

# ==================== BOT INSTANCE ====================

class ShadowSynBot(discord.Bot):
    def __init__(self):
        super().__init__(intents=discord.Intents.all())
        self.audio_queues = {}

bot = ShadowSynBot()

# ==================== GLOBAL ERROR HANDLER ====================

@bot.event
async def on_application_command_error(ctx: discord.ApplicationContext, error: discord.DiscordException):
    if isinstance(error, commands.CheckFailure):
        await safe_reply(ctx, "⛔ Restricted: You do not have permission to use this command.", ephemeral=True)
    elif isinstance(error, commands.CommandOnCooldown):
        await safe_reply(ctx, f"⏳ Cooldown: Try again in {error.retry_after:.1f}s.", ephemeral=True)
    else:
        traceback.print_exc()
        await safe_reply(ctx, f"⚠️ An error occurred: {error}", ephemeral=True)

# ==================== WAR ROSTER LOGIC ====================

def generate_war_embed(data):
    embed = discord.Embed(title=f"⚔️ {data['title']}", description=f"**Time:** {data['time']}\nSelect your class and if you'll miss any fights below!", color=THEME_COMBAT)
    class_counts = {c[0]: [] for c in QUINFALL_CLASSES}
    
    for uid, info in data.get("roster", {}).items():
        if isinstance(info, str):
            cls = info
            absences = []
        else:
            cls = info.get("class")
            if "absences" in info: absences = info["absences"]
            elif "fights" in info: absences = [f for f in ["1", "2", "3", "4", "5"] if f not in info["fights"]]
            else: absences = []
            
        fight_str = f" *(Absent Round {', '.join(sorted(absences))})*" if absences else ""
        if cls in class_counts:
            class_counts[cls].append(f"<@{uid}>{fight_str}")
            
    total_confirmed = 0
    for class_name, emoji in QUINFALL_CLASSES:
        users = class_counts.get(class_name, [])
        if users:
            embed.add_field(name=f"{emoji} {class_name} ({len(users)})", value="\n".join(users), inline=False)
            total_confirmed += len(users)

    not_attending = data.get("not_attending", [])
    if not_attending:
        embed.add_field(name=f"❌ Not Attending ({len(not_attending)})", value="\n".join([f"<@{uid}>" for uid in not_attending]), inline=False)
            
    embed.set_footer(text=f"Total Confirmed: {total_confirmed} | Not Attending: {len(not_attending)}")
    return embed

class WarClassSelect(Select):
    def __init__(self):
        options = [SelectOption(label=name, value=name, emoji=emoji) for name, emoji in QUINFALL_CLASSES]
        super().__init__(placeholder="1. Select Class to Join...", options=options, custom_id="war_class_select", min_values=1, max_values=1, row=0)
    async def callback(self, interaction: Interaction):
        msg_id = str(interaction.message.id)
        if msg_id not in war_db: return await interaction.response.send_message("❌ War not found in database.", ephemeral=True)
        
        selected_class = self.values[0]
        uid = str(interaction.user.id)
        
        if "roster" not in war_db[msg_id]: war_db[msg_id]["roster"] = {}
        if "not_attending" not in war_db[msg_id]: war_db[msg_id]["not_attending"] = []
        if uid in war_db[msg_id]["not_attending"]: war_db[msg_id]["not_attending"].remove(uid)
            
        if uid not in war_db[msg_id]["roster"]:
            war_db[msg_id]["roster"][uid] = {"class": selected_class, "absences": []}
        else:
            if isinstance(war_db[msg_id]["roster"][uid], str): war_db[msg_id]["roster"][uid] = {"class": selected_class, "absences": []}
            else: war_db[msg_id]["roster"][uid]["class"] = selected_class
                
        _save_wars()
        await interaction.response.edit_message(embed=generate_war_embed(war_db[msg_id]))

class WarAttendanceSelect(Select):
    def __init__(self):
        options = [SelectOption(label=f"Absent Fight {i}", value=str(i), emoji="❌") for i in range(1, 6)]
        super().__init__(placeholder="2. Select Fights to MISS (Leave empty if attending all)", options=options, custom_id="war_attendance_select", min_values=0, max_values=5, row=1)
    async def callback(self, interaction: Interaction):
        msg_id = str(interaction.message.id)
        if msg_id not in war_db: return await interaction.response.send_message("❌ War not found.", ephemeral=True)
        uid = str(interaction.user.id)
        if uid not in war_db[msg_id].get("roster", {}): return await interaction.response.send_message("❌ Please select a Class first!", ephemeral=True)
            
        if isinstance(war_db[msg_id]["roster"][uid], str):
            war_db[msg_id]["roster"][uid] = {"class": war_db[msg_id]["roster"][uid], "absences": self.values}
        else:
            war_db[msg_id]["roster"][uid]["absences"] = self.values
            
        _save_wars()
        await interaction.response.edit_message(embed=generate_war_embed(war_db[msg_id]))

class WarNotAttendingButton(Button):
    def __init__(self):
        super().__init__(label="Not Attending", style=ButtonStyle.danger, custom_id="war_not_attending_btn", emoji="❌", row=2)
    async def callback(self, interaction: Interaction):
        msg_id = str(interaction.message.id)
        if msg_id not in war_db: return await interaction.response.send_message("❌ War not found.", ephemeral=True)
        uid = str(interaction.user.id)
        
        if "not_attending" not in war_db[msg_id]: war_db[msg_id]["not_attending"] = []
        if uid in war_db[msg_id].get("roster", {}): del war_db[msg_id]["roster"][uid]
        if uid not in war_db[msg_id]["not_attending"]: war_db[msg_id]["not_attending"].append(uid)
            
        _save_wars()
        await interaction.response.edit_message(embed=generate_war_embed(war_db[msg_id]))

class WarLeaveButton(Button):
    def __init__(self):
        super().__init__(label="Clear My Status", style=ButtonStyle.secondary, custom_id="war_leave_btn", emoji="🗑️", row=2)
    async def callback(self, interaction: Interaction):
        msg_id = str(interaction.message.id)
        if msg_id not in war_db: return await interaction.response.send_message("❌ War not found.", ephemeral=True)
        uid = str(interaction.user.id)
        modified = False
        
        if uid in war_db[msg_id].get("roster", {}):
            del war_db[msg_id]["roster"][uid]; modified = True
        if uid in war_db[msg_id].get("not_attending", []):
            war_db[msg_id]["not_attending"].remove(uid); modified = True
            
        if modified:
            _save_wars()
            await interaction.response.edit_message(embed=generate_war_embed(war_db[msg_id]))
        else:
            await interaction.response.send_message("⚠️ You haven't selected a status yet.", ephemeral=True)

class WarRosterView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(WarClassSelect())
        self.add_item(WarAttendanceSelect())
        self.add_item(WarNotAttendingButton())
        self.add_item(WarLeaveButton())

# ==================== MUSIC LOGIC ====================

YTDL_PLAY_OPTIONS = {'format': 'bestaudio/best', 'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s', 'restrictfilenames': True, 'noplaylist': True, 'nocheckcertificate': True, 'ignoreerrors': False, 'logtostderr': False, 'quiet': True, 'no_warnings': True, 'default_search': 'auto', 'source_address': '0.0.0.0', 'socket_timeout': 10, 'retries': 5}
YTDL_SEARCH_OPTIONS = YTDL_PLAY_OPTIONS.copy()
YTDL_SEARCH_OPTIONS.update({'extract_flat': True, 'skip_download': True})
FFMPEG_OPTIONS = {'options': '-vn', 'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'}
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
        if 'entries' in data: data = data['entries'][0]
        filename = data['url'] if stream else ytdl_play.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS), data=data)

class MusicSelect(Select):
    def __init__(self, entries, ctx, vc):
        self.ctx = ctx; self.vc = vc; self.entries = entries
        options = [SelectOption(label=f"{i+1}. {e.get('title', 'Unknown')[:90]}", value=str(i)) for i, e in enumerate(entries[:5])]
        super().__init__(placeholder="Select a track...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: Interaction):
        if interaction.user.id != self.ctx.author.id: return await interaction.response.send_message("❌ Not your request.", ephemeral=True)
        await interaction.response.defer()
        selected = self.entries[int(self.values[0])]
        url = selected.get('url') or selected.get('webpage_url')
        if not url: return await self.ctx.send("❌ Error: Could not resolve URL for that track.")
        if self.vc.is_playing():
            if self.ctx.guild.id not in bot.audio_queues: bot.audio_queues[self.ctx.guild.id] = deque()
            bot.audio_queues[self.ctx.guild.id].append((url, selected.get('title')))
            await self.ctx.send(f"📝 **Queued:** {selected.get('title')}")
        else:
            await self.ctx.send(f"▶️ **Playing:** {selected.get('title')}")
            await play_track(self.vc, url, selected.get('title'), self.ctx.guild.id)
        try: await interaction.message.delete()
        except: pass

class MusicSelectionView(View):
    def __init__(self, entries, ctx, vc):
        super().__init__(timeout=60)
        self.add_item(MusicSelect(entries, ctx, vc))

def check_queue(gid, vc):
    if gid in bot.audio_queues and bot.audio_queues[gid]:
        url, title = bot.audio_queues[gid].popleft()
        asyncio.run_coroutine_threadsafe(play_track(vc, url, title, gid), bot.loop)

async def play_track(vc, url, title, gid):
    try:
        player = await YTDLSource.from_url(url, loop=bot.loop, stream=True)
        vc.play(player, after=lambda e: check_queue(gid, vc))
    except: pass

# ==================== SHADOW TOWER ====================

def get_tower_data(user_id):
    uid = str(user_id)
    if uid not in tower_db:
        tower_db[uid] = {
            "floor": 1, "max_floor": 1, "hp": 100, "max_hp": 100, "gold": 0, "checkpoint": 1, "potions": 3,
            "class": "Warrior", "level": 1, "xp": 0,
            "stats": {"str": 5, "vit": 5, "agi": 5, "int": 5},
            "equipment": {"Main Hand": None, "Off Hand": None, "Armor": None, "Accessory": None},
            "inventory": [], "pets": [], "adrenaline": 0
        }
    if "pets" not in tower_db[uid]: tower_db[uid]["pets"] = []
    return tower_db[uid]

def save_tower_data(user_id, data):
    if data["floor"] > data.get("max_floor", 1): data["max_floor"] = data["floor"]
    tower_db[str(user_id)] = data
    _save_tower()

def get_total_stats(data):
    total = data["stats"].copy()
    for slot in ITEM_SLOTS:
        item = data["equipment"].get(slot)
        if item:
            for stat, val in item.get("stats", {}).items(): total[stat] = total.get(stat, 0) + val
    total["atk"] = total["str"] * 2
    total["max_hp"] = 100 + (total["vit"] * 10)
    total["crit_chance"] = min(50, total["agi"] * 0.5)
    total["skill_dmg_mult"] = 1 + (total["int"] * 0.05)
    return total

def generate_rpg_item(floor):
    rarity_roll = random.randint(1, 100)
    rarity = "Legendary" if rarity_roll > 98 else "Epic" if rarity_roll > 85 else "Rare" if rarity_roll > 60 else "Uncommon" if rarity_roll > 30 else "Common"
    slot = random.choice(ITEM_SLOTS)
    budget = floor + ({"Common": 2, "Uncommon": 5, "Rare": 10, "Epic": 20, "Legendary": 40}[rarity])
    stats = {}
    for _ in range({"Common": 1, "Uncommon": 2, "Rare": 3, "Epic": 4, "Legendary": 4}[rarity]):
        s = random.choice(["str", "vit", "agi", "int"])
        stats[s] = stats.get(s, 0) + max(1, int(budget / len(stats) if stats else budget))
    
    dom_stat = max(stats, key=stats.get)
    name = f"{rarity} {slot} of { {'str': 'Might', 'vit': 'Health', 'agi': 'Swiftness', 'int': 'Wisdom'}[dom_stat] }"
    if rarity == "Legendary": name = f"The {random.choice(['God', 'Titan', 'Dragon', 'Void'])}'s {slot}"
    return {"id": str(uuid.uuid4())[:8], "name": name, "rarity": rarity, "slot": slot, "stats": stats, "value": budget * 5}

def get_biome(floor):
    for name, data in BIOMES.items():
        if data["range"][0] <= floor <= data["range"][1]: return name, data
    return "Void", BIOMES["Void"]

def get_monster(floor):
    sel = max([t for t in MONSTERS.keys() if floor >= t])
    return random.choice(MONSTERS[sel])

def draw_bar(curr, max_val, color="🟩", length=10):
    if max_val <= 0: return color + "⬛" * 9
    fill = max(1 if curr > 0 else 0, min(length, int((curr / max_val) * length)))
    return color * fill + "⬜" * (length - fill)

class LootDropView(View):
    def __init__(self, user, item):
        super().__init__(timeout=120)
        self.user = user; self.item = item; self.data = get_tower_data(user.id)
    @discord.ui.button(label="Take to Bag", style=ButtonStyle.success, emoji="🎒")
    async def take(self, button, interaction):
        if interaction.user.id != self.user.id: return
        self.data["inventory"].append(self.item); save_tower_data(self.user.id, self.data)
        view = TowerGameView(self.user)
        await interaction.response.edit_message(embed=view.update_embed("Resume Climbing", f"Looted **{self.item['name']}**."), view=view)
    @discord.ui.button(label="Salvage (Gold)", style=ButtonStyle.secondary, emoji="💰")
    async def salvage(self, button, interaction):
        if interaction.user.id != self.user.id: return
        self.data["gold"] += self.item["value"]; save_tower_data(self.user.id, self.data)
        view = TowerGameView(self.user)
        await interaction.response.edit_message(embed=view.update_embed("Resume Climbing", f"Salvaged for **{self.item['value']} Gold**."), view=view)

class TowerGameView(View):
    def __init__(self, user):
        super().__init__(timeout=300)
        self.user = user; self.user_id = str(user.id)
        self.data = get_tower_data(user.id)
        self.stats = get_total_stats(self.data)
        self.mode = "EXPLORE" 
        self.enemy = None; self.combat_log = []
        self.data["hp"] = min(self.data["hp"], self.stats["max_hp"])
        self.render_main_menu()

    def update_embed(self, title, desc, color=THEME_PRIMARY):
        if self.mode == "INVENTORY": return self.get_inventory_embed()
        elif self.mode == "SHOP": return self.get_shop_embed()
        b_name, b_data = get_biome(self.data['floor'])
        p_bar = draw_bar(self.data["hp"], self.stats["max_hp"], "🟩")
        a_bar = draw_bar(self.data.get("adrenaline", 0), 100, "🟨", 8)
        
        embed = discord.Embed(title=f"{b_data['emoji']} {title} | Floor {self.data['floor']}", description=desc, color=b_data["color"] if self.mode != "COMBAT" else THEME_COMBAT)
        if self.mode == "COMBAT" and self.enemy:
            e_bar = draw_bar(self.enemy['hp'], self.enemy['max_hp'], "🟥")
            embed.add_field(name=f"🆚 {self.enemy['name']}", value=f"{e_bar} {self.enemy['hp']} HP\n⚠️ **Intent:** {self.enemy.get('intent', 'Unknown')}", inline=False)
            if self.combat_log: embed.add_field(name="📜 Combat Log", value=f"
http://googleusercontent.com/immersive_entry_chip/0
