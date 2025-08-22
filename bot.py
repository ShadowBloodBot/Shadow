# bot.py — ShadowSyn Bot (Welcome, Audit, Departures, Speak, Custom Embed, Persistent Self-Assign Roles)
# Env: DISCORD_TOKEN

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

# ============================================================
#                       CONSTANTS
# ============================================================

VANITY_INVITE  = "https://discord.gg/shadowsyn"
THEME_PRIMARY  = 0x2B0B35

ARRIVALS_THREAD_ID      = 959629903186259978
ROLE_MINION_ID          = 955600021502431233
ROLE_ADMIN_ID           = 1214794734770323466  # Admin lock for role manager commands

DEFAULT_TARGET_ID       = 1166874144395247757
SPEAK_LOG_THREAD_ID     = 1400048671973703690
DEPARTURES_THREAD_ID    = 960088192177029140
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
#                       CONFIG (welcome/audit)
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
#                  PERSISTENCE (Role Picker)
# ============================================================

ROLE_STORE = Path("role_picker.json")
# {
#   "<guild_id>": {
#       "panel": {"channel_id": int, "message_id": int},
#       "options": [{"role_id": int, "label": "Rust"}, ...]
#   }
# }

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

def get_guild_role_cfg(guild_id: int) -> dict:
    store = _load_role_store()
    cfg = store.get(str(guild_id), {"panel": None, "options": []})
    # Always present options sorted by label (case-insensitive)
    cfg["options"] = sorted(
        cfg.get("options", []),
        key=lambda o: str(o.get("label", "")).casefold()
    )
    return cfg

def set_guild_role_cfg(guild_id: int, cfg: dict) -> None:
    # Sort before saving to persist alphabetical order
    cfg["options"] = sorted(
        cfg.get("options", []),
        key=lambda o: str(o.get("label", "")).casefold()
    )
    store = _load_role_store()
    store[str(guild_id)] = cfg
    _save_role_store(store)

# ============================================================
#                       SAFE REPLY HELPERS
# ============================================================

async def safe_defer(interaction: discord.Interaction, *, ephemeral: bool = False):
    try:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=ephemeral)
    except Exception:
        pass

async def safe_reply(interaction: discord.Interaction, *args, **kwargs):
    try:
        if not interaction.response.is_done():
            return await interaction.response.send_message(*args, **kwargs)
        else:
            return await interaction.followup.send(*args, **kwargs)
    except Exception:
        return None

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
        vanity = None
        try:
            vanity = guild.vanity_url_code
        except Exception:
            pass
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

# ============================================================
#                   BOT CORE
# ============================================================

class ShadowSynBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        for g in self.guilds:
            await _prime_invites_cache(g)
        await self.tree.sync()
        # Rehydrate role picker panels on startup
        for g in self.guilds:
            try:
                await rehydrate_role_panel(self, g)
            except Exception:
                pass

bot = ShadowSynBot()

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

@bot.event
async def on_guild_join(guild: discord.Guild):
    await _prime_invites_cache(guild)
    try:
        await rehydrate_role_panel(bot, guild)
    except Exception:
        pass

# ============================================================
#                WELCOME REPLACEMENT (Minion)
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
        dest = bot.get_channel(ARRIVALS_THREAD_ID)
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

# ============================================================
#                /SPEAK (TTS + TRANSLATE + LOG)
# ============================================================

async def ensure_voice(interaction: discord.Interaction):
    try:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await safe_reply(interaction, "❌ No guild/member", ephemeral=True)
            return None
        state = interaction.user.voice
        if not state or not state.channel:
            await safe_reply(interaction, "❌ Join a VC first.", ephemeral=True)
            return None
        vc = discord.utils.get(bot.voice_clients, guild=interaction.guild)
        if vc and vc.is_connected():
            if vc.channel.id == state.channel.id:
                return vc
            await vc.move_to(state.channel)
            return vc
        return await state.channel.connect(reconnect=True, timeout=15)
    except Exception as e:
        await safe_reply(interaction, f"❌ VC error: `{e}`", ephemeral=True)
        return None

async def log_speak_usage(interaction, text, lang):
    target, _ = await resolve_target(bot, SPEAK_LOG_THREAD_ID)
    if target:
        embed = discord.Embed(title="🗣️ /speak used", color=THEME_PRIMARY)
        embed.add_field(name="User", value=str(interaction.user), inline=False)
        embed.add_field(name="Language", value=lang, inline=True)
        embed.add_field(name="Text", value=text[:1024], inline=False)
        try:
            await target.send(embed=embed)
        except Exception:
            pass

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

# ============================================================
#                CUSTOM EMBED
# ============================================================

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
                await safe_reply(interaction, f"❌ Failed: `{e}`", ephemeral=True)
                return
        await safe_reply(interaction, "✅ Posted", ephemeral=True)

@bot.tree.command(name="send_custom", description="Send a custom embed here")
async def send_custom(interaction):
    try:
        await interaction.response.send_modal(CustomEmbedModal(interaction.channel.id))
    except Exception:
        await safe_reply(interaction, "❌ Couldn't open modal.", ephemeral=True)

# ============================================================
#                AUDIT LOGGER
# ============================================================

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

# ============================================================
#                DEPARTURES LOGGER
# ============================================================

_last_departures: Dict[int, float] = {}

async def _log_departure(member, reason="Left"):
    target, _ = await resolve_target(bot, DEPARTURES_THREAD_ID)
    if not target: return
    now = datetime.now().timestamp()
    if now - _last_departures.get(member.id, 0) < 5: return
    _last_departures[member.id] = now
    await target.send(f"🚪 {member} {reason}")

@bot.event
async def on_member_remove(member): await _log_departure(member, "Left")
@bot.event
async def on_member_ban(guild, user): await _log_departure(user, "Banned")

# ============================================================
#            SELF-ASSIGN ROLES: CORE VIEW/LOGIC
# ============================================================

def build_role_selects(options: List[dict]) -> List[Select]:
    """Build one or more Selects (Discord cap 25 options per select)."""
    # Sort options alphabetically by label for the UI
    options = sorted(options, key=lambda o: str(o.get("label", "")).casefold())
    selects: List[Select] = []
    chunk_size = 25
    for i in range(0, len(options), chunk_size):
        chunk = options[i:i+chunk_size]
        chunk_ids = [int(o["role_id"]) for o in chunk]
        sel = Select(
            placeholder="Select roles…",
            min_values=0,
            max_values=len(chunk),
            options=[discord.SelectOption(label=o["label"], value=str(o["role_id"])) for o in chunk],
            row=0
        )
        # store chunk ids for staging
        sel._chunk_ids = set(chunk_ids)  # type: ignore[attr-defined]
        selects.append(sel)
    return selects

class RolePickerView(View):
    """
    Ultra-minimal:
    - Multi-select dropdown(s)
    - Single Confirm button
    - Select events silently defer and STAGE picks (no auto-apply)
    - Confirm applies staged deltas once (debounced) with a success summary (EMBED)
    """
    def __init__(self, guild: discord.Guild, options: List[dict]):
        super().__init__(timeout=None)
        self.guild = guild
        # Keep options sorted
        self.options = sorted(options, key=lambda o: str(o.get("label", "")).casefold())
        self.staged: Dict[int, Set[int]] = {}        # user_id -> staged role_ids
        self._last_confirm_ts: Dict[int, float] = {} # anti-spam per user

        for sel in build_role_selects(self.options):
            sel.callback = self._on_select  # type: ignore
            self.add_item(sel)

        btn_conf = Button(label="Confirm", style=discord.ButtonStyle.success, row=2)
        btn_conf.callback = self._on_confirm  # type: ignore
        self.add_item(btn_conf)

    def _allowed_ids(self) -> Set[int]:
        return {int(o["role_id"]) for o in self.options}

    def _member_current_allowed(self, member: discord.Member) -> Set[int]:
        allowed = self._allowed_ids()
        return {r.id for r in member.roles if r.id in allowed}

    def _gather_live_values(self) -> Set[int]:
        picked: Set[int] = set()
        for item in self.children:
            if isinstance(item, Select) and item.values:
                picked.update(int(v) for v in item.values)
        return picked

    async def _on_select(self, interaction: discord.Interaction):
        # Quietly acknowledge to avoid "Interaction failed"
        try:
            await interaction.response.defer()
        except Exception:
            pass

        user_id = interaction.user.id
        current: Set[int] = set(self.staged.get(user_id, set()))

        # Rebuild staged for the chunk that changed
        for item in self.children:
            if isinstance(item, Select):
                chunk_ids: Set[int] = getattr(item, "_chunk_ids", set())  # type: ignore[attr-defined]
                current -= chunk_ids
                if item.values:
                    current |= {int(v) for v in item.values}

        self.staged[user_id] = current

    async def _on_confirm(self, interaction: discord.Interaction):
        now = time.time()
        last = self._last_confirm_ts.get(interaction.user.id, 0.0)
        if now - last < 1.5:
            return await safe_reply(interaction, "⏱️ Already applied. Give it a sec.", ephemeral=True)
        self._last_confirm_ts[interaction.user.id] = now

        member = interaction.guild.get_member(interaction.user.id) if interaction.guild else None
        if not member:
            return await safe_reply(interaction, "❌ Could not resolve member.", ephemeral=True)

        # If user never staged, use live values from selects
        desired: Set[int] = set(self.staged.get(member.id, set()))
        if not desired:
            desired = self._gather_live_values()
            self.staged[member.id] = desired

        allowed_ids: Set[int] = self._allowed_ids()
        current_ids: Set[int] = self._member_current_allowed(member)

        to_add_ids = list(desired - current_ids)
        to_remove_ids = list(current_ids - desired)

        bot_member = interaction.guild.me
        def manageable(r: discord.Role) -> bool:
            return bot_member.top_role > r and interaction.guild.me.guild_permissions.manage_roles

        # Disable Confirm during apply
        for c in self.children:
            if isinstance(c, Button) and c.label == "Confirm":
                c.disabled = True
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass

        added, removed, skipped = [], [], []

        # Adds
        for rid in to_add_ids:
            role = interaction.guild.get_role(rid)
            if role and manageable(role):
                try:
                    await member.add_roles(role, reason="Self-assign roles panel")
                    added.append(role.name)
                except Exception:
                    skipped.append(role.name if role else str(rid))
            elif role:
                skipped.append(role.name)
        # Removes
        for rid in to_remove_ids:
            role = interaction.guild.get_role(rid)
            if role and manageable(role):
                try:
                    await member.remove_roles(role, reason="Self-assign roles panel")
                    removed.append(role.name)
                except Exception:
                    skipped.append(role.name if role else str(rid))
            elif role:
                skipped.append(role.name)

        # reset staged for this user
        self.staged.pop(member.id, None)

        # ===== NEW: Confirm-success EMBED =====
        # Sort names in the summary for readability
        if added:  added  = sorted(added,  key=lambda s: s.casefold())
        if removed: removed = sorted(removed, key=lambda s: s.casefold())
        if skipped: skipped = sorted(skipped, key=lambda s: s.casefold())

        embed = discord.Embed(
            title="✅ Roles Updated",
            color=THEME_PRIMARY,
            timestamp=utcnow()
        )
        if added:
            embed.add_field(name="Added", value=", ".join(added)[:1024], inline=False)
        if removed:
            embed.add_field(name="Removed", value=", ".join(removed)[:1024], inline=False)
        if skipped:
            embed.add_field(name="Skipped", value=", ".join(skipped)[:1024] + " (unmanageable)", inline=False)
        if not (added or removed or skipped):
            embed.description = "No changes."

        embed.set_footer(text="ShadowSyn Role Manager")

        await safe_reply(interaction, embed=embed, ephemeral=True)

        # Re-enable Confirm after short debounce
        await asyncio.sleep(1.5)
        for c in self.children:
            if isinstance(c, Button) and c.label == "Confirm":
                c.disabled = False
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass

def role_picker_embed() -> discord.Embed:
    return discord.Embed(
        title="SELECT ROLES",
        description="Tick what you want via the dropdown(s), then press **Confirm**.",
        color=THEME_PRIMARY,
    )

async def rehydrate_role_panel(bot: discord.Client, guild: discord.Guild):
    cfg = get_guild_role_cfg(guild.id)
    if not cfg or not cfg.get("panel"):
        return
    panel = cfg["panel"]
    options = cfg.get("options", [])
    channel = guild.get_channel(panel.get("channel_id"))
    if not channel:
        try:
            channel = await bot.fetch_channel(panel.get("channel_id"))
        except Exception:
            return
    try:
        msg = await channel.fetch_message(panel.get("message_id"))
        # Ensure sorted options on rehydrate
        opts_sorted = sorted(options, key=lambda o: str(o.get("label", "")).casefold())
        await msg.edit(embed=role_picker_embed(), view=RolePickerView(guild, opts_sorted))
    except Exception:
        # Message deleted? Admin can /roles_post again.
        pass

# ============================================================
#            SELF-ASSIGN ROLES: ADMIN COMMANDS (LOCKED)
# ============================================================

def admin_only():
    async def predicate(interaction: discord.Interaction) -> bool:
        # HARD LOCK: must have ROLE_ADMIN_ID. No fallback to Administrator permission.
        if not isinstance(interaction.user, discord.Member):
            return False
        return any(r.id == ROLE_ADMIN_ID for r in interaction.user.roles)
    return app_commands.check(predicate)

ROLE_MENTION_RE = re.compile(r"<@&(\d+)>")
def _parse_role_mentions(text: str) -> List[int]:
    return [int(m) for m in ROLE_MENTION_RE.findall(text or "")]

@admin_only()
@bot.tree.command(name="roles_post", description="Post the persistent Select Roles panel here or in a target channel/thread.")
@app_commands.describe(target="Optional channel/thread to post in (defaults to here)")
async def roles_post(
    interaction: discord.Interaction,
    target: Union[discord.TextChannel, discord.Thread, None] = None
):
    await safe_defer(interaction, ephemeral=True)
    guild = interaction.guild
    if not guild:
        return await safe_reply(interaction, "❌ Guild not found.", ephemeral=True)

    cfg = get_guild_role_cfg(guild.id)
    options = cfg.get("options", [])
    dest = target or interaction.channel

    try:
        # Ensure sorted options when posting
        opts_sorted = sorted(options, key=lambda o: str(o.get("label", "")).casefold())
        msg = await dest.send(embed=role_picker_embed(), view=RolePickerView(guild, opts_sorted))
        cfg["panel"] = {"channel_id": dest.id, "message_id": msg.id}
        set_guild_role_cfg(guild.id, cfg)
        await safe_reply(interaction, f"✅ Panel posted in {dest.mention}.", ephemeral=True)
    except Exception as e:
        await safe_reply(interaction, f"❌ Failed: `{e}`", ephemeral=True)

@admin_only()
@bot.tree.command(name="roles_add", description="Add one or more roles to the picker (paste role mentions).")
@app_commands.describe(roles="Role mentions, e.g., @Rust @Battlefield @AoE4")
async def roles_add(interaction: discord.Interaction, roles: str):
    await safe_defer(interaction, ephemeral=True)
    guild = interaction.guild
    if not guild:
        return await safe_reply(interaction, "❌ Guild not found.", ephemeral=True)

    ids = _parse_role_mentions(roles)
    if not ids:
        return await safe_reply(interaction, "❌ No role mentions detected.", ephemeral=True)

    cfg = get_guild_role_cfg(guild.id)
    existing_ids = {int(o["role_id"]) for o in cfg.get("options", [])}
    added_labels = []

    for rid in ids:
        if rid in existing_ids:
            continue
        role = guild.get_role(rid)
        if role is None:
            try:
                role = await guild.fetch_role(rid)
            except Exception:
                continue
        cfg.setdefault("options", []).append({"role_id": role.id, "label": role.name})
        added_labels.append(role.name)

    set_guild_role_cfg(guild.id, cfg)  # persists sorted
    await safe_reply(interaction, f"✅ Added: {', '.join(sorted(added_labels, key=str.casefold)) or 'None'}", ephemeral=True)

@admin_only()
@bot.tree.command(name="roles_remove", description="Remove one or more roles from the picker (paste role mentions).")
@app_commands.describe(roles="Role mentions, e.g., @Rust @AoE4")
async def roles_remove(interaction: discord.Interaction, roles: str):
    await safe_defer(interaction, ephemeral=True)
    guild = interaction.guild
    if not guild:
        return await safe_reply(interaction, "❌ Guild not found.", ephemeral=True)

    ids = set(_parse_role_mentions(roles))
    if not ids:
        return await safe_reply(interaction, "❌ No role mentions detected.", ephemeral=True)

    cfg = get_guild_role_cfg(guild.id)
    opts = cfg.get("options", [])
    before = len(opts)
    opts = [o for o in opts if int(o["role_id"]) not in ids]
    cfg["options"] = opts
    set_guild_role_cfg(guild.id, cfg)  # persists sorted

    removed_count = before - len(opts)
    await safe_reply(interaction, f"✅ Removed {removed_count} role(s). Use `/roles_sync` to refresh panel.", ephemeral=True)

@admin_only()
@bot.tree.command(name="roles_list", description="List current picker roles.")
async def roles_list(interaction: discord.Interaction):
    await safe_defer(interaction, ephemeral=True)
    guild = interaction.guild
    cfg = get_guild_role_cfg(guild.id)
    opts = cfg.get("options", [])
    if not opts:
        return await safe_reply(interaction, "No roles configured.", ephemeral=True)
    # already sorted from getter, but sort again for safety
    lines = [f"- {o['label']} (`{o['role_id']}`)" for o in sorted(opts, key=lambda o: str(o['label']).casefold())]
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
    if not panel:
        return await safe_reply(interaction, "No panel saved. Use `/roles_post` first.", ephemeral=True)

    channel = guild.get_channel(panel.get("channel_id"))
    if not channel:
        try:
            channel = await bot.fetch_channel(panel.get("channel_id"))
        except Exception:
            return await safe_reply(interaction, "Saved channel not found.", ephemeral=True)
    try:
        msg = await channel.fetch_message(panel.get("message_id"))
    except Exception:
        return await safe_reply(interaction, "Saved message not found. Repost with `/roles_post`.", ephemeral=True)

    options = cfg.get("options", [])
    try:
        opts_sorted = sorted(options, key=lambda o: str(o.get("label", "")).casefold())
        await msg.edit(embed=role_picker_embed(), view=RolePickerView(guild, opts_sorted))
        await safe_reply(interaction, "✅ Panel refreshed.", ephemeral=True)
    except Exception as e:
        await safe_reply(interaction, f"❌ Failed: `{e}`", ephemeral=True)

# ============================================================
#                RUN
# ============================================================

def main():
    print("FFMPEG PATH:", which("ffmpeg"))
    bot.run(TOKEN)

if __name__ == "__main__":
    main()
