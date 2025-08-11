# bot.py — ShadowSyn Welcome + Custom Embed Bot
# + /speak voice TTS (hidden input, VC playback, auto-leave)
# Env: DISCORD_TOKEN

import os
import json
import asyncio
import tempfile
from pathlib import Path
from typing import Optional, Tuple, Union, Dict
from uuid import uuid4

import discord
from discord import app_commands
from discord.ui import View, Button, Modal, TextInput
from gtts import gTTS
from shutil import which

# ============================================================
#                       CONSTANTS
# ============================================================

# Server branding
VANITY_INVITE  = "https://discord.gg/shadowsyn"
THEME_PRIMARY  = 0x2B0B35  # blackish purple
THEME_ACCENT   = 0x7A0F2E  # wine red (not heavily used)
LOBBY_NAME     = "lobby"

# Persistence
CONFIG_PATH        = Path("welcome_config.json")
DEFAULT_TARGET_ID  = 1166874144395247757  # initial welcome thread

# Permissions / role-gates
MEMBER_ROLE_ID = 955600320287887400  # users must have this to run /speak

# Token
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise SystemExit("❌ DISCORD_TOKEN is not set in the environment.")

# ============================================================
#                       CONFIG I/O
# ============================================================

def load_config() -> dict:
    """Load config with safe defaults."""
    base = {"welcome_target_id": DEFAULT_TARGET_ID}
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
    """Check if the invoker has the Member role."""
    m = interaction.user
    return isinstance(m, discord.Member) and any(r.id == MEMBER_ROLE_ID for r in m.roles)

async def resolve_target(
    bot: discord.Client, target_id: int
) -> Tuple[Optional[discord.abc.Messageable], Optional[discord.abc.GuildChannel]]:
    """
    Resolve a channel/thread ID to a messageable object.
    Returns (messageable_target, parent_text_channel_for_invites).
    """
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
        f"{VANITY_INVITE}\n"
    )
    embed = discord.Embed(title="Welcome to ShadowSyn", description=desc, color=THEME_PRIMARY)
    embed.set_footer(text="Be cool. Have fun. Bring friends.")
    return embed

def make_embed(title: str, message: str) -> discord.Embed:
    embed = discord.Embed(title=title[:256], description=message[:4096], color=THEME_PRIMARY)
    embed.set_footer(text="ShadowSyn")
    return embed

def ffmpeg_available() -> bool:
    return which("ffmpeg") is not None

# ============================================================
#                       UI VIEWS
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

# In-memory preview store: key -> {guild_id, user_id, target_id, title, message}
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
#                       BOT CORE
# ============================================================

class ShadowSynBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.voice_states = True  # VC join/leave
        intents.members = True       # role checks for /speak
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        # Persistent UI
        self.add_view(InviteFriendsView())
        await self.tree.sync()

bot = ShadowSynBot()

# ============================================================
#                       COMMANDS
# ============================================================

# ----- Welcome poster -----
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

# ----- Custom embed with preview -----
async def start_custom_flow(interaction: discord.Interaction, target: Union[discord.TextChannel, discord.Thread]):
    try:
        await interaction.response.send_modal(CustomEmbedModal(key=None, target_id=target.id))
    except Exception as e:
        try:
            await interaction.followup.send(f"❌ Could not open modal: `{e}`", ephemeral=True)
        except Exception:
            pass

@bot.tree.command(name="send_custom", description="Post a custom embed to a selected text channel or thread (with preview).")
@app_commands.describe(target="Choose a text channel or thread")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.guild_only()
async def send_custom(interaction: discord.Interaction, target: Union[discord.TextChannel, discord.Thread]):
    await start_custom_flow(interaction, target)

@bot.tree.command(name="send_custome", description="(Alias) Post a custom embed to a selected text channel or thread (with preview).")
@app_commands.describe(target="Choose a text channel or thread")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.guild_only()
async def send_custome(interaction: discord.Interaction, target: Union[discord.TextChannel, discord.Thread]):
    await start_custom_flow(interaction, target)

# ----- Admin utilities -----
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

# ----- /speak (hidden VC TTS; role-gated) -----
async def ensure_voice(interaction: discord.Interaction) -> Optional[discord.VoiceClient]:
    """Join/move to the user's voice channel."""
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

@bot.tree.command(name="speak", description="Bot joins your VC and speaks the text (no message posted).")
@app_commands.describe(text="What should I say?")
@app_commands.check(has_member_role)   # require Member role
@app_commands.guild_only()
async def speak(interaction: discord.Interaction, text: str):
    # Hidden interaction
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

    # Synthesize to temp mp3 via gTTS
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
            tmp_path = f.name
        tts = gTTS(text=text[:5000], lang="en")
        tts.save(tmp_path)
    except Exception as e:
        await interaction.followup.send(f"❌ TTS failed: `{e}`", ephemeral=True)
        return

    # Play and wait; auto-leave
    try:
        audio = discord.FFmpegPCMAudio(tmp_path, before_options="-nostdin")
        vc.play(audio)
        while vc.is_playing():
            await asyncio.sleep(0.25)
        await interaction.followup.send("✅ Done.", ephemeral=True)
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
#                       ERROR HANDLING
# ============================================================

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        try:
            await interaction.response.send_message(
                "❌ You need the **Member** role to use `/speak`.",
                ephemeral=True
            )
        except discord.InteractionResponded:
            await interaction.followup.send(
                "❌ You need the **Member** role to use `/speak`.",
                ephemeral=True
            )

# ============================================================
#                       RUN
# ============================================================

def main():
    # Optional: log ffmpeg path for sanity during deploys
    print("FFMPEG PATH:", which("ffmpeg"))
    bot.run(TOKEN)

if __name__ == "__main__":
    main()
