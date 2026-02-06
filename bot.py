# bot.py — ShadowSyn (Master: Shadow Tower 3.2 - Economy Integration)
#
# === FEATURES ===
# [x] 🏰 SHADOW TOWER 3.2:
#     - 💰 ECONOMY: Bosses (Every 10 floors) drop 2-5 Scoins.
#     - 💎 ARTIFACTS: Rare loot type. Can be sold for +2 Scoins via the UI.
#     - 🚀 FLOW: Seamless start & XP bars retained.
#     - ⚡ VISUALS: Elite UI retained.
# [x] CASINO & CORE: All previous features maintained exactly.
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

VANITY_INVITE  = "https://discord.gg/shadowsyn"
THEME_PRIMARY  = 0x2B0B35
THEME_WIN      = 0x43B581 
THEME_LOSS     = 0xF04747 
THEME_GOLD     = 0xFFD700 
THEME_COMBAT   = 0xE67E22 
THEME_BOSS     = 0x992D22 
THEME_RARE     = 0x3498DB
THEME_EPIC     = 0x9B59B6
THEME_LEGEND   = 0xE67E22

# --- BIOME THEMES ---
BIOMES = {
    "Sewers": {"range": (1, 20), "color": 0x2ECC71, "emoji": "🤢", "effect": "Toxic: 5% Poison Dmg every 5 turns."},
    "Catacombs": {"range": (21, 40), "color": 0x95A5A6, "emoji": "💀", "effect": "Darkness: 20% Miss Chance."},
    "Magma Core": {"range": (41, 60), "color": 0xE74C3C, "emoji": "🌋", "effect": "Heat: Skills cost 5 HP."},
    "Void": {"range": (61, 999), "color": 0x8E44AD, "emoji": "🔮", "effect": "Void: Enemies deal True Damage."}
}

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

BOSSES = {
    10: "The Gatekeeper", 20: "Broodmother", 30: "Skeleton King",
    40: "High Warlord", 50: "The Kraken", 60: "Vampire Lord",
    70: "Red Dragon", 80: "Void Bringer", 100: "ShadowSyn Prime"
}

PERKS = [
    {"id": "glutton", "name": "🥩 Glutton", "desc": "Potions heal +50% HP."},
    {"id": "midas", "name": "🤑 Midas Touch", "desc": "+20% Gold from enemies."},
    {"id": "vampire", "name": "🩸 Vampirism", "desc": "Heal 5 HP on kill."},
    {"id": "thorns", "name": "🌵 Thorns", "desc": "Reflect 10% damage back."},
    {"id": "scholar", "name": "📖 Scholar", "desc": "+20% XP gain."}
]

AFFIXES = {
    "Vampiric": ("Heals on hit", 0), 
    "Sharp": ("+20% DMG", 0), 
    "Reinforced": ("+20% DEF", 0),
    "Cursed": ("High Stats, -HP", 0),
    "Lucky": ("+Gold Drop", 0)
}

# --- DATA ---
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
TOWER_STORE = (PERSIST_ROOT / "tower_v3.json")

active_haste_facts = []
scoins_db = {}
tower_db = {}

def _atomic_write(file_path: Path, data: Union[dict, list, set]):
    try:
        content = json.dumps(list(data) if isinstance(data, set) else data, indent=2)
        temp_path = file_path.with_suffix(".tmp")
        temp_path.write_text(content, encoding='utf-8')
        temp_path.replace(file_path)
    except Exception as e:
        print(f"⚠️ Persistence Error [{file_path.name}]: {e}")

def _load_persistence():
    global active_haste_facts, scoins_db, tower_db
    if HASTE_FACTS_STORE.exists():
        try: active_haste_facts = json.loads(HASTE_FACTS_STORE.read_text())
        except: active_haste_facts = list(DEFAULT_HASTE_FACTS)
    else: active_haste_facts = list(DEFAULT_HASTE_FACTS)

    if SCOINS_STORE.exists():
        try: scoins_db = json.loads(SCOINS_STORE.read_text())
        except: scoins_db = {}
    else: scoins_db = {}

    if TOWER_STORE.exists():
        try: tower_db = json.loads(TOWER_STORE.read_text())
        except: tower_db = {}
    else: tower_db = {}

def _save_haste_facts(): _atomic_write(HASTE_FACTS_STORE, active_haste_facts)
def _save_scoins(): _atomic_write(SCOINS_STORE, scoins_db)
def _save_tower(): _atomic_write(TOWER_STORE, tower_db)

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

# ==================== DATA LOADERS (INVITES) ====================

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

# ==================== SHADOW TOWER 3.2 (ELITE RPG) ====================

def get_tower_data(user_id):
    uid = str(user_id)
    if uid not in tower_db:
        tower_db[uid] = {
            "floor": 1, "max_floor": 1, 
            "hp": 100, "max_hp": 100, 
            "gold": 0, "checkpoint": 1, 
            "potions": 0, "atk": 0, "def": 0,
            "class": None, "xp": 0, "level": 1, 
            "perks": [], "pets": [], "gear": None,
            "adrenaline": 0
        }
    defaults = {"class": None, "xp": 0, "level": 1, "perks": [], "pets": [], "gear": None, "adrenaline": 0}
    for k, v in defaults.items():
        if k not in tower_db[uid]: tower_db[uid][k] = v
    return tower_db[uid]

def save_tower_data(user_id, data):
    tower_db[str(user_id)] = data
    _save_tower()

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

def get_xp_needed(lvl): return lvl * 50

def draw_bar(curr, max_val, color="🟩", length=10):
    if max_val <= 0: return color + "⬛" * 9
    pct = max(0, min(1, curr / max_val))
    fill = int(pct * length)
    if fill == 0 and curr > 0: fill = 1 
    return color * fill + "⬜" * (length - fill)

def draw_adren_bar(val):
    return draw_bar(val, 100, "🟨", 8)

def generate_loot(floor):
    # 5% Chance for Scoin Artifact
    if random.random() < 0.05:
        return {
            "name": "💰 Ancient Artifact",
            "type": "ARTIFACT",
            "val": 2, # Scoin Value
            "tier": "Special",
            "affix": None,
            "color": THEME_GOLD
        }

    roll = random.randint(1, 100)
    if roll > 95: tier, mult, color = "Legendary", 5, THEME_LEGEND
    elif roll > 80: tier, mult, color = "Epic", 3, THEME_EPIC
    elif roll > 60: tier, mult, color = "Rare", 2, THEME_RARE
    else: tier, mult, color = "Common", 1, 0x95A5A6

    is_weapon = random.choice([True, False])
    base_name = random.choice(["Dagger", "Sword", "Axe", "Scythe"]) if is_weapon else random.choice(["Shield", "Armor", "Cloak", "Helm"])
    stat_type = "ATK" if is_weapon else "DEF"
    val = (floor * mult) + random.randint(1, 5)

    affix = None
    if tier != "Common" and random.random() < 0.5:
        affix = random.choice(list(AFFIXES.keys()))
        base_name = f"{affix} {base_name}"
    
    return {
        "name": f"{tier} {base_name}",
        "type": stat_type,
        "val": val,
        "tier": tier,
        "affix": affix,
        "color": color
    }

# --- RPG VIEWS ---

class MysteryRoomView(View):
    def __init__(self, user, data):
        super().__init__(timeout=120)
        self.user = user
        self.data = data
        self.user_id = str(user.id)

    @discord.ui.button(label="Sacrifice 20% Max HP for +10 ATK", style=ButtonStyle.danger, emoji="🩸")
    async def sacrifice(self, button, interaction):
        if interaction.user.id != self.user.id: return
        
        loss = int(self.data["max_hp"] * 0.2)
        self.data["max_hp"] -= loss
        self.data["hp"] = min(self.data["hp"], self.data["max_hp"])
        self.data["atk"] += 10
        save_tower_data(self.user_id, self.data)
        
        await interaction.response.edit_message(
            embed=discord.Embed(title="🩸 The Pact is Sealed", description=f"You lost **{loss} Max HP**.\nYou gained **+10 ATK**.", color=THEME_LOSS),
            view=TowerGameView(self.user)
        )

    @discord.ui.button(label="Leave Safely", style=ButtonStyle.secondary, emoji="🏃")
    async def leave(self, button, interaction):
        if interaction.user.id != self.user.id: return
        await interaction.response.edit_message(
            embed=discord.Embed(title="🏃 Escape", description="You stepped away from the cursed shrine.", color=THEME_PRIMARY),
            view=TowerGameView(self.user)
        )

class PerkSelectView(View):
    def __init__(self, user, data):
        super().__init__(timeout=300)
        self.user = user
        self.data = data
        self.user_id = str(user.id)
        
        owned = [p for p in data["perks"]]
        available = [p for p in PERKS if p["id"] not in owned]
        if not available: 
            self.stop()
            return
            
        options = random.sample(available, min(3, len(available)))
        for opt in options:
            btn = Button(label=opt["name"], style=ButtonStyle.primary)
            async def cb(interaction, o=opt): await self.select_perk(interaction, o)
            btn.callback = cb
            self.add_item(btn)

    async def select_perk(self, interaction, perk):
        if interaction.user.id != self.user.id: return
        self.data["perks"].append(perk["id"])
        save_tower_data(self.user_id, self.data)
        
        embed = discord.Embed(title="🧬 Mutation Complete", description=f"You evolved: **{perk['name']}**\n*{perk['desc']}*", color=THEME_WIN)
        await interaction.response.edit_message(embed=embed, view=TowerGameView(self.user))

class LootView(View):
    def __init__(self, user, item):
        super().__init__(timeout=120)
        self.user = user
        self.item = item
        self.data = get_tower_data(user.id)
        
        # Adjust buttons for Artifacts
        if item.get("type") == "ARTIFACT":
            self.remove_item(self.equip) # Remove standard equip
            # Add Sell Button
            sell_btn = Button(label="Sell to Casino (+2 Scoins)", style=ButtonStyle.success, emoji="💰")
            async def sell_cb(interaction):
                if interaction.user.id != self.user.id: return
                update_balance(str(self.user.id), 2)
                save_tower_data(self.user.id, self.data)
                await interaction.response.edit_message(embed=discord.Embed(title="💰 Sold!", description="You sold the artifact for **2 Scoins**.", color=THEME_GOLD), view=TowerGameView(self.user))
            sell_btn.callback = sell_cb
            self.add_item(sell_btn)

    @discord.ui.button(label="Equip", style=ButtonStyle.success, emoji="⚔️")
    async def equip(self, button, interaction):
        if interaction.user.id != self.user.id: return
        old_gear = self.data.get("gear")
        if old_gear:
            if old_gear["type"] == "ATK": self.data["atk"] -= old_gear["val"]
            elif old_gear["type"] == "DEF": self.data["def"] -= old_gear["val"]
        
        self.data["gear"] = self.item
        if self.item["type"] == "ATK": self.data["atk"] += self.item["val"]
        elif self.item["type"] == "DEF": self.data["def"] += self.item["val"]
        
        save_tower_data(self.user.id, self.data)
        await interaction.response.edit_message(embed=discord.Embed(title="⚔️ Equipped", description=f"You wield **{self.item['name']}**.", color=THEME_WIN), view=TowerGameView(self.user))

    @discord.ui.button(label="Salvage", style=ButtonStyle.secondary, emoji="🔨")
    async def salvage(self, button, interaction):
        if interaction.user.id != self.user.id: return
        xp = self.item["val"] * 5
        gold = self.item["val"] * 10
        self.data["xp"] += xp
        self.data["gold"] += gold
        save_tower_data(self.user.id, self.data)
        await interaction.response.edit_message(embed=discord.Embed(title="🔨 Salvaged", description=f"Gained **{xp} XP** and **{gold} Gold**.", color=THEME_GOLD), view=TowerGameView(self.user))

class TowerGameView(View):
    def __init__(self, user):
        super().__init__(timeout=300)
        self.user = user
        self.user_id = str(user.id)
        self.data = get_tower_data(user.id)
        self.mode = "EXPLORE"
        self.enemy = None
        self.combat_log = []
        self.render_main_menu()

    def update_embed(self, title, desc, color=THEME_PRIMARY):
        b_name, b_data = get_biome(self.data['floor'])
        p_bar = draw_bar(self.data["hp"], self.data["max_hp"], "🟩")
        a_bar = draw_adren_bar(self.data.get("adrenaline", 0))
        final_color = b_data["color"]
        if self.mode == "COMBAT": final_color = THEME_COMBAT

        embed = discord.Embed(title=f"{b_data['emoji']} {title} | Floor {self.data['floor']}", description=desc, color=final_color)
        
        if self.mode == "COMBAT" and self.enemy:
            e_bar = draw_bar(self.enemy['hp'], self.enemy['max_hp'], "🟥")
            intent = self.enemy.get("intent", "Unknown")
            embed.add_field(name=f"🆚 {self.enemy['name']}", 
                           value=f"{e_bar} {self.enemy['hp']} HP\n⚠️ **Intent:** {intent}", inline=False)
            if self.combat_log:
                embed.add_field(name="📜 Log", value="\n".join(self.combat_log[-3:]), inline=False)

        stats = f"⚔️{self.data['atk']} 🛡️{self.data['def']} 💰{self.data['gold']}"
        embed.add_field(name=f"👤 {self.user.display_name} ({self.data['class']})", 
                       value=f"{p_bar} {self.data['hp']} HP\n{a_bar} Limit Break\n{stats}", inline=False)
        
        embed.set_footer(text=f"{b_name}: {b_data['effect']}")
        return embed

    def render_main_menu(self):
        self.clear_items()
        
        if self.mode == "COMBAT":
            self.add_item(Button(label="Attack", style=ButtonStyle.danger, custom_id="act_atk"))
            self.add_item(Button(label="Defend", style=ButtonStyle.secondary, custom_id="act_def"))
            
            adren = self.data.get("adrenaline", 0)
            cls = self.data["class"]
            
            if adren >= 100:
                skill_name = "ULTIMATE READY!"
                style = ButtonStyle.success 
                if cls == "Warrior": skill_name = "JUGGERNAUT (Immune)"
                elif cls == "Rogue": skill_name = "EXECUTE (Kill)"
                elif cls == "Mage": skill_name = "CATACLYSM (Nuke)"
                self.add_item(Button(label=skill_name, style=style, emoji="⚡", custom_id="act_ult"))
            else:
                skill_name = "Skill"
                if cls == "Warrior": skill_name = "Bash"
                elif cls == "Rogue": skill_name = "Dodge"
                elif cls == "Mage": skill_name = "Blast"
                self.add_item(Button(label=skill_name, style=ButtonStyle.primary, custom_id="act_skill"))
            
            if self.data["potions"] > 0:
                self.add_item(Button(label=f"Potion ({self.data['potions']})", style=ButtonStyle.secondary, emoji="🧪", custom_id="act_pot"))
                
        else:
            self.add_item(Button(label="Climb", style=ButtonStyle.success, emoji="🧗", custom_id="nav_climb"))
            self.add_item(Button(label="Rest (100g)", style=ButtonStyle.primary, emoji="💤", custom_id="nav_rest"))
            self.add_item(Button(label="Save", style=ButtonStyle.secondary, emoji="💾", custom_id="nav_save"))

    async def interaction_check(self, interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("🚫 Not your session.", ephemeral=True)
            return False
        
        cid = interaction.data["custom_id"]
        if "act_" in cid: await self.resolve_combat(interaction, cid)
        elif "nav_" in cid: await self.resolve_nav(interaction, cid)
        return False

    async def resolve_nav(self, interaction, cid):
        if cid == "nav_rest":
            if self.data["gold"] >= 100:
                self.data["gold"] -= 100
                self.data["hp"] = self.data["max_hp"]
                save_tower_data(self.user_id, self.data)
                await interaction.response.edit_message(embed=self.update_embed("💤 Rested", "HP Fully Restored."), view=self)
            else:
                await interaction.response.send_message("❌ Need 100 Gold.", ephemeral=True)
                
        elif cid == "nav_save":
            self.data["checkpoint"] = self.data["floor"]
            save_tower_data(self.user_id, self.data)
            await interaction.response.send_message("💾 **Checkpoint Saved.**", ephemeral=True)
            
        elif cid == "nav_climb":
            if random.random() < 0.10 and self.data["floor"] % 10 != 0:
                view = MysteryRoomView(self.user, self.data)
                embed = discord.Embed(title="🔮 Mystery Room", description="You found a **Cursed Shrine**.", color=0x9B59B6)
                await interaction.response.edit_message(embed=embed, view=view)
                return

            if self.data["floor"] % 10 == 0:
                boss_name = BOSSES.get(self.data["floor"], "Unknown Horror")
                self.start_combat(boss=True, name=boss_name)
            else:
                roll = random.randint(1, 100)
                if roll > 30: 
                    self.start_combat()
                else: 
                    item = generate_loot(self.data["floor"])
                    view = LootView(self.user, item)
                    embed = discord.Embed(title="🎁 Loot Found!", description=f"You found **{item['name']}**\nType: {item['type']} (+{item['val']})", color=item['color'])
                    await interaction.response.edit_message(embed=embed, view=view)
                    return
                    
            await interaction.response.edit_message(embed=self.update_embed("⚔️ Encounter!", "Prepare yourself!"), view=self)

    def start_combat(self, boss=False, name=None):
        self.mode = "COMBAT"
        floor = self.data["floor"]
        name = name or get_monster(floor)
        hp = (floor * 20) + (100 if boss else 0)
        power = (floor * 2) + (10 if boss else 2)
        self.enemy = {"name": name, "hp": hp, "max_hp": hp, "power": power, "intent": random.choice(["Attack", "Heavy Attack", "Defend"])}
        self.combat_log = [f"A wild **{name}** appears!"]
        self.render_main_menu()

    async def resolve_combat(self, interaction, action):
        p_dmg, p_block, p_act, enemy_stunned = 0, 0, "", False
        atk_stat = self.data["atk"]
        
        if "adrenaline" not in self.data: self.data["adrenaline"] = 0
        
        if action == "act_atk":
            p_dmg = atk_stat + random.randint(1, 5)
            if self.data["class"] == "Rogue" and random.random() < 0.2: p_dmg *= 2; p_act = "CRIT!"
            else: p_act = "Attacked"
            self.data["adrenaline"] = min(100, self.data["adrenaline"] + 10)
            
        elif action == "act_def":
            p_block = self.data["def"] * 3
            p_act = "Defended"
            self.data["adrenaline"] = min(100, self.data["adrenaline"] + 20)
            
        elif action == "act_skill":
            cls = self.data["class"]
            if cls == "Warrior": 
                p_dmg = self.data["def"] * 1.5
                enemy_stunned = True
                p_act = "Shield Bashed"
            elif cls == "Mage":
                p_dmg = atk_stat * 3 
                if self.data["hp"] > 5: self.data["hp"] -= 5
                else: self.data["hp"] = 1
                p_act = "Pyroblasted"
            elif cls == "Rogue":
                p_dmg = atk_stat * 1.5
                p_block = 999 
                p_act = "Shadow Stepped"
            self.data["adrenaline"] = min(100, self.data["adrenaline"] + 15)

        elif action == "act_ult":
            cls = self.data["class"]
            self.data["adrenaline"] = 0 
            if cls == "Warrior":
                p_block = 9999
                self.data["hp"] = min(self.data["max_hp"], self.data["hp"] + 50)
                p_act = "🛡️ **TITAN'S WRATH!** (Invincible + Healed 50)"
            elif cls == "Rogue":
                if self.enemy["hp"] < (self.enemy["max_hp"] * 0.4): p_dmg = 9999
                else: p_dmg = atk_stat * 5
                p_act = f"🩸 **EXECUTION!** (Dealt {int(p_dmg)} Dmg)"
            elif cls == "Mage":
                p_dmg = atk_stat * 8
                enemy_stunned = True
                p_act = f"🔮 **CATACLYSM!** (Stunned + {int(p_dmg)} True Dmg)"

        elif action == "act_pot":
            heal = 50
            if "glutton" in self.data["perks"]: heal = 75
            self.data["hp"] = min(self.data["max_hp"], self.data["hp"] + heal)
            self.data["potions"] -= 1
            p_act = "Drank Potion"

        e_dmg = 0
        e_intent = self.enemy["intent"]
        
        if not enemy_stunned:
            if e_intent == "Attack": e_dmg = self.enemy["power"]
            elif e_intent == "Heavy Attack": e_dmg = self.enemy["power"] * 1.5
            elif e_intent == "Defend": p_dmg = int(p_dmg * 0.5) 
        else:
            self.combat_log.append("💫 Enemy Stunned!")

        self.enemy["hp"] -= p_dmg
        if "vampire" in self.data["perks"]: self.data["hp"] = min(self.data["max_hp"], self.data["hp"] + 5)
        
        final_e_dmg = max(0, e_dmg - p_block - (self.data["def"] if action != "act_def" else 0))
        if final_e_dmg > 0:
            if "thorns" in self.data["perks"]: 
                refl = int(final_e_dmg * 0.1)
                self.enemy["hp"] -= refl
            self.data["hp"] -= final_e_dmg
            self.data["adrenaline"] = min(100, self.data["adrenaline"] + 10)
        
        self.combat_log.append(f"You {p_act} ({int(p_dmg)}). Enemy {e_intent} ({int(final_e_dmg)} dmg).")

        b_name, b_data = get_biome(self.data["floor"])
        if b_name == "Sewers" and random.random() < 0.2:
            self.data["hp"] -= int(self.data["max_hp"] * 0.05)
            self.combat_log.append("🤢 Poisoned by gas!")
        elif b_name == "Magma Core" and action == "act_skill":
            self.data["hp"] -= 5
            self.combat_log.append("🔥 Burnt by heat!")

        if self.enemy["hp"] <= 0:
            xp = 20 * (2 if "scholar" in self.data["perks"] else 1)
            gold = 50 * (1.2 if "midas" in self.data["perks"] else 1)
            self.data["xp"] += xp
            self.data["gold"] += int(gold)
            self.data["floor"] += 1
            self.data["adrenaline"] = 0 
            
            # --- SCOIN BOSS REWARD ---
            scoin_bonus = ""
            if (self.data["floor"] - 1) % 10 == 0: # Check if the defeated enemy was a Boss (floor 10, 20...)
                reward_amt = random.randint(2, 5)
                update_balance(self.user_id, reward_amt)
                scoin_bonus = f"\n💰 **BOSS BONUS:** +{reward_amt} Scoins to Casino Balance!"

            req = get_xp_needed(self.data["level"])
            xp_bar = draw_bar(self.data["xp"], req, "🟦") 
            desc = (f"💀 **{self.enemy['name']} Defeated!**\n"
                    f"💰 **+{int(gold)}** Gold\n"
                    f"✨ **+{xp}** XP{scoin_bonus}\n\n"
                    f"**Level {self.data['level']} Progress:**\n"
                    f"{xp_bar} `{self.data['xp']}/{req}`")
            
            if self.data["xp"] >= req:
                self.data["xp"] -= req
                self.data["level"] += 1
                self.data["max_hp"] += 10
                self.data["atk"] += 2
                self.data["def"] += 1
                self.data["hp"] = self.data["max_hp"]
                if self.data["level"] % 5 == 0:
                    await interaction.response.edit_message(embed=self.update_embed("🧬 Mutation!", "Choose a Perk:"), view=PerkSelectView(self.user, self.data))
                    return

            self.mode = "EXPLORE"
            self.enemy = None
            save_tower_data(self.user_id, self.data)
            
            self.render_main_menu() 
            await interaction.response.edit_message(embed=self.update_embed("🏆 Victory!", desc), view=self)
            
        elif self.data["hp"] <= 0:
            self.data["hp"] = 0
            self.data["level"] = 1
            self.data["xp"] = 0
            self.data["class"] = None
            self.data["floor"] = self.data["checkpoint"]
            self.data["gear"] = None 
            self.data["adrenaline"] = 0
            save_tower_data(self.user_id, self.data)
            await interaction.response.edit_message(embed=self.update_embed("💀 YOU DIED", "Level, Stats, and Gear lost.\nPerks & Pets persisted.", THEME_LOSS), view=None)
            
        else:
            self.enemy["intent"] = random.choice(["Attack", "Heavy Attack", "Defend"])
            save_tower_data(self.user_id, self.data)
            self.render_main_menu()
            await interaction.response.edit_message(embed=self.update_embed("⚔️ Combat", "Next round..."), view=self)

class ClassSelectView(View):
    def __init__(self, user_id):
        super().__init__(timeout=60)
        self.user_id = str(user_id)

    async def _set(self, i, cls, hp, atk, def_):
        if str(i.user.id) != self.user_id: return
        d = get_tower_data(i.user.id)
        d.update({"class": cls, "max_hp": hp, "hp": hp, "atk": atk, "def": def_})
        save_tower_data(i.user.id, d)
        view = TowerGameView(i.user)
        embed = view.update_embed("⚔️ The Gates Open", f"You have chosen **{cls}**.\nBegin your ascent.", THEME_PRIMARY)
        await i.response.edit_message(embed=embed, view=view)
        self.stop()

    @discord.ui.button(label="Warrior (Block/Stun)", style=ButtonStyle.danger, emoji="🛡️", row=0)
    async def warrior(self, b, i): await self._set(i, "Warrior", 150, 5, 8)

    @discord.ui.button(label="Rogue (Crit/Dodge)", style=ButtonStyle.success, emoji="🗡️", row=0)
    async def rogue(self, b, i): await self._set(i, "Rogue", 100, 12, 2)

    @discord.ui.button(label="Mage (True Dmg)", style=ButtonStyle.primary, emoji="🔮", row=0)
    async def mage(self, b, i): await self._set(i, "Mage", 120, 8, 3)

    @discord.ui.button(label="Game Guide / Info", style=ButtonStyle.secondary, emoji="ℹ️", row=1)
    async def info(self, button, interaction: Interaction):
        embed = discord.Embed(title="🏰 Shadow Tower Manual", color=THEME_PRIMARY)
        embed.add_field(name="⚔️ Tactical Combat (The Tick System)", value="Enemies display their **Intent** (e.g., 'Heavy Attack'). You must react:\n• **Defend** against Heavy Attacks to reduce damage.\n• **Attack** when they are vulnerable.\n• **Stun/Dodge** using class skills to skip their turn.", inline=False)
        embed.add_field(name="📈 Leveling & Perks", value="• **XP:** Earned by killing monsters. Bosses give double.\n• **Perks:** Every **5 Levels**, you gain a permanent mutation (e.g., *Vampirism* or *Midas Touch*) that stays with you forever.", inline=False)
        embed.add_field(name="💎 Loot 2.0 (Gacha)", value="• **Rarities:** Common < Rare < Epic < Legendary.\n• **Affixes:** Gear can have traits like *Vampiric* (Heal on hit) or *Thorned* (Reflect DMG).\n• **Choice:** You must choose to **Equip** (destroy old gear) or **Salvage** (Get XP/Gold) immediately.", inline=False)
        embed.add_field(name="💀 The Cycle of Death", value="If HP hits 0, you **DIE**.\n• **LOST:** Level, Class, Stats, Current Floor, Gear.\n• **KEPT:** Unlocked Perks, Gold/Scoins, Captured Pets.\n• *Tip: Buy checkpoints with Scoins to respawn safely.*", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

# ==================== CASINO: SLOTS ====================

def generate_slot_result(user, bet):
    user_id = str(user.id)
    update_balance(user_id, -bet)
    emojis = ["🍒", "🍋", "🍇", "💎", "7️⃣", "🔔", "🍊"]
    a, b, c = random.choice(emojis), random.choice(emojis), random.choice(emojis)
    payout = 0
    is_jackpot = False
    
    if a == b == c: 
        payout = bet * 13 
        is_jackpot = True
    elif a == b or b == c or a == c: 
        payout = int(bet * 1.5) 
    
    if payout > 0:
        update_balance(user_id, payout)
        col = THEME_GOLD if payout > bet * 2 else THEME_WIN
        msg = f"🎰 **{a} | {b} | {c}**\n✅ **WIN!** +{payout}"
    else:
        col = THEME_LOSS
        msg = f"🎰 **{a} | {b} | {c}**\n❌ **Lost** {bet}"
        
    embed = discord.Embed(description=msg, color=col)
    if user.display_avatar:
        embed.set_author(name=f"{user.display_name}'s Spin", icon_url=user.display_avatar.url)
    else:
        embed.set_author(name=f"{user.display_name}'s Spin")
    embed.set_footer(text=f"Bet: {bet} Scoins")
    return embed, is_jackpot, payout

class RepeatSpinView(View):
    def __init__(self, user_id, bet):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.bet = bet

    @discord.ui.button(label="Spin Again", style=ButtonStyle.primary, emoji="🔄")
    async def spin_btn(self, button, interaction: Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("🚫 Not your game.", ephemeral=True)
        bal = get_balance(str(self.user_id))
        if bal < self.bet:
            return await interaction.response.send_message(f"❌ Insufficient funds ({bal} < {self.bet}).", ephemeral=True)
        embed, is_jackpot, win_amount = generate_slot_result(interaction.user, self.bet)
        await interaction.response.send_message(embed=embed, view=RepeatSpinView(self.user_id, self.bet), ephemeral=True)
        if is_jackpot:
            target_thread = interaction.guild.get_channel(CASINO_CHANNEL_ID) or await interaction.guild.fetch_channel(CASINO_CHANNEL_ID)
            if target_thread:
                await target_thread.send(f"🚨 **JACKPOT!** 🎰\n**{interaction.user.display_name}** just hit a **3x Match** and won **{win_amount}** Scoins!")

class BetAmountModal(Modal):
    def __init__(self, title, balance, callback_func):
        super().__init__(title=title)
        self.balance = balance
        self.callback_func = callback_func
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

# ==================== CASINO: CHICKEN ====================

class ChickenButton(Button):
    def __init__(self, x, y, view_ref):
        super().__init__(style=ButtonStyle.secondary, label="\u200b", row=y)
        self.x = x
        self.y = y
        self.view_ref = view_ref
        self.idx = y * 5 + x

    async def callback(self, interaction: Interaction):
        if interaction.user.id != self.view_ref.user_id:
            return await interaction.response.send_message("🚫 Not your game.", ephemeral=True)
        await self.view_ref.handle_click(self, interaction)

class ChickenGameView(View):
    def __init__(self, user, bet, bones_count):
        super().__init__(timeout=180)
        self.user_id = user.id
        self.user = user
        self.bet = bet
        self.bones_count = bones_count
        self.grid_size = 20 
        self.bones_indices = set(random.sample(range(self.grid_size), bones_count))
        self.revealed = set()
        self.game_over = False
        self.multiplier = 1.0
        
        for y in range(4):
            for x in range(5):
                self.add_item(ChickenButton(x, y, self))
        
        self.cashout_btn = Button(style=ButtonStyle.success, label="Cash Out", row=4, emoji="💰", disabled=True)
        self.cashout_btn.callback = self.cash_out
        self.add_item(self.cashout_btn)

    def calculate_next_multiplier(self):
        remaining_tiles = self.grid_size - len(self.revealed)
        safe_remaining = remaining_tiles - self.bones_count
        if safe_remaining <= 0: return self.multiplier
        odds = remaining_tiles / safe_remaining
        return self.multiplier * odds * 0.97 

    async def handle_click(self, button, interaction: Interaction):
        if self.game_over: return
        idx = button.idx
        if idx in self.bones_indices:
            self.game_over = True
            update_balance(str(self.user_id), -self.bet)
            button.style = ButtonStyle.danger
            button.emoji = "🦴"
            button.label = ""
            for child in self.children:
                if isinstance(child, ChickenButton):
                    child.disabled = True
                    if child.idx in self.bones_indices and child.idx != idx:
                        child.style = ButtonStyle.secondary
                        child.emoji = "🦴"
            self.cashout_btn.disabled = True
            embed = discord.Embed(title="💥 BONE!", description=f"You hit a bone and lost **{self.bet}** Scoins.", color=THEME_LOSS)
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            self.revealed.add(idx)
            self.multiplier = self.calculate_next_multiplier()
            button.style = ButtonStyle.success
            button.emoji = "🍗"
            button.label = ""
            button.disabled = True
            self.cashout_btn.disabled = False
            self.cashout_btn.label = f"Cash Out ({int(self.bet * self.multiplier)})"
            current_win = int(self.bet * self.multiplier)
            embed = discord.Embed(title="🍗 CHICKEN!", description=f"Multiplier: **{self.multiplier:.2f}x**\nCurrent Win: **{current_win}**", color=THEME_GOLD)
            await interaction.response.edit_message(embed=embed, view=self)

    async def cash_out(self, interaction: Interaction):
        if interaction.user.id != self.user.id: return
        self.game_over = True
        win_amount = int(self.bet * self.multiplier)
        update_balance(str(self.user_id), -self.bet + win_amount)
        for child in self.children: child.disabled = True
        embed = discord.Embed(title="💰 CASHED OUT", description=f"You won **{win_amount}** Scoins!\nMultiplier: **{self.multiplier:.2f}x**", color=THEME_WIN)
        await interaction.response.edit_message(embed=embed, view=self)

class ChickenDifficultySelect(Select):
    def __init__(self, user, bet):
        self.user = user
        self.bet = bet
        options = [
            SelectOption(label="1 Bone (Safe)", value="1", description="Low Risk"),
            SelectOption(label="3 Bones", value="3", description="Medium Risk"),
            SelectOption(label="5 Bones", value="5", description="Classic Risk"),
            SelectOption(label="10 Bones", value="10", description="High Risk"),
            SelectOption(label="15 Bones", value="15", description="Extreme Risk"),
        ]
        super().__init__(placeholder="Select Difficulty (Bones)...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: Interaction):
        if interaction.user.id != self.user.id: return
        bones = int(self.values[0])
        bal = get_balance(str(self.user.id))
        if bal < self.bet:
            return await interaction.response.send_message("❌ Insufficient funds.", ephemeral=True)
        view = ChickenGameView(self.user, self.bet, bones)
        embed = discord.Embed(title="🍗 Chicken Cross", description=f"Bet: {self.bet} | Bones: {bones}\nFind the chickens, avoid the bones!", color=THEME_PRIMARY)
        await interaction.response.edit_message(embed=embed, view=view)

class ChickenSetupView(View):
    def __init__(self, user, bet):
        super().__init__(timeout=60)
        self.add_item(ChickenDifficultySelect(user, bet))

# ==================== CASINO: DICE (HIGH/LOW) ====================

class DiceGameView(View):
    def __init__(self, user, bet):
        super().__init__(timeout=60)
        self.user = user
        self.user_id = user.id
        self.bet = bet
        self.game_over = False

    @discord.ui.button(label="Low (2-6) [x2]", style=ButtonStyle.primary, emoji="⬇️", row=0)
    async def low_btn(self, button, interaction: Interaction):
        await self.process_roll(interaction, "low")

    @discord.ui.button(label="Seven (7) [x5]", style=ButtonStyle.secondary, emoji="7️⃣", row=0)
    async def seven_btn(self, button, interaction: Interaction):
        await self.process_roll(interaction, "seven")

    @discord.ui.button(label="High (8-12) [x2]", style=ButtonStyle.primary, emoji="⬆️", row=0)
    async def high_btn(self, button, interaction: Interaction):
        await self.process_roll(interaction, "high")

    async def process_roll(self, interaction: Interaction, choice):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("🚫 Not your game.", ephemeral=True)
        if self.game_over: return
        bal = get_balance(str(self.user.id))
        if bal < self.bet:
            return await interaction.response.send_message("❌ Insufficient funds.", ephemeral=True)
        
        update_balance(str(self.user_id), -self.bet)
        self.game_over = True
        d1 = random.randint(1, 6)
        d2 = random.randint(1, 6)
        total = d1 + d2
        dice_map = {1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣", 5: "5️⃣", 6: "6️⃣"}
        visual = f"{dice_map[d1]} + {dice_map[d2]} = **{total}**"
        
        won = False
        payout = 0
        if choice == "low" and total < 7:
            won = True
            payout = int(self.bet * 2)
        elif choice == "high" and total > 7:
            won = True
            payout = int(self.bet * 2)
        elif choice == "seven" and total == 7:
            won = True
            payout = int(self.bet * 5)
        
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
        self.user = user
        self.bet = bet
    async def callback(self, interaction: Interaction):
        if interaction.user.id != self.user.id: return
        bal = get_balance(str(self.user.id))
        if bal < self.bet: return await interaction.response.send_message("❌ Broke.", ephemeral=True)
        await interaction.response.send_message(f"🎲 **High/Low Dice**\nBet: **{self.bet}**", view=DiceGameView(self.user, self.bet), ephemeral=True)

# ==================== CASINO: DASHBOARD ====================

class DuelAcceptView(View):
    def __init__(self, p1, p2, amount):
        super().__init__(timeout=60)
        self.p1 = p1
        self.p2 = p2
        self.amount = amount
    @discord.ui.button(label="ACCEPT DUEL", style=ButtonStyle.danger, emoji="⚔️")
    async def accept(self, button, interaction: Interaction):
        if interaction.user.id != self.p2.id: return
        if get_balance(str(self.p1.id)) < self.amount or get_balance(str(self.p2.id)) < self.amount:
            return await interaction.response.send_message("❌ Someone went broke during the wait.", ephemeral=True)
        update_balance(str(self.p1.id), -self.amount)
        update_balance(str(self.p2.id), -self.amount)
        winner = random.choice([self.p1, self.p2])
        loser = self.p2 if winner == self.p1 else self.p1
        win_amt = self.amount * 2
        update_balance(str(winner.id), win_amt)
        embed = discord.Embed(title="🩸 DUEL FINISHED", description=f"🏆 **Winner:** {winner.mention}\n💀 **Loser:** {loser.mention}\n💰 **Won:** {win_amt} Scoins", color=THEME_GOLD)
        self.clear_items()
        await interaction.response.edit_message(view=self, embed=embed)

class ShopSelect(Select):
    def __init__(self):
        options = [
            SelectOption(label="Ban Haste", description="10,000 Scoins: Publicly banish Haste", value="ban_haste", emoji="🔨")
        ]
        super().__init__(placeholder="Select item to buy...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: Interaction):
        if not is_gambler(interaction.user):
            return await interaction.response.send_message("⛔ Restricted. Missing required role.", ephemeral=True)
        
        user_id = str(interaction.user.id)
        bal = get_balance(user_id)
        val = self.values[0]
        
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
        last = user_data["last_pull"]
        now = time.time()
        if now - last < (SCOIN_COOLDOWN_HOURS * 3600):
            remaining = (SCOIN_COOLDOWN_HOURS * 3600) - (now - last)
            hours = int(remaining // 3600)
            mins = int((remaining % 3600) // 60)
            return await interaction.response.send_message(f"⏳ **Cooldown:** {hours}h {mins}m.", ephemeral=True)
        update_balance(user_id, SCOIN_PULL_AMOUNT)
        scoins_db[user_id]["last_pull"] = now
        _save_scoins()
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

        async def modal_callback(inter, amount):
            await inter.response.send_message("🦴 **Select Difficulty (Bones)**", view=ChickenSetupView(inter.user, amount), ephemeral=True)

        await interaction.response.send_modal(BetAmountModal("Chicken Bet", bal, modal_callback))

    @discord.ui.button(label="Dice", style=ButtonStyle.primary, emoji="🎲", row=0)
    async def dice(self, button, interaction: Interaction):
        if interaction.channel.id != CASINO_CHANNEL_ID: return await interaction.response.send_message(f"❌ Go to <#{CASINO_CHANNEL_ID}>.", ephemeral=True)
        if not is_gambler(interaction.user): return await interaction.response.send_message("⛔ Restricted.", ephemeral=True)
        bal = get_balance(str(interaction.user.id))

        async def modal_callback(inter, amount):
            await inter.response.send_message(f"🎲 **High/Low Dice**\nBet: **{amount}**", view=DiceGameView(inter.user, amount), ephemeral=True)

        await interaction.response.send_modal(BetAmountModal("Dice Bet", bal, modal_callback))

    @discord.ui.button(label="Duel", style=ButtonStyle.danger, emoji="⚔️", row=1)
    async def duel(self, button, interaction: Interaction):
        if not is_gambler(interaction.user): return await interaction.response.send_message("⛔ Restricted.", ephemeral=True)
        await interaction.response.send_message("⚔️ To duel, use: `/duel @user [amount]`", ephemeral=True)
    @discord.ui.button(label="Shop", style=ButtonStyle.secondary, emoji="🛒", row=1)
    async def shop(self, button, interaction: Interaction):
        if not is_gambler(interaction.user): return await interaction.response.send_message("⛔ Restricted.", ephemeral=True)
        view = View()
        view.add_item(ShopSelect())
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
        self.vc = vc
        self.add_item(TextInput(label="New VC Name", placeholder="Enter name...", required=True, max_length=50))
    async def callback(self, interaction: Interaction):
        try:
            await self.vc.edit(name=self.children[0].value)
            await interaction.response.send_message(f"✅ Renamed.", ephemeral=True)
        except Exception as e: await interaction.response.send_message(f"❌ Failed: {e}", ephemeral=True)

class KickMemberDropdown(Select):
    def __init__(self, vc, members):
        options = [SelectOption(label=m.display_name, value=str(m.id)) for m in members]
        super().__init__(placeholder="Select member to kick...", options=options, min_values=1, max_values=1)
        self.vc = vc
    async def callback(self, interaction: Interaction):
        try:
            member = self.vc.guild.get_member(int(self.values[0]))
            if member and member in self.vc.members:
                await member.move_to(None)
                await interaction.response.send_message(f"👢 Kicked {member.display_name}.", ephemeral=True)
            else: await interaction.response.send_message("⚠️ Member not found.", ephemeral=True)
        except Exception as e: await interaction.response.send_message(f"❌ Failed: {e}", ephemeral=True)

class KickMemberView(View):
    def __init__(self, vc, members):
        super().__init__(timeout=30)
        self.add_item(KickMemberDropdown(vc, members))

class RoleRestrictSelect(Select):
    def __init__(self, vc, creator):
        self.vc = vc
        self.creator = creator
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
        self.vc = vc
        self.creator = creator
        try: self.add_item(RoleRestrictSelect(vc, creator))
        except: pass
    async def _check(self, i):
        if i.user.id == self.creator.id: return True
        if i.data.get("custom_id") == "delete_vc" and any(r.name == ADMIN_ROLE_NAME or r.id == ROLE_ADMIN_ID for r in i.user.roles): return True
        await i.response.send_message("🚫 Only creator.", ephemeral=True); return False
    @discord.ui.button(label="🔒 Lock", style=ButtonStyle.danger, custom_id="lock_vc")
    async def lock(self, button, i):
        if not await self._check(i): return
        await self.vc.set_permissions(i.guild.default_role, connect=False)
        await i.response.send_message("🔒 Locked.", ephemeral=True)
    @discord.ui.button(label="🔓 Unlock", style=ButtonStyle.success, custom_id="unlock_vc")
    async def unlock(self, button, i):
        if not await self._check(i): return
        await self.vc.set_permissions(i.guild.default_role, connect=True)
        await i.response.send_message("🔓 Unlocked.", ephemeral=True)
    @discord.ui.button(label="❌ Delete", style=ButtonStyle.red, custom_id="delete_vc")
    async def delete(self, button, i):
        if not await self._check(i): return
        await self.vc.delete()
        await i.response.send_message("🗑️ Deleted.", ephemeral=True)
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

# ==================== BOT CORE ====================

class ShadowSynBot(discord.Bot):
    def __init__(self):
        super().__init__(intents=discord.Intents.all())
        self.audio_queues = {}

bot = ShadowSynBot()

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    _load_persistence()
    for guild in bot.guilds:
        await _prime_invites_cache(guild)

@bot.event
async def on_guild_join(guild):
    await _prime_invites_cache(guild)

# ##### WELCOME / ARRIVALS SYSTEM #####
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
        # --- SEND TO ARRIVALS CHANNEL ---
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
    # Get the departures channel
    channel = member.guild.get_channel(DEPARTURES_THREAD_ID) or await member.guild.fetch_channel(DEPARTURES_THREAD_ID)
    if not channel: return

    # Default to "Member Left"
    title = "👋 Member Left"
    description = f"{member.mention} left the server."
    color = THEME_LOSS 
    footer_text = f"ID: {member.id}"
    
    now = utcnow()
    
    # Account Age
    age_str = format_age(member.created_at)
    joined_str = format_age(member.joined_at)

    # Audit Log Check for Kick (Last 10 seconds)
    try:
        async for entry in member.guild.audit_logs(limit=1, action=discord.AuditLogAction.kick):
            if entry.target.id == member.id:
                if (now - entry.created_at).total_seconds() < 10:
                    title = "🥾 Member Kicked"
                    description = f"{member.mention} kicked the server.\nBy: **{entry.user.name}** ({entry.user.display_name})"
                    color = 0xF04747 
                    break
    except: pass

    # Construct Embed
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
    # --- JTC LOGIC ---
    if after.channel and after.channel.id == JOIN_TO_CREATE_CHANNEL_ID:
        try:
            cat = get(guild.categories, id=VC_CATEGORY_ID) or after.channel.category
            new_vc = await guild.create_voice_channel(
                name=_limit_channel_name(_to_sans_bold_italic(f"{member.display_name}'s Room")), 
                category=cat, 
                bitrate=VC_DEFAULT_BITRATE
            )
            # EXPLICITLY GRANT SPEAK PERMS
            await new_vc.set_permissions(member, connect=True, speak=True)
            
            active_temp_vcs.add(new_vc.id)
            _save_active_vcs(active_temp_vcs)
            await member.move_to(new_vc)
            # CALL RESTORED FUNCTION
            asyncio.create_task(send_control_panel(new_vc, member))
        except: traceback.print_exc()
    # --- CLEANUP LOGIC ---
    if before.channel and before.channel.id in active_temp_vcs and len(before.channel.members) == 0:
        try: await before.channel.delete(); active_temp_vcs.discard(before.channel.id); _save_active_vcs(active_temp_vcs)
        except: pass
    
    # ##### ALERT / AUDIT SYSTEM (NO PINGS) #####
    if member.bot: return
    # --- SEND TO ALERT CHANNEL ---
    target, _ = await resolve_target(bot, DEFAULT_AUDIT_THREAD_ID)
    if not target: return

    msg = None
    
    # 1. Join/Leave/Move
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

    # 2. Self Mute/Deafen (Granular Check)
    elif before.self_mute != after.self_mute:
        status = "muted" if after.self_mute else "unmuted"
        msg = f"🎤 **{member.display_name}** **self-{status}**."
    elif before.self_deaf != after.self_deaf:
        status = "deafened" if after.self_deaf else "undeafened"
        msg = f"🎧 **{member.display_name}** **self-{status}**."

    # 3. Server Mute/Deafen (Admin Abilities Check)
    elif before.mute != after.mute:
        status = "server-muted" if after.mute else "server-unmuted"
        entry = await _find_audit_action(guild, discord.AuditLogAction.member_update, member.id)
        actor = f"**{entry.user.display_name}**" if entry else "Unknown Admin"
        msg = f"🙉 **{member.display_name}** was **{status}** by {actor}."
    elif before.deaf != after.deaf:
        status = "server-deafened" if after.deaf else "server-undeafened"
        entry = await _find_audit_action(guild, discord.AuditLogAction.member_update, member.id)
        actor = f"**{entry.user.display_name}**" if entry else "Unknown Admin"
        msg = f"🙉 **{member.display_name}** was **{status}** by {actor}."

    # 4. Stream/Video
    elif before.self_stream != after.self_stream:
        status = "started" if after.self_stream else "stopped"
        msg = f"📺 **{member.display_name}** **{status} streaming**."
    elif before.self_video != after.self_video:
        status = "enabled" if after.self_video else "disabled"
        msg = f"📷 **{member.display_name}** **{status} camera**."

    if msg:
        try: await target.send(msg)
        except: pass

# ==================== COMMANDS ====================

@bot.slash_command(name="speak", description="Text to Speech (Auto-Translates)")
@dj_or_admin()
async def speak(ctx, text: str, language: Option(str, choices=LANG_CHOICES, default="English")):
    vc = await ensure_voice_simple(ctx)
    if not vc: return

    try:
        # 1. Resolve Language Code
        lang_code = LANG_CODES.get(language, 'en')
        
        # 2. Translate if not English
        text_to_speak = text
        if lang_code != 'en':
            try:
                # Note: Assuming standard googletrans. If it fails, falls back to text.
                translation = await bot.loop.run_in_executor(None, lambda: translator.translate(text, dest=lang_code))
                text_to_speak = translation.text
            except Exception as tr_err:
                print(f"Translation Error: {tr_err}")
                text_to_speak = text 

        # 3. Notify User
        await safe_reply(ctx, f"🗣️ **{language}:** {text_to_speak}", ephemeral=True)

        # LOGGING
        log_ch = bot.get_channel(SPEAK_LOG_THREAD_ID)
        if log_ch:
            try: await log_ch.send(f"🗣️ **{ctx.author.display_name}** ({language}): {text_to_speak}")
            except: pass

        # 4. Generate Audio
        tts = gTTS(text=text_to_speak, lang=lang_code)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
            tts.save(fp.name)
            temp_path = fp.name
        
        # 5. Play
        vc.play(discord.FFmpegPCMAudio(temp_path), after=lambda e: os.remove(temp_path))

    except Exception as e:
        await safe_reply(ctx, f"❌ Error: {e}", ephemeral=True)

@bot.slash_command(name="haste", description="Random Haste Fact")
async def haste(ctx):
    if not active_haste_facts:
        return await safe_reply(ctx, "No facts yet.")
    fact = random.choice(active_haste_facts)
    await safe_reply(ctx, f"🍌 **Fact:** {fact}")

@bot.slash_command(name="morehaste", description="Add Haste Fact")
@admin_only()
async def morehaste(ctx, fact: str):
    active_haste_facts.append(fact)
    _save_haste_facts()
    await safe_reply(ctx, "✅ Added.")

@bot.slash_command(name="gamble", description="Open Casino")
async def gamble(ctx):
    # 1. CHANNEL LOCK & PRIVACY
    if ctx.channel.id != CASINO_CHANNEL_ID:
        return await safe_reply(ctx, f"❌ Go to <#{CASINO_CHANNEL_ID}> to gamble.", ephemeral=True)

    if not is_gambler(ctx.author): return await safe_reply(ctx, "⛔ Restricted.", ephemeral=True)
    embed = discord.Embed(title="🎰 ShadowSyn Casino", description="Welcome.", color=THEME_PRIMARY)
    embed.set_footer(text=f"Balance: {get_balance(str(ctx.author.id))}")
    # Ephemeral Dashboard (Hidden)
    await safe_reply(ctx, embed=embed, view=CasinoDashboard(), ephemeral=True)

@bot.slash_command(name="duel", description="Duel user")
async def duel(ctx, opponent: discord.Member, amount: str):
    if not is_gambler(ctx.author): return await safe_reply(ctx, "⛔ Restricted.", ephemeral=True)
    if amount == "all": bet = get_balance(str(ctx.author.id))
    else: bet = int(amount)
    embed = discord.Embed(title="⚔️ DUEL", description=f"{ctx.author.mention} vs {opponent.mention}\nPot: {bet*2}", color=discord.Color.red())
    await safe_reply(ctx, content=opponent.mention, embed=embed, view=DuelAcceptView(ctx.author, opponent, bet))

@bot.slash_command(name="wallet", description="Check balance")
async def wallet(ctx, user: Option(discord.User, required=False)):
    if not is_gambler(ctx.author): return await safe_reply(ctx, "⛔ Restricted.", ephemeral=True)
    t = user or ctx.author
    await safe_reply(ctx, f"💳 {t.display_name}: {get_balance(str(t.id))} Scoins")

@bot.slash_command(name="give_scoins", description="Owner Only")
@owner_only()
async def give_scoins(ctx, user: discord.Member, amount: int):
    update_balance(str(user.id), amount)
    await safe_reply(ctx, f"✅ Done. New balance: {get_balance(str(user.id))}", ephemeral=True)

@bot.slash_command(name="tower", description="Play The Shadow Tower")
async def tower(ctx):
    if ctx.channel.id != CASINO_CHANNEL_ID:
        return await safe_reply(ctx, f"❌ Go to <#{CASINO_CHANNEL_ID}>.", ephemeral=True)
    
    data = get_tower_data(ctx.author.id)
    
    if not data["class"]:
        return await safe_reply(ctx, "🛡️ **Choose your Class:**", view=ClassSelectView(ctx.author.id), ephemeral=True)

    view = TowerGameView(ctx.author)
    embed = view.update_embed("Welcome to the **Shadow Tower**.\nHow high can you climb?", THEME_PRIMARY)
    await safe_reply(ctx, embed=embed, view=view, ephemeral=True)

@bot.slash_command(name="tower_top", description="Tower Leaderboard")
async def tower_top(ctx):
    sorted_users = sorted(tower_db.items(), key=lambda x: x[1].get("max_floor", 1), reverse=True)
    msg = "**🏰 Tower Legends**\n"
    for i, (uid, data) in enumerate(sorted_users[:10]):
        try: user = await bot.fetch_user(int(uid)); name = user.display_name
        except: name = "Unknown Warrior"
        cls = data.get("class", "Novice")
        lvl = data.get("level", 1)
        msg += f"{i+1}. **{name}** ({cls} Lvl {lvl}) — Floor {data.get('max_floor', 1)}\n"
    await safe_reply(ctx, msg)

@bot.slash_command(name="revive", description="Revive in Tower (5000 Scoins)")
async def revive(ctx):
    if ctx.channel.id != CASINO_CHANNEL_ID: return await safe_reply(ctx, "❌ Wrong channel.", ephemeral=True)
    
    user_id = str(ctx.author.id)
    data = get_tower_data(ctx.author.id)
    
    if data["hp"] > 0:
        return await safe_reply(ctx, "❌ You are not dead.", ephemeral=True)
        
    cost = 5000
    bal = get_balance(user_id)
    if bal < cost:
        return await safe_reply(ctx, f"❌ You need {cost} Scoins to cheat death.", ephemeral=True)
        
    update_balance(user_id, -cost)
    data["hp"] = int(data["max_hp"] / 2) # Revive with half HP
    save_tower_data(user_id, data)
    
    await safe_reply(ctx, "💎 **HEROES NEVER DIE!**\nYou have been revived. Use `/tower` to continue.", ephemeral=True)

@bot.slash_command(name="respawn", description="Give up and return to Checkpoint")
async def respawn(ctx):
    if ctx.channel.id != CASINO_CHANNEL_ID: return await safe_reply(ctx, "❌ Wrong channel.", ephemeral=True)
    
    user_id = str(ctx.author.id)
    data = get_tower_data(ctx.author.id)
    
    if data["hp"] > 0: return await safe_reply(ctx, "❌ You are alive.", ephemeral=True)
    
    # Reset
    data["floor"] = data["checkpoint"]
    data["hp"] = data["max_hp"]
    data["atk"] = 0
    data["def"] = 0
    data["potions"] = 0
    
    save_tower_data(user_id, data)
    
    await safe_reply(ctx, f"💀 You accepted your fate.\nRespawned at Floor {data['floor']}. Gear lost.", ephemeral=True)

@bot.slash_command(name="pets", description="View your captured shadows")
async def pets(ctx):
    data = get_tower_data(ctx.author.id)
    if not data["pets"]:
        return await safe_reply(ctx, "🕸️ You haven't captured any shadows yet.")
    
    unique_pets = list(set(data["pets"]))
    desc = "\n".join([f"• {p}" for p in unique_pets])
    
    embed = discord.Embed(title=f"🕸️ {ctx.author.display_name}'s Shadows", description=desc, color=THEME_PRIMARY)
    embed.set_footer(text=f"Total Captured: {len(unique_pets)}")
    await safe_reply(ctx, embed=embed)

@bot.slash_command(name="silence", description="Pay 2000 Scoins to Timeout someone for 60s")
async def silence(ctx, user: discord.Member):
    if ctx.channel.id != CASINO_CHANNEL_ID: return await safe_reply(ctx, "❌ Wrong channel.", ephemeral=True)
    cost = 2000
    bal = get_balance(str(ctx.author.id))
    if bal < cost: return await safe_reply(ctx, f"❌ You need {cost} Scoins.", ephemeral=True)
    if user.guild_permissions.administrator: return await safe_reply(ctx, "❌ You cannot silence an Admin.", ephemeral=True)
    update_balance(str(ctx.author.id), -cost)
    try:
        await user.timeout_for(timedelta(seconds=60), reason=f"Paid Silence by {ctx.author.display_name}")
        await safe_reply(ctx, f"🤫 **Shhh!** {user.mention} has been silenced for 60s.")
    except Exception as e:
        update_balance(str(ctx.author.id), cost)
        await safe_reply(ctx, f"❌ Failed: {e}", ephemeral=True)

# --- CUSTOM EMBEDS (SIMPLE FORM) ---
class EasyEmbedModal(Modal):
    def __init__(self, channel, edit_msg=None):
        super().__init__(title="Edit Embed" if edit_msg else "Create Custom Embed")
        self.channel = channel
        self.edit_msg = edit_msg

        # Pre-fill data if editing
        pre_title = edit_msg.embeds[0].title if edit_msg and edit_msg.embeds else ""
        pre_desc = edit_msg.embeds[0].description if edit_msg and edit_msg.embeds else ""
        pre_foot = edit_msg.embeds[0].footer.text if edit_msg and edit_msg.embeds and edit_msg.embeds[0].footer else ""
        pre_col = str(hex(edit_msg.embeds[0].color.value)).replace("0x", "#") if edit_msg and edit_msg.embeds and edit_msg.embeds[0].color else ""

        self.add_item(TextInput(label="Title", placeholder="Embed Title...", value=pre_title, required=True))
        self.add_item(TextInput(label="Description", placeholder="Main content...", value=pre_desc, style=discord.InputTextStyle.paragraph, required=True))
        self.add_item(TextInput(label="Footer (Optional)", placeholder="Small text at bottom...", value=pre_foot, required=False))
        self.add_item(TextInput(label="Color (Hex)", placeholder="#2B0B35", value=pre_col, required=False))

    async def callback(self, interaction: Interaction):
        title = self.children[0].value
        desc = self.children[1].value
        footer = self.children[2].value
        color_raw = self.children[3].value
        
        # Default Color if blank or invalid
        try: 
            if color_raw: color = int(color_raw.replace("#", ""), 16)
            else: color = THEME_PRIMARY
        except: color = THEME_PRIMARY

        embed = discord.Embed(title=title, description=desc, color=color)
        if footer: embed.set_footer(text=footer)
        
        if self.edit_msg:
            await self.edit_msg.edit(embed=embed)
            await interaction.response.send_message("✅ Embed Updated!", ephemeral=True)
        else:
            await self.channel.send(embed=embed)
            await interaction.response.send_message("✅ Embed Sent!", ephemeral=True)

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
        if msg.author != ctx.bot.user:
            return await ctx.respond("❌ I can only edit my own messages.", ephemeral=True)
        await ctx.send_modal(EasyEmbedModal(target_channel, edit_msg=msg))
    except Exception as e:
        await ctx.respond(f"❌ Error finding message: {e}", ephemeral=True)

# --- MUSIC ---
def check_queue(gid, vc):
    if gid in bot.audio_queues and bot.audio_queues[gid]:
        url, title = bot.audio_queues[gid].popleft()
        asyncio.run_coroutine_threadsafe(play_track(vc, url, title, gid), bot.loop)

async def play_track(vc, url, title, gid):
    try:
        player = await YTDLSource.from_url(url, loop=bot.loop, stream=True)
        vc.play(player, after=lambda e: check_queue(gid, vc))
    except: pass

@bot.slash_command(name="play")
@dj_or_admin()
async def play(ctx, search: str):
    await safe_defer(ctx)
    vc = await ensure_voice_simple(ctx)
    if not vc: return
    
    # 1. Search for 5 results
    info = await bot.loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(YTDL_SEARCH_OPTIONS).extract_info(f"ytsearch5:{search}", download=False))
    if not info or 'entries' not in info or not info['entries']:
        return await safe_reply(ctx, "❌ No results found.", ephemeral=True)
    
    entries = info['entries']
    
    # 2. Present Dropdown
    view = MusicSelectionView(entries, ctx, vc)
    await safe_reply(ctx, "🔎 **Select a track:**", view=view)

@bot.slash_command(name="queue")
async def queue(ctx):
    if ctx.guild.id not in bot.audio_queues or not bot.audio_queues[ctx.guild.id]:
        return await safe_reply(ctx, "Queue is empty.")
    lines = [f"{i+1}. {title}" for i, (url, title) in enumerate(bot.audio_queues[ctx.guild.id])]
    await safe_reply(ctx, "\n".join(lines[:10]))

@bot.slash_command(name="skip")
@dj_or_admin()
async def skip(ctx):
    if ctx.guild.voice_client: ctx.guild.voice_client.stop(); await safe_reply(ctx, "⏭️ Skipped.")

@bot.slash_command(name="stop")
@dj_or_admin()
async def stop(ctx):
    if ctx.guild.id in bot.audio_queues: bot.audio_queues[ctx.guild.id].clear()
    if ctx.guild.voice_client: ctx.guild.voice_client.stop(); await safe_reply(ctx, "⏹️ Stopped.")

@bot.slash_command(name="join")
@dj_or_admin()
async def join(ctx):
    await ensure_voice_simple(ctx); await safe_reply(ctx, "✅ Joined.")

# --- RUN ---
if __name__ == "__main__":
    bot.run(TOKEN)
