# cogs/casino/cog.py — Slash commands for ShadowSyn VIP Casino

import discord
from discord import ApplicationContext
from discord.ext import commands

from .constants import GAMBLER_ROLE_ID, OWNER_ID, TARGET_GUILD_ID, THEME_GOLD
from .economy import (
    load_scoins,
    pending_buyins,
    pending_redemptions,
    update_balance,
)
from .helpers import deny_if_wrong_channel, is_gambler, safe_reply
from .views import GambleHubView, build_gamble_hub_embed


def owner_only():
    def predicate(ctx):
        return ctx.author.id == OWNER_ID

    return commands.check(predicate)


class CasinoCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        load_scoins()

    @commands.Cog.listener()
    async def on_ready(self):
        from .buyin import BuyInAdminView
        from .shop import RedemptionAdminView

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
            print(f"⚠️ Casino admin view restore failed: {exc}")

    @discord.slash_command(
        name="gamble",
        description="VIP Casino Hub — games, daily claim, buy-in & Steam redeem",
        guild_ids=[TARGET_GUILD_ID],
        default_member_permissions=discord.Permissions.none(),
    )
    @commands.has_role(GAMBLER_ROLE_ID)
    async def gamble(self, ctx: ApplicationContext):
        if await deny_if_wrong_channel(ctx):
            return
        if not is_gambler(ctx.author):
            return await safe_reply(ctx, "🚫 Access denied.", ephemeral=True)

        await safe_reply(
            ctx,
            embed=build_gamble_hub_embed(ctx.author),
            view=GambleHubView(ctx.author),
            ephemeral=True,
        )

    @gamble.error
    async def gamble_error(self, ctx: ApplicationContext, error: discord.DiscordException):
        if isinstance(error, commands.MissingRole):
            await safe_reply(
                ctx,
                "🚫 **Access Denied** — Member clearance required.",
                ephemeral=True,
            )

    @discord.slash_command(
        name="redemptions",
        description="Owner: view pending Steam & buy-in queues",
        guild_ids=[TARGET_GUILD_ID],
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
    async def redemptions_error(self, ctx: ApplicationContext, error: discord.DiscordException):
        if isinstance(error, commands.CheckFailure):
            await safe_reply(ctx, "🚫 Owner authorization required.", ephemeral=True)

    @discord.slash_command(
        name="give_coins",
        description="Owner: grant Coins to a member",
        guild_ids=[TARGET_GUILD_ID],
        default_member_permissions=discord.Permissions.none(),
    )
    @owner_only()
    async def give_coins(self, ctx: ApplicationContext, user: discord.Member, amount: int):
        new_bal = update_balance(str(user.id), amount)
        await safe_reply(
            ctx,
            f"✅ Granted **{amount:,}** 🪙 to {user.mention}. New balance: **{new_bal:,}**.",
            ephemeral=True,
        )

    @give_coins.error
    async def give_coins_error(self, ctx: ApplicationContext, error: discord.DiscordException):
        if isinstance(error, commands.CheckFailure):
            await safe_reply(
                ctx,
                "🚫 Owner authorization required.",
                ephemeral=True,
            )
