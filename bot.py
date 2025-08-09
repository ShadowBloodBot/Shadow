# bot.py — ShadowSyn Welcome/Embed Bot (guild-scoped + global prune)
# Env: DISCORD_TOKEN

import os
from typing import Optional
from urllib.parse import quote_plus

import discord
from discord import app_commands
from discord.ui import View, Button

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise SystemExit("❌ DISCORD_TOKEN is not set.")

# ========= CONFIG =========
WELCOME_THREAD_ID = 1166874144395247757  # your welcome thread
DEFAULT_INVITE_URL = "https://discord.gg/shadowsyn"
THEME_PRIMARY = 0x2B0B35  # blackish‑purple
THEME_ACCENT  = 0x7A0F2E  # wine‑red
LOBBY_NAME = "lobby"      # resolves to #lobby mention if it exists


# ========= HELPERS =========
async def get_thread(bot: discord.Client, thread_id: int) -> Optional[discord.Thread]:
    ch = bot.get_channel(thread_id)
    if ch is None:
        try:
            ch = await bot.fetch_channel(thread_id)
        except Exception:
            return None
    return ch if isinstance(ch, discord.Thread) else None

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


# ========= VIEW =========
class InviteShareView(View):
    def __init__(self, parent_text_channel: discord.abc.GuildChannel):
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
                await interaction.response.send_message("❌ Invalid parent channel for invites.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I lack permission to create invites here.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to create invite: `{e}`", ephemeral=True)


# ========= BOT =========
class ShadowSynBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.guilds = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        # We guild-sync on demand via /sync_here so startup stays safe across multiple guilds.
        await self.tree.sync()  # keep any existing globals in place until we prune


bot = ShadowSynBot()


# ========= COMMANDS =========
async def _send_welcome_logic(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)

    thread = await get_thread(bot, WELCOME_THREAD_ID)
    if thread is None:
        await interaction.followup.send("❌ I can’t access the configured welcome thread.", ephemeral=True)
        return

    lobby_ch = find_text_channel_by_name(interaction.guild, LOBBY_NAME) if interaction.guild else None
    lobby_mention = lobby_ch.mention if lobby_ch else "#lobby"

    embed = build_welcome_embed(lobby_mention)

    parent = thread.parent
    if not isinstance(parent, (discord.TextChannel, discord.VoiceChannel, discord.ForumChannel)):
        await interaction.followup.send("❌ The welcome thread’s parent channel is invalid for invites.", ephemeral=True)
        return

    view = InviteShareView(parent_text_channel=parent)
    try:
        await thread.send(embed=embed, view=view)
        await interaction.followup.send("✅ Welcome message sent.", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("❌ I don’t have permission to send in that thread.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to send welcome message: `{e}`", ephemeral=True)


# GUILD-SCOPED /send_welcome (no options, clean)
@bot.tree.command(name="send_welcome", description="Post the ShadowSyn welcome embed here (guild-scoped).")
@app_commands.checks.has_permissions(administrator=True)
async def send_welcome(interaction: discord.Interaction):
    await _send_welcome_logic(interaction)


@send_welcome.error
async def send_welcome_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("🚫 Admins only.", ephemeral=True)
    else:
        try:
            await interaction.response.send_message(f"❌ Error: `{error}`", ephemeral=True)
        except Exception:
            pass


# ===== Admin utilities =====
@bot.tree.command(name="sync_here", description="Admin: sync slash commands to THIS guild for instant updates.")
@app_commands.checks.has_permissions(administrator=True)
async def sync_here(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        await bot.tree.sync(guild=interaction.guild)
        await interaction.followup.send("✅ Synced commands to this guild.", ephemeral=True)
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

        # Fetch global commands via HTTP and delete any stale ones
        globals_list = await bot.http.get_global_commands(app_id)
        to_del = [c for c in globals_list if c.get("name") in {"send_welcome", "send_custom"}]
        for c in to_del:
            try:
                await bot.http.delete_global_command(app_id, c["id"])
            except Exception:
                pass

        await interaction.followup.send(f"🧹 Pruned {len(to_del)} old global command(s). Use `/sync_here` after if needed.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Prune failed: `{e}`", ephemeral=True)


# ========= RUN =========
def main():
    bot.run(TOKEN)

if __name__ == "__main__":
    main()
