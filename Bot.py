# bot.py — ShadowSyn (Master: High/Low Dice Added)
#
# === FEATURES ===
# [x] Casino: 
#     - 🆕 DICE (High/Low): Roll 2 dice. Bet Low (x2), High (x2), or 7 (x5).
#     - CHICKEN: Minesweeper style.
#     - SLOTS: 18% House Edge + Public Jackpot Alert.
#     - LOCKED: Only works in channel 1468766727134249091.
# [x] Departures: Rich Embeds (Account Age, Kick Detection).
# [x] Speak: Auto-Translates text before speaking.
# [x] Embeds: /send_custom & /edit_custom.
# [x] Music, VoiceMaster, Logs: Preserved.
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
from pathlib import Path
from typing import Optional, List, Set
from datetime import datetime, timezone
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

# =========================== CONSTANTS ===========================

VANITY_INVITE  = "https://discord.gg/shadowsyn"
THEME_PRIMARY  = 0x2B0B35
THEME_WIN      = 0x43B581 
THEME_LOSS     = 0xF04747 
THEME_GOLD     = 0xFFD700 

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

active_haste_facts = []
scoins_db = {} 

def _atomic_save(path: Path, data):
    """Safely saves data to a JSON file via atomic temp-file swap to prevent corruption."""
    try:
        tmp_path = path.with_suffix('.tmp')
        tmp_path.write_text(json.dumps(data, indent=2))
        tmp_path.replace(path)
    except Exception as e:
        print(f"Failed to atomic save {path}: {e}")

def _load_persistence():
    global active_haste_facts, scoins_db
    if HASTE_FACTS_STORE.exists():
        try: active_haste_facts = json.loads(HASTE_FACTS_STORE.read_text())
        except: active_haste_facts = list(DEFAULT_HASTE_FACTS)
    else: active_haste_facts = list(DEFAULT_HASTE_FACTS)

    if SCOINS_STORE.exists():
        try: scoins_db = json.loads(SCOINS_STORE.read_text())
        except: scoins_db = {}
    else: scoins_db = {}

def _save_haste_facts():
    _atomic_save(HASTE_FACTS_STORE, active_haste_facts)

def _save_scoins():
    _atomic_save(SCOINS_STORE, scoins_db)

def get_balance(user_id: str) -> int:
    return scoins_db.get(user_id, {}).get("balance", 0)

def update_balance(user_id: str, amount: int):
    user_id = str(user_id)
    if user_id not in scoins_db: scoins_db[user_id] = {"balance": 0, "last_pull": 0}
    scoins_db[user_id]["balance"] += amount
    _save_scoins()

# ==================== PERMISSIONS ====================

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

# ==================== HELPERS ====================

def _load_active_vcs() -> Set[int]:
    if ACTIVE_VCS_STORE.exists():
        try: return set(json.loads(ACTIVE_VCS_STORE.read_text()))
        except: return set()
    return set()

def _save_active_vcs(vcs: Set[int]) -> None:
    _atomic_save(ACTIVE_VCS_STORE, list(vcs))

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
    _atomic_save(INVITE_ROLE_STORE, data)

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

# === MUSIC DROPDOWN MENU ===
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
        
        if not url:
            return await self.ctx.send("❌ Error: Could not resolve URL for that track.")

        # Add to queue or play
        if self.vc.is_playing():
            if self.ctx.guild.id not in bot.audio_queues: bot.audio_queues[self.ctx.guild.id] = deque()
            bot.audio_queues[self.ctx.guild.id].append((url, title))
            await self.ctx.send(f"📝 **Queued:** {title}")
        else:
            await self.ctx.send(f"▶️ **Playing:** {title}")
            await play_track(self.vc, url, title, self.ctx.guild.id)
        
        # Disable view
        try: await interaction.message.delete()
        except: pass

class MusicSelectionView(View):
    def __init__(self, entries, ctx, vc):
        super().__init__(timeout=60)
        self.add_item(MusicSelect(entries, ctx, vc))

# ==================== CASINO: SLOTS ====================

def generate_slot_result(user, bet):
    user_id = str(user.id)
    update_balance(user_id, -bet)
    
    # 7 Symbols for 18% House Edge
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
        self.grid_size = 20 # 5x4 grid
        
        # Game State
        self.bones_indices = set(random.sample(range(self.grid_size), bones_count))
        self.revealed = set()
        self.game_over = False
        self.multiplier = 1.0
        
        # Setup Grid (Rows 0-3)
        for y in range(4):
            for x in range(5):
                self.add_item(ChickenButton(x, y, self))
        
        # Cashout Button (Row 4)
        self.cashout_btn = Button(style=ButtonStyle.success, label="Cash Out", row=4, emoji="💰", disabled=True)
        self.cashout_btn.callback = self.cash_out
        self.add_item(self.cashout_btn)

    def calculate_next_multiplier(self):
        remaining_tiles = self.grid_size - len(self.revealed)
        safe_remaining = remaining_tiles - self.bones_count
        if safe_remaining <= 0: return self.multiplier
        odds = remaining_tiles / safe_remaining
        return self.multiplier * odds * 0.97 # 3% House Edge

    async def handle_click(self, button, interaction: Interaction):
        if self.game_over: return
        
        idx = button.idx
        if idx in self.bones_indices:
            # HIT A BONE -> LOSS
            self.game_over = True
            update_balance(str(self.user_id), -self.bet)
            
            button.style = ButtonStyle.danger
            button.emoji = "🦴"
            button.label = ""
            
            # Reveal all bones
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
            # HIT A CHICKEN -> WIN
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
        if interaction.user.id != self.user_id: return
        self.game_over = True
        
        win_amount = int(self.bet * self.multiplier)
        # Net change: -bet + win
        update_balance(str(self.user_id), -self.bet + win_amount)

        # Disable all
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
        # Check Balance before starting
        bal = get_balance(str(self.user.id))
        if bal < self.bet:
            return await interaction.response.send_message("❌ Insufficient funds.", ephemeral=True)
        
        # Start Game
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
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("🚫 Not your game.", ephemeral=True)
        if self.game_over: return
        
        # Deduct bet immediately
        bal = get_balance(str(self.user_id))
        if bal < self.bet:
            return await interaction.response.send_message("❌ Insufficient funds.", ephemeral=True)
        
        update_balance(str(self.user_id), -self.bet)
        self.game_over = True # One shot game

        # Roll Dice
        d1 = random.randint(1, 6)
        d2 = random.randint(1, 6)
        total = d1 + d2
        
        # Visuals
        dice_map = {1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣", 5: "5️⃣", 6: "6️⃣"}
        visual = f"{dice_map[d1]} + {dice_map[d2]} = **{total}**"

        # Win Logic
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

        # Result
        if won:
            update_balance(str(self.user_id), payout)
            embed = discord.Embed(title="🎲 Dice Roll", description=f"{visual}\n✅ **WIN!** You won **{payout}** Scoins.", color=THEME_WIN)
        else:
            embed = discord.Embed(title="🎲 Dice Roll", description=f"{visual}\n❌ **LOSS.** You lost **{self.bet}** Scoins.", color=THEME_LOSS)
        
        # Disable buttons
        for child in self.children: child.disabled = True
        
        # Add "Play Again" button
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
        await interaction.response.send_message(
            f"🎲 **High/Low Dice**\nBet: **{self.bet}**", 
            view=DiceGameView(self.user, self.bet), 
            ephemeral=True
        )

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
        # Using explicit default intents and granting specific privileged permissions
        # to ensure Join-to-Create voice_states correctly bind without crashing
        intents = discord.Intents.default()
        intents.guilds = True
        intents.voice_states = True
        intents.members = True
        super().__init__(intents=intents)
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
        msg = f"🙊 **{member.display_name}** was **{status}** by {actor}."
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
            # Run translation in executor to prevent blocking
            try:
                # Note: Assuming standard googletrans. If it fails, falls back to text.
                translation = await bot.loop.run_in_executor(None, lambda: translator.translate(text, dest=lang_code))
                text_to_speak = translation.text
            except Exception as tr_err:
                print(f"Translation Error: {tr_err}")
                # Fallback to original text if translation fails
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
