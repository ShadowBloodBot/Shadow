# cogs/hub.py
import logging

import discord
from discord import ButtonStyle
from discord.ui import View, Button
from discord.ext import commands

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
# CONSTANTS & IDS
# ==============================================================================
THEME_PRIMARY = 0x2B0B35
OWNER_ID = 482463400929263627
ROLE_ADMIN_ID = 1214794734770323466
TARGET_GUILD_ID = 908659586536468540

LOBBY_CHANNEL_ID = 974113723188912218
GENERAL_OPEN_CHANNEL_ID = 956725685014134785
STEAM_CODES_CHANNEL_ID = 961870662006345798
WELCOME_CHANNEL_ID = 1166874144395247757
CLIPS_CHANNEL_ID = 955609588470808657
JTC_CHANNEL_ID = 1398618132788281364
ARMA_STATS_CHANNEL_ID = 1408314132473843734

MINION_ROLE_ID = 955600021502431233
ARRIVALS_THREAD_ID = 959629903186259978

MINION_BUTTON_ID = "hub_minion_grab"

HUB_TITLE = "Welcome -ShadowSyn-"
HUB_DESCRIPTION = (
    f"Grab your Starter role **[ Minion ]** so you can see\n"
    f"<#{GENERAL_OPEN_CHANNEL_ID}> & Share your <#{STEAM_CODES_CHANNEL_ID}>\n"
    f"Check out <#{WELCOME_CHANNEL_ID}> for anything else"
)


def _channel_url(channel_id: int) -> str:
    return f"https://discord.com/channels/{TARGET_GUILD_ID}/{channel_id}"


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


def _build_hub_embed() -> discord.Embed:
    return discord.Embed(
        title=HUB_TITLE,
        description=HUB_DESCRIPTION,
        color=THEME_PRIMARY,
    )


# ==============================================================================
# UI COMPONENTS
# ==============================================================================
class HubPanelView(View):
    """Persistent hub panel — Minion grab handled statelessly in on_interaction."""

    def __init__(self):
        super().__init__(timeout=None)
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
            url=_channel_url(GENERAL_OPEN_CHANNEL_ID),
        ))
        self.add_item(Button(
            label="Steam-Codes",
            style=ButtonStyle.link,
            emoji="📥",
            url=_channel_url(STEAM_CODES_CHANNEL_ID),
        ))
        self.add_item(Button(
            label="Welcome",
            style=ButtonStyle.link,
            emoji="👋",
            url=_channel_url(WELCOME_CHANNEL_ID),
        ))


# ==============================================================================
# CORE COG
# ==============================================================================
class HubCog(commands.Cog):
    def __init__(self, bot: discord.Bot):
        self.bot = bot

    # --------------------------------------------------------------------------
    # CHANNEL RESOLUTION
    # --------------------------------------------------------------------------
    async def _resolve_channel(self, channel_id: int):
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except Exception as e:
                logger.error(f"Hub channel {channel_id} unavailable: {e}")
                return None
        return channel

    # --------------------------------------------------------------------------
    # PERSISTENT VIEWS
    # --------------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_ready(self):
        try:
            self.bot.add_view(HubPanelView())
            logger.info("Hub persistent view restored.")
        except Exception as e:
            logger.error(f"Failed to restore hub view on_ready: {e}")

    # --------------------------------------------------------------------------
    # MINION GRANT (stateless component handler)
    # --------------------------------------------------------------------------
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

        role = guild.get_role(MINION_ROLE_ID)
        if role is None:
            logger.error(f"Minion role {MINION_ROLE_ID} not found in guild {guild.id}.")
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

        await safe_reply(
            interaction,
            f"👻 You're in. Start with <#{GENERAL_OPEN_CHANNEL_ID}>.",
            ephemeral=True,
        )
        await self._notify_arrivals(member)

    async def _notify_arrivals(self, member: discord.Member):
        """Mirror self-serve grants into the hidden arrivals thread for revoke power."""
        thread = await self._resolve_channel(ARRIVALS_THREAD_ID)
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

    # --------------------------------------------------------------------------
    # NEW MEMBER PING
    # --------------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot or member.guild.id != TARGET_GUILD_ID:
            return
        lobby = await self._resolve_channel(LOBBY_CHANNEL_ID)
        if lobby is None:
            return
        try:
            await lobby.send(
                content=member.mention,
                embed=_build_hub_embed(),
                view=HubPanelView(),
                allowed_mentions=discord.AllowedMentions(users=True),
            )
            logger.info(f"Hub welcome ping posted for {member.id}.")
        except Exception as e:
            logger.error(f"Failed to post hub welcome ping for {member.id}: {e}")

    # --------------------------------------------------------------------------
    # HELP
    # --------------------------------------------------------------------------
    @discord.slash_command(
        name="help",
        description="What ShadowSyn can do for you.",
        guild_ids=[TARGET_GUILD_ID],
    )
    async def help_command(self, ctx: discord.ApplicationContext):
        embed = discord.Embed(
            title="👻 ShadowSyn",
            color=THEME_PRIMARY,
        )
        embed.add_field(
            name="🔊 Voice",
            value=(
                f"Join <#{JTC_CHANNEL_ID}> to spawn your own room with a control panel "
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
                f"Hit **Submit Clip** in <#{CLIPS_CHANNEL_ID}> — Medal/YouTube link or file upload. "
                "Drop a 🔥 on the ones that deserve it."
            ),
            inline=False,
        )
        embed.add_field(
            name="🤖 Commands",
            value=(
                "`/speak` — bot speaks your text in VC, any language\n"
                "`/haste` — random Haste fact\n"
                f"`/stats` — Arma combat record (in <#{ARMA_STATS_CHANNEL_ID}>)"
            ),
            inline=False,
        )
        member = ctx.author
        if isinstance(member, discord.Member) and any(r.id == ROLE_ADMIN_ID for r in member.roles):
            embed.add_field(
                name="🛠️ Admin",
                value=(
                    "`/clips_deploy` · `/role_button` · "
                    "`/send_custom` · `/edit_custom` · `/morehaste` · `/steam`"
                ),
                inline=False,
            )
        await safe_reply(ctx, embed=embed, ephemeral=True)


def setup(bot: discord.Bot):
    bot.add_cog(HubCog(bot))
