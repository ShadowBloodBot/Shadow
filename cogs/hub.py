# cogs/hub.py
import logging

import discord
from discord import ButtonStyle
from discord.ui import View, Button
from discord.ext import commands

from cogs.guild_registry import (
    REGISTERED_GUILD_IDS,
    ch_id,
    channel_url,
    is_registered_guild,
    resolve_channel,
    resolve_role,
)

# ==============================================================================
# TELEMETRY
# ==============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | [ShadowSyn] %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("ShadowSyn.Hub")

# ==============================================================================
# CONSTANTS
# ==============================================================================
THEME_PRIMARY = 0x2B0B35
MINION_BUTTON_ID = "hub_minion_grab"
HUB_TITLE = "Welcome -ShadowSyn-"


def _hub_description(guild_id: int) -> str:
    general = ch_id(guild_id, "general_open")
    steam = ch_id(guild_id, "steam_codes")
    welcome = ch_id(guild_id, "welcome")
    return (
        f"Grab your Starter role **[ Minion ]** so you can see\n"
        f"<#{general}> & Share your <#{steam}>\n"
        f"Check out <#{welcome}> for anything else"
    )


def _build_hub_embed(guild_id: int) -> discord.Embed:
    return discord.Embed(
        title=HUB_TITLE,
        description=_hub_description(guild_id),
        color=THEME_PRIMARY,
    )


# ==============================================================================
# HELPERS
# ==============================================================================
async def safe_reply(ctx_or_inter, *args, **kwargs):
    try:
        if hasattr(ctx_or_inter, "respond"):
            return await ctx_or_inter.respond(*args, **kwargs)
        if hasattr(ctx_or_inter, "response"):
            if not ctx_or_inter.response.is_done():
                return await ctx_or_inter.response.send_message(*args, **kwargs)
            return await ctx_or_inter.followup.send(*args, **kwargs)
    except Exception:
        return None


# ==============================================================================
# UI COMPONENTS
# ==============================================================================
class HubPanelView(View):
    """Persistent hub panel — Minion grab handled statelessly in on_interaction."""

    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.add_item(Button(
            label="Minion",
            style=ButtonStyle.primary,
            emoji="👻",
            custom_id=MINION_BUTTON_ID,
        ))
        self.add_item(Button(
            label="General-Open",
            style=ButtonStyle.link,
            emoji="💬",
            url=channel_url(guild_id, "general_open"),
        ))
        self.add_item(Button(
            label="Steam-Codes",
            style=ButtonStyle.link,
            emoji="📥",
            url=channel_url(guild_id, "steam_codes"),
        ))
        self.add_item(Button(
            label="Welcome",
            style=ButtonStyle.link,
            emoji="👋",
            url=channel_url(guild_id, "welcome"),
        ))


# ==============================================================================
# CORE COG
# ==============================================================================
class HubCog(commands.Cog):
    def __init__(self, bot: discord.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        try:
            for gid in REGISTERED_GUILD_IDS:
                self.bot.add_view(HubPanelView(gid))
            logger.info("Hub persistent views restored for ShadowMain + ShadowBackup.")
        except Exception as e:
            logger.error(f"Failed to restore hub views on_ready: {e}")

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        custom_id = interaction.data.get("custom_id", "") if interaction.data else ""
        if custom_id != MINION_BUTTON_ID:
            return

        member = interaction.user
        guild = interaction.guild
        if guild is None or not isinstance(member, discord.Member):
            return await safe_reply(interaction, "❌ Use this inside the server.", ephemeral=True)
        if not is_registered_guild(guild.id):
            return

        role = resolve_role(guild, "minion")
        if role is None:
            logger.error("Minion role not found in guild %s.", guild.id)
            return await safe_reply(interaction, "❌ Starter role is missing. Tell an admin.", ephemeral=True)

        if role in member.roles:
            return await safe_reply(
                interaction,
                "👻 You're already in the Shadows.",
                ephemeral=True,
            )

        try:
            await member.add_roles(role, reason="ShadowSyn Hub: starter role self-grab")
        except discord.Forbidden:
            logger.error("Forbidden while granting Minion via hub button.")
            return await safe_reply(
                interaction,
                "❌ I can't assign roles right now. Tell an admin.",
                ephemeral=True,
            )
        except Exception as e:
            logger.error(f"Minion grant failed for {member.id}: {e}")
            return await safe_reply(interaction, "⚠️ Something broke. Try again.", ephemeral=True)

        general = ch_id(guild.id, "general_open")
        await safe_reply(
            interaction,
            f"👻 You're in. Start with <#{general}>.",
            ephemeral=True,
        )
        await self._notify_arrivals(member)

    async def _notify_arrivals(self, member: discord.Member):
        thread = await resolve_channel(self.bot, member.guild.id, "arrivals")
        if thread is None:
            return
        try:
            joined = (
                discord.utils.format_dt(member.joined_at, "R")
                if member.joined_at else "unknown"
            )
            embed = discord.Embed(
                description=(
                    f"👻 {member.mention} grabbed **Minion** via the Hub.\n"
                    f"Joined: {joined}"
                ),
                color=THEME_PRIMARY,
            )
            embed.set_author(
                name=str(member),
                icon_url=member.display_avatar.url if member.display_avatar else None,
            )
            await thread.send(embed=embed)
        except Exception as e:
            logger.warning(f"Failed to post hub grant notice to arrivals: {e}")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot or not is_registered_guild(member.guild.id):
            return
        lobby = await resolve_channel(self.bot, member.guild.id, "lobby")
        if lobby is None:
            return
        try:
            await lobby.send(
                content=member.mention,
                embed=_build_hub_embed(member.guild.id),
                view=HubPanelView(member.guild.id),
                allowed_mentions=discord.AllowedMentions(users=True),
            )
            logger.info(f"Hub welcome ping posted for {member.id} in guild {member.guild.id}.")
        except Exception as e:
            logger.error(f"Failed to post hub welcome ping for {member.id}: {e}")

    @discord.slash_command(
        name="help",
        description="What ShadowSyn can do for you.",
        guild_ids=REGISTERED_GUILD_IDS,
    )
    async def help_command(self, ctx: discord.ApplicationContext):
        gid = ctx.guild.id if ctx.guild else REGISTERED_GUILD_IDS[0]
        embed = discord.Embed(title="👻 ShadowSyn", color=THEME_PRIMARY)
        embed.add_field(
            name="🔊 Voice",
            value=(
                f"Join <#{ch_id(gid, 'jtc')}> to spawn your own room with a control panel "
                "— lock, rename, kick, bitrate, user limit."
            ),
            inline=False,
        )
        embed.add_field(
            name="🎵 Music",
            value=(
                "In VC: paste a **YouTube** or **Spotify** link — ShadowSyn plays it automatically.\n"
                "`/play` — song name (pick from results) or link\n"
                "`/pause` · `/resume` · `/skip` · `/stop` · `/queue`"
            ),
            inline=False,
        )
        embed.add_field(
            name="🏆 Clips",
            value=(
                f"Hit **Submit Clip** in <#{ch_id(gid, 'clips')}> — Medal/YouTube link or file upload. "
                "Drop a 🔥 on the ones that deserve it."
            ),
            inline=False,
        )
        embed.add_field(
            name="🎮 Steam Codes",
            value=(
                f"Open <#{ch_id(gid, 'steam_codes')}> and hit **Add Steam Code** — "
                "your friend code joins the guild directory (multiple alts allowed)."
            ),
            inline=False,
        )
        embed.add_field(
            name="🏜️ SAND",
            value=(
                "In the SAND thread: `/sand query <question>` — loot, craft, materials, forts, Storm Dive.\n"
                "`/sand help` for examples."
            ),
            inline=False,
        )
        embed.add_field(
            name="🎰 Casino",
            value=(
                f"`/gamble` in <#{ch_id(gid, 'casino')}> — Blackjack, Roulette, Vault Heist. "
                "Shared wallet across ShadowMain and ShadowBackup."
            ),
            inline=False,
        )
        embed.add_field(
            name="🤖 Commands",
            value=(
                "`/speak` — bot speaks your text in VC, any language\n"
                "`/haste` — random Haste fact\n"
                f"`/stats` — Arma combat record (in <#{ch_id(gid, 'arma_stats')}>)"
            ),
            inline=False,
        )
        embed.add_field(
            name="🛠️ Member Tools",
            value=(
                "`/poll` — live poll (option1, option2, + up to 3 more)\n"
                "`/remindme` — personal reminder (DM or this channel)\n"
                "`/countdown` — shared event timer with optional role ping"
            ),
            inline=False,
        )
        member = ctx.author
        admin_role = resolve_role(ctx.guild, "admin_shadow") if ctx.guild else None
        if (
            isinstance(member, discord.Member)
            and admin_role
            and admin_role in member.roles
        ):
            embed.add_field(
                name="🛠️ Admin",
                value=(
                    "`/clips_deploy` · `/steam_codes_deploy` · `/role_button` · "
                    "`/send_custom` · `/edit_custom` · `/morehaste` · `/steam`"
                ),
                inline=False,
            )
        await safe_reply(ctx, embed=embed, ephemeral=True)


def setup(bot: discord.Bot):
    bot.add_cog(HubCog(bot))
