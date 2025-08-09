# bot.py — ShadowSyn Welcome + Custom Embed Bot (fixed)
# Env: DISCORD_TOKEN

import os
import json
from pathlib import Path
from typing import Optional, Tuple, Union

import discord
from discord import app_commands
from discord.ui import View, Button

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise SystemExit("❌ DISCORD_TOKEN is not set in the environment.")

# ====== THEME / DEFAULTS ======
VANITY_INVITE = "https://discord.gg/shadowsyn"
THEME_PRIMARY = 0x2B0B35  # blackish purple
THEME_ACCENT  = 0x7A0F2E  # wine red (embed accents/footers only)
LOBBY_NAME = "lobby"

# ====== PERSISTED CONFIG ======
CONFIG_PATH = Path("welcome_config.json")
DEFAULT_TARGET_ID = 1166874144395247757  # your initial welcome thread

def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except Exception:
            pass
    return {"welcome_target_id": DEFAULT_TARGET_ID}

def save_config(cfg: dict) -> None:
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
    except Exception:
        pass

config = load_config()

# ====== HELPERS ======
async def resolve_target(
    bot: discord.Client, target_id: int
) -> Tuple[Optional[discord.abc.Messageable], Optional[discord.abc.GuildChannel]]:
    """
    Returns (messageable_target, parent_text_channel_for_invites).
    - If TextChannel: (channel, channel)
    - If Thread: auto-unarchive/join, return (thread, thread.parent)
    - Else: (None, None)
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

# ====== VIEWS ======
class InviteFriendsView(View):
    def __init__(self):
        super().__init__(timeout=None)
        btn = Button(
            label="Invite Friends",
            style=discord.ButtonStyle.primary,
            custom_id="invite_friends_ephemeral"
        )
        btn.callback = self.send_invite_ephemeral
        self.add_item(btn)

    async def send_invite_ephemeral(self, interaction: discord.Interaction):
        try:
            text = (
                "📨 **Invite Friends**\n"
                f"Here’s the server invite:\n{VANITY_INVITE}\n\n"
                "_Tip: Clicking this link in Discord opens the native **Invite Friends** panel._"
            )
            await interaction.response.send_message(text, ephemeral=True)
        except Exception:
            try:
                await interaction.followup.send(f"Here’s the invite: {VANITY_INVITE}", ephemeral=True)
            except Exception:
                pass

# ====== BOT CORE ======
class ShadowSynBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.guilds = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()

bot = ShadowSynBot()

# ====== WELCOME COMMANDS ======
async def send_welcome_impl(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)

    target_id = int(config.get("welcome_target_id") or DEFAULT_TARGET_ID)
    target, parent = await resolve_target(bot, target_id)
    if target is None:
        await interaction.followup.send(
            "❌ I can’t access the configured welcome target. "
            "Run `/set_welcome_target` **in your welcome thread** and try again.",
            ephemeral=True
        )
        return

    lobby_ch = find_text_channel_by_name(interaction.guild, LOBBY_NAME) if interaction.guild else None
    lobby_mention = lobby_ch.mention if lobby_ch else "#lobby"
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

# ====== CUSTOM EMBED COMMANDS ======
async def send_custom_impl(
    interaction: discord.Interaction,
    target: Union[discord.TextChannel, discord.Thread],
    title: str,
    message: str,
):
    await interaction.response.defer(ephemeral=True, thinking=True)

    # Ensure target is usable
    if isinstance(target, discord.Thread):
        try:
            if target.archived:
                await target.edit(archived=False)
        except Exception:
            pass
        try:
            await target.join()
        except Exception:
            pass
        messageable: discord.abc.Messageable = target
    elif isinstance(target, discord.TextChannel):
        messageable = target
    else:
        await interaction.followup.send("❌ Pick a text channel or a thread.", ephemeral=True)
        return

    embed = discord.Embed(title=title.strip()[:256], description=message[:4096], color=THEME_PRIMARY)
    embed.set_footer(text="ShadowSyn")
    try:
        await messageable.send(embed=embed)
        where = f"#{getattr(target, 'name', 'thread')}"
        await interaction.followup.send(f"✅ Custom embed sent to **{where}**.", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("❌ I don’t have permission to send there.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to send: `{e}`", ephemeral=True)

@bot.tree.command(
    name="send_custom",
    description="Post a custom embed to a selected text channel or thread."
)
@app_commands.describe(
    target="Choose a text channel or thread",
    title="Embed title",
    message="Embed message (supports new lines)"
)
@app_commands.checks.has_permissions(administrator=True)
@app_commands.guild_only()
async def send_custom(
    interaction: discord.Interaction,
    target: Union[discord.TextChannel, discord.Thread],
    title: str,
    message: str
):
    await send_custom_impl(interaction, target, title, message)

@bot.tree.command(
    name="send_custome",
    description="(Alias) Post a custom embed to a selected text channel or thread."
)
@app_commands.describe(
    target="Choose a text channel or thread",
    title="Embed title",
    message="Embed message (supports new lines)"
)
@app_commands.checks.has_permissions(administrator=True)
@app_commands.guild_only()
async def send_custome(
    interaction: discord.Interaction,
    target: Union[discord.TextChannel, discord.Thread],
    title: str,
    message: str
):
    await send_custom_impl(interaction, target, title, message)

# ====== OPTIONAL CLEANUP ======
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

# ====== RUN ======
def main():
    bot.run(TOKEN)

if __name__ == "__main__":
    main()
