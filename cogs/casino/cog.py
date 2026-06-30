# cogs/casino/cog.py — Slash commands for ShadowSyn VIP Casino

import logging

import discord
from discord import ApplicationContext
from discord.ext import commands

from cogs.guild_registry import REGISTERED_GUILD_IDS, has_admin_shadow, resolve_channel

from .constants import CASINO_OPEN_HUB_ID, OWNER_ID, THEME_GOLD
from .economy import (
    clear_panel_id,
    get_panel_id,
    load_scoins,
    pending_buyins,
    pending_redemptions,
    set_panel_id,
    update_balance,
)
from .helpers import deny_if_wrong_channel, is_gambler, open_gamble_hub, safe_reply
from .views import CasinoFloorView, build_casino_floor_embed

logger = logging.getLogger(__name__)


def owner_only():
    def predicate(ctx):
        return ctx.author.id == OWNER_ID

    return commands.check(predicate)


class CasinoCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._views_restored = False
        load_scoins()

    @commands.Cog.listener()
    async def on_ready(self):
        if self._views_restored:
            return
        self._views_restored = True

        from .buyin import BuyInAdminView
        from .shop import RedemptionAdminView

        try:
            self.bot.add_view(CasinoFloorView())
        except Exception as exc:
            logger.warning("Casino floor view restore failed: %s", exc)

        try:
            for req in pending_redemptions():
                self.bot.add_view(
                    RedemptionAdminView(
                        req["id"], int(req["user_id"]), req["coins"]
                    )
                )
            for req in pending_buyins():
                self.bot.add_view(
                    BuyInAdminView(req["id"], int(req["user_id"]), req["coins"])
                )
        except Exception as exc:
            logger.warning("Casino admin view restore failed: %s", exc)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        custom_id = interaction.data.get("custom_id", "") if interaction.data else ""
        if custom_id != CASINO_OPEN_HUB_ID:
            return
        try:
            await open_gamble_hub(interaction)
        except Exception as exc:
            logger.error(f"casino_open_hub failed: {exc}")

    @discord.slash_command(
        name="gamble",
        description="VIP Casino Hub — games, daily claim, buy-in & Steam redeem",
        guild_ids=REGISTERED_GUILD_IDS,
        default_member_permissions=discord.Permissions.none(),
    )
    async def gamble(self, ctx: ApplicationContext):
        if await deny_if_wrong_channel(ctx):
            return
        if not is_gambler(ctx.author, ctx.guild.id if ctx.guild else None):
            return await safe_reply(
                ctx,
                "🚫 **Access Denied** — Member clearance required.",
                ephemeral=True,
            )

        from .views import GambleHubView, build_gamble_hub_embed

        await safe_reply(
            ctx,
            embed=build_gamble_hub_embed(ctx.author),
            view=GambleHubView(ctx.author),
            ephemeral=True,
        )

    @discord.slash_command(
        name="casino_deploy",
        description="Post the pinned VIP Casino floor panel to this guild's casino channel.",
        guild_ids=REGISTERED_GUILD_IDS,
        default_member_permissions=discord.Permissions(administrator=True),
    )
    async def casino_deploy(self, ctx: ApplicationContext):
        if not ctx.guild:
            return await safe_reply(ctx, "⛔ Guild context required.", ephemeral=True)
        if not has_admin_shadow(ctx.author, ctx.guild.id):
            return await safe_reply(ctx, "🚫 Admin clearance required.", ephemeral=True)

        channel = await resolve_channel(self.bot, ctx.guild.id, "casino")
        if channel is None:
            return await safe_reply(
                ctx, "❌ Casino channel not found in registry.", ephemeral=True
            )

        await ctx.defer(ephemeral=True)

        old_id = get_panel_id(ctx.guild.id)
        if old_id:
            try:
                old_msg = await channel.fetch_message(old_id)
                await old_msg.delete()
            except discord.NotFound:
                clear_panel_id(ctx.guild.id)
            except Exception as exc:
                logger.warning(f"Could not delete old casino panel {old_id}: {exc}")

        try:
            msg = await channel.send(
                embed=build_casino_floor_embed(ctx.guild.id),
                view=CasinoFloorView(),
            )
            set_panel_id(ctx.guild.id, msg.id)
            self.bot.add_view(CasinoFloorView())
            await ctx.followup.send(
                f"✅ Casino floor live in {channel.mention} · message `{msg.id}`",
                ephemeral=True,
            )
        except Exception as exc:
            logger.error(f"casino_deploy failed: {exc}")
            await ctx.followup.send(f"❌ Deploy failed: {exc}", ephemeral=True)

    @casino_deploy.error
    async def casino_deploy_error(
        self, ctx: ApplicationContext, error: discord.DiscordException
    ):
        if isinstance(error, (commands.MissingRole, commands.CheckFailure)):
            await safe_reply(ctx, "🚫 Admin clearance required.", ephemeral=True)
        else:
            logger.error(f"casino_deploy error: {error}")
            await safe_reply(ctx, f"⚠️ Error: {error}", ephemeral=True)

    @discord.slash_command(
        name="redemptions",
        description="Owner: view pending Steam & buy-in queues",
        guild_ids=REGISTERED_GUILD_IDS,
        default_member_permissions=discord.Permissions.none(),
    )
    @owner_only()
    async def redemptions(self, ctx: ApplicationContext):
        steam = pending_redemptions()
        buys = pending_buyins()
        if not steam and not buys:
            return await safe_reply(ctx, "✅ No pending requests.", ephemeral=True)

        parts = []
        if steam:
            lines = [
                f"• `{req['id']}` — <@{req['user_id']}> — "
                f"**${req['usd']}** Steam ({req['coins']:,} 🪙)\n"
                f"  Steam: `{req['steam_id']}`"
                for req in steam
            ]
            parts.append("**🎁 Steam Redemptions**\n" + "\n".join(lines))
        if buys:
            lines = [
                f"• `{req['id']}` — <@{req['user_id']}> — "
                f"**${req['usd']}** → {req['coins']:,} 🪙\n"
                f"  Ref: `{req['payment_ref']}`"
                for req in buys
            ]
            parts.append("**💵 Coin Buy-Ins**\n" + "\n".join(lines))

        embed = discord.Embed(
            title="📋 Pending Queues",
            description="\n\n".join(parts),
            color=THEME_GOLD,
        )
        await safe_reply(ctx, embed=embed, ephemeral=True)

    @redemptions.error
    async def redemptions_error(
        self, ctx: ApplicationContext, error: discord.DiscordException
    ):
        if isinstance(error, commands.CheckFailure):
            await safe_reply(ctx, "🚫 Owner authorization required.", ephemeral=True)

    @discord.slash_command(
        name="give_coins",
        description="Owner: grant Coins to a member",
        guild_ids=REGISTERED_GUILD_IDS,
        default_member_permissions=discord.Permissions.none(),
    )
    @owner_only()
    async def give_coins(self, ctx: ApplicationContext, user: discord.Member, amount: int):
        if amount <= 0:
            return await safe_reply(
                ctx, "❌ Amount must be a positive integer.", ephemeral=True
            )
        new_bal = update_balance(str(user.id), amount)
        await safe_reply(
            ctx,
            f"✅ Granted **{amount:,}** 🪙 to {user.mention}. New balance: **{new_bal:,}**.",
            ephemeral=True,
        )

    @give_coins.error
    async def give_coins_error(
        self, ctx: ApplicationContext, error: discord.DiscordException
    ):
        if isinstance(error, commands.CheckFailure):
            await safe_reply(
                ctx,
                "🚫 Owner authorization required.",
                ephemeral=True,
            )
