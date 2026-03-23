# bot.py — ShadowSyn (Master: Unified v8.6.1 - Elite Baseline Restoration + Interactive FTC Engine Fix)
#
# === FEATURES ===
# [x] 📊 FTC v2.0: /ftc Mortgage Calculator (Owner Only). Reverse-engineering buying power & Live Edit UI.
# [x] ⚔️ WAR ROSTER: "Not Attending" status, separate embed category, and AP/DP/MDP stat tracking.
# [x] 🎰 CASINO: Dice (High/Low/7), Chicken, Slots, Duels, Shop.
# [x] 🎒 RPG TOWER: Inventory, Loot, Shop, Stats.
# [x] 🎛️ VOICEMASTER & MUSIC: All present.
# [x] 📄 CUSTOM EMBEDS: /send_custom & /edit_custom.
# [x] 🔒 VC LOCK FIX & BYPASS (v8.3/v8.4):
#     - Locking safely denies "Member" role category overrides.
#     - ONLY whitelist: current active members and the 2 Master Owners.
# [x] 🗣️ TTS REWRITE (v8.4): 
#     - Completely rewritten `/speak` logic from the ground up to prevent silent failures.
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
MASTER_OWNERS           = [132451058961219584, 482463400929263627]
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

async def safe_reply(ctx_or_inter, *args, **kwargs):
    try:
        if hasattr(ctx_or_inter, 'respond'): return await ctx_or_inter.respond(*args, **kwargs)
        elif hasattr(ctx_or_inter, 'response'):
            if not ctx_or_inter.response.is_done(): return await ctx_or_inter.response.send_message(*args, **kwargs)
            else: return await ctx_or_inter.followup.send(*args, **kwargs)
    except: return None

async def safe_defer(ctx, ephemeral=False):
    try:
        if hasattr(ctx, 'defer'):
            await ctx.defer(ephemeral=ephemeral)
        elif hasattr(ctx, 'response') and hasattr(ctx.response, 'defer'):
            if not ctx.response.is_done():
                await ctx.response.defer(ephemeral=ephemeral)
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
    if not user.voice or not user.voice.channel:
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
        else: 
            vc = await channel.connect(timeout=10, reconnect=True)
        return vc
    except Exception as e:
        await safe_reply(ctx, f"❌ Voice Error: {e}", ephemeral=True)
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


# ==================== BOT INSTANCE & STARTUP ====================
# Instantiating the bot here prevents NameErrors on the commands below

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


# ==================== FTC ENGINE ====================

def estimate_stamp_duty(price: float, state: str, fhb: bool) -> float:
    """Up-to-date accurate approximation for AU Stamp Duty 2024/2025."""
    state = state.upper()
    sd = 0.0

    if state == "NSW":
        sd = price * 0.04 if price <= 1000000 else price * 0.045
        if fhb:
            if price <= 800000: return 0.0
            elif price <= 1000000: return sd * ((price - 800000) / 200000)
    elif state == "VIC":
        sd = price * 0.055
        if fhb:
            if price <= 600000: return 0.0
            elif price <= 750000: return sd * ((price - 600000) / 150000)
    elif state == "QLD":
        # QLD recently raised FHB to 700k
        sd = price * 0.035 if price <= 1000000 else price * 0.045
        if fhb:
            if price <= 700000: return 0.0
            elif price <= 800000: return sd * ((price - 700000) / 100000)
    elif state == "WA":
        sd = price * 0.04
        if fhb:
            if price <= 450000: return 0.0
            elif price <= 600000: return sd * ((price - 450000) / 150000)
    elif state == "SA":
        sd = price * 0.045
        if fhb and price <= 650000: return 0.0
    else:
        # TAS, ACT, NT generic approximation
        sd = price * 0.045
        if fhb and price <= 500000: return 0.0

    return sd

def find_max_purchase_price(savings: int, lvr_target: float, state: str, fhb: bool) -> int:
    """Binary searches the maximum purchase price someone can afford with current savings."""
    low = 50000
    high = 5000000
    best_price = 0
    fees = 2500
    for _ in range(50): 
        mid = (low + high) / 2
        dep = mid * (1 - lvr_target)
        sd = estimate_stamp_duty(mid, state, fhb)
        total_needed = dep + sd + fees
        if total_needed <= savings:
            best_price = mid
            low = mid
        else:
            high = mid
    return int(best_price)

def generate_ftc_embed(savings: Optional[int], price: Optional[int], state: str, fhb: bool) -> discord.Embed:
    fees = 2500
    state = state.upper()
    fhb_str = "Yes" if fhb else "No"
    
    # 1. BOTH PROVIDED or ONLY PRICE PROVIDED (Forward Mode)
    if price:
        dep_10 = int(price * 0.10)
        loan_10 = price - dep_10
        lmi_10 = int(loan_10 * 0.02)
        sd_10 = int(estimate_stamp_duty(price, state, fhb))
        cash_needed_10 = dep_10 + sd_10 + fees
        
        dep_20 = int(price * 0.20)
        cash_needed_20 = dep_20 + sd_10 + fees
        
        desc = f"**Target Purchase Price:** ${price:,.0f} | **State:** {state} | **FHB:** {fhb_str}"
        if savings: desc += f" | **Savings:** ${savings:,.0f}"
        desc += "\n\n"
        
        # 10% Scenario
        desc += f"👉 **SCENARIO 1: 10% Deposit (90% LVR)**\n"
        desc += f"**Deposit Required:** ${dep_10:,.0f}\n"
        desc += f"**Est. Stamp Duty & Fees:** ${(sd_10 + fees):,.0f}\n"
        desc += f"**Total Cash Needed (Funds to Complete):** ${cash_needed_10:,.0f}\n"
        
        if savings:
            diff_10 = savings - cash_needed_10
            status_10 = f"Surplus of ${diff_10:,.0f}" if diff_10 >= 0 else f"Shortfall of ${abs(diff_10):,.0f}"
            desc += f"**Surplus/Shortfall:** {status_10}\n"
        desc += f"*Note: Est. LMI of ${lmi_10:,.0f} to be capitalized into the loan.*\n\n"

        # 20% Scenario
        desc += f"👉 **SCENARIO 2: 20% Deposit (80% LVR) - No LMI**\n"
        desc += f"**Deposit Required:** ${dep_20:,.0f}\n"
        desc += f"**Est. Stamp Duty & Fees:** ${(sd_10 + fees):,.0f}\n"
        desc += f"**Total Cash Needed (Funds to Complete):** ${cash_needed_20:,.0f}\n"
        
        if savings:
            diff_20 = savings - cash_needed_20
            status_20 = f"Surplus of ${diff_20:,.0f}" if diff_20 >= 0 else f"Shortfall of ${abs(diff_20):,.0f}"
            desc += f"**Surplus/Shortfall:** {status_20}\n"
        desc += f"*Note: Avoids LMI entirely.*\n\n"
        
        # Dynamic Talking Point (if savings provided)
        if savings:
            if diff_20 >= 0: tp = "Great news! We comfortably have the cash for a 20% deposit, meaning we can avoid LMI entirely."
            elif diff_10 >= 0: tp = "We are a bit short for the 20% right now, but we comfortably have the cash to get you into the market at 90% LVR if you're happy to capitalize the LMI."
            else: tp = f"We're currently short for both scenarios. We'll need to save an additional ${abs(diff_10):,.0f} to reach the 10% entry point."
            desc += f"🗣️ **Broker Talking Point:**\n_{tp}_"
            
        return discord.Embed(title="📊 Funds to Complete (FTC)", description=desc, color=THEME_GOLD)

    # 2. ONLY SAVINGS PROVIDED (Reverse Mode - Buying Power)
    elif savings:
        max_10 = find_max_purchase_price(savings, 0.90, state, fhb)
        max_20 = find_max_purchase_price(savings, 0.80, state, fhb)
        
        sd_10 = int(estimate_stamp_duty(max_10, state, fhb))
        sd_20 = int(estimate_stamp_duty(max_20, state, fhb))
        
        dep_10 = int(max_10 * 0.10)
        dep_20 = int(max_20 * 0.20)
        lmi_10 = int((max_10 * 0.90) * 0.02)
        
        desc = f"**Savings:** ${savings:,.0f} | **State:** {state} | **FHB:** {fhb_str}\n"
        desc += "*Displaying Maximum Buying Power based on available cash.*\n\n"
        
        desc += f"👉 **SCENARIO 1: Max Power at 10% Deposit (90% LVR)**\n"
        desc += f"**Max Purchase Price:** ${max_10:,.0f}\n"
        desc += f"**Deposit Required:** ${dep_10:,.0f}\n"
        desc += f"**Est. Stamp Duty & Fees:** ${(sd_10 + fees):,.0f}\n"
        desc += f"*Note: Est. LMI of ${lmi_10:,.0f} to be capitalized into the loan.*\n\n"
        
        desc += f"👉 **SCENARIO 2: Max Power at 20% Deposit (80% LVR)**\n"
        desc += f"**Max Purchase Price:** ${max_20:,.0f}\n"
        desc += f"**Deposit Required:** ${dep_20:,.0f}\n"
        desc += f"**Est. Stamp Duty & Fees:** ${(sd_20 + fees):,.0f}\n"
        desc += f"*Note: Avoids LMI entirely.*\n\n"
        
        tp = f"Based on your savings of ${savings:,.0f}, the absolute maximum we can purchase is roughly ${max_10:,.0f} using a 10% deposit strategy. Or, if you want to avoid LMI entirely, your cap is ${max_20:,.0f}."
        desc += f"🗣️ **Broker Talking Point:**\n_{tp}_"
        
        return discord.Embed(title="📊 Buying Power Calculator", description=desc, color=THEME_WIN)

class FTCEditModal(Modal):
    def __init__(self, view, mode):
        super().__init__(title="Edit Savings" if mode == "savings" else "Edit Purchase Price")
        self.view_ref = view
        self.mode = mode
        
        val = str(view.savings or "") if mode == "savings" else str(view.price or "")
        self.add_item(TextInput(label="Amount ($)", placeholder="e.g., 85000", value=val, required=False))

    async def callback(self, interaction: Interaction):
        raw = self.children[0].value.replace(",", "").replace("$", "").strip()
        try: 
            val = int(raw) if raw else None
        except: 
            return await interaction.response.send_message("❌ Invalid number.", ephemeral=True)
            
        if self.mode == "savings": self.view_ref.savings = val
        else: self.view_ref.price = val
            
        embed = generate_ftc_embed(self.view_ref.savings, self.view_ref.price, self.view_ref.state, self.view_ref.fhb)
        await interaction.response.edit_message(embed=embed, view=self.view_ref)

class FTCStateSelect(Select):
    def __init__(self, current_state):
        options = [SelectOption(label=s, default=(s==current_state)) for s in ["NSW", "VIC", "QLD", "WA", "SA", "TAS", "ACT", "NT"]]
        super().__init__(placeholder="Change State...", options=options, row=1)
    async def callback(self, interaction: Interaction):
        self.view.state = self.values[0]
        for opt in self.options: opt.default = (opt.label == self.view.state)
        embed = generate_ftc_embed(self.view.savings, self.view.price, self.view.state, self.view.fhb)
        await interaction.response.edit_message(embed=embed, view=self.view)

class FTCControlView(View):
    def __init__(self, savings, price, state, fhb, user_id):
        super().__init__(timeout=900)
        self.savings = savings
        self.price = price
        self.state = state
        self.fhb = fhb
        self.user_id = user_id
        
        self.add_item(FTCStateSelect(state))

    @discord.ui.button(label="Edit Savings", style=ButtonStyle.primary, emoji="💵", row=0)
    async def edit_sav(self, button, i):
        if i.user.id != self.user_id: return
        await i.response.send_modal(FTCEditModal(self, "savings"))

    @discord.ui.button(label="Edit Price", style=ButtonStyle.primary, emoji="🏠", row=0)
    async def edit_pri(self, button, i):
        if i.user.id != self.user_id: return
        await i.response.send_modal(FTCEditModal(self, "price"))
        
    @discord.ui.button(label="Toggle FHB", style=ButtonStyle.success, emoji="🔄", row=0)
    async def toggle_fhb(self, button, i):
        if i.user.id != self.user_id: return
        self.fhb = not self.fhb
        embed = generate_ftc_embed(self.savings, self.price, self.state, self.fhb)
        await i.response.edit_message(embed=embed, view=self)

@bot.slash_command(name="ftc", description="Interactive FTC & Buying Power Calculator (Owner Only)")
@owner_only()
async def ftc(
    ctx,
    state: Option(str, description="Australian State", choices=["NSW", "VIC", "QLD", "WA", "SA", "TAS", "ACT", "NT"]),
    savings: Option(int, description="Client savings amount", required=False),
    purchase_price: Option(int, description="Target purchase price", required=False),
    fhb: Option(bool, description="First Home Buyer?", default=False)
):
    if not savings and not purchase_price:
        return await safe_reply(ctx, "❌ You must provide at least `savings` or `purchase_price`.", ephemeral=True)
        
    embed = generate_ftc_embed(savings, purchase_price, state, fhb)
    view = FTCControlView(savings, purchase_price, state, fhb, ctx.author.id)
    await safe_reply(ctx, embed=embed, view=view)

# ==================== COMMANDS: WAR ROSTER ====================

@bot.slash_command(name="create_war", description="Create a Quinfall War Roster (requires War Role)")
async def create_war(
    ctx, 
    title: Option(str, description="Title of the war"), 
    hammer_time: Option(str, description="Paste timestamp from HammerTime (e.g., <t:170000000:F>)")
):
    if not is_war_role(ctx.author):
        return await safe_reply(ctx, "⛔ Restricted. You must have the required role.", ephemeral=True)
        
    target_channel = bot.get_channel(WAR_THREAD_ID) or await bot.fetch_channel(WAR_THREAD_ID)
    if not target_channel:
        return await safe_reply(ctx, "❌ War channel thread not found.", ephemeral=True)
        
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
    
    await safe_reply(ctx, f"✅ War roster created in {target_channel.mention}", ephemeral=True)

def generate_war_embed(data):
    embed = discord.Embed(title=f"⚔️ {data['title']}", description=f"**Time:** {data['time']}\nSelect your class and if you'll miss any fights below!", color=THEME_COMBAT)
    class_counts = {c[0]: [] for c in QUINFALL_CLASSES}
    
    for uid, info in data.get("roster", {}).items():
        stats_str = ""
        if isinstance(info, str):
            cls = info; absences = []
        else:
            cls = info.get("class")
            if "absences" in info: absences = info["absences"]
            elif "fights" in info: absences = [f for f in ["1", "2", "3", "4", "5"] if f not in info["fights"]]
            else: absences = []
            
            ap = info.get("ap")
            dp = info.get("dp")
            mdp = info.get("mdp")
            if ap and dp and mdp:
                stats_str = f" `[AP: {ap} | DP: {dp} | MDP: {mdp}]`"
            
        fight_str = f" *(Absent Round {', '.join(sorted(absences))})*" if absences else ""
        if cls in class_counts: class_counts[cls].append(f"<@{uid}>{stats_str}{fight_str}")
            
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

class WarStatsModal(Modal):
    def __init__(self, msg_id, selected_class):
        super().__init__(title="Enter Your Quinfall Stats")
        self.msg_id = msg_id
        self.selected_class = selected_class
        
        self.add_item(TextInput(label="AP (Attack Power)", placeholder="e.g., 4500", required=True, max_length=5))
        self.add_item(TextInput(label="DP (Defense Power)", placeholder="e.g., 3000", required=True, max_length=5))
        self.add_item(TextInput(label="MDP (Magic Defense)", placeholder="e.g., 2800", required=True, max_length=5))

    async def callback(self, interaction: Interaction):
        ap = self.children[0].value
        dp = self.children[1].value
        mdp = self.children[2].value
        uid = str(interaction.user.id)

        if self.msg_id not in war_db: 
            return await interaction.response.send_message("❌ War not found in database.", ephemeral=True)
        
        if "roster" not in war_db[self.msg_id]: war_db[self.msg_id]["roster"] = {}
        if "not_attending" not in war_db[self.msg_id]: war_db[self.msg_id]["not_attending"] = []
        if uid in war_db[self.msg_id]["not_attending"]: war_db[self.msg_id]["not_attending"].remove(uid)

        # Preserve previous absences if they already made a submission
        absences = []
        if uid in war_db[self.msg_id]["roster"] and isinstance(war_db[self.msg_id]["roster"][uid], dict):
            absences = war_db[self.msg_id]["roster"][uid].get("absences", [])

        war_db[self.msg_id]["roster"][uid] = {
            "class": self.selected_class, 
            "absences": absences,
            "ap": ap,
            "dp": dp,
            "mdp": mdp
        }
        _save_wars()

        try:
            msg = await interaction.channel.fetch_message(int(self.msg_id))
            await msg.edit(embed=generate_war_embed(war_db[self.msg_id]))
            await interaction.response.send_message("✅ Class and Stats updated successfully!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"⚠️ Saved, but failed to update embed: {e}", ephemeral=True)

class WarClassSelect(Select):
    def __init__(self):
        options = [SelectOption(label=name, value=name, emoji=emoji) for name, emoji in QUINFALL_CLASSES]
        super().__init__(placeholder="1. Select Class to Join...", options=options, custom_id="war_class_select", min_values=1, max_values=1, row=0)
        
    async def callback(self, interaction: Interaction):
        msg_id = str(interaction.message.id)
        if msg_id not in war_db: return await interaction.response.send_message("❌ War not found in database.", ephemeral=True)
        selected_class = self.values[0]
        
        # Pop the Modal for Stats instead of immediately updating
        await interaction.response.send_modal(WarStatsModal(msg_id, selected_class))

class WarAttendanceSelect(Select):
    def __init__(self):
        options = [SelectOption(label=f"Absent Fight {i}", value=str(i), emoji="❌") for i in range(1, 6)]
        super().__init__(placeholder="2. Select Fights to MISS (Leave empty if attending all)", options=options, custom_id="war_attendance_select", min_values=0, max_values=5, row=1)
        
    async def callback(self, interaction: Interaction):
        msg_id = str(interaction.message.id)
        if msg_id not in war_db: return await interaction.response.send_message("❌ War not found.", ephemeral=True)
        uid = str(interaction.user.id)
        
        if uid not in war_db[msg_id].get("roster", {}): return await interaction.response.send_message("❌ Select a Class first!", ephemeral=True)
        if isinstance(war_db[msg_id]["roster"][uid], str): 
            war_db[msg_id]["roster"][uid] = {"class": war_db[msg_id]["roster"][uid], "absences": self.values}
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
        
        if not url: return await interaction.followup.send("❌ Error: Could not resolve URL for that track.")

        if self.vc.is_playing():
            if self.ctx.guild.id not in bot.audio_queues: bot.audio_queues[self.ctx.guild.id] = deque()
            bot.audio_queues[self.ctx.guild.id].append((url, title))
            await interaction.followup.send(f"📝 **Queued:** {title}")
        else:
            await interaction.followup.send(f"▶️ **Playing:** {title}")
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

# ==================== VOICEMASTER DASHBOARD ====================

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
                await self.vc.set_permissions(interaction.guild.default_role, connect=None)
                if self.vc.category:
                    for target, overwrite in self.vc.category.overwrites.items():
                        if isinstance(target, discord.Role) and target != interaction.guild.default_role:
                            await self.vc.set_permissions(target, connect=None)
                await interaction.response.send_message("✅ Restriction cleared.", ephemeral=True)
            else:
                role = interaction.guild.get_role(int(self.values[0]))
                if role:
                    await self.vc.set_permissions(interaction.guild.default_role, connect=False)
                    await self.vc.set_permissions(role, connect=True)
                    await self.vc.set_permissions(self.creator, connect=True)
                    
                    # Grant explicit bypass to master owners
                    for oid in MASTER_OWNERS:
                        owner = interaction.guild.get_member(oid)
                        if owner:
                            await self.vc.set_permissions(owner, connect=True)
                    
                    # Deny category roles from bypassing this specific role lock
                    if self.vc.category:
                        for target, overwrite in self.vc.category.overwrites.items():
                            if isinstance(target, discord.Role) and target != interaction.guild.default_role and target.id != role.id:
                                if not target.permissions.administrator:
                                    await self.vc.set_permissions(target, connect=False)
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
        
        # Immediate defer prevents the 10062 Unknown Interaction error when API rate limits are hit
        await i.response.defer(ephemeral=True)
        
        # Whitelist current members so they don't get accidentally locked out
        for m in self.vc.members:
            await self.vc.set_permissions(m, connect=True)
            
        # Explicitly whitelist Master Owners so they bypass the lock
        for oid in MASTER_OWNERS:
            owner = i.guild.get_member(oid)
            if owner and owner not in self.vc.members:
                await self.vc.set_permissions(owner, connect=True)
            
        # Deny @everyone
        await self.vc.set_permissions(i.guild.default_role, connect=False)
        
        # Fix: Deny category-level role overrides (prevents "Member" roles from bypassing lock)
        if self.vc.category:
            for target, overwrite in self.vc.category.overwrites.items():
                if isinstance(target, discord.Role) and target != i.guild.default_role:
                    if not target.permissions.administrator:
                        await self.vc.set_permissions(target, connect=False)
                        
        await i.followup.send("🔒 Locked securely. (Owners bypass active)", ephemeral=True)
        
    @discord.ui.button(label="🔓 Unlock", style=ButtonStyle.success, custom_id="unlock_vc")
    async def unlock(self, button, i):
        if not await self._check(i): return
        
        # Immediate defer to prevent timeout errors
        await i.response.defer(ephemeral=True)
        
        # Reset default role to category inherit
        await self.vc.set_permissions(i.guild.default_role, connect=None)
        
        # Clear any role overwrites added by the lock
        if self.vc.category:
            for target, overwrite in self.vc.category.overwrites.items():
                if isinstance(target, discord.Role) and target != i.guild.default_role:
                    await self.vc.set_permissions(target, connect=None)
                    
        await i.followup.send("🔓 Unlocked.", ephemeral=True)
        
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


# ==================== RUN ====================
if __name__ == "__main__":
    bot.run(TOKEN)
