# bot.py — ShadowSyn Bot
# Features (Feature Lock — DO NOT REMOVE):
# - Welcome Minion card (on join) with one-tap role grant
# - /speak (gTTS + translate) with VC handling + usage log
# - Custom embed modal (/send_custom)
# - Durable welcome card: /send_welcome + /welcome_update
#   • Blue “Invite Friends” button (persistent) → sends ephemeral copy-ready invite
# - Audit logger for voice state changes
# - Departures logger (rich embed) with Left/Kicked/Banned detection
# - Persistent Self-Assign Roles panel (add & private remove) + full admin cmd suite
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
    if not user_input or not uc_id: return
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
            if not guild: return
            member = guild.get_member(self.target_member_id)
            role = guild.get_role(ROLE_MINION_ID)
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
            await safe_reply(inter, "❌ No guild/member", ephemeral=True); return None
        state = inter.user.voice
        if not state or not state.channel:
            await safe_reply(inter, "❌ Join a VC first.", ephemeral=True); return None
        vc = discord.utils.get(bot.voice_clients, guild=inter.guild)
        if vc and vc.is_connected():
            if vc.channel.id == state.channel.id: return vc
            await vc.move_to(state.channel); return vc
        return await state.channel.connect(reconnect=True, timeout=15)
    except Exception as e:
        await safe_reply(inter, f"❌ VC error: `{e}`", ephemeral=True); return None

async def log_speak_usage(inter, text, lang):
    target, _ = await resolve_target(bot, SPEAK_LOG_THREAD_ID)
    if target:
        embed = discord.Embed(title="🗣️ /speak used", color=THEME_PRIMARY)
        embed.add_field(name="User", value=str(inter.user), inline=False)
        embed.add_field(name="Language", value=lang, inline=True)
        embed.add_field(name="Text", value=text[:1024], inline=False)
        try: await target.send(embed=embed)
        except Exception: pass

@bot.tree.command(name="speak", description="Speak text in your VC")
@app_commands.describe(text="Message", language="Target language")
@app_commands.choices(language=LANG_CHOICES)
async def speak(interaction, text: str, language: app_commands.Choice[str] = None):
    await safe_defer(interaction, ephemeral=True)
    if not ffmpeg_available():
        return await safe_reply(interaction, "❌ FFmpeg missing", ephemeral=True)
    vc = await ensure_voice(interaction)
    if vc is None: return
    lang_code = (language.value if language else "en").lower()
    to_say = text
    if lang_code != "en":
        try:
            to_say = translator.translate(text, src="en", dest=lang_code).text
        except Exception:
            await safe_reply(interaction, "⚠️ Translate failed, using original.", ephemeral=True)
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
        self.add_item(self.title_input); self.add_item(self.message_input)

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
async def send_custom(interaction):
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
            "👋 **Welcome to all our new members!**\n"
            "We’re thrilled to have you join our community! 🎉\n\n"
            "🎮 **What we play:**\n"
            "We’re into just about anything FPS or Survival, plus some RTS "
            "(and yes — Age of Empires IV is goated) and MMO's.\n\n"
            "💬 **Your first steps:**\n"
            "Head over to **#lobby** and introduce yourself — let us know where you came from or what brought you here.\n\n"
            "🪪 Tag **@Blood** to get your role.\n\n"
            "❓ If you have any questions, **@Gravy** will love hearing you yap yap yap.\n\n"
            "🚫 **Rules (short version):** Don’t be annoying, overly sensitive, or spammy. "
            "Avoid @mentioning or DMing people you don’t know, and no self-promo unless approved. "
            "Keep personal info private and absolutely no vegans, piracy, NSFW, or other shady content. "
            "Use common sense — it covers the rest.\n\n"
            f"🔗 **Share our invite:** {VANITY_INVITE}\n\n"
            "Be cool. Have fun. Bring friends."
        ),
    )
    return e

class CopyInviteEphemeralView(View):
    """Shown in the ephemeral response; includes a link button."""
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
            custom_id="shadowsyn:welcome_invite_copy:v1"  # persistent id
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
        if not isinstance(inter.user, discord.Member): return False
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
        try:  # best-effort pin
            await msg.pin(reason="ShadowSyn Welcome")
        except Exception:
            pass
        await safe_reply(interaction, f"✅ Welcome card posted in {dest.mention}.", ephemeral=True)
    except Exception as e:
        await safe_reply(interaction, f"❌ Failed to post: `{e}`", ephemeral=True)

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
        # Try to find a pinned welcome from the bot
        try:
            pins = await dest.pins()
            for m in pins:
                if m.author.id == bot.user.id and m.embeds:
                    if (m.embeds[0].title or "").strip().lower() == "welcome to shadowsyn":
                        msg = m
                        break
        except Exception:
            msg = None
        # If not found in pins, look back a bit
        if msg is None:
            async for m in dest.history(limit=50):
                if m.author.id == bot.user.id and m.embeds:
                    if (m.embeds[0].title or "").strip().lower() == "welcome to shadowsyn":
                        msg = m
                        break

    if msg is None:
        return await safe_reply(interaction, "❌ Couldn’t find a welcome card here. Provide a `message_id` or use `/send_welcome`.", ephemeral=True)

    try:
        await msg.edit(embed=welcome_embed(), view=InviteCopyView())
        await safe_reply(interaction, "✅ Welcome card updated.", ephemeral=True)
    except Exception as e:
        await safe_reply(interaction, f"❌ Failed to update: `{e}`", ephemeral=True)

# ============================ AUDIT LOG ==========================

@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot: return
    target, _ = await resolve_target(bot, config.get("audit_channel_id", DEFAULT_AUDIT_THREAD_ID))
    if not target: return
    if before.channel != after.channel:
        if before.channel and not after.channel:
            msg = f"📤 {member} left {before.channel.name}"
        elif not before.channel and after.channel:
            msg = f"📥 {member} joined {after.channel.name}"
        else:
            msg = f"🔀 {member} moved {before.channel.name} → {after.channel.name}"
        await target.send(msg)
    elif before.self_mute != after.self_mute or before.self_deaf != after.self_deaf:
        await target.send(f"🎛️ {member} toggled mute/deafen")

# ========================= DEPARTURES LOG ========================

_last_departures: Dict[int, float] = {}

def _build_departure_embed(
    subject: Union[discord.Member, discord.User],
    *,
    reason_text: str,                # "Left" | "Kicked" | "Banned"
    executor: Optional[discord.User] = None,
    moderator_reason: Optional[str] = None
) -> discord.Embed:
    rt = reason_text.lower()
    title = "⛔ Member Banned" if rt == "banned" else ("👢 Member Kicked" if rt == "kicked" else "👋 Member Left")

    user_id = subject.id
    mention = f"<@{user_id}>"
    username = str(subject)
    avatar = safe_avatar_url(subject)

    embed = discord.Embed(title=title, color=discord.Color.orange(), timestamp=utcnow())
    if avatar:
        embed.set_thumbnail(url=avatar)

    embed.add_field(
        name="User",
        value=f"{mention}\n{discord.utils.escape_markdown(username)}\n`{user_id}`",
        inline=False
    )

    if isinstance(subject, discord.Member):
        embed.add_field(name="Joined", value=human_ago(subject.joined_at), inline=True)
        roles = [r for r in subject.roles if not r.is_default()]
        top = subject.top_role if roles else None
        top_disp = top.mention if top else "—"
        embed.add_field(name="Top Role", value=f"{top_disp}\n# Roles: {len(roles)}", inline=True)
        embed.add_field(name="Account Age", value=human_ago(subject.created_at), inline=True)
    else:
        embed.add_field(name="Account Age", value=human_ago(subject.created_at), inline=True)

    details_lines = [f"{mention} {rt} the server."]
    if executor:
        details_lines.append(f"By: **{executor}**")
    if moderator_reason:
        details_lines.append(f"Reason: {moderator_reason}")
    embed.add_field(name="Details", value="\n".join(details_lines), inline=False)

    embed.set_footer(text="ShadowSyn • Departures")
    return embed

async def _send_departure_embed(user_id: int, embed: discord.Embed):
    target, _ = await resolve_target(bot, DEPARTURES_THREAD_ID)
    if not target:
        return
    now = time.time()
    if now - _last_departures.get(user_id, 0) < 5:
        return
    _last_departures[user_id] = now
    try:
        await target.send(embed=embed)
    except Exception:
        try:
            await target.send("A member event occurred but the embed could not be sent.")
        except Exception:
            pass

@bot.event
async def on_member_remove(member: discord.Member):
    reason_text = "Left"
    executor = None
    mod_reason = None
    try:
        g = member.guild
        if g.me and g.me.guild_permissions.view_audit_log:
            async for entry in g.audit_logs(limit=6, action=discord.AuditLogAction.kick):
                if entry.target.id == member.id:
                    delta = abs((utcnow() - entry.created_at).total_seconds())
                    if delta < 120:
                        reason_text = "Kicked"
                        executor = entry.user
                        mod_reason = entry.reason
                        break
    except Exception:
        pass

    embed = _build_departure_embed(member, reason_text=reason_text, executor=executor, moderator_reason=mod_reason)
    await _send_departure_embed(member.id, embed)

@bot.event
async def on_member_ban(guild: discord.Guild, user: discord.User):
    executor = None
    ban_reason = None
    try:
        if guild.me and guild.me.guild_permissions.view_audit_log:
            async for entry in guild.audit_logs(limit=6, action=discord.AuditLogAction.ban):
                if entry.target.id == user.id:
                    executor = entry.user
                    ban_reason = entry.reason
                    break
    except Exception:
        pass
    embed = _build_departure_embed(user, reason_text="Banned", executor=executor, moderator_reason=ban_reason)
    await _send_departure_embed(user.id, embed)

# =========== SELF-ASSIGN ROLES: CORE VIEW / LOGIC ===============

def _sorted_opts(options: List[dict]) -> List[dict]:
    return sorted(options, key=lambda o: str(o.get("label", "")).casefold())

def build_role_selects(options: List[dict], *, placeholder: str, mode: str, guild_id: int) -> List[Select]:
    """Build Selects with PERSISTENT custom_id so interactions survive restarts."""
    options = _sorted_opts(options)
    selects: List[Select] = []
    chunk_size = 25
    for i in range(0, len(options), chunk_size):
        chunk = options[i:i+chunk_size]
        chunk_ids = [int(o["role_id"]) for o in chunk]
        sel = Select(
            placeholder=placeholder,
            min_values=0,
            max_values=len(chunk),
            options=[discord.SelectOption(label=o["label"], value=str(o["role_id"])) for o in chunk],
            custom_id=f"ss:roles:{mode}:g{guild_id}:c{i}"
        )
        sel._chunk_ids = set(chunk_ids)    # type: ignore[attr-defined]
        sel._mode = mode                   # type: ignore[attr-defined]
        selects.append(sel)
    return selects

class DualRolePickerView(View):
    def __init__(self, guild: discord.Guild, options: List[dict]):
        super().__init__(timeout=None)
        self.guild = guild
        self.options = _sorted_opts(options)
        self.stage_add: Dict[int, Set[int]] = {}
        self._last_confirm_ts: Dict[int, float] = {}

        for sel in build_role_selects(self.options, placeholder="➕ Add roles…", mode="add", guild_id=guild.id):
            sel.callback = self._on_select  # type: ignore
            self.add_item(sel)

        btn_conf = Button(
            label="Confirm",
            style=discord.ButtonStyle.success,
            row=2,
            custom_id=f"ss:roles:confirm:g{guild.id}"
        )
        btn_conf.callback = self._on_confirm  # type: ignore
        self.add_item(btn_conf)

        btn_remove = Button(
            label="Remove My Roles",
            style=discord.ButtonStyle.secondary,
            row=2,
            custom_id=f"ss:roles:openremove:g{guild.id}"
        )
        btn_remove.callback = self._open_remove_private  # type: ignore
        self.add_item(btn_remove)

    def _allowed_ids(self) -> Set[int]:
        return {int(o["role_id"]) for o in self.options}

    def _member_current_allowed(self, member: discord.Member) -> Set[int]:
        allowed = self._allowed_ids()
        return {r.id for r in member.roles if r.id in allowed}

    async def _on_select(self, interaction: discord.Interaction):
        # Ack quickly
        try:
            if not interaction.response.is_done():
                await interaction.response.defer()
        except Exception:
            pass
        uid = interaction.user.id
        staged = set()
        for item in self.children:
            if isinstance(item, Select):
                staged |= {int(v) for v in (item.values or [])}
        self.stage_add[uid] = staged

    async def _on_confirm(self, interaction: discord.Interaction):
        # Defer immediately to avoid "did not respond"
        await safe_defer(interaction, ephemeral=True)

        # Throttle spam
        now = time.time()
        if now - self._last_confirm_ts.get(interaction.user.id, 0.0) < 1.5:
            return await safe_reply(interaction, "⏱️ Already applied. Give it a sec.", ephemeral=True)
        self._last_confirm_ts[interaction.user.id] = now

        if not interaction.guild:
            return await safe_reply(interaction, "❌ Guild not found.", ephemeral=True)
        member = interaction.guild.get_member(interaction.user.id)
        if not member:
            return await safe_reply(interaction, "❌ Could not resolve member.", ephemeral=True)

        if not interaction.guild.me.guild_permissions.manage_roles:
            return await safe_reply(interaction, "❌ I need **Manage Roles** to do that.", ephemeral=True)

        allowed_ids = self._allowed_ids()
        current_ids = self._member_current_allowed(member)
        staged_add = set(self.stage_add.get(member.id, set())) & allowed_ids
        to_add_ids = list(staged_add - current_ids)

        bot_member = interaction.guild.me
        def manageable(r: discord.Role) -> bool:
            return bot_member.top_role > r and interaction.guild.me.guild_permissions.manage_roles

        added, skipped = [], []
        for rid in to_add_ids:
            role = interaction.guild.get_role(rid)
            if role and manageable(role):
                try:
                    await member.add_roles(role, reason="Self-assign roles panel (add)")
                    added.append(role.name)
                except Exception:
                    skipped.append(role.name if role else str(rid))
            elif role:
                skipped.append(role.name)

        self.stage_add.pop(member.id, None)

        if added:   added   = sorted(added,   key=lambda s: s.casefold())
        if skipped: skipped = sorted(skipped, key=lambda s: s.casefold())

        embed = discord.Embed(title="✅ Roles Updated", color=THEME_PRIMARY, timestamp=utcnow())
        if added:   embed.add_field(name="Added", value=", ".join(added)[:1024], inline=False)
        if skipped: embed.add_field(name="Skipped", value=", ".join(skipped)[:1024] + " (unmanageable)", inline=False)
        if not (added or skipped): embed.description = "No changes."
        embed.set_footer(text="ShadowSyn Role Manager")
        await safe_reply(interaction, embed=embed, ephemeral=True)

    async def _open_remove_private(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await safe_reply(interaction, "❌ Guild not found.", ephemeral=True)
        member = interaction.guild.get_member(interaction.user.id)
        if not member:
            return await safe_reply(interaction, "❌ Could not resolve member.", ephemeral=True)

        current_ids = self._member_current_allowed(member)
        remove_opts = [o for o in self.options if int(o["role_id"]) in current_ids]

        view = PrivateRemoveManager(interaction.guild, remove_opts)
        embed = discord.Embed(
            title="Remove My Roles",
            description="Select the roles you want to remove, then **Confirm**.",
            color=THEME_PRIMARY,
        )
        try:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        except Exception:
            await safe_reply(interaction, "❌ Couldn't open remove manager.", ephemeral=True)

class PrivateRemoveManager(View):
    def __init__(self, guild: discord.Guild, remove_options: List[dict]):
        super().__init__(timeout=300)
        self.guild = guild
        self.remove_stage: Set[int] = set()

        for i, sel in enumerate(build_role_selects(remove_options, placeholder="➖ Remove roles…", mode="remove", guild_id=guild.id)):
            # These selects are ephemeral; custom_ids are still fine
            sel.custom_id = f"ss:roles:remove:g{guild.id}:c{i}"  # type: ignore
            sel.callback = self._on_select  # type: ignore
            self.add_item(sel)

        btn = Button(label="Confirm", style=discord.ButtonStyle.success, custom_id=f"ss:roles:remove_confirm:g{guild.id}")
        btn.callback = self._on_confirm  # type: ignore
        self.add_item(btn)

    async def _on_select(self, interaction: discord.Interaction):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer()
        except Exception:
            pass
        staged = set()
        for item in self.children:
            if isinstance(item, Select):
                staged |= {int(v) for v in (item.values or [])}
        self.remove_stage = staged

    async def _on_confirm(self, interaction: discord.Interaction):
        await safe_defer(interaction, ephemeral=True)
        if not interaction.guild:
            return await safe_reply(interaction, "❌ Guild not found.", ephemeral=True)
        member = interaction.guild.get_member(interaction.user.id)
        if not member:
            return await safe_reply(interaction, "❌ Could not resolve member.", ephemeral=True)

        if not interaction.guild.me.guild_permissions.manage_roles:
            return await safe_reply(interaction, "❌ I need **Manage Roles** to do that.", ephemeral=True)

        bot_member = interaction.guild.me
        def manageable(r: discord.Role) -> bool:
            return bot_member.top_role > r and interaction.guild.me.guild_permissions.manage_roles

        current_ids = {r.id for r in member.roles}
        to_remove_ids = list(self.remove_stage & current_ids)

        removed, skipped = [], []
        for rid in to_remove_ids:
            role = interaction.guild.get_role(rid)
            if role and manageable(role):
                try:
                    await member.remove_roles(role, reason="Self-assign roles panel (private remove)")
                    removed.append(role.name)
                except Exception:
                    skipped.append(role.name if role else str(rid))
            elif role:
                skipped.append(role.name)

        if removed: removed = sorted(removed, key=lambda s: s.casefold())
        if skipped:  skipped  = sorted(skipped,  key=lambda s: s.casefold())

        embed = discord.Embed(title="✅ Roles Updated", color=THEME_PRIMARY, timestamp=utcnow())
        if removed: embed.add_field(name="Removed", value=", ".join(removed)[:1024], inline=False)
        if skipped: embed.add_field(name="Skipped", value=", ".join(skipped)[:1024] + " (unmanageable)", inline=False)
        if not (removed or skipped): embed.description = "No changes."
        embed.set_footer(text="ShadowSyn Role Manager")
        await safe_reply(interaction, embed=embed, ephemeral=True)

def role_picker_embed() -> discord.Embed:
    return discord.Embed(
        title="SELECT ROLES",
        description="Use the dropdowns to **Add** roles, then press **Confirm**.\nNeed to remove something? Tap **Remove My Roles** for a filtered list.",
        color=THEME_PRIMARY,
    )

async def rehydrate_role_panel(client: discord.Client, guild: discord.Guild):
    cfg = get_guild_role_cfg(guild.id)
    if not cfg or not cfg.get("panel"): return
    panel = cfg["panel"]
    options = cfg.get("options", [])
    channel = guild.get_channel(panel.get("channel_id"))
    if not channel:
        try: channel = await client.fetch_channel(panel.get("channel_id"))
        except Exception: return
    try:
        msg = await channel.fetch_message(panel.get("message_id"))
    except Exception:
        return
    # Register persistent view to this message id so interactions survive restarts
    try:
        client.add_view(DualRolePickerView(guild, options), message_id=msg.id)
    except Exception:
        pass
    # Optionally refresh the embed/view if options changed
    try:
        await msg.edit(embed=role_picker_embed(), view=DualRolePickerView(guild, options))
    except Exception:
        pass

# ======== SELF-ASSIGN ROLES: ADMIN COMMANDS (role-locked) =======

ROLE_MENTION_RE = re.compile(r"<@&(\d+)>")
def _parse_role_mentions(text: str) -> List[int]:
    return [int(m) for m in ROLE_MENTION_RE.findall(text or "")]

def _post_roles_panel(dest, guild, options):
    # Helper to post and register persistent view tied to message id
    return DualRolePickerView(guild, options)

@admin_only()
@bot.tree.command(name="roles_post", description="Post the persistent Select Roles panel here or in a target channel/thread.")
@app_commands.describe(target="Optional channel/thread to post in (defaults to here)")
async def roles_post(interaction: discord.Interaction, target: Union[discord.TextChannel, discord.Thread, None] = None):
    await safe_defer(interaction, ephemeral=True)
    guild = interaction.guild
    if not guild: return await safe_reply(interaction, "❌ Guild not found.", ephemeral=True)

    cfg = get_guild_role_cfg(guild.id)
    options = cfg.get("options", [])
    dest = target or interaction.channel
    try:
        view = DualRolePickerView(guild, options)
        msg = await dest.send(embed=role_picker_embed(), view=view)
        cfg["panel"] = {"channel_id": dest.id, "message_id": msg.id}
        set_guild_role_cfg(guild.id, cfg)
        # Register the view persistently to the specific message
        try:
            bot.add_view(DualRolePickerView(guild, options), message_id=msg.id)
        except Exception:
            pass
        await safe_reply(interaction, f"✅ Panel posted in {dest.mention}.", ephemeral=True)
    except Exception as e:
        await safe_reply(interaction, f"❌ Failed: `{e}`", ephemeral=True)

@admin_only()
@bot.tree.command(name="roles_add", description="Add one or more roles to the picker (paste role mentions).")
@app_commands.describe(roles="Role mentions, e.g., @Rust @Battlefield @AoE4")
async def roles_add(interaction: discord.Interaction, roles: str):
    await safe_defer(interaction, ephemeral=True)
    guild = interaction.guild
    if not guild: return await safe_reply(interaction, "❌ Guild not found.", ephemeral=True)

    ids = _parse_role_mentions(roles)
    if not ids: return await safe_reply(interaction, "❌ No role mentions detected.", ephemeral=True)

    cfg = get_guild_role_cfg(guild.id)
    existing_ids = {int(o["role_id"]) for o in cfg.get("options", [])}
    added_labels = []
    for rid in ids:
        if rid in existing_ids: continue
        role = guild.get_role(rid)
        if role is None:
            try: role = await guild.fetch_role(rid)
            except Exception: continue
        cfg.setdefault("options", []).append({"role_id": role.id, "label": role.name})
        added_labels.append(role.name)

    set_guild_role_cfg(guild_id=guild.id, cfg=cfg)
    await safe_reply(interaction, f"✅ Added: {', '.join(sorted(added_labels, key=str.casefold)) or 'None'}", ephemeral=True)

@admin_only()
@bot.tree.command(name="roles_remove", description="Remove one or more roles from the picker (paste role mentions).")
@app_commands.describe(roles="Role mentions, e.g., @Rust @AoE4")
async def roles_remove(interaction: discord.Interaction, roles: str):
    await safe_defer(interaction, ephemeral=True)
    guild = interaction.guild
    if not guild: return await safe_reply(interaction, "❌ Guild not found.", ephemeral=True)

    ids = set(_parse_role_mentions(roles))
    if not ids: return await safe_reply(interaction, "❌ No role mentions detected.", ephemeral=True)

    cfg = get_guild_role_cfg(guild.id)
    opts = cfg.get("options", [])
    before = len(opts)
    opts = [o for o in opts if int(o["role_id"]) not in ids]
    cfg["options"] = opts
    set_guild_role_cfg(guild.id, cfg)
    await safe_reply(interaction, f"✅ Removed {before - len(opts)} role(s). Use `/roles_sync` to refresh panel.", ephemeral=True)

@admin_only()
@bot.tree.command(name="roles_list", description="List current picker roles.")
async def roles_list(interaction: discord.Interaction):
    await safe_defer(interaction, ephemeral=True)
    guild = interaction.guild
    cfg = get_guild_role_cfg(guild.id)
    opts = cfg.get("options", [])
    if not opts: return await safe_reply(interaction, "No roles configured.", ephemeral=True)
    lines = [f"- {o['label']} (`{o['role_id']}`)" for o in _sorted_opts(opts)]
    await safe_reply(interaction, "\n".join(lines), ephemeral=True)

@admin_only()
@bot.tree.command(name="roles_clear", description="Clear all roles from the picker (panel remains).")
async def roles_clear(interaction: discord.Interaction):
    await safe_defer(interaction, ephemeral=True)
    guild = interaction.guild
    cfg = get_guild_role_cfg(guild.id)
    cfg["options"] = []
    set_guild_role_cfg(guild.id, cfg)
    await safe_reply(interaction, "✅ Cleared options. Use `/roles_sync` to refresh panel.", ephemeral=True)

@admin_only()
@bot.tree.command(name="roles_sync", description="Rebuild the posted panel with current options.")
async def roles_sync(interaction: discord.Interaction):
    await safe_defer(interaction, ephemeral=True)
    guild = interaction.guild
    cfg = get_guild_role_cfg(guild.id)
    panel = cfg.get("panel")
    if not panel: return await safe_reply(interaction, "No panel saved. Use `/roles_post` first.", ephemeral=True)

    channel = guild.get_channel(panel.get("channel_id"))
    if not channel:
        try: channel = await bot.fetch_channel(panel.get("channel_id"))
        except Exception: return await safe_reply(interaction, "Saved channel not found.", ephemeral=True)
    try:
        msg = await channel.fetch_message(panel.get("message_id"))
    except Exception:
        return await safe_reply(interaction, "Saved message not found. Repost with `/roles_post`.", ephemeral=True)

    options = cfg.get("options", [])
    try:
        await msg.edit(embed=role_picker_embed(), view=DualRolePickerView(guild, options))
        try:
            bot.add_view(DualRolePickerView(guild, options), message_id=msg.id)
        except Exception:
            pass
        await safe_reply(interaction, "✅ Panel refreshed.", ephemeral=True)
    except Exception as e:
        await safe_reply(interaction, f"❌ Failed: `{e}`", ephemeral=True)

# =================== YOUTUBE WATCHER & COMMANDS ==================

def yt_locked():
    async def predicate(inter: discord.Interaction) -> bool:
        if not isinstance(inter.user, discord.Member): return False
        return any(r.id == ROLE_YT_MANAGER_ID for r in inter.user.roles)
    return app_commands.check(predicate)

_YT_CH_REGEXES = [
    re.compile(r"youtube\.com/channel/([A-Za-z0-9_-]{10,})"),
    re.compile(r"youtube\.com/feeds/videos\.xml\?channel_id=([A-Za-z0-9_-]{10,})"),
]

def yt_feed_url(channel_id: str) -> str:
    return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

async def resolve_channel_id(inp: str) -> Optional[str]:
    text = (inp or "").strip()
    # UC direct
    if re.fullmatch(r"UC[0-9A-Za-z_-]{10,}", text):
        return text
    # channel/ or feeds URL
    for rx in _YT_CH_REGEXES:
        m = rx.search(text)
        if m: return m.group(1)
    # alias cache
    aliased = _lookup_alias(text)
    if aliased: return aliased
    # scrape handle/user
    url = f"https://www.youtube.com/{text}" if text.startswith("@") else text
    if "youtube.com" in url or text.startswith("@"):
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout, headers={"User-Agent": YT_USER_AGENT}) as session:
                async with session.get(url) as r:
                    if r.status != 200: return None
                    html = await r.text()
        except Exception:
            return None
        m = re.search(r'"channelId"\s*:\s*"(?P<uc>UC[0-9A-Za-z_-]{10,})"', html)
        if m: return m.group("uc")
    return None

async def normalize_channel_id(inp: str) -> Optional[str]:
    cid = await resolve_channel_id(inp)
    if cid: return cid
    if re.fullmatch(r"UC[0-9A-Za-z_-]{10,}", (inp or "").strip()): return inp.strip()
    return None

async def fetch_feed_latest(session: aiohttp.ClientSession, channel_id: str) -> Optional[Dict[str, str]]:
    url = yt_feed_url(channel_id)
    try:
        async with session.get(url, headers={"User-Agent": YT_USER_AGENT}) as r:
            if r.status != 200: return None
            text = await r.text()
    except Exception:
        return None
    try:
        ns = {"atom": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015", "media": "http://search.yahoo.com/mrss/"}
        root = ET.fromstring(text)
        entry = root.find("atom:entry", ns)
        if entry is None: return None
        vid  = entry.find("yt:videoId", ns).text
        title = entry.find("media:group/media:title", ns).text
        link_el = entry.find("atom:link", ns)
        link = link_el.attrib.get("href") if link_el is not None else f"https://www.youtube.com/watch?v={vid}"
        ch_title = root.find("atom:title", ns).text
        published = entry.find("atom:published", ns).text
        return {"video_id": vid, "title": title, "url": link, "channel_title": ch_title, "published": published}
    except Exception:
        return None

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
    except Exception:
        try: await target.send(f"{prefix}\n{url}")
        except Exception: pass

async def youtube_watch_loop(client: discord.Client):
    await client.wait_until_ready()

    # seed 'last_video_id' to avoid retro-spam
    store = _load_yt_store()
    async with aiohttp.ClientSession(headers={"User-Agent": YT_USER_AGENT}) as session:
        for ch_id, cfg in list(store.get("channels", {}).items()):
            latest = await fetch_feed_latest(session, ch_id)
            if latest:
                cfg.setdefault("last_video_id", latest["video_id"])
                cfg["channel_title"] = latest.get("channel_title") or cfg.get("channel_title") or ""
                store["channels"][ch_id] = cfg
        _save_yt_store(store)

    while not client.is_closed():
        try:
            store = _load_yt_store()
            channels = store.get("channels", {})
            if not channels:
                await asyncio.sleep(YT_POLL_SECONDS); continue

            async with aiohttp.ClientSession(headers={"User-Agent": YT_USER_AGENT}) as session:
                for ch_id, cfg in list(channels.items()):
                    latest = await fetch_feed_latest(session, ch_id)
                    if not latest:
                        await asyncio.sleep(1.0); continue
                    cfg["channel_title"] = latest.get("channel_title") or cfg.get("channel_title") or ""
                    last = cfg.get("last_video_id")
                    if latest["video_id"] != last:
                        await post_video_announcement(client, latest)
                        cfg["last_video_id"] = latest["video_id"]
                        store["channels"][ch_id] = cfg
                        _save_yt_store(store)
                    await asyncio.sleep(1.0)
        except Exception:
            pass
        await asyncio.sleep(YT_POLL_SECONDS)

# ---- YT commands (locked to ROLE_YT_MANAGER_ID) ----

def yt_locked():
    async def predicate(inter: discord.Interaction) -> bool:
        if not isinstance(inter.user, discord.Member): return False
        return any(r.id == ROLE_YT_MANAGER_ID for r in inter.user.roles)
    return app_commands.check(predicate)

@yt_locked()
@bot.tree.command(name="yt_add", description="Watch a YouTube channel (URL, @handle, or UC id).")
@app_commands.describe(channel_url_or_id="Channel URL or @handle or raw UC id")
async def yt_add(interaction: discord.Interaction, channel_url_or_id: str):
    await safe_defer(interaction, ephemeral=True)
    ch_id = await normalize_channel_id(channel_url_or_id)
    if not ch_id:
        return await safe_reply(interaction, "❌ Couldn’t resolve a channel id.", ephemeral=True)
    store = _load_yt_store(); store.setdefault("channels", {}); store.setdefault("aliases", {})
    store["channels"].setdefault(ch_id, {"last_video_id": None, "channel_title": ""})
    _save_yt_store(store)
    _add_alias(channel_url_or_id, ch_id)  # remember the exact input form
    await safe_reply(interaction, f"✅ Watching `{ch_id}`. New uploads will post in <#{YT_POST_TARGET_ID}>.", ephemeral=True)

@yt_locked()
@bot.tree.command(name="yt_remove", description="Stop watching a YouTube channel (URL, @handle, or UC id).")
@app_commands.describe(channel_id_or_url="Channel URL or @handle or UC id")
async def yt_remove(interaction: discord.Interaction, channel_id_or_url: str):
    await safe_defer(interaction, ephemeral=True)
    ch_id = _lookup_alias(channel_id_or_url) or await normalize_channel_id(channel_id_or_url)
    if not ch_id:
        return await safe_reply(interaction, "❌ Couldn’t resolve a channel id.", ephemeral=True)
    store = _load_yt_store()
    if store.get("channels", {}).pop(ch_id, None) is None:
        return await safe_reply(interaction, "ℹ️ That channel wasn’t being watched.", ephemeral=True)
    store.get("aliases", {}).pop(_alias_key(channel_id_or_url), None)
    _save_yt_store(store)
    await safe_reply(interaction, f"✅ Removed `{ch_id}`.", ephemeral=True)

@yt_locked()
@bot.tree.command(name="yt_list", description="List watched YouTube channels.")
async def yt_list(interaction: discord.Interaction):
    await safe_defer(interaction, ephemeral=True)
    store = _load_yt_store()
    channels = store.get("channels", {})
    if not channels:
        return await safe_reply(interaction, "No channels are being watched.", ephemeral=True)
    lines = []
    for ch_id, cfg in channels.items():
        title = cfg.get("channel_title") or "Unknown"
        last = cfg.get("last_video_id") or "—"
        lines.append(f"- **{title}** (`{ch_id}`) • last: `{last}` → <#{YT_POST_TARGET_ID}>")
    await safe_reply(interaction, "\n".join(lines)[:1990], ephemeral=True)

@yt_locked()
@bot.tree.command(name="yt_test", description="Post the latest upload (URL, @handle, or UC id).")
@app_commands.describe(channel_id_or_url="Channel URL or @handle or UC id")
async def yt_test(interaction: discord.Interaction, channel_id_or_url: str):
    await safe_defer(interaction, ephemeral=True)
    ch_id = _lookup_alias(channel_id_or_url) or await normalize_channel_id(channel_id_or_url)
    if not ch_id:
        return await safe_reply(interaction, "❌ Couldn’t resolve a channel id.", ephemeral=True)
    store = _load_yt_store()
    if ch_id not in store.get("channels", {}):
        return await safe_reply(interaction, "❌ That channel isn’t being watched. Use `/yt_add` first.", ephemeral=True)
    async with aiohttp.ClientSession(headers={"User-Agent": YT_USER_AGENT}) as session:
        latest = await fetch_feed_latest(session, ch_id)
    if not latest:
        return await safe_reply(interaction, "❌ Couldn’t fetch the feed right now.", ephemeral=True)
    await post_video_announcement(bot, latest)
    await safe_reply(interaction, "✅ Posted the latest video to the thread.", ephemeral=True)

# =============================== RUN ============================

def main():
    print("FFMPEG PATH:", which("ffmpeg"))
    print("PERSIST_ROOT:", PERSIST_ROOT)
    bot.run(TOKEN)

if __name__ == "__main__":
    main()
