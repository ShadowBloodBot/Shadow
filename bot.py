# bot.py — ShadowSyn Welcome + Custom Embed Bot + Moderation Logger (logs support THREADS)
# Runtime: python-3.11.9
# Requirements:
#   discord.py>=2.4.0
#   python-dotenv>=1.0.1
# Procfile:
#   worker: python -u bot.py
#
# Env:
#   DISCORD_TOKEN

import os
import json
from pathlib import Path
from typing import Optional, Tuple, Union, Dict, Any
from uuid import uuid4
from datetime import datetime, timezone, timedelta

import discord
from discord import app_commands
from discord.ui import View, Button, Modal, TextInput

# ========= ENV / STARTUP =========
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise SystemExit("❌ DISCORD_TOKEN is not set in the environment.")

# ========= THEME / DEFAULTS =========
VANITY_INVITE = "https://discord.gg/shadowsyn"
THEME_PRIMARY = 0x2B0B35  # blackish purple
THEME_GOOD    = 0x2b9348  # green
THEME_WARN    = 0xf39c12  # orange
THEME_BAD     = 0xe74c3c  # red
THEME_INFO    = 0x5865F2  # blurple

LOBBY_NAME = "lobby"

# ========= PERSISTED CONFIG =========
CONFIG_PATH = Path("welcome_config.json")
DEFAULT_TARGET_ID = 1166874144395247757  # initial welcome thread
# Updated: your audit log THREAD id
DEFAULT_AUDIT_LOG_CHANNEL_ID = 961726632249425930

def load_config() -> dict:
    base = {
        "welcome_target_id": DEFAULT_TARGET_ID,
        "audit_log_channel_id": DEFAULT_AUDIT_LOG_CHANNEL_ID,
        "vanity_invite": VANITY_INVITE,
        "lobby_name": LOBBY_NAME,
    }
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text())
            base.update(data or {})
        except Exception:
            pass
    return base

def save_config(cfg: dict) -> None:
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
    except Exception:
        pass

config = load_config()

# ========= HELPERS =========
async def resolve_target(
    bot: discord.Client, target_id: int
) -> Tuple[Optional[discord.abc.Messageable], Optional[discord.abc.GuildChannel]]:
    """Returns (messageable_target, parent_text_channel_for_invites)."""
    ch = bot.get_channel(target_id)
    if ch is None:
        try:
            ch = await bot.fetch_channel(target_id)
        except discord.Forbidden:
            return None, None
        except Exception:
            return None, None

    if isinstance(ch, discord.TextChannel):
        return ch, ch

    if isinstance(ch, discord.Thread):
        try:
            if ch.archived:
                await ch.edit(archived=False)
        except Exception:
            pass
        try:
            await ch.join()
        except Exception:
            pass
        parent = ch.parent if isinstance(ch.parent, discord.TextChannel) else None
        return ch, parent

    return None, None

def find_text_channel_by_name(guild: discord.Guild, name: str) -> Optional[discord.TextChannel]:
    n = name.lower().strip()
    for ch in guild.text_channels:
        if ch.name.lower() == n:
            return ch
    return None

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
        f"{config.get('vanity_invite')}\n"
    )
    embed = discord.Embed(title="Welcome to ShadowSyn", description=desc, color=THEME_PRIMARY)
    embed.set_footer(text="Be cool. Have fun. Bring friends.")
    return embed

def make_embed(title: str, message: str, color: int = THEME_PRIMARY) -> discord.Embed:
    embed = discord.Embed(title=title[:256], description=message[:4096], color=color)
    embed.set_footer(text="ShadowSyn")
    embed.timestamp = datetime.now(timezone.utc)
    return embed

# ========= UI: INVITE BUTTON =========
INVITE_BTN_ID = "invite_friends_ephemeral"

class InviteFriendsView(View):
    def __init__(self):
        # timeout=None => eligible for persistent registration
        super().__init__(timeout=None)
        btn = Button(
            label="Invite Friends",
            style=discord.ButtonStyle.primary,
            custom_id=INVITE_BTN_ID
        )
        btn.callback = self.send_invite_ephemeral
        self.add_item(btn)

    async def send_invite_ephemeral(self, interaction: discord.Interaction):
        text = (
            "📨 **Invite Friends**\n"
            f"Here’s the server invite:\n{config.get('vanity_invite')}\n\n"
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
                await interaction.followup.send(f"Here’s the invite: {config.get('vanity_invite')}", ephemeral=True)
            except Exception:
                pass

# ========= PREVIEW STATE =========
PREVIEW_STORE: Dict[str, Dict] = {}

class CustomPreviewView(View):
    def __init__(self, key: str):
        super().__init__(timeout=300)
        self.key = key

        self.post_btn = Button(label="✅ Post", style=discord.ButtonStyle.success, custom_id=f"post:{key}")
        self.edit_btn = Button(label="✏️ Edit", style=discord.ButtonStyle.primary, custom_id=f"edit:{key}")
        self.cancel_btn = Button(label="🗑️ Cancel", style=discord.ButtonStyle.danger, custom_id=f"cancel:{key}")

        self.post_btn.callback = self.post
        self.edit_btn.callback = self.edit
        self.cancel_btn.callback = self.cancel

        self.add_item(self.post_btn)
        self.add_item(self.edit_btn)
        self.add_item(self.cancel_btn)

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
            label="Title",
            placeholder="Embed title",
            default=title_default[:256],
            max_length=256,
            required=True
        )
        self.message_input = TextInput(
            label="Message",
            placeholder="Type your embed message. Use Shift+Enter for new lines.",
            style=discord.TextStyle.paragraph,
            default=message_default[:4000] if message_default else None,
            max_length=4000,
            required=True
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

# ========= BOT CORE =========
class ShadowSynBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True
        intents.voice_states = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        # Register persistent views so buttons work across restarts
        self.add_view(InviteFriendsView())
        await self.tree.sync()

bot = ShadowSynBot()

# ========= LOGGING CORE (now supports TextChannel OR Thread) =========
async def get_log_target(guild: Optional[discord.Guild]) -> Optional[discord.abc.Messageable]:
    if not guild:
        return None
    ch_id = int(config.get("audit_log_channel_id") or 0)
    if not ch_id:
        return None
    target, _ = await resolve_target(bot, ch_id)
    return target  # can be TextChannel or Thread (both Messageable)

async def send_log(
    guild: Optional[discord.Guild],
    title: str,
    color: int,
    fields: Dict[str, str],
    footer: Optional[str] = None,
    thumbnail: Optional[Union[str, discord.Asset]] = None
) -> None:
    if guild is None:
        return
    dest = await get_log_target(guild)
    if dest is None:
        return
    embed = discord.Embed(title=title[:256], color=color)
    embed.timestamp = datetime.now(timezone.utc)
    for k, v in fields.items():
        if v:
            embed.add_field(name=k[:256], value=v[:1024], inline=False)
    if footer:
        embed.set_footer(text=footer[:2048])
    if thumbnail:
        try:
            embed.set_thumbnail(url=str(thumbnail))
        except Exception:
            pass
    try:
        await dest.send(embed=embed)
    except Exception:
        pass

async def find_audit(
    guild: discord.Guild,
    action: discord.AuditLogAction,
    target_id: Optional[int] = None,
    within: float = 10.0
) -> Optional[discord.AuditLogEntry]:
    try:
        now = datetime.now(timezone.utc)
        async for entry in guild.audit_logs(limit=5, action=action):
            if (now - entry.created_at).total_seconds() > within:
                continue
            if target_id is not None:
                tgt = getattr(entry, "target", None)
                if hasattr(tgt, "id"):
                    if tgt.id != target_id:
                        continue
            return entry
    except discord.Forbidden:
        return None
    except Exception:
        return None
    return None

# ========= WELCOME COMMANDS =========
async def send_welcome_impl(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)

    target_id = int(config.get("welcome_target_id") or DEFAULT_TARGET_ID)
    target, _ = await resolve_target(bot, target_id)
    if target is None:
        await interaction.followup.send(
            "❌ I can’t access the configured welcome target. "
            "Run `/set_welcome_target` **in your welcome thread** and try again.",
            ephemeral=True
        )
        return

    lobby_name = config.get("lobby_name", LOBBY_NAME)
    lobby_ch = find_text_channel_by_name(interaction.guild, lobby_name) if interaction.guild else None
    lobby_mention = lobby_ch.mention if lobby_ch else f"#{lobby_name}"
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
        await interaction.followup.send("❌ Run this inside a text channel or a thread.", ephemeral=True)
        return

    if isinstance(ch, discord.Thread):
        try:
            if ch.archived:
                await ch.edit(archived=False)
            await ch.join()
        except Exception:
            pass

    config["welcome_target_id"] = ch.id
    save_config(config)
    kind = "thread" if isinstance(ch, discord.Thread) else "channel"
    await interaction.followup.send(f"✅ Set welcome target to this {kind}: **#{ch.name}** (`{ch.id}`).", ephemeral=True)

# ========= CUSTOM EMBED (PREVIEW FLOW) =========
async def start_custom_flow(interaction: discord.Interaction, target: Union[discord.TextChannel, discord.Thread]):
    try:
        await interaction.response.send_modal(CustomEmbedModal(key=None, target_id=target.id))
    except Exception as e:
        try:
            await interaction.followup.send(f"❌ Could not open modal: `{e}`", ephemeral=True)
        except Exception:
            pass

@bot.tree.command(
    name="send_custom",
    description="Post a custom embed to a selected text channel or thread (with preview)."
)
@app_commands.describe(target="Choose a text channel or thread")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.guild_only()
async def send_custom(
    interaction: discord.Interaction,
    target: Union[discord.TextChannel, discord.Thread],
):
    await start_custom_flow(interaction, target)

@bot.tree.command(
    name="send_custome",
    description="(Alias) Post a custom embed to a selected text channel or thread (with preview)."
)
@app_commands.describe(target="Choose a text channel or thread")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.guild_only()
async def send_custome(
    interaction: discord.Interaction,
    target: Union[discord.TextChannel, discord.Thread],
):
    await start_custom_flow(interaction, target)

# ========= ADMIN UTILITIES =========
@bot.tree.command(name="sync_here", description="Admin: sync all slash commands to this guild for instant use.")
@app_commands.checks.has_permissions(administrator=True)
async def sync_here(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        await bot.tree.sync(guild=interaction.guild)
        await interaction.followup.send("✅ Commands synced to this guild.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Sync failed: `{e}`", ephemeral=True)

@bot.tree.command(name="prune_old_commands", description="Admin: delete stale GLOBAL commands named send_welcome/send_custom.")
@app_commands.checks.has_permissions(administrator=True)
async def prune_old_commands(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        app_id = bot.application_id or (bot.user and bot.user.id)
        if not app_id:
            await interaction.followup.send("❌ Could not determine application_id.", ephemeral=True)
            return

        globals_list = await bot.http.get_global_commands(app_id)
        to_del = [c for c in globals_list if c.get("name") in {"send_welcome", "send_custom", "send_custome"}]
        for c in to_del:
            try:
                await bot.http.delete_global_command(app_id, c["id"])
            except Exception:
                pass

        await interaction.followup.send(f"🧹 Pruned {len(to_del)} old global command(s).", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Prune failed: `{e}`", ephemeral=True)

# Accepts a TextChannel OR a Thread now
@bot.tree.command(name="set_log_channel", description="Set the audit log destination (channel or thread).")
@app_commands.checks.has_permissions(administrator=True)
async def set_log_channel(interaction: discord.Interaction, target: Union[discord.TextChannel, discord.Thread]):
    config["audit_log_channel_id"] = target.id
    save_config(config)
    kind = "thread" if isinstance(target, discord.Thread) else "channel"
    await interaction.response.send_message(f"✅ Audit log {kind} set to {target.mention}", ephemeral=True)

@bot.tree.command(name="set_vanity", description="Set the invite URL used by the Invite button & welcome.")
@app_commands.checks.has_permissions(administrator=True)
async def set_vanity(interaction: discord.Interaction, invite_url: str):
    config["vanity_invite"] = invite_url
    save_config(config)
    await interaction.response.send_message("✅ Vanity invite updated.", ephemeral=True)

@bot.tree.command(name="set_lobby", description="Set the lobby channel name mention in the welcome embed.")
@app_commands.checks.has_permissions(administrator=True)
async def set_lobby(interaction: discord.Interaction, lobby_name: str):
    config["lobby_name"] = lobby_name
    save_config(config)
    await interaction.response.send_message(f"✅ Lobby name set to `{lobby_name}`.", ephemeral=True)

# ========= MODERATION EVENT LISTENERS =========
def _fmt_user(user: Union[discord.Member, discord.User, None]) -> str:
    if user is None:
        return "`Unknown`"
    return f"{user.mention} (`{user}` / `{user.id}`)"

def _fmt_channel(ch: Optional[discord.abc.GuildChannel]) -> str:
    if ch is None:
        return "`Unknown`"
    if isinstance(ch, discord.VoiceChannel):
        return f"{ch.mention} (`{ch.name}` / `{ch.id}`)"
    if isinstance(ch, discord.StageChannel):
        return f"{ch.mention} (`{ch.name}` / `{ch.id}`)"
    if isinstance(ch, discord.TextChannel):
        return f"{ch.mention} (`{ch.name}` / `{ch.id}`)"
    return f"`{getattr(ch, 'name', 'Unknown')}` / `{getattr(ch, 'id', '??')}`"

@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    guild = after.guild

    # Nickname change
    if before.nick != after.nick:
        actor = None
        reason = None
        entry = await find_audit(guild, discord.AuditLogAction.member_update, target_id=after.id, within=15)
        if entry:
            actor = entry.user
            reason = entry.reason
        await send_log(
            guild,
            title="📝 Nickname Changed",
            color=THEME_INFO,
            fields={
                "Member": _fmt_user(after),
                "Moderator": _fmt_user(actor),
                "Old Nick": before.nick or "`None`",
                "New Nick": after.nick or "`None`",
                "Reason": reason or "`Not provided`",
            },
            thumbnail=after.display_avatar
        )

    # Timeout changes
    before_cdu = before.communication_disabled_until
    after_cdu = after.communication_disabled_until
    if before_cdu != after_cdu:
        actor = None
        reason = None
        entry = await find_audit(guild, discord.AuditLogAction.member_update, target_id=after.id, within=15)
        if entry:
            actor = entry.user
            reason = entry.reason

        if after_cdu and (not before_cdu or after_cdu > datetime.now(timezone.utc)):
            dur = (after_cdu - datetime.now(timezone.utc)).total_seconds()
            human = f"{int(dur//3600)}h {int((dur%3600)//60)}m"
            await send_log(
                guild,
                title="⏳ Timeout Applied",
                color=THEME_WARN,
                fields={
                    "Member": _fmt_user(after),
                    "Moderator": _fmt_user(actor),
                    "Until": f"<t:{int(after_cdu.timestamp())}:F>",
                    "Approx Duration": human,
                    "Reason": reason or "`Not provided`",
                },
                thumbnail=after.display_avatar
            )
        else:
            await send_log(
                guild,
                title="✅ Timeout Removed",
                color=THEME_GOOD,
                fields={
                    "Member": _fmt_user(after),
                    "Moderator": _fmt_user(actor),
                    "Reason": reason or "`Not provided`",
                },
                thumbnail=after.display_avatar
            )

    # Server mute/deafen flips
    if before.voice or after.voice:
        try:
            b = before.voice
            a = after.voice
            if b and a:
                if b.mute != a.mute:
                    entry = await find_audit(guild, discord.AuditLogAction.member_update, target_id=after.id, within=15)
                    await send_log(
                        guild,
                        title="🔇 Server Mute Toggled",
                        color=THEME_WARN if a.mute else THEME_GOOD,
                        fields={
                            "Member": _fmt_user(after),
                            "Moderator": _fmt_user(entry.user if entry else None),
                            "Now": "`Muted`" if a.mute else "`Unmuted`",
                        },
                        thumbnail=after.display_avatar
                    )
                if b.deaf != a.deaf:
                    entry = await find_audit(guild, discord.AuditLogAction.member_update, target_id=after.id, within=15)
                    await send_log(
                        guild,
                        title="🔈 Server Deafen Toggled",
                        color=THEME_WARN if a.deaf else THEME_GOOD,
                        fields={
                            "Member": _fmt_user(after),
                            "Moderator": _fmt_user(entry.user if entry else None),
                            "Now": "`Deafened`" if a.deaf else "`Undeafened`",
                        },
                        thumbnail=after.display_avatar
                    )
        except Exception:
            pass

@bot.event
async def on_member_remove(member: discord.Member):
    guild = member.guild
    entry = await find_audit(guild, discord.AuditLogAction.kick, target_id=member.id, within=15)
    if entry:
        await send_log(
            guild,
            title="👢 Member Kicked",
            color=THEME_BAD,
            fields={
                "Member": _fmt_user(member),
                "Moderator": _fmt_user(entry.user),
                "Reason": entry.reason or "`Not provided`",
            },
            thumbnail=member.display_avatar
        )

@bot.event
async def on_member_ban(guild: discord.Guild, user: Union[discord.Member, discord.User]):
    entry = await find_audit(guild, discord.AuditLogAction.ban, target_id=getattr(user, "id", None), within=20)
    await send_log(
        guild,
        title="⛔ Member Banned",
        color=THEME_BAD,
        fields={
            "Member": _fmt_user(user),
            "Moderator": _fmt_user(entry.user if entry else None),
            "Reason": (entry.reason if entry else None) or "`Not provided`",
        },
        thumbnail=getattr(user, "display_avatar", None)
    )

@bot.event
async def on_member_unban(guild: discord.Guild, user: Union[discord.Member, discord.User]):
    entry = await find_audit(guild, discord.AuditLogAction.unban, target_id=getattr(user, "id", None), within=20)
    await send_log(
        guild,
        title="♻️ Member Unbanned",
        color=THEME_INFO,
        fields={
            "Member": _fmt_user(user),
            "Moderator": _fmt_user(entry.user if entry else None),
            "Reason": (entry.reason if entry else None) or "`Not provided`",
        },
        thumbnail=getattr(user, "display_avatar", None)
    )

@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    if before.channel != after.channel:
        guild = member.guild
        entry = await find_audit(guild, discord.AuditLogAction.member_move, target_id=None, within=10)
        moderator = entry.user if entry else None
        await send_log(
            guild,
            title="↔️ Member Moved",
            color=THEME_INFO,
            fields={
                "Member": _fmt_user(member),
                "Moderator": _fmt_user(moderator),
                "From": _fmt_channel(before.channel) if before.channel else "`None`",
                "To": _fmt_channel(after.channel) if after.channel else "`Disconnected`",
            },
            thumbnail=member.display_avatar
        )

# ========= RUN =========
def main():
    bot.run(TOKEN)

if __name__ == "__main__":
    main()
