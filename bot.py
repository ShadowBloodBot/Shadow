# bot.py — ShadowSyn (Final: Crash Fix + Duel @User System)
#
# === FEATURES ===
# 1. VoiceMaster: Join-to-Create VCs + Control Panel
# 2. Music: Crash-Proof Playback + Zombie Connection Fix
# 3. Clip System: Force Recording (Records "Unknown" users too)
# 4. Haste Facts: /haste (Public) + /morehaste (Admin)
# 5. Scoins Casino: /gamble (Dashboard), /duel (Direct Challenge)
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
    if HASTE_FACTS_STORE.exists():
        try: active_haste_facts = json.loads(HASTE_FACTS_STORE.read_text())
        except: active_haste_facts = list(DEFAULT_HASTE_FACTS)
    else: active_haste_facts = list(DEFAULT_HASTE_FACTS)
    if SCOINS_STORE.exists():
        try: scoins_db = json.loads(SCOINS_STORE.read_text())
        except: scoins_db = {}
    else: scoins_db = {}

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
        if any(r.id == ROLE_ADMIN_ID for r in ctx.author.roles): return True
        if any(r.id == ROLE_DJ_ID for r in ctx.author.roles): return True
        return False
    return commands.check(predicate)

def owner_only():
    def predicate(ctx):
        return ctx.author.id == OWNER_ID
    return commands.check(predicate)

# ==================== MUSIC ENGINE ====================

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

# ==================== CASINO SYSTEM (UI) ====================

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

class ShopSelect(Select):
    def __init__(self):
        options = [
            SelectOption(label="Pull Reset", description="15 Scoins: Reset your daily timer.", value="reset", emoji="🔄"),
            SelectOption(label="Shadow Tag", description="50 Scoins: Add [Shadow] to nickname.", value="tag", emoji="🏷️")
        ]
        super().__init__(placeholder="Select an item to buy...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: Interaction):
        user_id = str(interaction.user.id)
        bal = get_balance(user_id)
        val = self.values[0]
        
        if val == "reset":
            cost = 15
            if bal < cost: return await interaction.response.send_message("❌ Too poor.", ephemeral=True)
            if user_id in scoins_db:
                scoins_db[user_id]["last_pull"] = 0
                update_balance(user_id, -cost)
                await interaction.response.send_message("✅ **Purchased:** Pull Timer Reset! Go Collect now.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Error data.", ephemeral=True)

        elif val == "tag":
            cost = 50
            if bal < cost: return await interaction.response.send_message("❌ Too poor.", ephemeral=True)
            try:
                update_balance(user_id, -cost)
                new_nick = f"[Shadow] {interaction.user.display_name}"[:32]
                await interaction.user.edit(nick=new_nick)
                await interaction.response.send_message(f"✅ **Purchased:** Shadow Tag applied.", ephemeral=True)
            except Exception as e:
                update_balance(user_id, cost) # Refund
                await interaction.response.send_message(f"❌ Failed (Refunded): Bot lacks permission.", ephemeral=True)

class DuelAcceptView(View):
    def __init__(self, p1, p2, amount):
        super().__init__(timeout=60)
        self.p1 = p1
        self.p2 = p2
        self.amount = amount

    @discord.ui.button(label="ACCEPT DUEL", style=ButtonStyle.danger, emoji="⚔️")
    async def accept(self, button, interaction: Interaction):
        if interaction.user.id != self.p2.id: return
        
        # Re-check funds
        if get_balance(str(self.p1.id)) < self.amount or get_balance(str(self.p2.id)) < self.amount:
            return await interaction.response.send_message("❌ Someone went broke during the wait.", ephemeral=True)
        
        # Deduct
        update_balance(str(self.p1.id), -self.amount)
        update_balance(str(self.p2.id), -self.amount)
        
        # Roll
        winner = random.choice([self.p1, self.p2])
        loser = self.p2 if winner == self.p1 else self.p1
        win_amt = self.amount * 2
        update_balance(str(winner.id), win_amt)
        
        embed = discord.Embed(title="🩸 DUEL FINISHED", description=f"🏆 **Winner:** {winner.mention}\n💀 **Loser:** {loser.mention}\n💰 **Won:** {win_amt} Scoins", color=THEME_GOLD)
        self.clear_items()
        await interaction.response.edit_message(view=self, embed=embed)

class CasinoDashboard(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Collect", style=ButtonStyle.success, emoji="💰", row=0)
    async def collect(self, button, interaction: Interaction):
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
        bal = get_balance(str(interaction.user.id))
        async def run_slots(inter, amount):
            update_balance(str(inter.user.id), -amount)
            # Animation
            emojis = ["🍒", "🍋", "🍇", "💎", "7️⃣"]
            a, b, c = random.choice(emojis), random.choice(emojis), random.choice(emojis)
            
            payout = 0
            if a == b == c: payout = amount * 10
            elif a == b or b == c or a == c: payout = int(amount * 1.5)
            
            if payout > 0:
                update_balance(str(inter.user.id), payout)
                col = THEME_GOLD if payout > amount * 2 else THEME_WIN
                msg = f"🎰 **{a} | {b} | {c}**\n✅ **WIN!** +{payout}"
            else:
                col = THEME_LOSS
                msg = f"🎰 **{a} | {b} | {c}**\n❌ **Lost** {amount}"
            
            embed = discord.Embed(description=msg, color=col)
            await inter.response.send_message(embed=embed)

        await interaction.response.send_modal(BetAmountModal("Slots Bet", bal, run_slots))

    @discord.ui.button(label="Duel", style=ButtonStyle.danger, emoji="⚔️", row=0)
    async def duel(self, button, interaction: Interaction):
        # FIXED: Removed broken UserSelect. Now instructs to use slash command.
        await interaction.response.send_message("⚔️ To duel someone, use the command:\n`/duel @user [amount]`", ephemeral=True)

    @discord.ui.button(label="Shop", style=ButtonStyle.secondary, emoji="🛒", row=1)
    async def shop(self, button, interaction: Interaction):
        view = View()
        view.add_item(ShopSelect())
        await interaction.response.send_message("Welcome to the Shop:", view=view, ephemeral=True)

    @discord.ui.button(label="Wallet", style=ButtonStyle.secondary, emoji="💳", row=1)
    async def wallet_btn(self, button, interaction: Interaction):
        bal = get_balance(str(interaction.user.id))
        await interaction.response.send_message(f"💳 Balance: **{bal}** Scoins.", ephemeral=True)

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
        if HAS_SINKS and vc and vc.is_connected():
            if not vc.recording:
                try:
                    vc.start_recording(RingBufferSink(time_limit=30), dummy_callback)
                    print(f"🎙️ Auto-recording started in {channel.name}")
                except Exception as e: print(f"⚠️ Auto-recording failed: {e}")
        return vc
    except Exception as e:
        await safe_reply(ctx, f"❌ Voice Error: {e}", ephemeral=True)
        return None

# ==================== COMMANDS ====================

@bot.slash_command(name="gamble", description="Open the Scoin Casino")
async def gamble(ctx: discord.ApplicationContext):
    embed = discord.Embed(title="🎰 ShadowSyn Casino", description="Welcome to the underworld economy.\nSelect a game below.", color=THEME_PRIMARY)
    user_id = str(ctx.author.id)
    bal = get_balance(user_id)
    embed.set_footer(text=f"Your Balance: {bal} Scoins")
    await safe_reply(ctx, embed=embed, view=CasinoDashboard())

@bot.slash_command(name="duel", description="Challenge a user to a wager")
async def duel_cmd(ctx: discord.ApplicationContext, opponent: discord.Member, amount: str):
    if opponent.id == ctx.author.id: return await safe_reply(ctx, "❌ Cannot duel yourself.", ephemeral=True)
    if opponent.bot: return await safe_reply(ctx, "❌ Cannot duel bots.", ephemeral=True)
    
    # Balance Checks
    challenger_bal = get_balance(str(ctx.author.id))
    opponent_bal = get_balance(str(opponent.id))
    
    if amount.lower() == "all": bet = challenger_bal
    else:
        try: bet = int(amount)
        except: return await safe_reply(ctx, "❌ Invalid amount.", ephemeral=True)
    
    if bet <= 0: return await safe_reply(ctx, "❌ Bet must be positive.", ephemeral=True)
    if challenger_bal < bet: return await safe_reply(ctx, f"❌ You only have {challenger_bal} Scoins.", ephemeral=True)
    if opponent_bal < bet: return await safe_reply(ctx, f"❌ {opponent.display_name} only has {opponent_bal} Scoins.", ephemeral=True)
    
    # Send Challenge
    embed = discord.Embed(title="⚔️ DUEL CHALLENGE", description=f"{ctx.author.mention} challenges {opponent.mention}!\n💰 **Pot:** {bet*2} Scoins\n\nClick **Accept** to fight.", color=discord.Color.red())
    await safe_reply(ctx, content=opponent.mention, embed=embed, view=DuelAcceptView(ctx.author, opponent, bet))

@bot.slash_command(name="wallet", description="Check your balance")
async def wallet(ctx: discord.ApplicationContext, user: Option(discord.User, required=False)):
    target = user or ctx.author
    bal = get_balance(str(target.id))
    embed = discord.Embed(description=f"💳 **{target.display_name}** has `{bal}` Scoins.", color=THEME_PRIMARY)
    await safe_reply(ctx, embed=embed)

@bot.slash_command(name="leaderboard", description="Top 10 Scoin Rich List")
async def leaderboard(ctx: discord.ApplicationContext):
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

# --- OTHER COMMANDS ---

@bot.slash_command(name="speak", description="Speak text in your VC")
@dj_or_admin()
async def speak(ctx: discord.ApplicationContext, text: Option(str, "Message"), language: Option(str, "Language", choices=LANG_CHOICES, default="English")):
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
    except Exception as e: await safe_reply(ctx, f"❌ Error: `{e}`", ephemeral=True)

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

@bot.slash_command(name="send_custom", description="Send a custom embed here")
@admin_only()
async def send_custom(ctx: discord.ApplicationContext):
    await ctx.send_modal(CustomEmbedModal(ctx.channel.id, ctx.bot))

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
    except Exception as e: await safe_reply(ctx, f"❌ Failed: `{e}`", ephemeral=True)

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
    except Exception as e: await safe_reply(ctx, f"❌ Failed: `{e}`", ephemeral=True)

# --- INVITE ROLES ---
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

# --- MUSIC / CLIPS ---
@bot.slash_command(name="join", description="Join VC and start Auto-Recording")
@dj_or_admin()
async def join(ctx: discord.ApplicationContext):
    await safe_defer(ctx, ephemeral=True)
    vc = await ensure_voice_simple(ctx)
    if vc: await safe_reply(ctx, f"✅ Joined {vc.channel.mention} and started auto-recording.", ephemeral=True)

@bot.slash_command(name="clip", description="Clip last 30s and save to channel")
@dj_or_admin()
async def clip(ctx: discord.ApplicationContext):
    await safe_defer(ctx, ephemeral=True)
    vc = ctx.guild.voice_client
    if not vc or not vc.is_connected(): return await safe_reply(ctx, "❌ I am not in a voice channel.", ephemeral=True)
    if not HAS_SINKS: return await safe_reply(ctx, "❌ Clipping not supported (Missing Py-Cord).", ephemeral=True)
    if not hasattr(vc, "recording") or not vc.recording:
        try:
            vc.start_recording(RingBufferSink(time_limit=30), dummy_callback)
            return await safe_reply(ctx, "⚠️ Recording started now. Try again in 30s.", ephemeral=True)
        except: return await safe_reply(ctx, "❌ Could not access recording stream.", ephemeral=True)
    sink = vc.sink
    if not isinstance(sink, RingBufferSink): return await safe_reply(ctx, "❌ Current recording format does not support clipping.", ephemeral=True)
    input_files = []
    temp_files_to_cleanup = []
    try:
        for user_id, audio_deque in sink.buffer.items():
            if not audio_deque: continue
            data = b''.join(audio_deque)
            if len(data) == 0: continue
            f_path = f"temp_{user_id}_{int(time.time())}.wav"
            with wave.open(f_path, 'wb') as wav:
                wav.setnchannels(2); wav.setsampwidth(2); wav.setframerate(48000); wav.writeframes(data)
            input_files.append(f_path); temp_files_to_cleanup.append(f_path)
        if not input_files: return await safe_reply(ctx, "ℹ️ No recent audio found (Buffer empty). Speak for 5 seconds and try again.", ephemeral=True)
        final_file = None
        if len(input_files) == 1: final_file = discord.File(input_files[0], filename=f"clip_{int(time.time())}.wav")
        else:
            output_filename = f"mixed_clip_{int(time.time())}.mp3"
            cmd = ['ffmpeg', '-y']
            for f in input_files: cmd.extend(['-i', f])
            cmd.extend(['-filter_complex', f'amix=inputs={len(input_files)}:duration=longest', output_filename])
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.path.exists(output_filename): final_file = discord.File(output_filename); temp_files_to_cleanup.append(output_filename)
            else: return await safe_reply(ctx, "❌ Failed to mix audio.", ephemeral=True)
        target_id = CLIPS_TARGET_ID
        target_ch, _ = await resolve_target(ctx.bot, target_id)
        if target_ch and final_file:
            await target_ch.send(content=f"✂️ **Clip recorded by {ctx.author.mention}**", file=final_file)
            await safe_reply(ctx, f"✅ Clip saved to {target_ch.mention}.", ephemeral=True)
        else: await safe_reply(ctx, "⚠️ Target channel not found.", file=final_file, ephemeral=True)
    except Exception as e:
        print(f"Clip Error: {e}")
        await safe_reply(ctx, f"❌ Error processing clip: {e}", ephemeral=True)
    finally:
        for f in temp_files_to_cleanup:
            try: os.remove(f)
            except: pass

@bot.slash_command(name="play", description="Search & Play music (Queue enabled)")
@dj_or_admin()
async def play(ctx: discord.ApplicationContext, search: Option(str, description="Song name or URL")):
    await safe_defer(ctx)
    try:
        if re.match(r'^https?://', search):
            vc = await ensure_voice_simple(ctx)
            if not vc: return
            guild_id = ctx.guild.id
            if guild_id not in bot.audio_queues: bot.audio_queues[guild_id] = deque()
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
        if 'entries' not in data or not data['entries']: return await safe_reply(ctx, "❌ No results found.", ephemeral=True)
        tracks = data['entries']
        view = MusicSearchView(tracks)
        await safe_reply(ctx, f"🔎 Results for **{search}**:", view=view, ephemeral=True)
    except Exception as e:
        print(f"[DEBUG] Play Error: {e}")
        await safe_reply(ctx, f"❌ Error: `{e}`", ephemeral=True)

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
        if guild_id not in bot.audio_queues: bot.audio_queues[guild_id] = deque()
        if vc.is_playing():
            bot.audio_queues[guild_id].append((url, title))
            await interaction.followup.send(f"📝 **Queued:** {title}", ephemeral=True)
        else:
            try: await interaction.edit_original_response(content=f"▶️ **Playing:** {title}", view=None)
            except: pass
            await play_track(vc, url, title, guild_id)

class MusicSearchView(View):
    def __init__(self, tracks: List[dict]):
        super().__init__(timeout=60)
        self.add_item(MusicSelect(tracks))

@bot.slash_command(name="skip", description="Skip the current song")
@dj_or_admin()
async def skip(ctx: discord.ApplicationContext):
    vc = ctx.guild.voice_client
    if vc and vc.is_playing():
        vc.stop()
        await safe_reply(ctx, "⏭️ Skipped.", ephemeral=True)
    else: await safe_reply(ctx, "❌ Nothing is playing.", ephemeral=True)

@bot.slash_command(name="queue", description="Show the music queue")
@dj_or_admin()
async def queue(ctx: discord.ApplicationContext):
    gid = ctx.guild.id
    if gid not in bot.audio_queues or not bot.audio_queues[gid]: return await safe_reply(ctx, "ℹ️ Queue is empty.", ephemeral=True)
    lines = []
    for i, (url, title) in enumerate(list(bot.audio_queues[gid])[:10]): lines.append(f"`{i+1}.` {title}")
    embed = discord.Embed(title="🎵 Music Queue", description="\n".join(lines), color=THEME_PRIMARY)
    if len(bot.audio_queues[gid]) > 10: embed.set_footer(text=f"...and {len(bot.audio_queues[gid])-10} more")
    await safe_reply(ctx, embed=embed, ephemeral=True)

@bot.slash_command(name="stop", description="Stop music and clear queue")
@dj_or_admin()
async def stop(ctx: discord.ApplicationContext):
    vc = ctx.guild.voice_client
    if vc:
        if ctx.guild.id in bot.audio_queues: bot.audio_queues[ctx.guild.id].clear()
        await vc.disconnect()
        await safe_reply(ctx, "⏹️ Stopped & Cleared.", ephemeral=True)
    else: await safe_reply(ctx, "ℹ️ Not connected.", ephemeral=True)

# --- ROLE PICKER ---
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
