# bot.py — ShadowSyn Bot
# Features (Feature Lock — DO NOT REMOVE):
# - Welcome Minion card (on join) with one-tap role grant
# - /speak (gTTS + translate) with VC handling + usage log
# - Custom embed modal (/send_custom)
# - Durable welcome card: /send_welcome + /welcome_update
#   • Blue “Invite Friends” button (persistent) → sends ephemeral copy-ready invite
# - Audit logger for voice state changes
# - Departures logger (rich embed) with Left/Kicked/Banned detection
# - Persistent Self-Assign Roles panel (instant add/remove) + full admin cmd suite
# - YouTube watcher (RSS): accepts URL/@handle/UC with alias memory; posts to ONE fixed thread
#
# Env:
#   DISCORD_TOKEN
# Persistence (under $PERSIST_PATH or /data):
#   role_picker.json, youtube_watch.json

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
from discord import app_commands
from discord.ui import View, Button, Modal, TextInput, Select
from gtts import gTTS
from shutil import which
from googletrans import Translator

# YouTube deps
import aiohttp
import xml.etree.ElementTree as ET

# =========================== CONSTANTS ===========================

VANITY_INVITE  = "https://discord.gg/shadowsyn"
THEME_PRIMARY  = 0x2B0B35

ARRIVALS_THREAD_ID      = 959629903186259978
ROLE_MINION_ID          = 955600021502431233
ROLE_ADMIN_ID           = 1214794734770323466  # Admin lock for role manager commands
ROLE_MEMBER_ID          = 955600320287887400   # /speak lock

DEFAULT_TARGET_ID       = 1166874144395247757
SPEAK_LOG_THREAD_ID     = 1400048671973703690
DEPARTURES_THREAD_ID    = 960088192177029140
DEFAULT_AUDIT_THREAD_ID = 961726632249425930

# YouTube watcher (LOCKED to one thread)
ROLE_YT_MANAGER_ID      = 960088893351415898
YT_POST_TARGET_ID       = 959631286882934784   # <- always post here
YT_POLL_SECONDS         = 180
YT_USER_AGENT           = "ShadowSynBot/YouTubeWatcher"

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise SystemExit("❌ DISCORD_TOKEN is not set.")

translator = Translator()
LANG_CHOICES = [
    app_commands.Choice(name="English",  value="en"),
    app_commands.Choice(name="Japanese", value="ja"),
    app_commands.Choice(name="German",   value="de"),
    app_commands.Choice(name="Spanish",  value="es"),
]

# ====================== CONFIG (welcome/audit) ====================

CONFIG_PATH = Path("welcome_config.json")

def load_config() -> dict:
    base = {
        "welcome_target_id": DEFAULT_TARGET_ID,
        "audit_channel_id": DEFAULT_AUDIT_THREAD_ID,
    }
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text())
            if isinstance(data, dict):
                base.update(data)
        except Exception:
            pass
    return base

def save_config(cfg: dict) -> None:
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
    except Exception:
        pass

config = load_config()

# ==================== PERSISTENCE ROOT & FILES ===================

PERSIST_ROOT = Path(os.getenv("PERSIST_PATH", "/data")).resolve()
try:
    PERSIST_ROOT.mkdir(parents=True, exist_ok=True)
except Exception:
    PERSIST_ROOT = Path(".").resolve()

# Role picker store
ROLE_STORE = (PERSIST_ROOT / "role_picker.json")

def _load_role_store() -> Dict[str, dict]:
    if ROLE_STORE.exists():
        try:
            return json.loads(ROLE_STORE.read_text())
        except Exception:
            return {}
    return {}

def _save_role_store(data: Dict[str, dict]) -> None:
    try:
        ROLE_STORE.write_text(json.dumps(data, indent=2))
    except Exception:
        pass

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

# YouTube store (channels + alias map)
YT_STORE = (PERSIST_ROOT / "youtube_watch.json")
# {
#   "channels": { "UCxxxx": {"last_video_id": "VIDEO_ID", "channel_title": "Name"} },
#   "aliases":  { "<normalized input>": "UCxxxx" }
# }
def _load_yt_store() -> Dict[str, dict]:
    base = {"channels": {}, "aliases": {}}
    if YT_STORE.exists():
        try:
            data = json.loads(YT_STORE.read_text())
            if isinstance(data, dict):
                base.update(data)
        except Exception:
            pass
    base.setdefault("channels", {})
    base.setdefault("aliases", {})
    return base

def _save_yt_store(data: Dict[str, dict]) -> None:
    data.setdefault("channels", {})
    data.setdefault("aliases", {})
    try:
        YT_STORE.write_text(json.dumps(data, indent=2))
    except Exception:
        pass

def _alias_key(text: str) -> str:
    s = (text or "").strip().lower().rstrip("/")
    s = re.sub(r"^https?://(www\.)?", "", s)
    return s

def _add_alias(user_input: str, uc_id: str):
    if not user_input or not uc_id:
        return
    store = _load_yt_store()
    store["aliases"][_alias_key(user_input)] = uc_id
    _save_yt_store(store)

def _lookup_alias(user_input: str) -> Optional[str]:
    return _load_yt_store().get("aliases", {}).get(_alias_key(user_input))

# ========================= SAFE HELPERS ==========================

async def safe_defer(inter: discord.Interaction, *, ephemeral: bool = False):
    try:
        if not inter.response.is_done():
            await inter.response.defer(ephemeral=ephemeral)
    except Exception:
        pass

async def safe_reply(inter: discord.Interaction, *args, **kwargs):
    try:
        if not inter.response.is_done():
            return await inter.response.send_message(*args, **kwargs)
        else:
            return await inter.followup.send(*args, **kwargs)
    except Exception:
        return None

def safe_avatar_url(member: Union[discord.Member, discord.User]) -> Optional[str]:
    try:
        return member.display_avatar.url
    except Exception:
        return None

def utcnow():
    return datetime.now(timezone.utc)

def ffmpeg_available() -> bool:
    return which("ffmpeg") is not None

async def resolve_target(
    client: discord.Client, target_id: int
) -> Tuple[Optional[discord.abc.Messageable], Optional[discord.abc.GuildChannel]]:
    ch = client.get_channel(target_id)
    if ch is None:
        try:
            ch = await client.fetch_channel(target_id)
        except Exception:
            return None, None
    if isinstance(ch, discord.TextChannel):
        return ch, ch
    if isinstance(ch, discord.Thread):
        try:
            if ch.archived or ch.locked:
                await ch.edit(archived=False, locked=False)
            await ch.join()
        except Exception:
            pass
        parent = ch.parent if isinstance(ch.parent, discord.TextChannel) else None
        return ch, parent
    return None, None

# Human "x days ago"
def human_ago(dt: Optional[datetime]) -> str:
    if not isinstance(dt, datetime):
        return "Unknown"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = utcnow() - dt
    s = int(max(delta.total_seconds(), 0))
    units = [
        ("year",   31536000),
        ("month",  2629800),
        ("day",    86400),
        ("hour",   3600),
        ("minute", 60),
    ]
    for name, secs in units:
        if s >= secs:
            v = s // secs
            return f"{v} {name}{'' if v == 1 else 's'} ago"
    return "just now"

def safe_display_name(obj: Union[discord.Member, discord.User]) -> str:
    """Return server nickname if available, else a sensible name."""
    try:
        if isinstance(obj, discord.Member):
            return obj.display_name
        return obj.global_name or obj.name  # type: ignore[attr-defined]
    except Exception:
        return str(obj)

# ======================= INVITE ATTRIBUTION ======================

_INVITES_CACHE: Dict[int, Dict[str, int]] = {}

def _can_track_invites(guild: discord.Guild) -> bool:
    me = guild.me
    return bool(me and me.guild_permissions.manage_guild)

async def _prime_invites_cache(guild: discord.Guild):
    if not _can_track_invites(guild):
        _INVITES_CACHE[guild.id] = {}
        return
    try:
        invites = await guild.invites()
        _INVITES_CACHE[guild.id] = {inv.code: (inv.uses or 0) for inv in invites}
    except Exception:
        _INVITES_CACHE[guild.id] = {}

async def _detect_join_source(member: discord.Member) -> Optional[str]:
    guild = member.guild
    if not guild:
        return None
    if not _can_track_invites(guild):
        vanity = None
        try:
            vanity = guild.vanity_url_code
        except Exception:
            pass
        return f"Joined via Vanity: `{vanity}`" if vanity else None
    try:
        before = _INVITES_CACHE.get(guild.id, {})
        current = await guild.invites()
        increased = None
        for inv in current:
            prev = before.get(inv.code, 0)
            if (inv.uses or 0) > prev:
                increased = inv
                break
        _INVITES_CACHE[guild.id] = {inv.code: (inv.uses or 0) for inv in current}
        if increased:
            inviter = increased.inviter
            inviter_name = f"{inviter}" if inviter else "Unknown"
            return f"Joined via `{increased.code}`, invited by **{inviter_name}**"
        vanity = None
        try:
            vanity = guild.vanity_url_code
        except Exception:
            pass
        if vanity:
            return f"Joined via Vanity: `{vanity}`"
        return None
    except Exception:
        return None

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

        # Persistent welcome invite button
        try:
            self.add_view(InviteCopyView())
        except Exception:
            pass

        await self.tree.sync()

        # Rehydrate role panel(s) and register persistent views with message_id
        for g in self.guilds:
            try:
                await rehydrate_role_panel(self, g)
            except Exception:
                pass

        # Start YouTube watcher
        if self._yt_task is None:
            self._yt_task = asyncio.create_task(youtube_watch_loop(self))

bot = ShadowSynBot()

@bot.event
async def on_ready():
    try:
        bot.add_view(InviteCopyView())
    except Exception:
        pass
    print(f"✅ Logged in as {bot.user} | ROLE_STORE: {ROLE_STORE} | YT_STORE: {YT_STORE}")

@bot.event
async def on_guild_join(guild: discord.Guild):
    await _prime_invites_cache(guild)
    try:
        await rehydrate_role_panel(bot, guild)
    except Exception:
        pass

# ================== WELCOME (Minion quick-grant) =================

def setup_welcome(client: discord.Client):
    class MinionView(View):
        def __init__(self, target_member_id: int):
            super().__init__(timeout=60*60*24)
            self.target_member_id = target_member_id
            btn = Button(label="Minion", style=discord.ButtonStyle.success)
            btn.callback = self._grant_minion
            self.add_item(btn)

        async def _grant_minion(self, interaction: discord.Interaction):
            guild = interaction.guild
            if not guild:
                return
            member = guild.get_member(self.target_member_id)
            role = guild.get_role(ROLE_MINION_ID)
            if member and role:
                try:
                    await member.add_roles(role, reason=f"Granted by {interaction.user}")
                    await safe_reply(interaction, f"✅ Gave {role.name} to {member.mention}", ephemeral=True)
                except Exception as e:
                    await safe_reply(interaction, f"❌ Failed: `{e}`", ephemeral=True)

    async def _send_arrival_card(member: discord.Member):
        if member.bot:
            return
        dest = client.get_channel(ARRIVALS_THREAD_ID)
        if not dest:
            return
        invite_line = await _detect_join_source(member)
        icon = safe_avatar_url(member)
        embed = discord.Embed(
            description=f"{member.mention} joined **{member.guild.name}**",
            color=discord.Color.dark_theme()
        )
        embed.set_author(name=str(member), icon_url=icon)
        if invite_line:
            embed.add_field(name="Joined Via", value=invite_line, inline=False)
        embed.set_footer(text="Tap to grant Minion")
        await dest.send(embed=embed, view=MinionView(member.id))

    @bot.event
    async def on_member_join(member: discord.Member):
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
            if vc.channel.id == state.channel.id:
                return vc
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
        try:
            await target.send(embed=embed)
        except Exception:
            pass

@bot.tree.command(name="speak", description="Speak text in your VC")
@app_commands.describe(text="Message", language="Target language")
@app_commands.choices(language=LANG_CHOICES)
async def speak(interaction: discord.Interaction, text: str, language: app_commands.Choice[str] = None):
    await safe_defer(interaction, ephemeral=True)

    # -------- Member role lock for /speak --------
    if not isinstance(interaction.user, discord.Member) or not any(
        r.id == ROLE_MEMBER_ID for r in interaction.user.roles
    ):
        return await safe_reply(
            interaction,
            "❌ `/speak` is only available to members with the **Member** role.",
            ephemeral=True,
        )
    # ---------------------------------------------

    if not ffmpeg_available():
        return await safe_reply(interaction, "❌ FFmpeg missing", ephemeral=True)
    vc = await ensure_voice(interaction)
    if vc is None:
        return
    lang_code = (language.value if language else "en").lower()
    to_say = text
    if lang_code != "en":
        try:
            to_say = translator.translate(text, src="en", dest=lang_code).text
        except Exception:
            await safe_reply(interaction, "⚠️ Translate failed, using original.", ephemeral=True)
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
            tmp = f.name
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
            try:
                await ch.send(embed=embed)
            except Exception as e:
                return await safe_reply(interaction, f"❌ Failed: `{e}`", ephemeral=True)
        await safe_reply(interaction, "✅ Posted", ephemeral=True)

@bot.tree.command(name="send_custom", description="Send a custom embed here")
async def send_custom(interaction: discord.Interaction):
    try:
        await interaction.response.send_modal(CustomEmbedModal(interaction.channel.id))
    except Exception:
        await safe_reply(interaction, "❌ Couldn't open modal.", ephemeral=True)

# ====================== DURABLE WELCOME COMMANDS =================

def welcome_embed() -> discord.Embed:
    e = discord.Embed(
        title="Welcome to ShadowSyn",
        color=THEME_PRIMARY,
        description=(
            "👋 **Welcome to ShadowSyn**\n"
            "You’re in a PvP-first Discord. Keep it simple, play hard, don’t be a problem.\n\n"
            "🎮 **What we play**\n"
            "We jump into every new PvP MMO or survival release. Right now we’re mainly on **WoW Ascension** "
            "and **Aion 2**, with groups playing **ARC Raiders**, **Counter-Strike 2** and **Battlefield 6**.\n\n"
            "💬 **First steps**\n"
            "Say hi in **#lobby** – where you’re from, what you play, and what you’re looking for.\n\n"
            "🪪 **Game roles**\n"
            "Go to **#self-roles** and pick the **game roles** you actually play. That’s how you get the right pings and channels.\n\n"
            "❓ **Questions**\n"
            "Ping **@Gravy** if you need something or want to spin up a group.\n\n"
            "🚫 **Rules (quick version)**\n"
            "No spam, no drama, no random DMs, no self-promo without approval. No NSFW, no piracy, no weird stuff. "
            "Use common sense — if you’re annoying, you won’t last.\n\n"
            f"🔗 **Invite**\nIf you like it here, invite people you actually want to play with: {VANITY_INVITE}"
        ),
    )
    return e

class CopyInviteEphemeralView(View):
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(Button(label="Open Link", style=discord.ButtonStyle.link, url=VANITY_INVITE))

class InviteCopyView(View):
    """
    Blue public button. On click, sends the user an ephemeral message with
    a copy-ready code block and an 'Open Link' button. Persistent via custom_id.
    """
    def __init__(self):
        super().__init__(timeout=None)
        btn = Button(
            label="Invite Friends",
            style=discord.ButtonStyle.primary,
            emoji="🔗",
            custom_id="shadowsyn:welcome_invite_copy:v1"
        )
        btn.callback = self._send_copyable  # type: ignore
        self.add_item(btn)

    async def _send_copyable(self, interaction: discord.Interaction):
        msg = (
            "✅ Invite ready to copy:\n"
            f"```text\n{VANITY_INVITE}\n```\n"
            "Desktop: click the **copy** icon. Mobile: **tap & hold** to copy."
        )
        await safe_reply(interaction, content=msg, view=CopyInviteEphemeralView(), ephemeral=True)

def admin_only():
    async def predicate(inter: discord.Interaction) -> bool:
        if not isinstance(inter.user, discord.Member):
            return False
        return any(r.id == ROLE_ADMIN_ID for r in inter.user.roles)
    return app_commands.check(predicate)

@admin_only()
@bot.tree.command(name="send_welcome", description="Post the welcome card here or to a target channel/thread.")
@app_commands.describe(target="Optional channel/thread to post in (defaults to here)")
async def send_welcome(
    interaction: discord.Interaction,
    target: Union[discord.TextChannel, discord.Thread, None] = None
):
    await safe_defer(interaction, ephemeral=True)
    dest = target or interaction.channel
    try:
        view = InviteCopyView()
        msg = await dest.send(embed=welcome_embed(), view=view)
        try:
            await msg.pin(reason="ShadowSyn Welcome")
        except Exception:
            pass
        await safe_reply(interaction, f"✅ Welcome card posted in {dest.mention}.", ephemeral=True)
    except Exception as e:
        await safe_reply(interaction, f"❌ Failed: `{e}`", ephemeral=True)

@admin_only()
@bot.tree.command(name="welcome_update", description="Update an existing welcome card (by message ID or detect pinned).")
@app_commands.describe(
    message_id="Optional: message ID of the existing welcome card",
    target="Optional: channel/thread where the message lives (defaults to here)"
)
async def welcome_update(
    interaction: discord.Interaction,
    message_id: Optional[str] = None,
    target: Union[discord.TextChannel, discord.Thread, None] = None
):
    await safe_defer(interaction, ephemeral=True)
    dest = target or interaction.channel

    msg = None
    if message_id:
        try:
            msg = await dest.fetch_message(int(message_id))
        except Exception:
            return await safe_reply(interaction, "❌ Couldn’t fetch that message ID here.", ephemeral=True)
    else:
        try:
            pins = await dest.pins()
            for m in pins:
                if m.author.id == bot.user.id and m.embeds:
                    if (m.embeds[0].title or "").strip().lower() == "welcome to shadowsyn":
                        msg = m
                        break
        except Exception:
            msg = None
        if msg is None:
            async for m in dest.history(limit=50):
                if m.author.id == bot.user.id and m.embeds:
                    if (m.embeds[0].title or "").strip().lower() == "welcome to shadowsyn":
                        msg = m
                        break

    if msg is None:
        return await safe_reply(
            interaction,
            "❌ Couldn’t find a welcome card here. Provide a `message_id` or use `/send_welcome`.",
            ephemeral=True,
        )

    try:
        await msg.edit(embed=welcome_embed(), view=InviteCopyView())
        await safe_reply(interaction, "✅ Welcome card updated.", ephemeral=True)
    except Exception as e:
        await safe_reply(interaction, f"❌ Failed: `{e}`", ephemeral=True)

# ============================ AUDIT LOG ==========================
# ... (rest of file unchanged: audit logger, departures, role picker view, YT watcher, run() etc.)
