# bot.py — ShadowSyn Bot (Welcome, Audit, Departures, Speak, Custom Embed)
# Env: DISCORD_TOKEN

import os
import json
import asyncio
import tempfile
from pathlib import Path
from typing import Optional, Tuple, Union, Dict
from uuid import uuid4
from datetime import datetime, timezone, timedelta

import discord
from discord import app_commands
from discord.ui import View, Button, Modal, TextInput
from gtts import gTTS
from shutil import which
from googletrans import Translator

# ============================================================
#                       CONSTANTS
# ============================================================

VANITY_INVITE  = "https://discord.gg/shadowsyn"
THEME_PRIMARY  = 0x2B0B35
LOBBY_NAME     = "lobby"

ARRIVALS_THREAD_ID = 959629903186259978
ROLE_MINION_ID     = 955600021502431233
ROLE_ADMIN_ID      = 1214794734770323466

DEFAULT_TARGET_ID  = 1166874144395247757
SPEAK_LOG_THREAD_ID = 1400048671973703690
DEPARTURES_THREAD_ID = 960088192177029140
DEFAULT_AUDIT_THREAD_ID = 961726632249425930

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise SystemExit("❌ DISCORD_TOKEN is not set in the environment.")

translator = Translator()
LANG_CHOICES = [
    app_commands.Choice(name="English",  value="en"),
    app_commands.Choice(name="Japanese", value="ja"),
    app_commands.Choice(name="German",   value="de"),
    app_commands.Choice(name="Spanish",  value="es"),
]

# ============================================================
#                       CONFIG
# ============================================================

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

# ============================================================
#                       HELPERS
# ============================================================

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
    bot: discord.Client, target_id: int
) -> Tuple[Optional[discord.abc.Messageable], Optional[discord.abc.GuildChannel]]:
    ch = bot.get_channel(target_id)
    if ch is None:
        try:
            ch = await bot.fetch_channel(target_id)
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

# ============================================================
#                   INVITE ATTRIBUTION
# ============================================================

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
        try:
            vanity = guild.vanity_url_code
        except Exception:
            vanity = None
        return f"Joined via Vanity: `{vanity}`" if vanity else None
    try:
        before = _INVITES_CACHE.get(guild.id, {})
        current_invites = await guild.invites()
        increased = None
        for inv in current_invites:
            prev_uses = before.get(inv.code, 0)
            if (inv.uses or 0) > prev_uses:
                increased = inv
                break
        _INVITES_CACHE[guild.id] = {inv.code: (inv.uses or 0) for inv in current_invites}
        if increased:
            inviter = increased.inviter
            inviter_name = f"{inviter}" if inviter else "Unknown"
            return f"Joined via `{increased.code}`, invited by **{inviter_name}**"
        try:
            vanity = guild.vanity_url_code
        except Exception:
            vanity = None
        if vanity:
            return f"Joined via Vanity: `{vanity}`"
        return None
    except Exception:
        return None

# ============================================================
#                   UI VIEWS
# ============================================================

INVITE_BTN_ID = "invite_friends_ephemeral"

class InviteFriendsView(View):
    def __init__(self):
        super().__init__(timeout=None)
        btn = Button(label="Invite Friends", style=discord.ButtonStyle.primary, custom_id=INVITE_BTN_ID)
        btn.callback = self.send_invite_ephemeral
        self.add_item(btn)

    async def send_invite_ephemeral(self, interaction: discord.Interaction):
        text = f"📨 Invite link:\n{VANITY_INVITE}"
        try:
            await interaction.response.send_message(text, ephemeral=True)
        except Exception:
            pass

# ============================================================
#                   BOT CORE
# ============================================================

class ShadowSynBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.voice_states = True
        intents.members = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        for g in self.guilds:
            await _prime_invites_cache(g)
        self.add_view(InviteFriendsView())
        await self.tree.sync()

bot = ShadowSynBot()

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

@bot.event
async def on_guild_join(guild: discord.Guild):
    await _prime_invites_cache(guild)

# ============================================================
#                MEE6 WELCOME REPLACEMENT
# ============================================================

def setup_welcome(bot: discord.Client):
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
                await member.add_roles(role, reason=f"Granted by {interaction.user}")
                await interaction.response.send_message(f"✅ Gave {role.name} to {member.mention}", ephemeral=True)

    async def _send_arrival_card(member: discord.Member):
        if member.bot: return
        dest = bot.get_channel(ARRIVALS_THREAD_ID)
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

# ============================================================
#                /SPEAK (TTS + TRANSLATE + LOG)
# ============================================================

async def ensure_voice(interaction: discord.Interaction) -> Optional[discord.VoiceClient]:
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        return None
    state = interaction.user.voice
    if not state or not state.channel:
        await interaction.response.send_message("❌ Join a VC first.", ephemeral=True)
        return None
    try:
        return await state.channel.connect(reconnect=True, timeout=15)
    except Exception as e:
        await interaction.response.send_message(f"❌ VC error: {e}", ephemeral=True)
        return None

async def log_speak_usage(interaction: discord.Interaction, text: str, lang: str):
    target, _ = await resolve_target(bot, SPEAK_LOG_THREAD_ID)
    if target:
        embed = discord.Embed(title="🗣️ /speak used", color=THEME_PRIMARY)
        embed.add_field(name="User", value=str(interaction.user), inline=False)
        embed.add_field(name="Language", value=lang, inline=True)
        embed.add_field(name="Text", value=text[:1024], inline=False)
        await target.send(embed=embed)

@bot.tree.command(name="speak", description="Speak text in your VC")
@app_commands.describe(text="Message in English", language="Target language")
@app_commands.choices(language=LANG_CHOICES)
async def speak(interaction: discord.Interaction, text: str, language: app_commands.Choice[str] = None):
    await interaction.response.defer(ephemeral=True)
    if not ffmpeg_available():
        return await interaction.followup.send("❌ FFmpeg missing", ephemeral=True)
    vc = await ensure_voice(interaction)
    if vc is None: return
    lang_code = (language.value if language else "en").lower()
    to_say = text
    if lang_code != "en":
        try:
            result = translator.translate(text, src="en", dest=lang_code)
            to_say = result.text
        except Exception: pass
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
            tmp = f.name
        gTTS(text=to_say, lang=lang_code).save(tmp)
        audio = discord.FFmpegPCMAudio(tmp)
        vc.play(audio)
        await log_speak_usage(interaction, text, lang_code)
        await interaction.followup.send("✅ Spoke text", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

# ============================================================
#                CUSTOM EMBED COMMAND
# ============================================================

class CustomEmbedModal(Modal, title="Send Custom Embed"):
    def __init__(self, target_id: int):
        super().__init__(timeout=300)
        self.target_id = target_id
        self.title_input = TextInput(label="Title", max_length=256)
        self.message_input = TextInput(label="Message", style=discord.TextStyle.paragraph, max_length=4000)
        self.add_item(self.title_input); self.add_item(self.message_input)
    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(title=self.title_input.value, description=self.message_input.value, color=THEME_PRIMARY)
        ch = interaction.client.get_channel(self.target_id)
        if ch: await ch.send(embed=embed)
        await interaction.response.send_message("✅ Posted", ephemeral=True)

@bot.tree.command(name="send_custom", description="Send a custom embed here")
async def send_custom(interaction: discord.Interaction):
    await interaction.response.send_modal(CustomEmbedModal(interaction.channel.id))

# ============================================================
#                RUN
# ============================================================

def main():
    print("FFMPEG PATH:", which("ffmpeg"))
    bot.run(TOKEN)

if __name__ == "__main__":
    main()
