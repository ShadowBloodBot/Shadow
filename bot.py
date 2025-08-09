# bot.py — ShadowSyn Welcome Bot (robust thread/channel targeting)
# Env: DISCORD_TOKEN
# Features:
# - /send_welcome posts fixed welcome embed to saved target (channel or thread)
# - /set_welcome_target saves the current channel/thread as the target
# - Auto-join private threads before sending
# - Invite/share buttons (no webhooks)
# - Black‑Purple‑Red theme

import os
import json
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import quote_plus

import discord
from discord import app_commands
from discord.ui import View, Button

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise SystemExit("❌ DISCORD_TOKEN is not set in the environment.")

# ====== THEME / DEFAULTS ======
DEFAULT_INVITE_URL = "https://discord.gg/shadowsyn"
THEME_PRIMARY = 0x2B0B35  # blackish purple
THEME_ACCENT  = 0x7A0F2E  # wine red
LOBBY_NAME = "lobby"

# ====== PERSISTED CONFIG ======
CONFIG_PATH = Path("welcome_config.json")
DEFAULT_TARGET_ID = 1166874144395247757  # Provided by you; can be overridden via /set_welcome_target

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
    - If target is TextChannel: (channel, channel)
    - If target is Thread (public/private): auto-join if needed, return (thread, thread.parent)
    - If not found/accessible: (None, None)
    """
    ch = bot.get_channel(target_id)
    if ch is None:
        try:
            ch = await bot.fetch_channel(target_id)
        except discord.Forbidden:
            return None, None
        except Exception:
            return None, None

    # Text channel
    if isinstance(ch, discord.TextChannel):
        return ch, ch

    # Thread (public/private/news/forum thread)
    if isinstance(ch, discord.Thread):
        try:
            if ch.archived:
                # Unarchive if we can; otherwise, send will fail
                await ch.edit(archived=False)
        except Exception:
            pass
        try:
            # If private thread, we might need to join
            if not ch.me:  # older libs; safety guard
                pass
            # discord.py offers thread.join() if not joined
            await ch.join()
        except Exception:
            # join may fail if already joined or lacking perms; continue and try send
            pass
        parent = ch.parent if isinstance(ch.parent, discord.TextChannel) else None
        return ch, parent

    # Forum channel post also arrives as Thread; handled above
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
        f"{DEFAULT_INVITE_URL}\n"
    )
    embed = discord.Embed(title="Welcome to ShadowSyn", description=desc, color=THEME_PRIMARY)
    embed.set_footer(text="Be cool. Have fun. Bring friends.")
    return embed

class InviteShareView(View):
    def __init__(self, parent_text_channel: Optional[discord.abc.GuildChannel]):
        super().__init__(timeout=None)
        self.parent_text_channel = parent_text_channel

        self.add_item(Button(label="📨 Join / Share Invite", url=DEFAULT_INVITE_URL))

        personal = Button(
            label="🔗 Create Personal Invite (24h, 1 use)",
            style=discord.ButtonStyle.primary,
            custom_id="make_personal_invite"
        )
        personal.callback = self.make_personal_invite
        self.add_item(personal)

        share_text = "Join me on ShadowSyn — elite FPS/Survival/MMO community:"
        tweet = f"https://twitter.com/intent/tweet?text={quote_plus(share_text)}&url={quote_plus(DEFAULT_INVITE_URL)}"
        self.add_item(Button(label="📣 Share on X", url=tweet))

    async def make_personal_invite(self, interaction: discord.Interaction):
        try:
            perms = interaction.user.guild_permissions
            if not (perms.manage_guild or perms.create_instant_invite):
                await interaction.response.send_message(
                    "🚫 You need *Create Invite* or *Manage Server* permission.", ephemeral=True
                )
                return

            if isinstance(self.parent_text_channel, (discord.TextChannel, discord.VoiceChannel, discord.ForumChannel)):
                invite = await self.parent_text_channel.create_invite(
                    max_age=86400, max_uses=1, unique=True,
                    reason=f"Personal invite created by {interaction.user}"
                )
                await interaction.response.send_message(
                    f"✅ **Personal Invite (24h / 1 use)**\n{invite.url}", ephemeral=True
                )
            else:
                await interaction.response.send_message("❌ No valid parent channel to create invites.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I lack permission to create invites here.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to create invite: `{e}`", ephemeral=True)

# ====== BOT ======
class ShadowSynBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.guilds = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()

bot = ShadowSynBot()

# ====== COMMANDS ======
async def send_welcome_impl(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)

    target_id = int(config.get("welcome_target_id") or DEFAULT_TARGET_ID)
    target, parent = await resolve_target(bot, target_id)
    if target is None:
        await interaction.followup.send("❌ I can’t access the configured welcome target. Check ID/perms or run `/set_welcome_target` in the correct channel/thread.", ephemeral=True)
        return

    lobby_ch = find_text_channel_by_name(interaction.guild, LOBBY_NAME) if interaction.guild else None
    lobby_mention = lobby_ch.mention if lobby_ch else "#lobby"
    embed = build_welcome_embed(lobby_mention)
    view = InviteShareView(parent_text_channel=parent)

    try:
        await target.send(embed=embed, view=view)
        await interaction.followup.send("✅ Welcome message sent.", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("❌ I don’t have permission to send there.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to send: `{e}`", ephemeral=True)

@bot.tree.command(name="send_welcome", description="Post the ShadowSyn welcome embed to the saved target.")
@app_commands.checks.has_permissions(administrator=True)
async def send_welcome(interaction: discord.Interaction):
    await send_welcome_impl(interaction)

@send_welcome.error
async def send_welcome_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("🚫 Admins only.", ephemeral=True)
    else:
        try:
            await interaction.response.send_message(f"❌ Error: `{error}`", ephemeral=True)
        except Exception:
            pass

@bot.tree.command(name="set_welcome_target", description="Set the current channel/thread as the welcome target.")
@app_commands.checks.has_permissions(administrator=True)
async def set_welcome_target(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)
    ch = interaction.channel

    # Only allow TextChannel or Thread
    if not isinstance(ch, (discord.TextChannel, discord.Thread)):
        await interaction.followup.send("❌ Run this inside a text channel or a thread.", ephemeral=True)
        return

    # If it's a thread, ensure bot can join/unarchive now so future sends succeed
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

@set_welcome_target.error
async def set_welcome_target_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("🚫 Admins only.", ephemeral=True)
    else:
        try:
            await interaction.response.send_message(f"❌ Error: `{error}`", ephemeral=True)
        except Exception:
            pass

# Optional: keep /prune_old_commands from earlier if you still see duplicates
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
        to_del = [c for c in globals_list if c.get("name") in {"send_welcome", "send_custom"}]
        for c in to_del:
            try:
                await bot.http.delete_global_command(app_id, c["id"])
            except Exception:
                pass

        await interaction.followup.send(f"🧹 Pruned {len(to_del)} old global command(s).", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Prune failed: `{e}`", ephemeral=True)

def main():
    bot.run(TOKEN)

if __name__ == "__main__":
    main()
