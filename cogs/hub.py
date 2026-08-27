# cogs/hub.py — Minion starter-role grab handler + /help
# The static hub panel itself lives on the welcome panel (cogs/welcome.py).
import logging

import discord
from discord.ext import commands

from cogs.guild_registry import (
    REGISTERED_GUILD_IDS,
    ch_id,
    has_admin_shadow,
    is_registered_guild,
    resolve_channel,
    resolve_role,
)
from cogs.utils import safe_reply

logger = logging.getLogger("ShadowSyn.Hub")

# ==============================================================================
# CONSTANTS
# ==============================================================================
THEME_PRIMARY = 0x2B0B35
MINION_BUTTON_ID = "hub_minion_grab"


# ==============================================================================
# CORE COG
# ==============================================================================
class HubCog(commands.Cog):
    def __init__(self, bot: discord.Bot):
        self.bot = bot

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

        # ACK first — add_roles can exceed Discord's 3s interaction window.
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        try:
            await member.add_roles(role, reason="ShadowSyn Hub: starter role self-grab")
        except discord.Forbidden:
            logger.error("Forbidden while granting Minion via hub button.")
            return await interaction.followup.send(
                "❌ I can't assign roles right now. Tell an admin.",
                ephemeral=True,
            )
        except Exception as e:
            logger.error(f"Minion grant failed for {member.id}: {e}")
            return await interaction.followup.send(
                "⚠️ Something broke. Try again.",
                ephemeral=True,
            )

        game_roles = ch_id(guild.id, "game_roles")
        mention = f"<#{game_roles}>" if game_roles else "#game-roles"
        await interaction.followup.send(
            f"👻 You're in. Pick your games in {mention}.",
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

    @discord.slash_command(
        name="help",
        description="What ShadowSyn can do for you.",
        guild_ids=REGISTERED_GUILD_IDS,
    )
    async def help_command(self, ctx: discord.ApplicationContext):
        gid = ctx.guild.id if ctx.guild else REGISTERED_GUILD_IDS[0]
        embed = discord.Embed(title="👻 ShadowSyn", color=THEME_PRIMARY)
        def _ch(key: str) -> str:
            cid = ch_id(gid, key)
            return f"<#{cid}>" if cid else f"`#{key}`"

        embed.add_field(
            name="🔊 Voice",
            value=(
                f"Join {_ch('jtc')} to spawn your own room with a control panel "
                "— lock, rename, kick, bitrate, user limit."
            ),
            inline=False,
        )
        embed.add_field(
            name="🎵 Music",
            value=(
                "`/play <song name>` — pick from search results (join VC first)\n"
                "`/play <YouTube or Spotify link>` — plays that URL\n"
                "`/pause` · `/resume` · `/skip` · `/stop` · `/queue`"
            ),
            inline=False,
        )
        embed.add_field(
            name="🏆 Clips",
            value=(
                f"Drop a link or video file in {_ch('clips')} — Medal, YouTube, Twitch, TikTok, and more. "
                "Comments go in that clip's thread."
            ),
            inline=False,
        )
        embed.add_field(
            name="🎮 Steam Codes",
            value=(
                f"Open {_ch('steam_codes')} and hit **Add Steam Code** — "
                "your friend code joins the guild directory (multiple alts allowed)."
            ),
            inline=False,
        )
        embed.add_field(
            name="🏜️ SAND",
            value=(
                "In the SAND thread: `/sand craft <item>` — materials & recipes; `/sand craft pristine` for all Pristine turrets.\n"
                "`/sand help` for examples."
            ),
            inline=False,
        )
        embed.add_field(
            name="🎰 Casino",
            value=(
                f"`/gamble` or the pinned floor panel in {_ch('casino')} — "
                "Blackjack, Roulette, Vault Heist. Shared wallet across ShadowMain and ShadowBackup."
            ),
            inline=False,
        )
        embed.add_field(
            name="🤖 Commands",
            value=(
                "`/speak` — bot speaks your text in VC, any language\n"
                "`/haste` — random Haste fact"
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
        if ctx.guild and has_admin_shadow(member, ctx.guild.id):
            embed.add_field(
                name="🛠️ Admin",
                value=(
                    "`/welcome_deploy` · `/clips_deploy` · `/steam_codes_deploy` · `/casino_deploy` · "
                    "`/role_button` · `/send_custom` · `/edit_custom` · `/morehaste` · `/steam`"
                ),
                inline=False,
            )
        await safe_reply(ctx, embed=embed, ephemeral=True)


def setup(bot: discord.Bot):
    bot.add_cog(HubCog(bot))
