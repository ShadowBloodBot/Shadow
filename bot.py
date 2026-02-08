# bot.py — ShadowSyn (Master: v6.1 - Full UI RPG)
#
# === FEATURES ===
# [x] 🎒 UI INVENTORY: No commands. Click "Bag" -> Use Dropdown to Equip.
# [x] ⚔️ RPG STATS: STR (Dmg), VIT (HP), AGI (Crit), INT (Gold/Heal).
# [x] 🛒 SHOP: Auto-triggers every 5 floors. Sell/Buy buttons.
# [x] 💎 LOOT: "Diablo-style" generation (Rarity + Stats).
# [x] 🛡️ STABILITY: All crash fixes included.
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

VANITY_INVITE   = "https://discord.gg/shadowsyn"
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
        except: active_haste_facts = []

    if SCOINS_STORE.exists():
        try: scoins_db = json.loads(SCOINS_STORE.read_text())
        except: scoins_db = {}

    if TOWER_STORE.exists():
        try: tower_db = json.loads(TOWER_STORE.read_text())
        except: tower_db = {}

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

# ==================== SHADOW TOWER 6.1 (FULL UI OVERHAUL) ====================

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
    # Base Stats
    total = data["stats"].copy()
    
    # Add Equipment Stats
    for slot in ITEM_SLOTS:
        item = data["equipment"].get(slot)
        if item:
            for stat, val in item.get("stats", {}).items():
                total[stat] = total.get(stat, 0) + val
    
    # Derived Stats
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
    
    # Stat Budget
    budget = floor + ({"Common": 2, "Uncommon": 5, "Rare": 10, "Epic": 20, "Legendary": 40}[rarity])
    
    stats = {}
    possible_stats = ["str", "vit", "agi", "int"]
    
    # Assign stats
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

# --- RPG VIEWS ---

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
        await interaction.response.edit_message(embed=discord.Embed(title="🎒 Looted", description=f"You picked up **{self.item['name']}**.", color=THEME_WIN), view=None)
        
        await asyncio.sleep(1)
        view = TowerGameView(self.user)
        # Assuming last message is editable or we send new one. For smooth UX we send ephemeral confirm then user acts on next turn.
        # Actually better UX: Update original message to "Looted" then show next menu.
        await interaction.followup.send(embed=view.update_embed("Ready", "Continue climbing."), view=view, ephemeral=True)

    @discord.ui.button(label="Salvage (Gold)", style=ButtonStyle.secondary, emoji="💰")
    async def salvage(self, button, interaction):
        if interaction.user.id != self.user.id: return
        val = self.item["value"]
        self.data["gold"] += val
        save_tower_data(self.user.id, self.data)
        await interaction.response.edit_message(embed=discord.Embed(title="🔨 Salvaged", description=f"You gained **{val} Gold**.", color=THEME_GOLD), view=None)
        
        await asyncio.sleep(1)
        view = TowerGameView(self.user)
        await interaction.followup.send(embed=view.update_embed("Ready", "Continue climbing."), view=view, ephemeral=True)

class TowerGameView(View):
    def __init__(self, user):
        super().__init__(timeout=300)
        self.user = user
        self.user_id = str(user.id)
        self.data = get_tower_data(user.id)
        self.stats = get_total_stats(self.data)
        self.mode = "EXPLORE" # EXPLORE, COMBAT, INVENTORY, SHOP
        self.enemy = None
        self.combat_log = []
        
        # Ensure HP capped
        self.data["hp"] = min(self.data["hp"], self.stats["max_hp"])
        
        self.render_main_menu()

    def update_embed(self, title, desc, color=THEME_PRIMARY):
        if self.mode == "INVENTORY":
            return self.get_inventory_embed()
        elif self.mode == "SHOP":
            return self.get_shop_embed()

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
            
            # THE BAG BUTTON
            gear_btn = Button(label="Bag/Gear", style=ButtonStyle.secondary, emoji="🎒", row=1)
            gear_btn.callback = lambda i: self.wrapper(i, "nav_gear")
            self.add_item(gear_btn)

        elif self.mode == "INVENTORY":
            # Equip Select
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
        val = interaction.data["values"][0]
        to_equip = next((i for i in self.data["inventory"] if i["id"] == val), None)
        if to_equip:
            slot = to_equip["slot"]
            current = self.data["equipment"].get(slot)
            if current: self.data["inventory"].append(current)
            self.data["equipment"][slot] = to_equip
            self.data["inventory"].remove(to_equip)
            save_tower_data(self.user.id, self.data)
            self.stats = get_total_stats(self.data) # Update stats immediately
            await interaction.response.edit_message(embed=self.update_embed("Gear Updated", ""), view=self)
            # Re-render to update dropdown
            self.render_main_menu()
            await interaction.edit_original_response(view=self)

    async def wrapper(self, interaction, cid):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("🚫 Not your session.", ephemeral=True)
        try:
            await interaction.response.defer()
            if "act_" in cid: await self.resolve_combat(interaction, cid)
            elif cid == "nav_gear":
                self.mode = "INVENTORY"
                self.render_main_menu()
                await interaction.edit_original_response(embed=self.update_embed("Inventory", ""), view=self)
            elif cid == "nav_back":
                self.mode = "EXPLORE"
                self.render_main_menu()
                await interaction.edit_original_response(embed=self.update_embed("Exploration", "Back to the tower."), view=self)
            elif "shop_" in cid: await self.resolve_shop(interaction, cid)
            else: await self.resolve_nav(interaction, cid)
        except Exception as e:
            traceback.print_exc()

    async def resolve_shop(self, interaction, cid):
        if cid == "shop_buy":
            if self.data["gold"] >= 50:
                self.data["gold"] -= 50
                self.data["potions"] += 1
                save_tower_data(self.user.id, self.data)
                await interaction.edit_original_response(embed=self.update_embed("Shop", "Bought potion."), view=self)
            else:
                await interaction.followup.send("❌ Not enough gold.", ephemeral=True)
        elif cid == "shop_sell":
            total = sum([i["value"] for i in self.data["inventory"]])
            count = len(self.data["inventory"])
            self.data["inventory"] = []
            self.data["gold"] += total
            save_tower_data(self.user.id, self.data)
            await interaction.edit_original_response(embed=self.update_embed("Shop", f"Sold {count} items for {total}g."), view=self)
        elif cid == "shop_leave":
            self.mode = "EXPLORE"
            self.data["floor"] += 1 # Advance floor after shopping
            self.render_main_menu()
            await interaction.edit_original_response(embed=self.update_embed("Exploration", "Moving on..."), view=self)

    async def resolve_nav(self, interaction, cid):
        if cid == "nav_rest":
            if self.data["gold"] >= 100:
                self.data["gold"] -= 100
                self.data["hp"] = self.stats["max_hp"]
                save_tower_data(self.user.id, self.data)
                await interaction.edit_original_response(embed=self.update_embed("💤 Rested", "HP Fully Restored."), view=self)
            else:
                await interaction.followup.send("❌ Need 100 Gold.", ephemeral=True)
        
        elif cid == "nav_climb":
            # Shop Logic
            if self.data["floor"] % 5 == 0 and self.data["floor"] > 1:
                self.mode = "SHOP"
                self.render_main_menu()
                await interaction.edit_original_response(embed=self.update_embed("Shop", "Safe zone reached."), view=self)
                return

            roll = random.randint(1, 100)
            if roll <= 30: # Loot
                item = generate_rpg_item(self.data["floor"])
                view = LootDropView(self.user, item)
                stats_str = "\n".join([f"• **{k.upper()}:** +{v}" for k,v in item['stats'].items()])
                desc = f"You found a chest!\n\n**{item['name']}**\n{stats_str}\n\n*Value: {item['value']} Gold*"
                color = RARITY_COLORS.get(item['rarity'], 0xFFFFFF)
                embed = discord.Embed(title="🎁 Treasure Found!", description=desc, color=color)
                await interaction.edit_original_response(embed=embed, view=view)
            else: # Combat
                self.start_combat()
                await interaction.edit_original_response(embed=self.update_embed("⚔️ Encounter!", "Prepare yourself!"), view=self)

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
            if random.randint(1, 100) <= self.stats["crit_chance"]:
                dmg = int(dmg * 1.5); self.combat_log.append(f"💥 CRIT! You deal {dmg} dmg.")
            else: self.combat_log.append(f"🗡️ You deal {dmg} dmg.")
            p_dmg = dmg
            self.data["adrenaline"] = min(100, self.data["adrenaline"] + 10)
        elif action == "act_def":
            p_block = self.stats["vit"]; self.combat_log.append(f"🛡️ Block raised ({p_block}).")
            self.data["adrenaline"] = min(100, self.data["adrenaline"] + 5)
        elif action == "act_ult":
            p_dmg = self.stats["atk"] * 3; self.combat_log.append(f"⚡ LIMIT BREAK! {p_dmg} DMG!")
            self.data["adrenaline"] = 0
        elif action == "act_pot":
            heal = 50 + (self.stats["int"] * 2)
            self.data["hp"] = min(self.stats["max_hp"], self.data["hp"] + heal)
            self.data["potions"] -= 1
            self.combat_log.append(f"🧪 Healed +{heal} HP.")

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
            xp_gain = 20 + self.data["floor"]
            gold_gain = 10 + (self.data["floor"] * 2)
            self.data["xp"] += xp_gain; self.data["gold"] += gold_gain
            self.data["floor"] += 1
            self.mode = "EXPLORE"
            self.enemy = None
            req = self.data["level"] * 100
            if self.data["xp"] >= req:
                self.data["xp"] -= req; self.data["level"] += 1
                self.data["stats"]["str"] += 1; self.data["stats"]["vit"] += 1
                self.combat_log.append("✨ LEVEL UP! Stats Increased.")
            save_tower_data(self.user_id, self.data)
            self.render_main_menu()
            await interaction.edit_original_response(embed=self.update_embed("Victory!", f"Enemy Defeated.\n+{xp_gain} XP | +{gold_gain} Gold"), view=self)
        elif self.data["hp"] <= 0:
            self.data["hp"] = 0
            lost_gold = int(self.data["gold"] / 2)
            self.data["gold"] -= lost_gold
            self.data["floor"] = max(1, self.data["floor"] - 5)
            save_tower_data(self.user_id, self.data)
            await interaction.edit_original_response(embed=self.update_embed("💀 Defeated", f"You fainted.\nLost {lost_gold} Gold.\nFloor reduced."), view=None)
        else:
            save_tower_data(self.user_id, self.data)
            await interaction.edit_original_response(embed=self.update_embed("Combat", "Fighting..."), view=self)

# ==================== COMMANDS ====================

@bot.slash_command(name="tower", description="Play RPG Tower")
async def tower(ctx):
    view = TowerGameView(ctx.author)
    await safe_reply(ctx, embed=view.update_embed("Tower Entrance", "Begin your journey."), view=view, ephemeral=True)

@bot.slash_command(name="gamble", description="Open Casino")
async def gamble(ctx):
    if ctx.channel.id != CASINO_CHANNEL_ID: return await safe_reply(ctx, "❌ Wrong channel.", ephemeral=True)
    if not is_gambler(ctx.author): return await safe_reply(ctx, "⛔ Restricted.", ephemeral=True)
    embed = discord.Embed(title="🎰 ShadowSyn Casino", description="Welcome.", color=THEME_PRIMARY)
    embed.set_footer(text=f"Balance: {get_balance(str(ctx.author.id))}")
    await safe_reply(ctx, embed=embed, view=CasinoDashboard(), ephemeral=True) 

# --- RUN ---
if __name__ == "__main__":
    bot.run(TOKEN)
