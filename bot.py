# bot.py — ShadowSyn Welcome + Custom Embed Bot
# + /speak voice TTS (hidden input, VC playback, auto-leave, translation, usage logs)
# + Mee6 welcome replacement (arrivals card + Minion button) + Invite Attribution (member invite / vanity)
# + Diagnostics: /welcome_diag, /welcome_test
# + Voice Audit Logger: /set_audit_channel, /audit_diag, /audit_test  (RESILIENT QUEUE + THREAD SUPPORT + FULL STATE COVERAGE)
# + Departures Logger (leave/kick/ban) -> thread 960088192177029140 with de-dupe
# + /send_custom (auto-posts in the channel/thread used)
# + 🎮 Role Picker panel (reaction-role replacement) with dropdown + admin management (/roles_panel, /roles_add, /roles_remove, /roles_list, /roles_sync_tag)
# Env: DISCORD_TOKEN

import os
import json
import asyncio
import tempfile
from pathlib import Path
from typing import Optional, Tuple, Union, Dict, List
from uuid import uuid4
from datetime import datetime, timezone, timedelta

import discord
from discord import app_commands
from discord.ui import View, Button, Modal, TextInput, Select
from gtts import gTTS
from shutil import which
from googletrans import Translator

# ============================================================
#                       CONSTANTS
# ============================================================

# Server branding
VANITY_INVITE  = "https://discord.gg/shadowsyn"
THEME_PRIMARY  = 0x2B0B35  # blackish purple
THEME_ACCENT   = 0x7A0F2E  # wine red (not heavily used)
LOBBY_NAME     = "lobby"

# Mee6 replacement targets/roles
ARRIVALS_THREAD_ID = 959629903186259978  # where the join card is posted
ROLE_MINION_ID     = 955600021502431233  # Minion role granted by the button
ROLE_ADMIN_ID      = 1214794734770323466 # Admin role allowed to press (and Role Picker access)

# Persistence
CONFIG_PATH        = Path("welcome_config.json")
DEFAULT_TARGET_ID  = 1166874144395247757  # initial welcome thread for /send_welcome

# Permissions / role-gates
MEMBER_ROLE_ID = 955600320287887400  # users must have this to run /speak

# /speak usage log destination (thread)
SPEAK_LOG_THREAD_ID = 1400048671973703690

# Departures (leave/kick/ban) log destination (thread)
DEPARTURES_THREAD_ID = 960088192177029140

# >>> Default Audit Destination (YOUR REQUIRED THREAD)
DEFAULT_AUDIT_THREAD_ID = 961726632249425930

# ===== Role system gate: only this user OR members with ROLE_ADMIN_ID can use Role Picker =====
ALLOWED_ROLE_USER_ID = 482463400929263627  # your user id

def role_feature_allowed(interaction: discord.Interaction) -> bool:
    """Only allow Role Picker if invoker is the whitelisted user or has ROLE_ADMIN_ID."""
    try:
        if interaction.user and interaction.user.id == ALLOWED_ROLE_USER_ID:
            return True
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return False
        return any(r.id == ROLE_ADMIN_ID for r in interaction.user.roles)
    except Exception:
        return False

async def _deny_role_access(interaction: discord.Interaction):
    try:
        await interaction.response.send_message("❌ You’re not allowed to use the Role Picker.", ephemeral=True)
    except discord.InteractionResponded:
        await interaction.followup.send("❌ You’re not allowed to use the Role Picker.", ephemeral=True)

# Token
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise SystemExit("❌ DISCORD_TOKEN is not set in the environment.")

# Language options for /speak
translator = Translator()
LANG_CHOICES = [
    app_commands.Choice(name="English",  value="en"),
    app_commands.Choice(name="Japanese", value="ja"),
    app_commands.Choice(name="German",   value="de"),
    app_commands.Choice(name="Spanish",  value="es"),
]

# ============================================================
#                       CONFIG I/O
# ============================================================

def load_config() -> dict:
    base = {
        "welcome_target_id": DEFAULT_TARGET_ID,
        "audit_channel_id": DEFAULT_AUDIT_THREAD_ID,
        # 🎮 Role Picker persistence
        "assignable_roles": [],   # list of role IDs
        "role_tag": "[Game]",     # /roles_sync_tag scans role names containing this
        "role_picker_title": "Pick Your Game Roles",
        "role_picker_desc": "Select the games you play to get access. Use **Add** or **Remove**.",
        "role_picker_max_select": 10,
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

def has_member_role(interaction: discord.Interaction) -> bool:
    m = interaction.user
    return isinstance(m, discord.Member) and any(r.id == MEMBER_ROLE_ID for r in m.roles)

async def resolve_target(
    bot: discord.Client, target_id: int
) -> Tuple[Optional[discord.abc.Messageable], Optional[discord.abc.GuildChannel]]:
    ch = bot.get_channel(target_id)
    if ch is None:
        try:
            ch = await bot.fetch_channel(target_id)
        except (discord.Forbidden, Exception):
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

def find_text_channel_by_name(guild: discord.Guild, name: str) -> Optional[discord.TextChannel]:
    n = name.lower().strip()
    return discord.utils.find(lambda ch: ch.name.lower() == n, guild.text_channels)

def make_embed(title: str, message: str) -> discord.Embed:
    embed = discord.Embed(title=title[:256], description=message[:4096], color=THEME_PRIMARY)
    embed.set_footer(text="ShadowSyn")
    return embed

def ffmpeg_available() -> bool:
    return which("ffmpeg") is not None

def safe_avatar_url(member: Union[discord.Member, discord.User]) -> Optional[str]:
    try:
        return member.display_avatar.url
    except Exception:
        return None

def utcnow():
    return datetime.now(timezone.utc)

def role_by_id(guild: discord.Guild, rid: int) -> Optional[discord.Role]:
    try:
        return guild.get_role(rid)
    except Exception:
        return None

def ensure_assignable_ids(guild: discord.Guild) -> List[int]:
    """Filter config['assignable_roles'] to those that still exist; save back if pruned."""
    ids = list(dict.fromkeys(int(x) for x in config.get("assignable_roles", []) if isinstance(x, int) or str(x).isdigit()))
    existing = []
    changed = False
    for rid in ids:
        if guild.get_role(int(rid)) is not None:
            existing.append(int(rid))
        else:
            changed = True
    if changed:
        config["assignable_roles"] = existing
        save_config(config)
    return existing

# ============================================================
#                   INVITE ATTRIBUTION (CACHE)
# ============================================================

# guild_id -> {invite_code: uses}
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
            return f"Joined via `{increased.code}`, invited by **{inviter_name}** (uses: {increased.uses or 0})"

        try:
            vanity = guild.vanity_url_code
        except Exception:
            vanity = None
        if vanity:
            return f"Joined via Vanity: `{vanity}`"
        return None
    except Exception:
        return None

async def _on_invite_create(invite: discord.Invite):
    try:
        d = _INVITES_CACHE.setdefault(invite.guild.id, {})
        d[invite.code] = invite.uses or 0
    except Exception:
        pass

async def _on_invite_delete(invite: discord.Invite):
    try:
        d = _INVITES_CACHE.setdefault(invite.guild.id, {})
        d.pop(invite.code, None)
    except Exception:
        pass

# ============================================================
#                       UI VIEWS (INVITE & CUSTOM)
# ============================================================

INVITE_BTN_ID = "invite_friends_ephemeral"

class InviteFriendsView(View):
    def __init__(self):
        super().__init__(timeout=None)  # persistent across restarts
        btn = Button(label="Invite Friends", style=discord.ButtonStyle.primary, custom_id=INVITE_BTN_ID)
        btn.callback = self.send_invite_ephemeral
        self.add_item(btn)

    async def send_invite_ephemeral(self, interaction: discord.Interaction):
        text = (
            "📨 **Invite Friends**\n"
            f"Here’s the server invite:\n{VANITY_INVITE}\n\n"
            "_Tip: Clicking this link in Discord opens the native **Invite Friends** panel._"
        )
        try:
            await interaction.response.send_message(text, ephemeral=True)
        except discord.InteractionResponded:
            try:
                await interaction.followup.send(text, ephemeral=True)
            except Exception:
                pass
        except Exception:
            try:
                await interaction.followup.send(f"Here’s the invite: {VANITY_INVITE}", ephemeral=True)
            except Exception:
                pass

# ----- Custom embed modal + preview flow -----

PREVIEW_STORE: Dict[str, Dict] = {}

class CustomPreviewView(View):
    def __init__(self, key: str):
        super().__init__(timeout=300)
        self.key = key

        post_btn   = Button(label="✅ Post",   style=discord.ButtonStyle.success, custom_id=f"post:{key}")
        edit_btn   = Button(label="✏️ Edit",   style=discord.ButtonStyle.primary, custom_id=f"edit:{key}")
        cancel_btn = Button(label="🗑️ Cancel", style=discord.ButtonStyle.danger,  custom_id=f"cancel:{key}")

        post_btn.callback   = self.post
        edit_btn.callback   = self.edit
        cancel_btn.callback = self.cancel

        self.add_item(post_btn)
        self.add_item(edit_btn)
        self.add_item(cancel_btn)

    async def post(self, interaction: discord.Interaction):
        data = PREVIEW_STORE.get(self.key)
        if not data or data.get("user_id") != interaction.user.id:
            await interaction.response.send_message("❌ Preview expired. Please run `/send_custom` again.", ephemeral=True)
            return

        target_obj, _ = await resolve_target(interaction.client, data["target_id"])
        if not target_obj:
            await interaction.response.send_message("❌ I can’t access that channel/thread anymore.", ephemeral=True)
            return

        try:
            await target_obj.send(embed=make_embed(data["title"], data["message"]))
            await interaction.response.edit_message(content="✅ Posted.", view=None, embed=None)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don’t have permission to send there.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to post: `{e}`", ephemeral=True)
        finally:
            PREVIEW_STORE.pop(self.key, None)

    async def edit(self, interaction: discord.Interaction):
        data = PREVIEW_STORE.get(self.key)
        if not data or data.get("user_id") != interaction.user.id:
            await interaction.response.send_message("❌ Preview expired. Please run `/send_custom` again.", ephemeral=True)
            return

        try:
            await interaction.response.send_modal(CustomEmbedModal(
                key=self.key,
                target_id=data["target_id"],
                title_default=data["title"],
                message_default=data["message"]
            ))
        except Exception as e:
            await interaction.followup.send(f"❌ Could not open modal: `{e}`", ephemeral=True)

    async def cancel(self, interaction: discord.Interaction):
        PREVIEW_STORE.pop(self.key, None)
        try:
            await interaction.response.edit_message(content="❎ Cancelled.", view=None, embed=None)
        except Exception:
            try:
                await interaction.followup.send("❎ Cancelled.", ephemeral=True)
            except Exception:
                pass

class CustomEmbedModal(Modal, title="Send Custom Embed"):
    def __init__(self, key: Optional[str], target_id: int, title_default: str = "", message_default: str = ""):
        super().__init__(timeout=300)
        self.key = key or str(uuid4())
        self.target_id = target_id

        self.title_input = TextInput(
            label="Title", placeholder="Embed title",
            default=title_default[:256], max_length=256, required=True
        )
        self.message_input = TextInput(
            label="Message", placeholder="Type your embed message. Use Shift+Enter for new lines.",
            style=discord.TextStyle.paragraph, default=message_default[:4000] if message_default else None,
            max_length=4000, required=True
        )

        self.add_item(self.title_input)
        self.add_item(self.message_input)

    async def on_submit(self, interaction: discord.Interaction):
        PREVIEW_STORE[self.key] = {
            "guild_id": interaction.guild_id,
            "user_id": interaction.user.id,
            "target_id": self.target_id,
            "title": str(self.title_input.value),
            "message": str(self.message_input.value),
        }

        embed = make_embed(PREVIEW_STORE[self.key]["title"], PREVIEW_STORE[self.key]["message"])
        view = CustomPreviewView(self.key)

        try:
            await interaction.response.send_message("👀 **Preview** — Post when ready.", embed=embed, view=view, ephemeral=True)
        except discord.InteractionResponded:
            await interaction.followup.send("👀 **Preview** — Post when ready.", embed=embed, view=view, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Could not show preview: `{e}`", ephemeral=True)

# ============================================================
#                       🎮 ROLE PICKER (REACTION-ROLE REPLACEMENT)
# ============================================================

ROLE_PANEL_BUTTON_ID = "roles:open_picker"

def _assignable_role_objects(guild: discord.Guild) -> List[discord.Role]:
    ids = ensure_assignable_ids(guild)
    roles: List[discord.Role] = []
    for rid in ids:
        r = guild.get_role(int(rid))
        if r:
            roles.append(r)
    # Keep options sorted alphabetically for UX
    roles.sort(key=lambda r: r.name.lower())
    return roles

class RolePickerEphemeral(View):
    """Ephemeral dynamic picker with multi-select + Add/Remove buttons."""
    def __init__(self, guild: discord.Guild, member: discord.Member, page: int = 0):
        super().__init__(timeout=300)
        self.guild = guild
        self.member = member
        self.page = page

        roles = _assignable_role_objects(guild)
        # Pagination (25 max options per Select)
        chunk = 25
        pages = max(1, (len(roles) + chunk - 1) // chunk)
        self.total_pages = pages
        start = page * chunk
        end = start + chunk
        page_roles = roles[start:end]

        options = []
        for r in page_roles:
            options.append(discord.SelectOption(label=r.name[:100], value=str(r.id), default=(r in member.roles)))

        max_select = max(1, min(config.get("role_picker_max_select", 10), 25))
        self.select = Select(placeholder="Choose game roles…", min_values=0, max_values=min(max_select, len(options)), options=options)
        self.select.callback = self._noop  # we rely on buttons to apply
        self.add_item(self.select)

        add_btn = Button(label="✅ Add Selected", style=discord.ButtonStyle.success)
        rem_btn = Button(label="🗑️ Remove Selected", style=discord.ButtonStyle.danger)
        add_btn.callback = self._add_selected
        rem_btn.callback = self._remove_selected
        self.add_item(add_btn)
        self.add_item(rem_btn)

        if pages > 1:
            prev_btn = Button(label="◀️ Prev", style=discord.ButtonStyle.secondary)
            next_btn = Button(label="Next ▶️", style=discord.ButtonStyle.secondary)
            prev_btn.callback = self._prev
            next_btn.callback = self._next
            self.add_item(prev_btn)
            self.add_item(next_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not role_feature_allowed(interaction):
            await _deny_role_access(interaction)
            return False
        return True

    async def _noop(self, interaction: discord.Interaction):
        # No-op so users can change selections before applying
        await interaction.response.defer(ephemeral=True)

    async def _apply(self, interaction: discord.Interaction, add: bool):
        await interaction.response.defer(ephemeral=True, thinking=True)
        chosen_ids = [int(v) for v in self.select.values]
        roles_map = {r.id: r for r in _assignable_role_objects(self.guild)}

        to_add = []
        to_remove = []
        for rid in chosen_ids:
            r = roles_map.get(rid)
            if not r:
                continue
            if add:
                if r not in self.member.roles:
                    to_add.append(r)
            else:
                if r in self.member.roles:
                    to_remove.append(r)

        # Safety: bot perms & role position
        me = self.guild.me
        if not me or not me.guild_permissions.manage_roles:
            return await interaction.followup.send("❌ I need **Manage Roles**.", ephemeral=True)

        def role_managable(r: discord.Role) -> bool:
            try:
                return me.top_role > r and not r.managed
            except Exception:
                return False

        to_add = [r for r in to_add if role_managable(r)]
        to_remove = [r for r in to_remove if role_managable(r)]

        results = []
        try:
            if to_add:
                await self.member.add_roles(*to_add, reason=f"Role Picker ({interaction.user})")
                results.append(f"Added: " + ", ".join(f"**{r.name}**" for r in to_add))
            if to_remove:
                await self.member.remove_roles(*to_remove, reason=f"Role Picker ({interaction.user})")
                results.append(f"Removed: " + ", ".join(f"**{r.name}**" for r in to_remove))
            if not results:
                results.append("No changes.")
        except discord.Forbidden:
            results = ["❌ I don't have permission or my role is too low."]
        except Exception as e:
            results = [f"❌ Error: {e}"]

        await interaction.followup.send("\n".join(results), ephemeral=True)

    async def _add_selected(self, interaction: discord.Interaction):
        await self._apply(interaction, add=True)

    async def _remove_selected(self, interaction: discord.Interaction):
        await self._apply(interaction, add=False)

    async def _prev(self, interaction: discord.Interaction):
        new_page = (self.page - 1) % self.total_pages
        view = RolePickerEphemeral(self.guild, self.member, page=new_page)
        title = config.get("role_picker_title", "Pick Your Game Roles")
        desc = f"Page **{new_page+1}/{self.total_pages}** — {config.get('role_picker_desc','Select roles.')}"
        embed = discord.Embed(title=title, description=desc, color=THEME_PRIMARY)
        await interaction.response.edit_message(embed=embed, view=view)

    async def _next(self, interaction: discord.Interaction):
        new_page = (self.page + 1) % self.total_pages
        view = RolePickerEphemeral(self.guild, self.member, page=new_page)
        title = config.get("role_picker_title", "Pick Your Game Roles")
        desc = f"Page **{new_page+1}/{self.total_pages}** — {config.get('role_picker_desc','Select roles.')}"
        embed = discord.Embed(title=title, description=desc, color=THEME_PRIMARY)
        await interaction.response.edit_message(embed=embed, view=view)

class RolePanelPersistent(View):
    """Persistent panel with a single button that opens the ephemeral picker."""
    def __init__(self):
        super().__init__(timeout=None)
        open_btn = Button(label="🎮 Open Role Picker", style=discord.ButtonStyle.primary, custom_id=ROLE_PANEL_BUTTON_ID)
        open_btn.callback = self._open_picker
        self.add_item(open_btn)

    async def _open_picker(self, interaction: discord.Interaction):
        if not role_feature_allowed(interaction):
            return await _deny_role_access(interaction)
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Not in a guild.", ephemeral=True)
        title = config.get("role_picker_title", "Pick Your Game Roles")
        desc = config.get("role_picker_desc", "Select roles and press **Add** or **Remove**.")
        embed = discord.Embed(title=title, description=desc, color=THEME_PRIMARY)
        try:
            await interaction.response.send_message(embed=embed, view=RolePickerEphemeral(interaction.guild, interaction.user), ephemeral=True)
        except discord.InteractionResponded:
            await interaction.followup.send(embed=embed, view=RolePickerEphemeral(interaction.guild, interaction.user), ephemeral=True)

# ============================================================
#                       BOT CORE
# ============================================================

# ---------- AUDIT PIPELINE (SUPER FIX) ----------
_AUDIT_QUEUE: asyncio.Queue = asyncio.Queue(maxsize=1000)
_AUDIT_WORKER_TASK: Optional[asyncio.Task] = None

async def _get_audit_target(guild: discord.Guild) -> Optional[discord.abc.Messageable]:
    chan_id = config.get("audit_channel_id") or DEFAULT_AUDIT_THREAD_ID
    if not chan_id:
        return None

    ch = guild.get_channel(chan_id)
    if ch is None:
        try:
            ch = await guild.fetch_channel(chan_id)
        except Exception:
            return None

    me = guild.me
    if not me:
        return None

    if isinstance(ch, discord.Thread):
        try:
            if ch.archived or ch.locked:
                try:
                    await ch.edit(archived=False, locked=False)
                except discord.Forbidden:
                    pass
            try:
                await ch.join()
            except discord.Forbidden:
                pass
            perms = ch.permissions_for(me)
            if perms.view_channel and perms.send_messages:
                return ch
        except Exception:
            return None

    if isinstance(ch, discord.TextChannel):
        p = ch.permissions_for(me)
        if p.view_channel and p.send_messages and p.embed_links:
            return ch

    return None

def _member_card(title: str, member: discord.Member, thumb: Optional[str]=None) -> discord.Embed:
    e = discord.Embed(title=title, color=0x2D7DFF, timestamp=utcnow())
    e.add_field(name="Member", value=f"{member.mention}\n`{member} / {member.id}`", inline=False)
    if thumb:
        e.set_thumbnail(url=thumb)
    return e

async def _find_moderator_for_move(guild: discord.Guild, target_member: discord.Member) -> Optional[discord.Member]:
    if not guild.me or not guild.me.guild_permissions.view_audit_log:
        return None
    await asyncio.sleep(1.0)
    try:
        async for entry in guild.audit_logs(limit=8):
            if entry.action in (discord.AuditLogAction.member_move, discord.AuditLogAction.member_disconnect):
                if getattr(entry.target, "id", None) == target_member.id:
                    return entry.user if isinstance(entry.user, discord.Member) else guild.get_member(getattr(entry.user, "id", 0))
    except Exception:
        return None
    return None

async def _audit_worker(bot: "ShadowSynBot"):
    backoff = 0.0
    while True:
        try:
            guild_id, member_id, etype, before_id, after_id = await _AUDIT_QUEUE.get()

            try:
                guild = bot.get_guild(guild_id)
                if guild is None:
                    _AUDIT_QUEUE.task_done(); continue
                dest = await _get_audit_target(guild)
                if dest is None:
                    _AUDIT_QUEUE.task_done(); continue

                try:
                    member = guild.get_member(member_id) or await guild.fetch_member(member_id)
                except discord.NotFound:
                    _AUDIT_QUEUE.task_done(); continue
                except Exception:
                    member = guild.get_member(member_id)

                before_ch = guild.get_channel(before_id) if before_id else None
                after_ch  = guild.get_channel(after_id)  if after_id  else None

                def chfmt(ch):
                    if ch is None: return "`N/A`"
                    mention = getattr(ch, "mention", f"`{ch.id}`")
                    base = f"{mention} (`{ch.id}`)"
                    if hasattr(ch, 'name'):
                        base += f" • **{ch.name}**"
                    return base

                thumb = safe_avatar_url(member)

                embed = None
                moderator = None

                async def _mod_for_member_update():
                    try:
                        if not guild.me.guild_permissions.view_audit_log:
                            return None
                        async for entry in guild.audit_logs(limit=8):
                            if entry.action == discord.AuditLogAction.member_update and getattr(entry.target, "id", None) == member.id:
                                created = entry.created_at.replace(tzinfo=timezone.utc) if entry.created_at.tzinfo is None else entry.created_at
                                if (utcnow() - created).total_seconds() <= 15:
                                    return entry.user if isinstance(entry.user, discord.Member) else guild.get_member(getattr(entry.user, "id", 0))
                    except Exception:
                        return None

                if etype == "join":
                    embed = _member_card("🔊 Member Joined", member, thumb)
                    embed.add_field(name="To", value=chfmt(after_ch), inline=False)

                elif etype == "leave":
                    moderator = await _find_moderator_for_move(guild, member)
                    title = "🔌 Member Disconnected" if moderator else "🔇 Member Left"
                    embed = _member_card(title, member, thumb)
                    embed.add_field(name="From", value=chfmt(before_ch), inline=False)
                    if moderator:
                        embed.add_field(name="Moderator", value=f"{moderator.mention}\n`{moderator} / {moderator.id}`", inline=False)

                elif etype == "move":
                    moderator = await _find_moderator_for_move(guild, member)
                    embed = _member_card("↔️ Member Moved", member, thumb)
                    if moderator:
                        embed.add_field(name="Moderator", value=f"{moderator.mention}\n`{moderator} / {moderator.id}`", inline=False)
                    embed.add_field(name="From", value=chfmt(before_ch), inline=False)
                    embed.add_field(name="To", value=chfmt(after_ch), inline=False)

                elif etype in ("self_mute","self_unmute","self_deaf","self_undeaf","stream_start","stream_stop","video_start","video_stop"):
                    titles = {
                        "self_mute":"🔈 Self Muted", "self_unmute":"🔊 Self Unmuted",
                        "self_deaf":"🙉 Self Deafened", "self_undeaf":"👂 Self Undeafened",
                        "stream_start":"📺 Stream Started", "stream_stop":"🛑 Stream Stopped",
                        "video_start":"🎥 Video Started", "video_stop":"🧿 Video Stopped",
                    }
                    embed = _member_card(titles.get(etype, "🎙️ Voice State"), member, thumb)
                    embed.add_field(name="Channel", value=chfmt(after_ch or before_ch), inline=False)

                elif etype in ("server_mute","server_unmute","server_deaf","server_undeaf"):
                    titles = {
                        "server_mute":"🚫 Server Muted", "server_unmute":"✅ Server Unmuted",
                        "server_deaf":"🚫 Server Deafened", "server_undeaf":"✅ Server Undeafened",
                    }
                    embed = _member_card(titles.get(etype, "🛠️ Voice Moderation"), member, thumb)
                    moderator = await _mod_for_member_update()
                    if moderator:
                        embed.add_field(name="Moderator", value=f"{moderator.mention}\n`{moderator} / {moderator.id}`", inline=False)
                    embed.add_field(name="Channel", value=chfmt(after_ch or before_ch), inline=False)

                if embed is not None:
                    try:
                        await dest.send(embed=embed)
                        backoff = 0.0
                    except discord.HTTPException as he:
                        backoff = min(10.0, (backoff + 1.0))
                        print(f"[AUDIT] HTTPException, backoff {backoff}s: {he}")
                        await asyncio.sleep(backoff)
                    except discord.Forbidden:
                        pass
                    except Exception as send_err:
                        print(f"[AUDIT] Send error: {send_err}")

            except Exception as inner:
                print(f"[AUDIT] Worker item error: {inner}")

            _AUDIT_QUEUE.task_done()

        except Exception as loop_err:
            print(f"[AUDIT] Worker loop error: {loop_err}")
            await asyncio.sleep(1.0)

def _start_audit_worker(bot: "ShadowSynBot"):
    global _AUDIT_WORKER_TASK
    if _AUDIT_WORKER_TASK and not _AUDIT_WORKER_TASK.done():
        return
    _AUDIT_WORKER_TASK = bot.loop.create_task(_audit_worker(bot))
    def _restart(t: asyncio.Task):
        try:
            exc = t.exception()
            if exc:
                print(f"[AUDIT] Worker crashed: {exc} — restarting")
        except Exception:
            pass
        _start_audit_worker(bot)
    _AUDIT_WORKER_TASK.add_done_callback(_restart)

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
        # persistent views
        self.add_view(InviteFriendsView())
        self.add_view(RolePanelPersistent())
        _start_audit_worker(self)
        await self.tree.sync()

bot = ShadowSynBot()

@bot.event
async def on_ready():
    try:
        for g in bot.guilds:
            dest = await _get_audit_target(g)
            name = getattr(dest, "name", None) or (getattr(dest, "parent", None).name if isinstance(dest, discord.Thread) and dest.parent else "unknown")
            print(f"[AUDIT] Guild: {g.name} -> audit target resolved: {bool(dest)} ({type(dest).__name__ if dest else 'None'}) • {name}")
    except Exception as e:
        print(f"[AUDIT] on_ready diag error: {e}")

    print(f"Logged in as {bot.user} • Members intent={bot.intents.members} • Voice intent={bot.intents.voice_states}")

@bot.event
async def on_guild_join(guild: discord.Guild):
    await _prime_invites_cache(guild)

@bot.event
async def on_invite_create(invite: discord.Invite):
    await _on_invite_create(invite)

@bot.event
async def on_invite_delete(invite: discord.Invite):
    await _on_invite_delete(invite)

# ============================================================
#                MEE6 WELCOME REPLACEMENT (AUTOMATED)
# ============================================================

def setup_welcome(bot: discord.Client):
    class MinionView(View):
        def __init__(self, target_member_id: int):
            super().__init__(timeout=60 * 60 * 24)
            self.target_member_id = target_member_id
            btn = Button(label="Minion", style=discord.ButtonStyle.success)
            btn.callback = self._grant_minion
            self.add_item(btn)

        async def interaction_check(self, interaction: discord.Interaction) -> bool:
            guild = interaction.guild
            if not guild:
                await interaction.response.send_message("Guild not found.", ephemeral=True)
                return False
            invoker = guild.get_member(interaction.user.id)
            if not invoker:
                await interaction.response.send_message("Member not found.", ephemeral=True)
                return False
            has_admin_role = any(r.id == ROLE_ADMIN_ID for r in invoker.roles)
            if has_admin_role or invoker.guild_permissions.manage_roles:
                return True
            await interaction.response.send_message("You don’t have permission to give roles.", ephemeral=True)
            return False

        async def _grant_minion(self, interaction: discord.Interaction):
            guild = interaction.guild
            if not guild:
                return await interaction.response.send_message("Guild not found.", ephemeral=True)
            target_member = guild.get_member(self.target_member_id)
            if not target_member:
                return await interaction.response.send_message("Member not found.", ephemeral=True)
            minion_role = guild.get_role(ROLE_MINION_ID)
            if not minion_role:
                return await interaction.response.send_message(f"Minion role `{ROLE_MINION_ID}` not found.", ephemeral=True)
            try:
                if minion_role in target_member.roles:
                    await interaction.response.send_message(f"{target_member.mention} already has **{minion_role.name}**.", ephemeral=True)
                else:
                    await target_member.add_roles(minion_role, reason=f"Granted by {interaction.user} via Welcome button")
                    await interaction.response.send_message(f"✅ Gave **{minion_role.name}** to {target_member.mention}.", ephemeral=True)
                    try:
                        if interaction.message:
                            view = View.from_message(interaction.message)
                            for item in view.children:
                                if isinstance(item, Button):
                                    item.disabled = True
                            await interaction.message.edit(view=view)
                    except Exception:
                        pass
            except discord.Forbidden:
                await interaction.response.send_message("I need **Manage Roles**, and my top role must be **above** Minion.", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"Unexpected error: {e}", ephemeral=True)

        async def on_timeout(self):
            for child in self.children:
                if isinstance(child, Button):
                    child.disabled = True

    async def _send_arrival_card(member: discord.Member):
        if member.bot:
            return

        dest = bot.get_channel(ARRIVALS_THREAD_ID)
        if dest is None:
            try:
                dest = await bot.fetch_channel(ARRIVALS_THREAD_ID)
            except Exception:
                dest = None

        me = member.guild.me
        target: Optional[discord.abc.Messageable] = None

        if isinstance(dest, discord.Thread):
            try:
                if dest.archived or dest.locked:
                    await dest.edit(archived=False, locked=False)
                await dest.join()
            except Exception:
                pass
            p = dest.permissions_for(me)
            if p.view_channel and p.send_messages and p.embed_links:
                target = dest

        elif isinstance(dest, discord.TextChannel):
            p = dest.permissions_for(me)
            if p.view_channel and p.send_messages and p.embed_links:
                target = dest

        if target is None:
            target = member.guild.system_channel

        if target is None:
            print("[ARRIVALS] No writable destination found.")
            return

        invite_line = await _detect_join_source(member)  # may be None

        icon = safe_avatar_url(member)
        embed = discord.Embed(
            description=f"{member.mention} joined **{member.guild.name}**",
            color=discord.Color.dark_theme()
        )
        embed.set_author(name=str(member), icon_url=icon)
        if invite_line:
            embed.add_field(name="Joined Via", value=invite_line, inline=False)
        embed.set_footer(text="Tap the button below to grant Minion")

        view = MinionView(member.id)

        try:
            await target.send(embed=embed, view=view)
            print(f"[ARRIVALS] Posted card for {member} in #{getattr(target, 'name', 'thread')}")
        except discord.Forbidden:
            print("[ARRIVALS] Forbidden to send in target.")
            try:
                if member.guild.system_channel:
                    await member.guild.system_channel.send(
                        f"⚠️ I couldn't post in arrivals `{ARRIVALS_THREAD_ID}`. "
                        f"Give me **View**, **Send**, **Embed Links**, **Send in Threads**."
                    )
            except Exception:
                pass
        except Exception as e:
            print(f"[ARRIVALS] Unexpected send error: {e}")

    @bot.event
    async def on_member_join(member: discord.Member):
        if _can_track_invites(member.guild):
            try:
                await _prime_invites_cache(member.guild)
            except Exception:
                pass
        print(f"[JOIN] {member} joined (id={member.id})")
        await _send_arrival_card(member)

setup_welcome(bot)

# ============================================================
#                 VOICE AUDIT LOGGER (JOIN/LEAVE/MOVE + STATES)
# ============================================================

@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    try:
        if member.bot:
            return

        events = []

        if before.channel is None and after.channel is not None:
            events.append({"type": "join", "before_id": None, "after_id": after.channel.id})
        elif before.channel is not None and after.channel is None:
            events.append({"type": "leave", "before_id": before.channel.id, "after_id": None})
        elif (before.channel is not None and after.channel is not None and before.channel.id != after.channel.id):
            events.append({"type": "move", "before_id": before.channel.id, "after_id": after.channel.id})

        if before.self_mute != after.self_mute:
            events.append({"type": "self_mute" if after.self_mute else "self_unmute",
                           "before_id": getattr(before.channel, "id", None), "after_id": getattr(after.channel, "id", None)})
        if before.self_deaf != after.self_deaf:
            events.append({"type": "self_deaf" if after.self_deaf else "self_undeaf",
                           "before_id": getattr(before.channel, "id", None), "after_id": getattr(after.channel, "id", None)})
        if before.self_stream != after.self_stream:
            events.append({"type": "stream_start" if after.self_stream else "stream_stop",
                           "before_id": getattr(before.channel, "id", None), "after_id": getattr(after.channel, "id", None)})
        if getattr(before, "self_video", False) != getattr(after, "self_video", False):
            events.append({"type": "video_start" if getattr(after, "self_video", False) else "video_stop",
                           "before_id": getattr(before.channel, "id", None), "after_id": getattr(after.channel, "id", None)})

        if before.mute != after.mute:
            events.append({"type": "server_mute" if after.mute else "server_unmute",
                           "before_id": getattr(before.channel, "id", None), "after_id": getattr(after.channel, "id", None)})
        if before.deaf != after.deaf:
            events.append({"type": "server_deaf" if after.deaf else "server_undeaf",
                           "before_id": getattr(before.channel, "id", None), "after_id": getattr(after.channel, "id", None)})

        if not events:
            return

        for ev in events:
            payload = (member.guild.id, member.id, ev["type"], ev["before_id"], ev["after_id"])
            try:
                _AUDIT_QUEUE.put_nowait(payload)
            except asyncio.QueueFull:
                try:
                    _ = _AUDIT_QUEUE.get_nowait()
                    _AUDIT_QUEUE.task_done()
                except Exception:
                    pass
                try:
                    _AUDIT_QUEUE.put_nowait(payload)
                except Exception:
                    pass

    except Exception as e:
        print(f"[VOICE] on_voice_state_update error: {e}")

@bot.tree.command(name="set_audit_channel", description="Bind audit logs to this channel.")
@app_commands.checks.has_permissions(administrator=True)
async def set_audit_channel(interaction: discord.Interaction):
    ch = interaction.channel
    if not isinstance(ch, (discord.TextChannel, discord.Thread)):
        return await interaction.response.send_message("Run this inside a text channel or a thread.", ephemeral=True)
    config["audit_channel_id"] = ch.id
    save_config(config)
    await interaction.response.send_message(f"✅ Audit destination set to **{getattr(ch,'name','unknown')}** (`{ch.id}`).", ephemeral=True)

@bot.tree.command(name="audit_diag", description="Check audit log setup & permissions.")
@app_commands.checks.has_permissions(administrator=True)
async def audit_diag(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)
    guild = interaction.guild
    if not guild:
        return await interaction.followup.send("Not in a guild.", ephemeral=True)

    chan_cfg = config.get("audit_channel_id") or DEFAULT_AUDIT_THREAD_ID
    dest = await _get_audit_target(guild)
    e = discord.Embed(title="Audit Logger Diagnostics", color=THEME_PRIMARY)
    e.add_field(name="Configured ID", value=str(chan_cfg), inline=False)
    e.add_field(name="Resolved", value=str(bool(dest)), inline=True)
    e.add_field(name="Can View Audit Log", value=str(guild.me.guild_permissions.view_audit_log), inline=True)
    if isinstance(dest, discord.Thread):
        p = dest.permissions_for(guild.me)
        e.add_field(name="Type", value="Thread", inline=True)
        e.add_field(name="archived", value=str(dest.archived), inline=True)
        e.add_field(name="locked", value=str(dest.locked), inline=True)
        e.add_field(name="send_messages", value=str(p.send_messages), inline=True)
    elif isinstance(dest, discord.TextChannel):
        p = dest.permissions_for(guild.me)
        e.add_field(name="Type", value="TextChannel", inline=True)
        e.add_field(name="view_channel", value=str(p.view_channel), inline=True)
        e.add_field(name="send_messages", value=str(p.send_messages), inline=True)
        e.add_field(name="embed_links", value=str(p.embed_links), inline=True)
    await interaction.followup.send(embed=e, ephemeral=True)

@bot.tree.command(name="audit_test", description="Post a sample voice audit card here.")
@app_commands.checks.has_permissions(administrator=True)
async def audit_test(interaction: discord.Interaction):
    e = _member_card("🔧 Audit Test", interaction.user, safe_avatar_url(interaction.user))
    e.add_field(name="From", value="`#unknown`", inline=False)
    e.add_field(name="To", value="`#unknown`", inline=False)
    await interaction.response.send_message(embed=e, ephemeral=False)

# ============================================================
#                       DEPARTURES LOGGER
# ============================================================

_RECENT_DEPARTURES: Dict[int, datetime] = {}

def _recently_logged(user_id: int, window_secs: int = 10) -> bool:
    now = utcnow()
    ts = _RECENT_DEPARTURES.get(user_id)
    if ts and (now - ts) <= timedelta(seconds=window_secs):
        return True
    _RECENT_DEPARTURES[user_id] = now
    return False

async def _resolve_kick_or_ban(guild: discord.Guild, target_id: int, window_seconds: int = 45):
    if not guild.me.guild_permissions.view_audit_log:
        return (None, None, None)
    try:
        now = utcnow()
        async for entry in guild.audit_logs(limit=10, oldest_first=False):
            if not entry.target or getattr(entry.target, "id", None) != target_id:
                continue
            created = entry.created_at.replace(tzinfo=timezone.utc) if entry.created_at.tzinfo is None else entry.created_at
            if (now - created).total_seconds() > window_seconds:
                continue
            if entry.action == discord.AuditLogAction.kick:
                return ("kick", entry.user, entry.reason)
            if entry.action == discord.AuditLogAction.ban:
                return ("ban", entry.user, entry.reason)
    except Exception:
        pass
    return (None, None, None)

def _departure_embed_base(title: str, color: int) -> discord.Embed:
    e = discord.Embed(title=title, color=color, timestamp=utcnow())
    e.set_footer(text="ShadowSyn • Departures")
    return e

async def _send_departure_card(bot: discord.Client, guild: discord.Guild, user: Union[discord.Member, discord.User],
                               title: str, details: str, color: int):
    target, _ = await resolve_target(bot, DEPARTURES_THREAD_ID)
    if not target:
        return
    try:
        embed = _departure_embed_base(title, color)
        avatar = safe_avatar_url(user)
        if avatar:
            embed.set_thumbnail(url=avatar)

        if isinstance(user, discord.Member):
            joined = user.joined_at or utcnow()
            top_role = user.top_role.mention if user.top_role else "None"
            embed.add_field(name="User", value=f"{user.mention}\n`{user} / {user.id}`", inline=False)
            embed.add_field(name="Joined", value=f"<t:{int(joined.timestamp())}:R>", inline=True)
            embed.add_field(name="Top Role", value=top_role, inline=True)
            role_count = len([r for r in user.roles if r.name != "@everyone"])
            embed.add_field(name="# Roles", value=str(role_count), inline=True)
        else:
            embed.add_field(name="User", value=f"`{user} / {user.id}`", inline=False)

        try:
            created = user.created_at
            if created:
                created = created.replace(tzinfo=timezone.utc) if created.tzinfo is None else created
                embed.add_field(name="Account Age", value=f"<t:{int(created.timestamp())}:R>", inline=True)
        except Exception:
            pass

        embed.add_field(name="Details", value=details or "`(none)`", inline=False)
        await target.send(embed=embed)
    except Exception:
        pass

@bot.event
async def on_member_remove(member: discord.Member):
    await asyncio.sleep(1.2)
    if _recently_logged(member.id):
        return

    action, moderator, reason = await _resolve_kick_or_ban(member.guild, member.id, window_seconds=45)
    mod_txt = f" by **{moderator}**" if moderator else ""
    reason_txt = f"\n**Reason:** {reason}" if reason else ""

    if action == "kick":
        await _send_departure_card(
            bot, member.guild, member,
            title="🚪 Member Kicked",
            details=f"{member.mention} was kicked{mod_txt}.{reason_txt}",
            color=discord.Color.orange().value
        )
    elif action == "ban":
        await _send_departure_card(
            bot, member.guild, member,
            title="⛔ Member Banned",
            details=f"{member} was banned{mod_txt}.{reason_txt}",
            color=discord.Color.red().value
        )
    else:
        await _send_departure_card(
            bot, member.guild, member,
            title="👋 Member Left",
            details=f"{member.mention} left the server.",
            color=discord.Color.dark_grey().value
        )

@bot.event
async def on_member_ban(guild: discord.Guild, user: discord.User):
    await asyncio.sleep(0.8)
    if _recently_logged(user.id):
        return

    action, moderator, reason = await _resolve_kick_or_ban(guild, user.id, window_seconds=60)
    mod_txt = f" by **{moderator}**" if moderator else ""
    reason_txt = f"\n**Reason:** {reason}" if reason else ""
    await _send_departure_card(
        bot, guild, user,
        title="⛔ Member Banned",
        details=f"{user} was banned{mod_txt}.{reason_txt}",
        color=discord.Color.red().value
    )

# ============================================================
#                       COMMANDS (WELCOME & CUSTOM)
# ============================================================

def build_welcome_embed(lobby_mention: str) -> discord.Embed:
    desc = (
        "👋 **Welcome to all our new members!**\n"
        "We’re thrilled to have you join our community! 🎉\n\n"
        "🎮 **What we play:**\n"
        "We’re into just about anything FPS or Survival, plus some RTS "
        "(and yes — Age of Empires IV is goated) and MMO's.\n\n"
        "💬 **Your first steps:**\n\n"
        f"Head over to {lobby_mention} and introduce yourself — let us know where you came from or what brought you here.\n\n"
        "Tag **@Blood** to get your role.\n\n"
        "Enjoy your stay! If you have any questions, **@Gravy** will love hearing you yap yap yap.\n\n"
        "Don’t be annoying, overly sensitive, or spammy. Avoid @mentioning or DMing people you don’t know, "
        "and no self-promo unless approved. Keep personal info private and absolutely no vegans, piracy, NSFW, or other shady content. "
        "Use common sense — it covers the rest.\n\n"
        "Spread the love by sharing our server invite link\n"
        f"{VANITY_INVITE}\n"
    )
    embed = discord.Embed(title="Welcome to ShadowSyn", description=desc, color=THEME_PRIMARY)
    embed.set_footer(text="Be cool. Have fun. Bring friends.")
    return embed

@bot.tree.command(name="welcome_diag", description="Diagnose arrivals permissions & config.")
@app_commands.checks.has_permissions(administrator=True)
async def welcome_diag(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)
    guild = interaction.guild
    if not guild:
        return await interaction.followup.send("Not in a guild.", ephemeral=True)

    me = guild.me
    try:
        dest = bot.get_channel(ARRIVALS_THREAD_ID) or await bot.fetch_channel(ARRIVALS_THREAD_ID)
    except Exception:
        dest = None

    where = f"{type(dest).__name__} `{getattr(dest,'name','?')}` ({ARRIVALS_THREAD_ID})" if dest else f"(missing) {ARRIVALS_THREAD_ID}"
    fields = []

    if isinstance(dest, discord.Thread):
        p = dest.permissions_for(me)
        fields += [("view_channel", p.view_channel),
                   ("send_messages (thread)", p.send_messages),
                   ("embed_links", p.embed_links)]
    elif isinstance(dest, discord.TextChannel):
        p = dest.permissions_for(me)
        fields += [("view_channel", p.view_channel),
                   ("send_messages", p.send_messages),
                   ("embed_links", p.embed_links)]
    else:
        fields.append(("channel_accessible", False))

    r = guild.get_role(ROLE_MINION_ID)
    fields.append(("minion_role_found", bool(r)))
    fields.append(("bot_above_minion", me.top_role > r if r else False))
    fields.append(("manage_roles", me.guild_permissions.manage_roles))
    fields.append(("manage_guild (invite tracking)", me.guild_permissions.manage_guild))

    e = discord.Embed(title="Welcome Diagnostics", color=THEME_PRIMARY)
    e.add_field(name="Arrivals target", value=where, inline=False)
    for k, v in fields:
        e.add_field(name=k, value=str(v)), 
    await interaction.followup.send(embed=e, ephemeral=True)

@bot.tree.command(name="welcome_test", description="Post a Minion-button card for a member to the arrivals channel.")
@app_commands.describe(member="Member to show on the test card")
@app_commands.checks.has_permissions(administrator=True)
async def welcome_test(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.defer(ephemeral=True)

    try:
        dest = bot.get_channel(ARRIVALS_THREAD_ID) or await bot.fetch_channel(ARRIVALS_THREAD_ID)
    except Exception:
        dest = None

    me = interaction.guild.me
    target = None
    if isinstance(dest, discord.Thread):
        try:
            if dest.archived or dest.locked:
                await dest.edit(archived=False, locked=False)
            await dest.join()
        except Exception:
            pass
        p = dest.permissions_for(me)
        if p.view_channel and p.send_messages and p.embed_links:
            target = dest
    elif isinstance(dest, discord.TextChannel):
        p = dest.permissions_for(me)
        if p.view_channel and p.send_messages and p.embed_links:
            target = dest
    if target is None:
        target = interaction.guild.system_channel
    if target is None:
        return await interaction.followup.send("No writable destination found.", ephemeral=True)

    join_via = await _detect_join_source(member)
    icon = safe_avatar_url(member)
    embed = discord.Embed(
        description=f"{member.mention} joined **{interaction.guild.name}**",
        color=discord.Color.dark_theme()
    )
    embed.set_author(name=str(member), icon_url=icon)
    if join_via:
        embed.add_field(name="Joined Via", value=join_via, inline=False)
    embed.set_footer(text="Tap the button below to grant Minion")

    class MinionView(View):
        def __init__(self, target_member_id: int):
            super().__init__(timeout=60*60*24)
            self.target_member_id = target_member_id
            btn = Button(label="Minion", style=discord.ButtonStyle.success)
            btn.callback = self._grant_minion
            self.add_item(btn)
        async def interaction_check(self, inter: discord.Interaction) -> bool:
            m = inter.guild.get_member(inter.user.id)
            if m and (any(r.id == ROLE_ADMIN_ID for r in m.roles) or m.guild_permissions.manage_roles):
                return True
            await inter.response.send_message("No permission.", ephemeral=True); return False
        async def _grant_minion(self, inter: discord.Interaction):
            role = inter.guild.get_role(ROLE_MINION_ID)
            tgt = inter.guild.get_member(self.target_member_id)
            if not role or not tgt:
                return await inter.response.send_message("Role/member missing.", ephemeral=True)
            try:
                if role not in tgt.roles:
                    await tgt.add_roles(role, reason=f"Granted by {inter.user} (test)")
                await inter.response.send_message(f"✅ Gave **{role.name}** to {tgt.mention}.", ephemeral=True)
            except Exception as e:
                await inter.response.send_message(f"Error: {e}", ephemeral=True)

    await target.send(embed=embed, view=MinionView(member.id))
    await interaction.followup.send("Posted test card.", ephemeral=True)

# ----- Manual long welcome embed -----
async def send_welcome_impl(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)
    target_id = int(config.get("welcome_target_id") or DEFAULT_TARGET_ID)
    target, _ = await resolve_target(bot, target_id)
    if target is None:
        return await interaction.followup.send(
            "❌ I can’t access the configured welcome target. Run `/set_welcome_target` **in your welcome thread** and try again.",
            ephemeral=True
        )

    lobby_ch = find_text_channel_by_name(interaction.guild, LOBBY_NAME) if interaction.guild else None
    lobby_mention = lobby_ch.mention if lobby_ch else f"#{LOBBY_NAME}"
    embed = build_welcome_embed(lobby_mention)
    view = InviteFriendsView()

    try:
        await target.send(embed=embed, view=view)
        await interaction.followup.send("✅ Welcome message posted.", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("❌ I don’t have permission to send there.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to send: `{e}`", ephemeral=True)

@bot.tree.command(name="send_welcome", description="Post the ShadowSyn welcome embed to the saved target.")
@app_commands.checks.has_permissions(administrator=True)
async def send_welcome(interaction: discord.Interaction):
    await send_welcome_impl(interaction)

@bot.tree.command(name="set_welcome_target", description="Set the current channel/thread as the welcome target.")
@app_commands.checks.has_permissions(administrator=True)
async def set_welcome_target(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)
    ch = interaction.channel
    if not isinstance(ch, (discord.TextChannel, discord.Thread)):
        return await interaction.followup.send("❌ Run this inside a text channel or a thread.", ephemeral=True)
    if isinstance(ch, discord.Thread):
        try:
            if ch.archived or ch.locked:
                await ch.edit(archived=False, locked=False)
            await ch.join()
        except Exception:
            pass
    config["welcome_target_id"] = ch.id
    save_config(config)
    kind = "thread" if isinstance(ch, discord.Thread) else "channel"
    await interaction.followup.send(f"✅ Set welcome target to this {kind}: **#{ch.name}** (`{ch.id}`).", ephemeral=True)

# ======== /send_custom — auto-post HERE ========
@bot.tree.command(
    name="send_custom",
    description="Create a custom embed and post it here (this channel/thread)."
)
@app_commands.checks.has_permissions(administrator=True)
@app_commands.guild_only()
async def send_custom(interaction: discord.Interaction):
    ch = interaction.channel
    if not isinstance(ch, (discord.TextChannel, discord.Thread)):
        return await interaction.response.send_message(
            "❌ Run this in a **text channel** or a **thread** inside a server.",
            ephemeral=True
        )
    me = interaction.guild.me if interaction.guild else None
    if not me:
        return await interaction.response.send_message("❌ Not in a guild.", ephemeral=True)
    if isinstance(ch, discord.Thread):
        try:
            if ch.archived or ch.locked:
                try:
                    await ch.edit(archived=False, locked=False)
                except discord.Forbidden:
                    pass
            try:
                await ch.join()
            except discord.Forbidden:
                pass
        except Exception:
            pass
    perms = ch.permissions_for(me)
    if not (perms.view_channel and perms.send_messages and perms.embed_links):
        return await interaction.response.send_message(
            "❌ I need **View Channel**, **Send Messages**, and **Embed Links** here.",
            ephemeral=True
        )
    try:
        await interaction.response.send_modal(CustomEmbedModal(key=None, target_id=ch.id))
    except Exception as e:
        await interaction.followup.send(f"❌ Could not open modal: `{e}`", ephemeral=True)

# ============================================================
#                       🎮 ROLE PICKER COMMANDS
# ============================================================

def _admin_check(member: discord.Member) -> bool:
    return bool(member.guild_permissions.administrator or any(r.id == ROLE_ADMIN_ID for r in member.roles))

@bot.tree.command(name="roles_panel", description="Post the Role Picker panel here.")
@app_commands.check(role_feature_allowed)   # only your user OR ROLE_ADMIN_ID
@app_commands.guild_only()
async def roles_panel(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    try:
        title = config.get("role_picker_title", "Pick Your Game Roles")
        desc = config.get("role_picker_desc", "Select roles and press **Add** or **Remove**.")
        e = discord.Embed(title=title, description=desc, color=THEME_PRIMARY)
        await interaction.channel.send(embed=e, view=RolePanelPersistent())
        await interaction.followup.send("✅ Posted Role Picker panel.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to post panel: `{e}`", ephemeral=True)

@bot.tree.command(name="roles_add", description="Add a role to the Role Picker allowlist.")
@app_commands.describe(role="The role to make selectable")
@app_commands.check(role_feature_allowed)
@app_commands.guild_only()
async def roles_add(interaction: discord.Interaction, role: discord.Role):
    ids = ensure_assignable_ids(interaction.guild)
    if role.id not in ids:
        ids.append(role.id)
        config["assignable_roles"] = ids
        save_config(config)
        await interaction.response.send_message(f"✅ Added **{role.name}**.", ephemeral=True)
    else:
        await interaction.response.send_message(f"Already present: **{role.name}**.", ephemeral=True)

@bot.tree.command(name="roles_remove", description="Remove a role from the Role Picker allowlist.")
@app_commands.describe(role="The role to remove from the picker")
@app_commands.check(role_feature_allowed)
@app_commands.guild_only()
async def roles_remove(interaction: discord.Interaction, role: discord.Role):
    ids = ensure_assignable_ids(interaction.guild)
    if role.id in ids:
        ids = [x for x in ids if x != role.id]
        config["assignable_roles"] = ids
        save_config(config)
        await interaction.response.send_message(f"🗑️ Removed **{role.name}**.", ephemeral=True)
    else:
        await interaction.response.send_message("That role is not in the picker list.", ephemeral=True)

@bot.tree.command(name="roles_list", description="Show current Role Picker roles.")
@app_commands.check(role_feature_allowed)
@app_commands.guild_only()
async def roles_list(interaction: discord.Interaction):
    ids = ensure_assignable_ids(interaction.guild)
    if not ids:
        return await interaction.response.send_message("No roles configured yet. Use `/roles_add` or `/roles_sync_tag`.", ephemeral=True)
    names = []
    for rid in ids:
        r = interaction.guild.get_role(rid)
        if r:
            names.append(f"- **{r.name}** (`{r.id}`)")
    e = discord.Embed(title="Assignable Roles", description="\n".join(names)[:4000], color=THEME_PRIMARY)
    await interaction.response.send_message(embed=e, ephemeral=True)

@bot.tree.command(name="roles_sync_tag", description="Auto-add all roles containing a tag (default: [Game]).")
@app_commands.describe(tag="Case-insensitive substring to match in role names, e.g. [Game]")
@app_commands.check(role_feature_allowed)
@app_commands.guild_only()
async def roles_sync_tag(interaction: discord.Interaction, tag: Optional[str] = None):
    await interaction.response.defer(ephemeral=True, thinking=True)
    tag = (tag or config.get("role_tag") or "[Game]").strip()
    ids = set(ensure_assignable_ids(interaction.guild))
    added = []
    for r in interaction.guild.roles:
        try:
            if r.name and (tag.lower() in r.name.lower()) and not r.managed and r != interaction.guild.default_role:
                if r.id not in ids:
                    ids.add(r.id)
                    added.append(r.name)
        except Exception:
            continue
    config["assignable_roles"] = list(ids)
    config["role_tag"] = tag
    save_config(config)
    if added:
        await interaction.followup.send(f"✅ Added {len(added)} roles with tag **{tag}**.\n" + ", ".join(f"`{n}`" for n in added)[:1900], ephemeral=True)
    else:
        await interaction.followup.send(f"No new roles matched **{tag}**.", ephemeral=True)

# ============================================================
#                       /SPEAK (TTS + TRANSLATE + LOG)
# ============================================================

async def ensure_voice(interaction: discord.Interaction) -> Optional[discord.VoiceClient]:
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        return None
    state = interaction.user.voice
    if not state or not state.channel:
        await interaction.response.send_message("❌ Join a voice channel first.", ephemeral=True)
        return None
    try:
        if interaction.guild.voice_client and interaction.guild.voice_client.channel != state.channel:
            await interaction.guild.voice_client.move_to(state.channel)
            return interaction.guild.voice_client
        if interaction.guild.voice_client:
            return interaction.guild.voice_client
        return await state.channel.connect(reconnect=True, timeout=15)
    except Exception as e:
        await interaction.response.send_message(f"❌ Can’t join VC: `{e}`", ephemeral=True)
        return None

async def log_speak_usage(interaction: discord.Interaction, original_text: str, lang_code: str):
    target, _ = await resolve_target(bot, SPEAK_LOG_THREAD_ID)
    if not target:
        return

    pretty = next((c.name for c in LANG_CHOICES if c.value == lang_code), lang_code)
    vc_name = (
        interaction.user.voice.channel.mention
        if (isinstance(interaction.user, discord.Member) and interaction.user.voice and interaction.user.voice.channel)
        else "`N/A`"
    )
    text_channel = interaction.channel.mention if isinstance(interaction.channel, discord.TextChannel) else "`N/A`"

    embed = discord.Embed(title="🗣️ /speak used", color=THEME_PRIMARY)
    embed.add_field(name="User", value=f"{interaction.user.mention} (`{interaction.user.id}`)", inline=False)
    embed.add_field(name="Language", value=pretty, inline=True)
    embed.add_field(name="Voice Channel", value=vc_name, inline=True)
    embed.add_field(name="Typed Text (EN)", value=(original_text[:1024] or "`(empty)`"), inline=False)
    embed.set_footer(text=f"Invoked in {text_channel}")

    try:
        await target.send(embed=embed)
    except Exception:
        pass

@bot.tree.command(name="speak", description="Bot joins your VC and speaks the text (no message posted).")
@app_commands.describe(
    text="Type your message in English",
    language="Target language to speak"
)
@app_commands.choices(language=LANG_CHOICES)
@app_commands.check(has_member_role)
@app_commands.guild_only()
async def speak(
    interaction: discord.Interaction,
    text: str,
    language: app_commands.Choice[str] = None
):
    try:
        await interaction.response.defer(ephemeral=True)
    except discord.InteractionResponded:
        pass

    if not ffmpeg_available():
        await interaction.followup.send("❌ FFmpeg isn’t available in this container. Rebuild with FFmpeg and try again.", ephemeral=True)
        return

    vc = await ensure_voice(interaction)
    if vc is None:
        return

    lang_code = (language.value if language else "en").lower()
    to_say = text[:5000]

    await log_speak_usage(interaction, original_text=text, lang_code=lang_code)

    if lang_code != "en":
        try:
            result = translator.translate(to_say, src="en", dest=lang_code)
            to_say = result.text[:5000]
        except Exception as e:
            await interaction.followup.send(f"⚠️ Translation failed ({e}); speaking original English.", ephemeral=True)

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
            tmp_path = f.name
        tts = gTTS(text=to_say, lang=lang_code)
        tts.save(tmp_path)
    except Exception as e:
        await interaction.followup.send(f"❌ TTS failed: `{e}`", ephemeral=True)
    else:
        try:
            audio = discord.FFmpegPCMAudio(tmp_path, before_options="-nostdin")
            vc.play(audio)
            while vc.is_playing():
                await asyncio.sleep(0.25)
            pretty = next((c.name for c in LANG_CHOICES if c.value == lang_code), lang_code)
            await interaction.followup.send(f"✅ Spoke in **{pretty}**.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Playback error: `{e}`", ephemeral=True)
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass
            try:
                await vc.disconnect(force=False)
            except Exception:
                pass

# ============================================================
#                       ERROR HANDLING & RUN
# ============================================================

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    # Tailored error copy so Role Picker checks don't show the /speak message.
    if isinstance(error, app_commands.CheckFailure):
        try:
            cmd = getattr(interaction.command, "name", "") if interaction.command else ""
            if cmd.startswith("roles"):
                msg = "❌ You’re not allowed to use the Role Picker."
            elif cmd == "speak":
                msg = "❌ You need the **Member** role to use `/speak`."
            else:
                msg = "❌ You don’t have permission to use this command."
            await interaction.response.send_message(msg, ephemeral=True)
        except discord.InteractionResponded:
            await interaction.followup.send(msg, ephemeral=True)

def main():
    print("FFMPEG PATH:", which("ffmpeg"))
    bot.run(TOKEN)

if __name__ == "__main__":
    main()
