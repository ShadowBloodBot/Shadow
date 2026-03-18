# bot.py — ShadowSyn (Master: Unified v8.0 - Elite Baseline Restoration)
#
# === FEATURES ===
# [x] ⚔️ WAR ROSTER: "Not Attending" status and separate embed category.
# [x] 🎰 CASINO: Dice (High/Low/7), Chicken, Slots, Duels, Shop.
# [x] 🎒 RPG TOWER: Inventory, Loot, Shop, Stats.
# [x] 🎛️ VOICEMASTER & MUSIC: All present.
# [x] 🗣️ VOICE FIX (v8.0): 
#     - Completely RESTORED the proven v6 `ensure_voice_simple` connection logic.
#     - Ripped out `safe_reply` error-swallowing to permanently cure "Integration Error" on /haste.
#     - Uses native Py-cord deferrals to prevent timeouts during TTS generation.
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
import uuid
import warnings
import logging
from pathlib import Path
from typing import Optional, List, Set, Union
from datetime import datetime, timezone, timedelta
from collections import deque

import discord
from discord import Option, ButtonStyle, SelectOption, Interaction, AuditLogAction
from discord.ui import View, Button, Modal, TextInput, Select
from discord.ext import commands

from gtts import gTTS
from shutil import which
from googletrans import Translator
from discord.utils import get
import yt_dlp

# --- SUPPRESS CONSOLE SPAM ---
warnings.simplefilter("ignore", ResourceWarning)
logging.getLogger("asyncio").setLevel(logging.CRITICAL)

# =========================== CONSTANTS ===========================

THEME_PRIMARY   = 0x2B0B35
THEME_WIN       = 0x43B581 
THEME_LOSS      = 0xF04747 
THEME_GOLD      = 0xFFD700 
THEME_COMBAT    = 0xE67E22 

# --- RPG CONFIG ---
RARITY_COLORS = {
    "Common": 0x95A5A6,    # Gray
    "Uncommon": 0x2ECC71,  # Green
    "Rare": 0x3498DB,      # Blue
    "Epic": 0x9B59B6,      # Purple
    "Legendary": 0xE67E22  # Orange
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

# --- BIOME THEMES ---
BIOMES = {
    "Sewers": {"range": (1, 20), "color": 0x2ECC71, "emoji": "🤢", "effect": "Toxic: 5% Poison Dmg every 5 turns."},
    "Catacombs": {"range": (21, 40), "color": 0x95A5A6, "emoji": "💀", "effect": "Darkness: 20% Miss Chance."},
    "Magma Core": {"range": (41, 60), "color": 0xE74C3C, "emoji": "🌋", "effect": "Heat: Skills cost 5 HP."},
    "Void": {"range": (61, 999), "color": 0x8E44AD, "emoji": "🔮", "effect": "Void: Enemies deal True Damage."}
}

# --- WAR ROSTER CONFIG ---
WAR_THREAD_ID = 1475981718904242309
WAR_ROLE_ID = 955600320287887400
QUINFALL_CLASSES = [
    ("Sword / Shield", "🛡️"),
    ("Life Staff", "🪄"),
    ("Two-Handed Sword", "🗡️"),
    ("Spear", "🍢"),
    ("Dual Axe", "🪓"),
    ("Dual Dagger", "⚔️"),
    ("War Hammer", "🔨"),
    ("Bow", "🏹"),
    ("Dual Crossbow", "🎯"),
    ("Arcane Staff", "🔮")
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
    _map = {"A": "𝘼", "B": "𝘽", "C": "𝘾", "D": "𝘿", "E": "𝙀", "F": "𝙁", "G": "𝙂", "H": "𝙃", "I": "𝙄", "J": "𝙅", "K": "𝙆", "L": "𝙇", "M": "𝙈", "N": "𝙉", "O": "𝙊", "P": "𝙋", "Q": "𝙌", "R": "𝙍", "S": "𝙎", "T": "𝙏", "U": "𝙐", "V": "𝙑", "W": "𝙒", "X": "𝙓", "Y": "𝙔", "Z": "𝙕", "a": "𝙖", "b": "𝙗", "c": "𝙘", "d": "𝙙", "e": "𝙚", "f": "𝙛", "g": "𝙜", "h": "𝙝", "i": "𝙞", "j": "𝙟", "k": "𝙠", "l": "𝙡", "m": "𝙢", "n": "𝙣", "o": "𝙤", "p": "𝙥", "q": "𝙦", "r": "𝙧", "s": "s", "t": "𝙩", "u": "𝙪", "v": "𝙫", "w": "𝙬", "x": "𝙭", "y": "𝙮", "z": "𝙯"}
    return "".join(_map.get(ch, ch) for ch in text)

def _limit_channel_name(name: str, limit: int = 100) -> str:
    return name[:limit] if len(name) > limit else name

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

# --- RESTORED v6 VOICE LOGIC ---
async def ensure_voice_simple(ctx):
    """The original, proven logic to connect the bot."""
    user = ctx.user if isinstance(ctx, discord.Interaction) else ctx.author
    if not user.voice or not user.voice.channel:
        await ctx.respond("❌ Join a VC first!", ephemeral=True)
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
        else: 
            vc = await channel.connect(timeout=10, reconnect=True)
        return vc
    except Exception as e:
        await ctx.respond(f"❌ Voice Error: {e}", ephemeral=True)
        return None

def safe_avatar_url(member):
    try: return member.display_avatar.url
    except: return None

def safe_display_name(obj):
    try: return obj.display_name if isinstance(obj, discord.Member) else (obj.global_name or obj.name)
    except: return str(obj)

def utcnow(): return datetime.now(timezone.utc)
def ffmpeg_available(): return which("ffmpeg") is not None

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
    _atomic_write(INVITE_ROLE_STORE, data)

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
        intents = discord.Intents.default()
        intents.guilds = True
        intents.voice_states = True
        intents.members = True
        intents.message_content = True
        super().__init__(intents=intents)
        self.audio_queues = {}

bot = ShadowSynBot()

# ==================== COMMANDS: WAR ROSTER ====================

@bot.slash_command(name="create_war", description="Create a Quinfall War Roster (requires War Role)")
async def create_war(
    ctx, 
    title: Option(str, description="Title of the war"), 
    hammer_time: Option(str, description="Paste timestamp from HammerTime (e.g., <t:170000000:F>)")
):
    if not is_war_role(ctx.author):
        return await ctx.respond("⛔ Restricted. You must have the required role.", ephemeral=True)
        
    target_channel = bot.get_channel(WAR_THREAD_ID) or await bot.fetch_channel(WAR_THREAD_ID)
    if not target_channel:
        return await ctx.respond("❌ War channel thread not found.", ephemeral=True)
        
    war_data = {
        "title": title,
        "time": hammer_time,
        "roster": {},
        "not_attending": []
    }
    
    embed = generate_war_embed(war_data)
    view = WarRosterView()
    
    msg = await target_channel.send(content="@everyone New War Scheduled!", embed=embed, view=view)
    
    war_db[str(msg.id)] = war_data
    _save_wars()
    
    await ctx.respond(f"✅ War roster created in {target_channel.mention}", ephemeral=True)

def generate_war_embed(data):
    embed = discord.Embed(title=f"⚔️ {data['title']}", description=f"**Time:** {data['time']}\nSelect your class and if you'll miss any fights below!", color=THEME_COMBAT)
    class_counts = {c[0]: [] for c in QUINFALL_CLASSES}
    
    for uid, info in data.get("roster", {}).items():
        if isinstance(info, str):
            cls = info; absences = []
        else:
            cls = info.get("class")
            if "absences" in info: absences = info["absences"]
            elif "fights" in info: absences = [f for f in ["1", "2", "3", "4", "5"] if f not in info["fights"]]
            else: absences = []
            
        fight_str = f" *(Absent Round {', '.join(sorted(absences))})*" if absences else ""
        if cls in class_counts: class_counts[cls].append(f"<@{uid}>{fight_str}")
            
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
            
        if uid not in war_db[msg_id]["roster"] or isinstance(war_db[msg_id]["roster"][uid], str):
            war_db[msg_id]["roster"][uid] = {"class": selected_class, "absences": []}
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
        
        if uid not in war_db[msg_id].get("roster", {}): return await interaction.response.send_message("❌ Select a Class first!", ephemeral=True)
        if isinstance(war_db[msg_id]["roster"][uid], str): war_db[msg_id]["roster"][uid] = {"class": war_db[msg_id]["roster"][uid], "absences": self.values}
        else:
            war_db[msg_id]["roster"][uid]["absences"] = self.values
            if "fights" in war_db[msg_id]["roster"][uid]: del war_db[msg_id]["roster"][uid]["fights"]
        _save_wars()
        await interaction.response.edit_message(embed=generate_war_embed(war_db[msg_id]))

class WarNotAttendingButton(Button):
    def __init__(self): super().__init__(label="Not Attending", style=ButtonStyle.danger, custom_id="war_not_attending_btn", emoji="❌", row=2)
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
    def __init__(self): super().__init__(label="Clear My Status", style=ButtonStyle.secondary, custom_id="war_leave_btn", emoji="🗑️", row=2)
    async def callback(self, interaction: Interaction):
        msg_id = str(interaction.message.id)
        if msg_id not in war_db: return await interaction.response.send_message("❌ War not found.", ephemeral=True)
        uid = str(interaction.user.id)
        modified = False
        if uid in war_db[msg_id].get("roster", {}): del war_db[msg_id]["roster"][uid]; modified = True
        if uid in war_db[msg_id].get("not_attending", []): war_db[msg_id]["not_attending"].remove(uid); modified = True
        if modified: _save_wars(); await interaction.response.edit_message(embed=generate_war_embed(war_db[msg_id]))
        else: await interaction.response.send_message("⚠️ You haven't selected a status yet.", ephemeral=True)

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

def check_queue(gid, vc):
    if gid in bot.audio_queues and bot.audio_queues[gid]:
        url, title = bot.audio_queues[gid].popleft()
        asyncio.run_coroutine_threadsafe(play_track(vc, url, title, gid), bot.loop)

async def play_track(vc, url, title, gid):
    try:
        player = await YTDLSource.from_url(url, loop=bot.loop, stream=True)
        vc.play(player, after=lambda e: check_queue(gid, vc))
    except Exception as e: 
        print(f"[Music] Error: {e}")
        pass

class MusicSelect(Select):
    def __init__(self, entries, ctx, vc):
        self.ctx = ctx
        self.vc = vc
        self.entries = entries
        options = []
        for i, e in enumerate(entries[:5]):
            title = e.get('title', 'Unknown Track')
            options.append(SelectOption(label=f"{i+1}. {title[:90]}", value=str(i)))
        super().__init__(placeholder="Select a track...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: Interaction):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("❌ Not your request.", ephemeral=True)
        
        await interaction.response.defer()
        idx = int(self.values[0])
        selected = self.entries[idx]
        url = selected.get('url') or selected.get('webpage_url')
        title = selected.get('title')
        
        if not url: return await self.ctx.send("❌ Error: Could not resolve URL for that track.")

        if self.vc.is_playing():
            if self.ctx.guild.id not in bot.audio_queues: bot.audio_queues[self.ctx.guild.id] = deque()
            bot.audio_queues[self.ctx.guild.id].append((url, title))
            await self.ctx.send(f"📝 **Queued:** {title}")
        else:
            await self.ctx.send(f"▶️ **Playing:** {title}")
            await play_track(self.vc, url, title, self.ctx.guild.id)
        
        try: await interaction.message.delete()
        except: pass

class MusicSelectionView(View):
    def __init__(self, entries, ctx, vc):
        super().__init__(timeout=60)
        self.add_item(MusicSelect(entries, ctx, vc))


# ==================== SHADOW TOWER 6.4 (STABLE) ====================

def get_tower_data(user_id):
    uid = str(user_id)
    if uid not in tower_db:
        tower_db[uid] = {
            "floor": 1, "max_floor": 1, 
            "hp": 100, "max_hp": 100, 
            "gold": 0, "checkpoint": 1, 
            "potions": 3,
            "class": "Warrior", "level": 1, "xp": 0,
            "stats": {"str": 5, "vit": 5, "agi": 5, "int": 5},
            "equipment": {
                "Main Hand": None, "Off Hand": None, "Armor": None, "Accessory": None
            },
            "inventory": [],
            "adrenaline": 0
        }
    return tower_db[uid]

def save_tower_data(user_id, data):
    tower_db[str(user_id)] = data
    _save_tower()

def get_total_stats(data):
    total = data["stats"].copy()
    for slot in ITEM_SLOTS:
        item = data["equipment"].get(slot)
        if item:
            for stat, val in item.get("stats", {}).items():
                total[stat] = total.get(stat, 0) + val
    total["atk"] = total["str"] * 2
    total["max_hp"] = 100 + (total["vit"] * 10)
    total["crit_chance"] = min(50, total["agi"] * 0.5)
    total["skill_dmg_mult"] = 1 + (total["int"] * 0.05)
    return total

def generate_rpg_item(floor):
    rarity_roll = random.randint(1, 100)
    if rarity_roll > 98: rarity = "Legendary"
    elif rarity_roll > 85: rarity = "Epic"
    elif rarity_roll > 60: rarity = "Rare"
    elif rarity_roll > 30: rarity = "Uncommon"
    else: rarity = "Common"
    
    slot = random.choice(ITEM_SLOTS)
    budget = floor + ({"Common": 2, "Uncommon": 5, "Rare": 10, "Epic": 20, "Legendary": 40}[rarity])
    stats = {}
    possible_stats = ["str", "vit", "agi", "int"]
    num_stats = {"Common": 1, "Uncommon": 2, "Rare": 3, "Epic": 4, "Legendary": 4}[rarity]
    
    for _ in range(num_stats):
        s = random.choice(possible_stats)
        val = max(1, int(budget / num_stats))
        stats[s] = stats.get(s, 0) + val
        
    name_prefix = {"str": "Might", "vit": "Health", "agi": "Swiftness", "int": "Wisdom"}
    dominant_stat = max(stats, key=stats.get)
    name = f"{rarity} {slot} of {name_prefix[dominant_stat]}"
    
    if rarity == "Legendary":
        name = f"The {random.choice(['God', 'Titan', 'Dragon', 'Void'])}'s {slot}"

    return {
        "id": str(uuid.uuid4())[:8],
        "name": name,
        "rarity": rarity,
        "slot": slot,
        "stats": stats,
        "value": budget * 5
    }

def get_biome(floor):
    for name, data in BIOMES.items():
        if data["range"][0] <= floor <= data["range"][1]: return name, data
    return "Void", BIOMES["Void"]

def get_monster(floor):
    tiers = sorted(MONSTERS.keys())
    sel = 1
    for t in tiers:
        if floor >= t: sel = t
    return random.choice(MONSTERS[sel])

def draw_bar(curr, max_val, color="🟩", length=10):
    if max_val <= 0: return color + "⬛" * 9
    pct = max(0, min(1, curr / max_val))
    fill = int(pct * length)
    if fill == 0 and curr > 0: fill = 1 
    return color * fill + "⬜" * (length - fill)

class LootDropView(View):
    def __init__(self, user, item):
        super().__init__(timeout=120)
        self.user = user
        self.item = item
        self.data = get_tower_data(user.id)

    @discord.ui.button(label="Take to Bag", style=ButtonStyle.success, emoji="🎒")
    async def take(self, button, interaction):
        if interaction.user.id != self.user.id: return
        self.data["inventory"].append(self.item)
        save_tower_data(self.user.id, self.data)
        view = TowerGameView(self.user)
        await interaction.response.edit_message(embed=view.update_embed("Resume Climbing", f"Looted **{self.item['name']}**."), view=view)

    @discord.ui.button(label="Salvage (Gold)", style=ButtonStyle.secondary, emoji="💰")
    async def salvage(self, button, interaction):
        if interaction.user.id != self.user.id: return
        val = self.item["value"]
        self.data["gold"] += val
        save_tower_data(self.user.id, self.data)
        view = TowerGameView(self.user)
        await interaction.response.edit_message(embed=view.update_embed("Resume Climbing", f"Salvaged for **{val} Gold**."), view=view)

class TowerGameView(View):
    def __init__(self, user):
        super().__init__(timeout=300)
        self.user = user
        self.user_id = str(user.id)
        self.data = get_tower_data(user.id)
        self.stats = get_total_stats(self.data)
        self.mode = "EXPLORE" 
        self.enemy = None
        self.combat_log = []
        self.data["hp"] = min(self.data["hp"], self.stats["max_hp"])
        self.render_main_menu()

    def update_embed(self, title, desc, color=THEME_PRIMARY):
        if self.mode == "INVENTORY": return self.get_inventory_embed()
        elif self.mode == "SHOP": return self.get_shop_embed()

        b_name, b_data = get_biome(self.data['floor'])
        p_bar = draw_bar(self.data["hp"], self.stats["max_hp"], "🟩")
        a_bar = draw_bar(self.data.get("adrenaline", 0), 100, "🟨", 8)
        
        final_color = b_data["color"]
        if self.mode == "COMBAT": final_color = THEME_COMBAT

        embed = discord.Embed(title=f"{b_data['emoji']} {title} | Floor {self.data['floor']}", description=desc, color=final_color)
        
        if self.mode == "COMBAT" and self.enemy:
            e_bar = draw_bar(self.enemy['hp'], self.enemy['max_hp'], "🟥")
            intent = self.enemy.get("intent", "Unknown")
            embed.add_field(name=f"🆚 {self.enemy['name']}", 
                            value=f"{e_bar} {self.enemy['hp']} HP\n⚠️ **Intent:** {intent}", inline=False)
            if self.combat_log:
                log_text = "\n".join(self.combat_log[-6:])
                embed.add_field(name="📜 Combat Log", value=f"```ansi\n{log_text}\n```", inline=False)

        stats_disp = f"⚔️{self.stats['atk']} 🛡️{self.stats['vit']//2} 💰{self.data['gold']}"
        embed.add_field(name=f"👤 {self.user.display_name} (Lvl {self.data['level']})", 
                        value=f"{p_bar} {self.data['hp']} HP\n{a_bar} Limit Break\n{stats_disp}", inline=False)
        embed.set_footer(text=f"{b_name}: {b_data['effect']}")
        return embed

    def get_inventory_embed(self):
        stats = get_total_stats(self.data)
        embed = discord.Embed(title=f"🎒 {self.user.display_name}'s Gear", color=THEME_PRIMARY)
        s_text = (f"❤️ **HP:** {self.data['hp']}/{stats['max_hp']}\n"
                  f"⚔️ **ATK:** {stats['atk']} (Str: {stats['str']})\n"
                  f"🛡️ **DEF:** {stats['vit'] // 2} (Vit: {stats['vit']})\n"
                  f"⚡ **CRIT:** {stats['crit_chance']}% (Agi: {stats['agi']})")
        embed.add_field(name="📊 Stats", value=s_text, inline=True)
        g_text = ""
        for slot in ITEM_SLOTS:
            item = self.data["equipment"].get(slot)
            if item:
                stats_str = " ".join([f"**{k.upper()}**+{v}" for k,v in item['stats'].items()])
                g_text += f"**{slot}:** {item['name']} ({stats_str})\n"
            else: g_text += f"**{slot}:** Empty\n"
        embed.add_field(name="🛡️ Equipment", value=g_text, inline=False)
        i_text = f"Items: {len(self.data['inventory'])}"
        if not self.data["inventory"]: i_text += "\n(Empty)"
        else:
            for item in self.data["inventory"][:5]: i_text += f"\n• {item['name']}"
            if len(self.data['inventory']) > 5: i_text += "\n...and more."
        embed.add_field(name="🎒 Backpack", value=i_text, inline=False)
        return embed

    def get_shop_embed(self):
        embed = discord.Embed(title="⛺ Safe Zone Merchant", description="Stay a while and listen.", color=THEME_GOLD)
        embed.add_field(name="Your Gold", value=f"💰 {self.data['gold']}")
        embed.add_field(name="Potions", value=f"🧪 {self.data['potions']}")
        embed.add_field(name="Inventory Value", value=f"💎 {sum([i['value'] for i in self.data['inventory']])}g")
        return embed

    def render_main_menu(self):
        self.clear_items()
        if self.mode == "COMBAT":
            atk_btn = Button(label="Attack", style=ButtonStyle.danger, emoji="⚔️", row=0)
            atk_btn.callback = lambda i: self.wrapper(i, "act_atk")
            self.add_item(atk_btn)
            def_btn = Button(label="Defend", style=ButtonStyle.secondary, emoji="🛡️", row=0)
            def_btn.callback = lambda i: self.wrapper(i, "act_def")
            self.add_item(def_btn)
            if self.data["potions"] > 0:
                pot_btn = Button(label=f"Potion ({self.data['potions']})", style=ButtonStyle.success, emoji="🧪", row=0)
                pot_btn.callback = lambda i: self.wrapper(i, "act_pot")
                self.add_item(pot_btn)
            if self.data["adrenaline"] >= 100:
                ult_btn = Button(label="LIMIT BREAK", style=ButtonStyle.primary, emoji="⚡", row=1)
                ult_btn.callback = lambda i: self.wrapper(i, "act_ult")
                self.add_item(ult_btn)
        elif self.mode == "EXPLORE":
            climb_btn = Button(label="Climb", style=ButtonStyle.success, emoji="🧗", row=0)
            climb_btn.callback = lambda i: self.wrapper(i, "nav_climb")
            self.add_item(climb_btn)
            rest_btn = Button(label="Rest (100g)", style=ButtonStyle.primary, emoji="💤", row=0)
            rest_btn.callback = lambda i: self.wrapper(i, "nav_rest")
            self.add_item(rest_btn)
            gear_btn = Button(label="Bag/Gear", style=ButtonStyle.secondary, emoji="🎒", row=1)
            gear_btn.callback = lambda i: self.wrapper(i, "nav_gear")
            self.add_item(gear_btn)
        elif self.mode == "INVENTORY":
            if self.data["inventory"]:
                options = []
                for item in self.data["inventory"][:25]:
                    s_str = ", ".join([f"{k.upper()}+{v}" for k,v in item["stats"].items()])
                    options.append(SelectOption(label=f"{item['name']} ({item['slot']})", description=s_str, value=item["id"]))
                select = Select(placeholder="Equip Item...", options=options, row=0)
                select.callback = self.equip_callback
                self.add_item(select)
            back_btn = Button(label="Back to Game", style=ButtonStyle.secondary, emoji="↩️", row=1)
            back_btn.callback = lambda i: self.wrapper(i, "nav_back")
            self.add_item(back_btn)
        elif self.mode == "SHOP":
            buy_btn = Button(label="Buy Potion (50g)", style=ButtonStyle.success, emoji="🧪", row=0)
            buy_btn.callback = lambda i: self.wrapper(i, "shop_buy")
            self.add_item(buy_btn)
            sell_btn = Button(label="Sell Junk (Inventory)", style=ButtonStyle.danger, emoji="💰", row=0)
            sell_btn.callback = lambda i: self.wrapper(i, "shop_sell")
            self.add_item(sell_btn)
            leave_btn = Button(label="Leave Shop", style=ButtonStyle.secondary, emoji="👋", row=1)
            leave_btn.callback = lambda i: self.wrapper(i, "shop_leave")
            self.add_item(leave_btn)

    async def equip_callback(self, interaction):
        if interaction.user.id != self.user.id: return
        await interaction.response.defer() 
        val = interaction.data["values"][0]
        to_equip = next((i for i in self.data["inventory"] if i["id"] == val), None)
        if to_equip:
            slot = to_equip["slot"]
            current = self.data["equipment"].get(slot)
            if current: self.data["inventory"].append(current)
            self.data["equipment"][slot] = to_equip
            self.data["inventory"].remove(to_equip)
            save_tower_data(self.user.id, self.data)
            self.stats = get_total_stats(self.data) 
            self.render_main_menu() 
            await interaction.edit_original_response(embed=self.update_embed("Gear Updated", ""), view=self)

    async def wrapper(self, interaction, cid):
        if interaction.user.id != self.user.id: return await interaction.response.send_message("🚫 Not your session.", ephemeral=True)
        try:
            await interaction.response.defer()
            if "act_" in cid: await self.resolve_combat(interaction, cid)
            elif cid == "nav_gear":
                self.mode = "INVENTORY"; self.render_main_menu()
                await interaction.edit_original_response(embed=self.update_embed("Inventory", ""), view=self)
            elif cid == "nav_back":
                self.mode = "EXPLORE"; self.render_main_menu()
                await interaction.edit_original_response(embed=self.update_embed("Exploration", "Back to the tower."), view=self)
            elif "shop_" in cid: await self.resolve_shop(interaction, cid)
            else: await self.resolve_nav(interaction, cid)
        except Exception as e: traceback.print_exc()

    async def resolve_shop(self, interaction, cid):
        if cid == "shop_buy":
            if self.data["gold"] >= 50:
                self.data["gold"] -= 50; self.data["potions"] += 1; save_tower_data(self.user.id, self.data)
                await interaction.edit_original_response(embed=self.update_embed("Shop", "Bought potion."), view=self)
            else: await interaction.followup.send("❌ Not enough gold.", ephemeral=True)
        elif cid == "shop_sell":
            total = sum([i["value"] for i in self.data["inventory"]])
            count = len(self.data["inventory"])
            self.data["inventory"] = []; self.data["gold"] += total; save_tower_data(self.user.id, self.data)
            await interaction.edit_original_response(embed=self.update_embed("Shop", f"Sold {count} items for {total}g."), view=self)
        elif cid == "shop_leave":
            self.mode = "EXPLORE"; self.data["floor"] += 1; self.render_main_menu()
            await interaction.edit_original_response(embed=self.update_embed("Exploration", "Moving on..."), view=self)

    async def resolve_nav(self, interaction, cid):
        if cid == "nav_rest":
            if self.data["gold"] >= 100:
                self.data["gold"] -= 100; self.data["hp"] = self.stats["max_hp"]; save_tower_data(self.user.id, self.data)
                await interaction.edit_original_response(embed=self.update_embed("💤 Rested", "HP Fully Restored."), view=self)
            else: await interaction.followup.send("❌ Need 100 Gold.", ephemeral=True)
        elif cid == "nav_climb":
            if self.data["floor"] % 5 == 0 and self.data["floor"] > 1:
                self.mode = "SHOP"; self.render_main_menu()
                await interaction.edit_original_response(embed=self.update_embed("Shop", "Safe zone reached."), view=self)
                return
            roll = random.randint(1, 100)
            if roll <= 30: 
                item = generate_rpg_item(self.data["floor"]); view = LootDropView(self.user, item)
                stats_str = "\n".join([f"• **{k.upper()}:** +{v}" for k,v in item['stats'].items()])
                desc = f"You found a chest!\n\n**{item['name']}**\n{stats_str}\n\n*Value: {item['value']} Gold*"
                color = RARITY_COLORS.get(item['rarity'], 0xFFFFFF)
                embed = discord.Embed(title="🎁 Treasure Found!", description=desc, color=color)
                await interaction.edit_original_response(embed=embed, view=view)
            else: 
                self.start_combat(); await interaction.edit_original_response(embed=self.update_embed("⚔️ Encounter!", "Prepare yourself!"), view=self)

    def start_combat(self):
        self.mode = "COMBAT"
        floor = self.data["floor"]
        name = get_monster(floor)
        hp = (floor * 25) + 80
        power = (floor * 3) + 5
        self.enemy = {"name": name, "hp": hp, "max_hp": hp, "power": power, "intent": random.choice(["Attack", "Heavy Attack"])}
        self.combat_log = [f"⚔️ Encountered {name}!"]
        self.render_main_menu()

    async def resolve_combat(self, interaction, action):
        if not self.enemy: return
        p_dmg, p_block = 0, 0
        if action == "act_atk":
            dmg = self.stats["atk"] + random.randint(-2, 2)
            if random.randint(1, 100) <= self.stats["crit_chance"]: dmg = int(dmg * 1.5); self.combat_log.append(f"💥 CRIT! You deal {dmg} dmg.")
            else: self.combat_log.append(f"🗡️ You deal {dmg} dmg.")
            p_dmg = dmg; self.data["adrenaline"] = min(100, self.data["adrenaline"] + 10)
        elif action == "act_def":
            p_block = self.stats["vit"]; self.combat_log.append(f"🛡️ Block raised ({p_block}).")
            self.data["adrenaline"] = min(100, self.data["adrenaline"] + 5)
        elif action == "act_ult":
            p_dmg = self.stats["atk"] * 3; self.combat_log.append(f"⚡ LIMIT BREAK! {p_dmg} DMG!")
            self.data["adrenaline"] = 0
        elif action == "act_pot":
            heal = 50 + (self.stats["int"] * 2); self.data["hp"] = min(self.stats["max_hp"], self.data["hp"] + heal)
            self.data["potions"] -= 1; self.combat_log.append(f"🧪 Healed +{heal} HP.")

        self.enemy["hp"] -= p_dmg
        if self.enemy["hp"] > 0:
            e_dmg = self.enemy["power"]
            if self.enemy["intent"] == "Heavy Attack": e_dmg = int(e_dmg * 1.5)
            mitigation = (self.stats["vit"] // 3) + p_block
            final_dmg = max(0, e_dmg - mitigation)
            self.data["hp"] -= final_dmg
            self.combat_log.append(f"👾 {self.enemy['name']} hits for {final_dmg} (Mitigated {mitigation}).")
            self.enemy["intent"] = random.choice(["Attack", "Heavy Attack", "Defend"])
        
        if self.enemy["hp"] <= 0:
            xp_gain = 20 + self.data["floor"]; gold_gain = 10 + (self.data["floor"] * 2)
            self.data["xp"] += xp_gain; self.data["gold"] += gold_gain; self.data["floor"] += 1
            self.mode = "EXPLORE"; self.enemy = None; req = self.data["level"] * 100
            if self.data["xp"] >= req:
                self.data["xp"] -= req; self.data["level"] += 1
                self.data["stats"]["str"] += 1; self.data["stats"]["vit"] += 1
                self.combat_log.append("✨ LEVEL UP! Stats Increased.")
            save_tower_data(self.user_id, self.data); self.render_main_menu()
            await interaction.edit_original_response(embed=self.update_embed("Victory!", f"Enemy Defeated.\n+{xp_gain} XP | +{gold_gain} Gold"), view=self)
        elif self.data["hp"] <= 0:
            self.data["hp"] = 0; lost_gold = int(self.data["gold"] / 2)
            self.data["gold"] -= lost_gold; self.data["floor"] = max(1, self.data["floor"] - 5)
            save_tower_data(self.user_id, self.data)
            await interaction.edit_original_response(embed=self.update_embed("💀 Defeated", f"You fainted.\nLost {lost_gold} Gold.\nFloor reduced."), view=None)
        else:
            save_tower_data(self.user_id, self.data)
            await interaction.edit_original_response(embed=self.update_embed("Combat", "Fighting..."), view=self)

# ==================== CASINO LOGIC ====================

def generate_slot_result(user, bet):
    user_id = str(user.id)
    update_balance(user_id, -bet)
    emojis = ["🍒", "🍋", "🍇", "💎", "7️⃣", "🔔", "🍊"]
    a, b, c = random.choice(emojis), random.choice(emojis), random.choice(emojis)
    payout = 0; is_jackpot = False
    if a == b == c: payout = bet * 13; is_jackpot = True
    elif a == b or b == c or a == c: payout = int(bet * 1.5) 
    if payout > 0:
        update_balance(user_id, payout)
        col = THEME_GOLD if payout > bet * 2 else THEME_WIN
        msg = f"🎰 **{a} | {b} | {c}**\n✅ **WIN!** +{payout}"
    else:
        col = THEME_LOSS
        msg = f"🎰 **{a} | {b} | {c}**\n❌ **Lost** {bet}"
    embed = discord.Embed(description=msg, color=col)
    if user.display_avatar: embed.set_author(name=f"{user.display_name}'s Spin", icon_url=user.display_avatar.url)
    else: embed.set_author(name=f"{user.display_name}'s Spin")
    embed.set_footer(text=f"Bet: {bet} Scoins")
    return embed, is_jackpot, payout

class RepeatSpinView(View):
    def __init__(self, user_id, bet):
        super().__init__(timeout=120)
        self.user_id = user_id; self.bet = bet
    @discord.ui.button(label="Spin Again", style=ButtonStyle.primary, emoji="🔄")
    async def spin_btn(self, button, interaction: Interaction):
        if interaction.user.id != self.user_id: return await interaction.response.send_message("🚫 Not your game.", ephemeral=True)
        try:
            await interaction.response.defer(ephemeral=True) 
            bal = get_balance(str(self.user_id))
            if bal < self.bet: return await interaction.followup.send(f"❌ Insufficient funds ({bal} < {self.bet}).", ephemeral=True)
            embed, is_jackpot, win_amount = generate_slot_result(interaction.user, self.bet)
            await interaction.followup.send(embed=embed, view=RepeatSpinView(self.user_id, self.bet), ephemeral=True)
            if is_jackpot:
                target_thread = interaction.guild.get_channel(CASINO_CHANNEL_ID) or await interaction.guild.fetch_channel(CASINO_CHANNEL_ID)
                if target_thread: await target_thread.send(f"🚨 **JACKPOT!** 🎰\n**{interaction.user.display_name}** just hit a **3x Match** and won **{win_amount}** Scoins!")
        except Exception as e: await interaction.followup.send(f"⚠️ Error: {e}", ephemeral=True)

class BetAmountModal(Modal):
    def __init__(self, title, balance, callback_func):
        super().__init__(title=title)
        self.balance = balance; self.callback_func = callback_func
        self.add_item(TextInput(label=f"Amount (Max: {balance})", placeholder="Enter amount or 'all'", min_length=1))
    async def callback(self, interaction: Interaction):
        raw = self.children[0].value.lower()
        if raw == "all": amount = self.balance
        else:
            try: amount = int(raw)
            except: return await interaction.response.send_message("❌ Invalid number.", ephemeral=True)
        if amount <= 0: return await interaction.response.send_message("❌ Must bet > 0.", ephemeral=True)
        if amount > self.balance: return await interaction.response.send_message("❌ Insufficient funds.", ephemeral=True)
        await self.callback_func(interaction, amount)

class ChickenButton(Button):
    def __init__(self, x, y, view_ref):
        super().__init__(style=ButtonStyle.secondary, label="\u200b", row=y)
        self.x = x; self.y = y; self.view_ref = view_ref; self.idx = y * 5 + x
    async def callback(self, interaction: Interaction):
        if interaction.user.id != self.view_ref.user_id: return await interaction.response.send_message("🚫 Not your game.", ephemeral=True)
        await self.view_ref.handle_click(self, interaction)

class ChickenGameView(View):
    def __init__(self, user, bet, bones_count):
        super().__init__(timeout=180)
        self.user_id = user.id; self.user = user; self.bet = bet; self.bones_count = bones_count
        self.grid_size = 20; self.bones_indices = set(random.sample(range(self.grid_size), bones_count))
        self.revealed = set(); self.game_over = False; self.multiplier = 1.0
        for y in range(4):
            for x in range(5): self.add_item(ChickenButton(x, y, self))
        self.cashout_btn = Button(style=ButtonStyle.success, label="Cash Out", row=4, emoji="💰", disabled=True)
        self.cashout_btn.callback = self.cash_out; self.add_item(self.cashout_btn)
    def calculate_next_multiplier(self):
        remaining_tiles = self.grid_size - len(self.revealed); safe_remaining = remaining_tiles - self.bones_count
        if safe_remaining <= 0: return self.multiplier
        odds = remaining_tiles / safe_remaining
        return self.multiplier * odds * 0.97 
    async def handle_click(self, button, interaction: Interaction):
        if self.game_over: return
        idx = button.idx
        if idx in self.bones_indices:
            self.game_over = True; update_balance(str(self.user_id), -self.bet)
            button.style = ButtonStyle.danger; button.emoji = "🦴"; button.label = ""
            for child in self.children:
                if isinstance(child, ChickenButton):
                    child.disabled = True
                    if child.idx in self.bones_indices and child.idx != idx: child.style = ButtonStyle.secondary; child.emoji = "🦴"
            self.cashout_btn.disabled = True
            embed = discord.Embed(title="💥 BONE!", description=f"You hit a bone and lost **{self.bet}** Scoins.", color=THEME_LOSS)
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            self.revealed.add(idx); self.multiplier = self.calculate_next_multiplier()
            button.style = ButtonStyle.success; button.emoji = "🍗"; button.label = ""; button.disabled = True
            self.cashout_btn.disabled = False; self.cashout_btn.label = f"Cash Out ({int(self.bet * self.multiplier)})"
            current_win = int(self.bet * self.multiplier)
            embed = discord.Embed(title="🍗 CHICKEN!", description=f"Multiplier: **{self.multiplier:.2f}x**\nCurrent Win: **{current_win}**", color=THEME_GOLD)
            await interaction.response.edit_message(embed=embed, view=self)
    async def cash_out(self, interaction: Interaction):
        if interaction.user.id != self.user.id: return
        self.game_over = True; win_amount = int(self.bet * self.multiplier)
        update_balance(str(self.user_id), -self.bet + win_amount)
        for child in self.children: child.disabled = True
        embed = discord.Embed(title="💰 CASHED OUT", description=f"You won **{win_amount}** Scoins!\nMultiplier: **{self.multiplier:.2f}x**", color=THEME_WIN)
        await interaction.response.edit_message(embed=embed, view=self)

class ChickenDifficultySelect(Select):
    def __init__(self, user, bet):
        self.user = user; self.bet = bet
        options = [SelectOption(label="1 Bone (Safe)", value="1"), SelectOption(label="3 Bones", value="3"), SelectOption(label="5 Bones", value="5"), SelectOption(label="10 Bones", value="10"), SelectOption(label="15 Bones", value="15")]
        super().__init__(placeholder="Select Difficulty...", min_values=1, max_values=1, options=options)
    async def callback(self, interaction: Interaction):
        if interaction.user.id != self.user.id: return
        bones = int(self.values[0]); bal = get_balance(str(self.user.id))
        if bal < self.bet: return await interaction.response.send_message("❌ Insufficient funds.", ephemeral=True)
        view = ChickenGameView(self.user, self.bet, bones)
        embed = discord.Embed(title="🍗 Chicken Cross", description=f"Bet: {self.bet} | Bones: {bones}", color=THEME_PRIMARY)
        await interaction.response.edit_message(embed=embed, view=view)

class ChickenSetupView(View):
    def __init__(self, user, bet):
        super().__init__(timeout=60)
        self.add_item(ChickenDifficultySelect(user, bet))

class DiceGameView(View):
    def __init__(self, user, bet):
        super().__init__(timeout=60)
        self.user = user; self.user_id = user.id; self.bet = bet; self.game_over = False
    @discord.ui.button(label="Low (2-6) [x2]", style=ButtonStyle.primary, emoji="⬇️", row=0)
    async def low_btn(self, button, interaction: Interaction): await self.process_roll(interaction, "low")
    @discord.ui.button(label="Seven (7) [x5]", style=ButtonStyle.secondary, emoji="7️⃣", row=0)
    async def seven_btn(self, button, interaction: Interaction): await self.process_roll(interaction, "seven")
    @discord.ui.button(label="High (8-12) [x2]", style=ButtonStyle.primary, emoji="⬆️", row=0)
    async def high_btn(self, button, interaction: Interaction): await self.process_roll(interaction, "high")
    async def process_roll(self, interaction: Interaction, choice):
        if interaction.user.id != self.user.id: return await interaction.response.send_message("🚫 Not your game.", ephemeral=True)
        if self.game_over: return
        bal = get_balance(str(self.user.id))
        if bal < self.bet: return await interaction.response.send_message("❌ Insufficient funds.", ephemeral=True)
        update_balance(str(self.user.id), -self.bet); self.game_over = True
        d1 = random.randint(1, 6); d2 = random.randint(1, 6); total = d1 + d2
        dice_map = {1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣", 5: "5️⃣", 6: "6️⃣"}
        visual = f"{dice_map[d1]} + {dice_map[d2]} = **{total}**"
        won = False; payout = 0
        if choice == "low" and total < 7: won = True; payout = int(self.bet * 2)
        elif choice == "high" and total > 7: won = True; payout = int(self.bet * 2)
        elif choice == "seven" and total == 7: won = True; payout = int(self.bet * 5)
        if won:
            update_balance(str(self.user_id), payout)
            embed = discord.Embed(title="🎲 Dice Roll", description=f"{visual}\n✅ **WIN!** You won **{payout}** Scoins.", color=THEME_WIN)
        else:
            embed = discord.Embed(title="🎲 Dice Roll", description=f"{visual}\n❌ **LOSS.** You lost **{self.bet}** Scoins.", color=THEME_LOSS)
        for child in self.children: child.disabled = True
        self.add_item(PlayAgainDiceButton(self.user, self.bet))
        await interaction.response.edit_message(embed=embed, view=self)

class PlayAgainDiceButton(Button):
    def __init__(self, user, bet):
        super().__init__(label="Roll Again", style=ButtonStyle.success, emoji="🔄", row=1)
        self.user = user; self.bet = bet
    async def callback(self, interaction: Interaction):
        if interaction.user.id != self.user.id: return
        bal = get_balance(str(self.user.id))
        if bal < self.bet: return await interaction.response.send_message("❌ Broke.", ephemeral=True)
        await interaction.response.send_message(f"🎲 **High/Low Dice**\nBet: **{self.bet}**", view=DiceGameView(self.user, self.bet), ephemeral=True)

class DuelAcceptView(View):
    def __init__(self, p1, p2, amount):
        super().__init__(timeout=60)
        self.p1 = p1; self.p2 = p2; self.amount = amount
    @discord.ui.button(label="ACCEPT DUEL", style=ButtonStyle.danger, emoji="⚔️")
    async def accept(self, button, interaction: Interaction):
        if interaction.user.id != self.p2.id: return
        if get_balance(str(self.p1.id)) < self.amount or get_balance(str(self.p2.id)) < self.amount:
            return await interaction.response.send_message("❌ Someone went broke during the wait.", ephemeral=True)
        update_balance(str(self.p1.id), -self.amount); update_balance(str(self.p2.id), -self.amount)
        winner = random.choice([self.p1, self.p2]); loser = self.p2 if winner == self.p1 else self.p1
        win_amt = self.amount * 2; update_balance(str(winner.id), win_amt)
        embed = discord.Embed(title="🩸 DUEL FINISHED", description=f"🏆 **Winner:** {winner.mention}\n💀 **Loser:** {loser.mention}\n💰 **Won:** {win_amt} Scoins", color=THEME_GOLD)
        self.clear_items()
        await interaction.response.edit_message(view=self, embed=embed)

class ShopSelect(Select):
    def __init__(self):
        options = [SelectOption(label="Ban Haste", description="10,000 Scoins: Publicly banish Haste", value="ban_haste", emoji="🔨")]
        super().__init__(placeholder="Select item to buy...", min_values=1, max_values=1, options=options)
    async def callback(self, interaction: Interaction):
        if not is_gambler(interaction.user): return await interaction.response.send_message("⛔ Restricted. Missing required role.", ephemeral=True)
        user_id = str(interaction.user.id); bal = get_balance(user_id); val = self.values[0]
        if val == "ban_haste":
            cost = 10000
            if bal < cost: return await interaction.response.send_message("❌ You need 10,000 Scoins.", ephemeral=True)
            update_balance(user_id, -cost)
            await interaction.response.send_message("🔨 **Haste has been BANNED!** (Not really, but you paid 10,000 Scoins for the flex).", ephemeral=False)

class CasinoDashboard(View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="Collect", style=ButtonStyle.success, emoji="💰", row=0)
    async def collect(self, button, interaction: Interaction):
        if not is_gambler(interaction.user): return await interaction.response.send_message("⛔ Restricted.", ephemeral=True)
        user_id = str(interaction.user.id)
        user_data = scoins_db.get(user_id, {"balance": 0, "last_pull": 0})
        last = user_data["last_pull"]; now = time.time()
        if now - last < (SCOIN_COOLDOWN_HOURS * 3600):
            remaining = (SCOIN_COOLDOWN_HOURS * 3600) - (now - last)
            hours = int(remaining // 3600); mins = int((remaining % 3600) // 60)
            return await interaction.response.send_message(f"⏳ **Cooldown:** {hours}h {mins}m.", ephemeral=True)
        update_balance(user_id, SCOIN_PULL_AMOUNT)
        scoins_db[user_id]["last_pull"] = now; _save_scoins()
        await interaction.response.send_message(f"💰 **Payday!** +{SCOIN_PULL_AMOUNT} Scoins.", ephemeral=True)
    @discord.ui.button(label="Slots", style=ButtonStyle.primary, emoji="🎰", row=0)
    async def slots(self, button, interaction: Interaction):
        if interaction.channel.id != CASINO_CHANNEL_ID: return await interaction.response.send_message(f"❌ Go to <#{CASINO_CHANNEL_ID}>.", ephemeral=True)
        if not is_gambler(interaction.user): return await interaction.response.send_message("⛔ Restricted.", ephemeral=True)
        bal = get_balance(str(interaction.user.id))
        async def modal_callback(inter, amount):
            embed, is_jackpot, win_amount = generate_slot_result(inter.user, amount)
            await inter.response.send_message(embed=embed, view=RepeatSpinView(inter.user.id, amount), ephemeral=True)
            if is_jackpot:
                target_thread = inter.guild.get_channel(CASINO_CHANNEL_ID) or await inter.guild.fetch_channel(CASINO_CHANNEL_ID)
                if target_thread: await target_thread.send(f"🚨 **JACKPOT!** 🎰\n**{inter.user.display_name}** just hit a **3x Match** and won **{win_amount}** Scoins!")
        await interaction.response.send_modal(BetAmountModal("Slots Bet", bal, modal_callback))
    @discord.ui.button(label="Chicken", style=ButtonStyle.primary, emoji="🍗", row=0)
    async def chicken(self, button, interaction: Interaction):
        if interaction.channel.id != CASINO_CHANNEL_ID: return await interaction.response.send_message(f"❌ Go to <#{CASINO_CHANNEL_ID}>.", ephemeral=True)
        if not is_gambler(interaction.user): return await interaction.response.send_message("⛔ Restricted.", ephemeral=True)
        bal = get_balance(str(interaction.user.id))
        async def modal_callback(inter, amount): await inter.response.send_message("🦴 **Select Difficulty (Bones)**", view=ChickenSetupView(inter.user, amount), ephemeral=True)
        await interaction.response.send_modal(BetAmountModal("Chicken Bet", bal, modal_callback))
    @discord.ui.button(label="Dice", style=ButtonStyle.primary, emoji="🎲", row=0)
    async def dice(self, button, interaction: Interaction):
        if interaction.channel.id != CASINO_CHANNEL_ID: return await interaction.response.send_message(f"❌ Go to <#{CASINO_CHANNEL_ID}>.", ephemeral=True)
        if not is_gambler(interaction.user): return await interaction.response.send_message("⛔ Restricted.", ephemeral=True)
        bal = get_balance(str(interaction.user.id))
        async def modal_callback(inter, amount): await inter.response.send_message(f"🎲 **High/Low Dice**\nBet: **{amount}**", view=DiceGameView(inter.user, amount), ephemeral=True)
        await interaction.response.send_modal(BetAmountModal("Dice Bet", bal, modal_callback))
    @discord.ui.button(label="Duel", style=ButtonStyle.danger, emoji="⚔️", row=1)
    async def duel(self, button, interaction: Interaction):
        if not is_gambler(interaction.user): return await interaction.response.send_message("⛔ Restricted.", ephemeral=True)
        await interaction.response.send_message("⚔️ To duel, use: `/duel @user [amount]`", ephemeral=True)
    @discord.ui.button(label="Shop", style=ButtonStyle.secondary, emoji="🛒", row=1)
    async def shop(self, button, interaction: Interaction):
        if not is_gambler(interaction.user): return await interaction.response.send_message("⛔ Restricted.", ephemeral=True)
        view = View(); view.add_item(ShopSelect())
        await interaction.response.send_message("🛒 **Scoin Shop**", view=view, ephemeral=True)
    @discord.ui.button(label="Wallet", style=ButtonStyle.secondary, emoji="💳", row=1)
    async def wallet_btn(self, button, interaction: Interaction):
        if not is_gambler(interaction.user): return await interaction.response.send_message("⛔ Restricted.", ephemeral=True)
        bal = get_balance(str(interaction.user.id))
        await interaction.response.send_message(f"💳 Balance: **{bal}** Scoins.", ephemeral=True)

# ==================== VOICEMASTER ====================

class VCNameModal(Modal):
    def __init__(self, vc):
        super().__init__(title="Rename Voice Channel")
        self.vc = vc; self.add_item(TextInput(label="New VC Name", placeholder="Enter name...", required=True, max_length=50))
    async def callback(self, interaction: Interaction):
        try: await self.vc.edit(name=self.children[0].value); await interaction.response.send_message(f"✅ Renamed.", ephemeral=True)
        except Exception as e: await interaction.response.send_message(f"❌ Failed: {e}", ephemeral=True)

class KickMemberDropdown(Select):
    def __init__(self, vc, members):
        options = [SelectOption(label=m.display_name, value=str(m.id)) for m in members]
        super().__init__(placeholder="Select member to kick...", options=options, min_values=1, max_values=1)
        self.vc = vc
    async def callback(self, interaction: Interaction):
        try:
            member = self.vc.guild.get_member(int(self.values[0]))
            if member and member in self.vc.members: await member.move_to(None); await interaction.response.send_message(f"👢 Kicked {member.display_name}.", ephemeral=True)
            else: await interaction.response.send_message("⚠️ Member not found.", ephemeral=True)
        except Exception as e: await interaction.response.send_message(f"❌ Failed: {e}", ephemeral=True)

class KickMemberView(View):
    def __init__(self, vc, members):
        super().__init__(timeout=30)
        self.add_item(KickMemberDropdown(vc, members))

class RoleRestrictSelect(Select):
    def __init__(self, vc, creator):
        self.vc = vc; self.creator = creator
        options = [SelectOption(label="Everyone (default)", value="everyone")]
        roles = sorted([r for r in vc.guild.roles if r != vc.guild.default_role and not r.managed], key=lambda r: r.position, reverse=True)[:24]
        for r in roles: options.append(SelectOption(label=(r.name or "Role")[:100], value=str(r.id)))
        super().__init__(placeholder="Restrict VC...", options=options, min_values=1, max_values=1, custom_id="restrict_role_select")
    async def callback(self, interaction: Interaction):
        if interaction.user.id != self.creator.id: return await interaction.response.send_message("🚫 Only creator.", ephemeral=True)
        try:
            if self.values[0] == "everyone":
                await self.vc.set_permissions(interaction.guild.default_role, connect=True)
                await interaction.response.send_message("✅ Restriction cleared.", ephemeral=True)
            else:
                role = interaction.guild.get_role(int(self.values[0]))
                if role:
                    await self.vc.set_permissions(interaction.guild.default_role, connect=False)
                    await self.vc.set_permissions(role, connect=True)
                    await self.vc.set_permissions(self.creator, connect=True)
                    await interaction.response.send_message(f"🔐 Restricted to {role.name}.", ephemeral=True)
        except: await interaction.response.send_message("❌ Failed.", ephemeral=True)

class VCControlPanel(View):
    def __init__(self, vc, creator):
        super().__init__(timeout=None)
        self.vc = vc; self.creator = creator
        try: self.add_item(RoleRestrictSelect(vc, creator))
        except: pass
    async def _check(self, i):
        if i.user.id == self.creator.id: return True
        if i.data.get("custom_id") == "delete_vc" and any(r.name == ADMIN_ROLE_NAME or r.id == ROLE_ADMIN_ID for r in i.user.roles): return True
        await i.response.send_message("🚫 Only creator.", ephemeral=True); return False
    @discord.ui.button(label="🔒 Lock", style=ButtonStyle.danger, custom_id="lock_vc")
    async def lock(self, button, i):
        if not await self._check(i): return
        await self.vc.set_permissions(i.guild.default_role, connect=False); await i.response.send_message("🔒 Locked.", ephemeral=True)
    @discord.ui.button(label="🔓 Unlock", style=ButtonStyle.success, custom_id="unlock_vc")
    async def unlock(self, button, i):
        if not await self._check(i): return
        await self.vc.set_permissions(i.guild.default_role, connect=True); await i.response.send_message("🔓 Unlocked.", ephemeral=True)
    @discord.ui.button(label="❌ Delete", style=ButtonStyle.red, custom_id="delete_vc")
    async def delete(self, button, i):
        if not await self._check(i): return
        await self.vc.delete(); await i.response.send_message("🗑️ Deleted.", ephemeral=True)
    @discord.ui.button(label="✏️ Rename", style=ButtonStyle.blurple, custom_id="rename_vc")
    async def rename(self, button, i):
        if not await self._check(i): return
        await i.response.send_modal(VCNameModal(self.vc))
    @discord.ui.button(label="👢 Kick", style=ButtonStyle.gray, custom_id="kick_members")
    async def kick(self, button, i):
        if not await self._check(i): return
        m = [m for m in self.vc.members if m != i.guild.me]
        if not m: return await i.response.send_message("⚠️ No one to kick.", ephemeral=True)
        await i.response.send_message("Select:", view=KickMemberView(self.vc, m), ephemeral=True)
    @discord.ui.select(placeholder="Bitrate", options=[SelectOption(label="64k", value="64000"), SelectOption(label="384k", value="384000")], custom_id="bitrate_select")
    async def bitrate(self, select, i):
        if not await self._check(i): return
        try: await self.vc.edit(bitrate=int(select.values[0])); await i.response.send_message(f"📶 Set.", ephemeral=True)
        except: await i.response.send_message("❌ Failed.", ephemeral=True)
    @discord.ui.select(placeholder="Limit", options=[SelectOption(label="Unl", value="0"), SelectOption(label="5", value="5"), SelectOption(label="10", value="10")], custom_id="limit_select")
    async def limit(self, select, i):
        if not await self._check(i): return
        try: await self.vc.edit(user_limit=int(select.values[0])); await i.response.send_message(f"👥 Set.", ephemeral=True)
        except: await i.response.send_message("❌ Failed.", ephemeral=True)

# ==================== BOT EVENTS ====================

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    _load_persistence()
    for guild in bot.guilds:
        await _prime_invites_cache(guild)
    bot.add_view(WarRosterView()) 

@bot.event
async def on_guild_join(guild):
    await _prime_invites_cache(guild)

def setup_welcome(client):
    class MinionView(View):
        def __init__(self, target_member_id):
            super().__init__(timeout=86400)
            self.target = target_member_id
            b = Button(label="Minion", style=ButtonStyle.success)
            b.callback = self.grant
            self.add_item(b)
        async def grant(self, i):
            m = i.guild.get_member(self.target)
            r = i.guild.get_role(ROLE_MINION_ID)
            if m and r: await m.add_roles(r); await i.response.send_message(f"✅ Granted.", ephemeral=True)
            else: await i.response.send_message("❌ Error.", ephemeral=True)
    
    @client.event
    async def on_member_join(member):
        try:
            code = await _detect_used_invite_code(member)
            if code: await _apply_invite_role(member, code)
        except: pass
        ch = client.get_channel(ARRIVALS_THREAD_ID)
        if ch:
            src = await _detect_join_source(member)
            em = discord.Embed(description=f"{member.mention} joined **{member.guild.name}**", color=0x2B0B35)
            em.set_author(name=str(member), icon_url=member.display_avatar.url)
            if src: em.add_field(name="Source", value=src)
            em.set_footer(text="Tap to grant Minion")
            await ch.send(embed=em, view=MinionView(member.id))
setup_welcome(bot)

@bot.event
async def on_member_remove(member):
    channel = member.guild.get_channel(DEPARTURES_THREAD_ID) or await member.guild.fetch_channel(DEPARTURES_THREAD_ID)
    if not channel: return

    title = "👋 Member Left"
    description = f"{member.mention} left the server."
    color = THEME_LOSS 
    footer_text = f"ID: {member.id}"
    now = utcnow()
    age_str = format_age(member.created_at)
    joined_str = format_age(member.joined_at)

    try:
        async for entry in member.guild.audit_logs(limit=1, action=discord.AuditLogAction.kick):
            if entry.target.id == member.id:
                if (now - entry.created_at).total_seconds() < 10:
                    title = "🥾 Member Kicked"
                    description = f"{member.mention} kicked the server.\nBy: **{entry.user.name}** ({entry.user.display_name})"
                    color = 0xF04747 
                    break
    except: pass

    embed = discord.Embed(title=title, color=color, timestamp=now)
    embed.set_author(name=f"{member.name} ({member.display_name})", icon_url=safe_avatar_url(member))
    embed.set_thumbnail(url=safe_avatar_url(member))
    embed.add_field(name="User", value=f"{member.mention}\n{member.name} ({member.display_name})", inline=False)
    embed.add_field(name="Joined", value=joined_str, inline=True)
    embed.add_field(name="Account Age", value=age_str, inline=True)
    embed.add_field(name="Details", value=description, inline=False)
    embed.set_footer(text=footer_text)
    await channel.send(embed=embed)

async def _find_audit_action(guild, action, target_id):
    if not (guild.me and guild.me.guild_permissions.view_audit_log): return None
    try:
        async for entry in guild.audit_logs(limit=10, action=action):
            if entry.target.id == target_id and (utcnow() - entry.created_at.replace(tzinfo=timezone.utc)).total_seconds() <= 30: return entry
    except: pass
    return None

async def send_control_panel(vc, member):
    try:
        await asyncio.sleep(1)
        embed = discord.Embed(title="🎛️ Voice Control", description=f"Manage **{vc.name}**", color=THEME_PRIMARY)
        view = VCControlPanel(vc, member)
        await vc.send(embed=embed, view=view)
    except:
        try: await member.send(f"🎛️ **{vc.name}** Control Panel:", view=VCControlPanel(vc, member))
        except: pass

@bot.event
async def on_voice_state_update(member, before, after):
    guild = member.guild
    if after.channel and after.channel.id == JOIN_TO_CREATE_CHANNEL_ID:
        try:
            cat = get(guild.categories, id=VC_CATEGORY_ID) or after.channel.category
            new_vc = await guild.create_voice_channel(
                name=_limit_channel_name(_to_sans_bold_italic(f"{member.display_name}'s Room")), 
                category=cat, 
                bitrate=VC_DEFAULT_BITRATE
            )
            await new_vc.set_permissions(member, connect=True, speak=True)
            active_temp_vcs.add(new_vc.id)
            _save_active_vcs(active_temp_vcs)
            await member.move_to(new_vc)
            asyncio.create_task(send_control_panel(new_vc, member))
        except: traceback.print_exc()
        
    if before.channel and before.channel.id in active_temp_vcs and len(before.channel.members) == 0:
        try: await before.channel.delete(); active_temp_vcs.discard(before.channel.id); _save_active_vcs(active_temp_vcs)
        except: pass
        
    if member.bot: return
    target, _ = await resolve_target(bot, DEFAULT_AUDIT_THREAD_ID)
    if not target: return

    msg = None
    if before.channel != after.channel:
        if before.channel is None and after.channel is not None:
            msg = f"🟢 **{member.display_name}** joined **{after.channel.name}**."
        elif before.channel is not None and after.channel is None:
            msg = f"🔴 **{member.display_name}** left **{before.channel.name}**."
        elif before.channel is not None and after.channel is not None:
            entry = await _find_audit_action(guild, discord.AuditLogAction.member_move, member.id)
            if entry:
                actor = f"**{entry.user.display_name}**"
                msg = f"🔀 **{member.display_name}** moved **{before.channel.name}** ➜ **{after.channel.name}** by {actor}."
            else:
                msg = f"🔀 **{member.display_name}** moved **{before.channel.name}** ➜ **{after.channel.name}**."
    elif before.self_mute != after.self_mute:
        status = "muted" if after.self_mute else "unmuted"
        msg = f"🎤 **{member.display_name}** **self-{status}**."
    elif before.self_deaf != after.self_deaf:
        status = "deafened" if after.self_deaf else "undeafened"
        msg = f"🎧 **{member.display_name}** **self-{status}**."
    elif before.mute != after.mute:
        status = "server-muted" if after.mute else "server-unmuted"
        entry = await _find_audit_action(guild, discord.AuditLogAction.member_update, member.id)
        actor = f"**{entry.user.display_name}**" if entry else "Unknown Admin"
        msg = f"🙊 **{member.display_name}** was **{status}** by {actor}."
    elif before.deaf != after.deaf:
        status = "server-deafened" if after.deaf else "server-undeafened"
        entry = await _find_audit_action(guild, discord.AuditLogAction.member_update, member.id)
        actor = f"**{entry.user.display_name}**" if entry else "Unknown Admin"
        msg = f"🙉 **{member.display_name}** was **{status}** by {actor}."
    elif before.self_stream != after.self_stream:
        status = "started" if after.self_stream else "stopped"
        msg = f"📺 **{member.display_name}** **{status} streaming**."
    elif before.self_video != after.self_video:
        status = "enabled" if after.self_video else "disabled"
        msg = f"📷 **{member.display_name}** **{status} camera**."

    if msg:
        try: await target.send(msg)
        except: pass


# ==================== COMMANDS: TTS & AUDIO ====================

def _process_tts(text_val: str, lang_val: str):
    """Safely runs translation and generates TTS without locking threads."""
    final_text = text_val
    if lang_val != 'en':
        try:
            try: loop = asyncio.get_event_loop()
            except RuntimeError: loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
            
            t = Translator()
            res = t.translate(text_val, dest=lang_val)
            if res and res.text: final_text = res.text
            loop.close()
        except Exception as e: print(f"Translation Exception: {e}")
            
    if not final_text.strip(): final_text = text_val
    
    fd, path = tempfile.mkstemp(suffix=".mp3")
    os.close(fd)
    
    try: 
        tts = gTTS(text=final_text, lang=lang_val)
        tts.save(path)
        if os.path.getsize(path) == 0:
            raise Exception("gTTS returned an empty audio file. (API failure).")
    except Exception as e: 
        raise Exception(f"TTS Engine Error: {e}")
        
    return final_text, path

@bot.slash_command(name="speak", description="Text to Speech (Auto-Translates)")
@dj_or_admin()
async def speak(ctx, text: str, language: Option(str, choices=LANG_CHOICES, default="English")):
    # 1. Immediately defer to prevent Discord's "Integration Error" timeout
    await ctx.defer(ephemeral=True)
    
    user = ctx.user if isinstance(ctx, discord.Interaction) else ctx.author
    if not user.voice or not user.voice.channel:
        return await ctx.respond("❌ Join a Voice Channel first!")
        
    lang_code = LANG_CODES.get(language, 'en')

    try:
        # 2. Generate the audio file FIRST
        text_to_speak, filepath = await bot.loop.run_in_executor(None, _process_tts, text, lang_code)

        # 3. Connect cleanly using the proven v6 logic
        vc = ctx.guild.voice_client
        if vc and not vc.is_connected():
            try: await vc.disconnect(force=True)
            except: pass
            vc = None
        
        if vc:
            if vc.channel.id != user.voice.channel.id: await vc.move_to(user.voice.channel)
        else: 
            vc = await user.voice.channel.connect(timeout=10, reconnect=True)

        if vc.is_playing():
            return await ctx.followup.send("❌ Audio is already playing. Stop it first.")

        def _after_play(error):
            if error: print(f"Speak Playback Error: {error}")
            try:
                if os.path.exists(filepath): os.remove(filepath)
            except: pass

        # 4. Playback with an anti-loop safety net
        try:
            vc.play(discord.FFmpegPCMAudio(filepath), after=_after_play)
        except discord.ClientException as play_err:
            if "Not connected to voice" in str(play_err):
                # Forcefully clear the dead Py-cord state but do NOT enter an infinite retry loop
                if ctx.guild.voice_client:
                    try: await ctx.guild.voice_client.disconnect(force=True)
                    except: pass
                return await ctx.followup.send("❌ Voice socket dropped. I've reset the connection, please try your command again.")
            else:
                raise play_err

        await ctx.followup.send(f"🗣️ **{language}:** {text_to_speak}")

        log_ch = bot.get_channel(SPEAK_LOG_THREAD_ID)
        if log_ch:
            try: await log_ch.send(f"🗣️ **{ctx.author.display_name}** ({language}): {text_to_speak}")
            except: pass

    except Exception as e:
        traceback.print_exc()
        await ctx.followup.send(f"❌ Voice Error: {e}")


# ==================== COMMANDS: MISC & EMBEDS ====================

@bot.slash_command(name="haste", description="Random Haste Fact")
async def haste(ctx):
    if not active_haste_facts:
        return await ctx.respond("No facts yet.")
    fact = random.choice(active_haste_facts)
    # Replaced safe_reply with native context respond to fix Integration Errors
    await ctx.respond(f"🍌 **Fact:** {fact}")

@bot.slash_command(name="morehaste", description="Add Haste Fact")
@admin_only()
async def morehaste(ctx, fact: str):
    active_haste_facts.append(fact)
    _save_haste_facts()
    await ctx.respond("✅ Added.", ephemeral=True)

class EasyEmbedModal(Modal):
    def __init__(self, channel, edit_msg=None):
        super().__init__(title="Edit Embed" if edit_msg else "Create Custom Embed")
        self.channel = channel; self.edit_msg = edit_msg
        pre_title = edit_msg.embeds[0].title if edit_msg and edit_msg.embeds else ""
        pre_desc = edit_msg.embeds[0].description if edit_msg and edit_msg.embeds else ""
        pre_foot = edit_msg.embeds[0].footer.text if edit_msg and edit_msg.embeds and edit_msg.embeds[0].footer else ""
        pre_col = str(hex(edit_msg.embeds[0].color.value)).replace("0x", "#") if edit_msg and edit_msg.embeds and edit_msg.embeds[0].color else ""

        self.add_item(TextInput(label="Title", placeholder="Embed Title...", value=pre_title, required=True))
        self.add_item(TextInput(label="Description", placeholder="Main content...", value=pre_desc, style=discord.InputTextStyle.paragraph, required=True))
        self.add_item(TextInput(label="Footer (Optional)", placeholder="Small text at bottom...", value=pre_foot, required=False))
        self.add_item(TextInput(label="Color (Hex)", placeholder="#2B0B35", value=pre_col, required=False))

    async def callback(self, interaction: Interaction):
        title = self.children[0].value; desc = self.children[1].value
        footer = self.children[2].value; color_raw = self.children[3].value
        try: 
            if color_raw: color = int(color_raw.replace("#", ""), 16)
            else: color = THEME_PRIMARY
        except: color = THEME_PRIMARY

        embed = discord.Embed(title=title, description=desc, color=color)
        if footer: embed.set_footer(text=footer)
        
        if self.edit_msg:
            await self.edit_msg.edit(embed=embed); await interaction.response.send_message("✅ Embed Updated!", ephemeral=True)
        else:
            await self.channel.send(embed=embed); await interaction.response.send_message("✅ Embed Sent!", ephemeral=True)

@bot.slash_command(name="send_custom", description="Send a clean embed message")
@admin_only()
async def send_custom(ctx, channel: Option(discord.TextChannel, required=False)):
    target = channel or ctx.channel
    await ctx.send_modal(EasyEmbedModal(target))

@bot.slash_command(name="edit_custom", description="Edit an existing bot embed")
@admin_only()
async def edit_custom(ctx, message_id: str, channel: Option(discord.TextChannel, required=False)):
    target_channel = channel or ctx.channel
    try:
        msg = await target_channel.fetch_message(int(message_id))
        if msg.author != ctx.bot.user: return await ctx.respond("❌ I can only edit my own messages.", ephemeral=True)
        await ctx.send_modal(EasyEmbedModal(target_channel, edit_msg=msg))
    except Exception as e: await ctx.respond(f"❌ Error finding message: {e}", ephemeral=True)

@bot.slash_command(name="play")
@dj_or_admin()
async def play(ctx, search: str):
    user = ctx.user if isinstance(ctx, discord.Interaction) else ctx.author
    channel = user.voice.channel if user.voice else None
    if not channel:
        return await ctx.respond("❌ Join a VC first!", ephemeral=True)
        
    await ctx.defer()
    info = await bot.loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(YTDL_SEARCH_OPTIONS).extract_info(f"ytsearch5:{search}", download=False))
    if not info or 'entries' not in info or not info['entries']:
        return await ctx.followup.send("❌ No results found.")
        
    # Standard connection before showing UI
    vc = ctx.guild.voice_client
    if vc and not vc.is_connected():
        try: await vc.disconnect(force=True)
        except: pass
        vc = None
        
    if vc:
        if vc.channel.id != channel.id: await vc.move_to(channel)
    else: 
        vc = await channel.connect(timeout=10, reconnect=True)
        
    view = MusicSelectionView(info['entries'], ctx)
    await ctx.followup.send("🔎 **Select a track:**", view=view)

@bot.slash_command(name="queue")
async def queue(ctx):
    if ctx.guild.id not in bot.audio_queues or not bot.audio_queues[ctx.guild.id]:
        return await ctx.respond("Queue is empty.", ephemeral=True)
    lines = [f"{i+1}. {title}" for i, (url, title) in enumerate(bot.audio_queues[ctx.guild.id])]
    await ctx.respond("\n".join(lines[:10]), ephemeral=True)

@bot.slash_command(name="skip")
@dj_or_admin()
async def skip(ctx):
    if ctx.guild.voice_client: ctx.guild.voice_client.stop(); await ctx.respond("⏭️ Skipped.", ephemeral=True)

@bot.slash_command(name="stop")
@dj_or_admin()
async def stop(ctx):
    if ctx.guild.id in bot.audio_queues: bot.audio_queues[ctx.guild.id].clear()
    if ctx.guild.voice_client: ctx.guild.voice_client.stop(); await ctx.respond("⏹️ Stopped.", ephemeral=True)

@bot.slash_command(name="join")
@dj_or_admin()
async def join(ctx):
    user = ctx.user if isinstance(ctx, discord.Interaction) else ctx.author
    channel = user.voice.channel if user.voice else None
    if not channel:
        return await ctx.respond("❌ Join a VC first!", ephemeral=True)
        
    vc = ctx.guild.voice_client
    if vc and not vc.is_connected():
        try: await vc.disconnect(force=True)
        except: pass
        vc = None
        
    if vc:
        if vc.channel.id != channel.id: await vc.move_to(channel)
        await ctx.respond("✅ Joined.", ephemeral=True)
    else:
        await channel.connect(timeout=10, reconnect=True)
        await ctx.respond("✅ Joined.", ephemeral=True)

# --- RUN ---
if __name__ == "__main__":
    bot.run(TOKEN)
