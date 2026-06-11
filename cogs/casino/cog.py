# cogs/casino/cog.py — Slash commands for ShadowSyn VIP Casino

import random

import discord
from discord import ApplicationContext, Option
from discord.ext import commands

from .constants import (
    DAILY_CLAIM_AMOUNT,
    GAMBLER_ROLE_ID,
    OWNER_ID,
    SHOP_MIN_COINS,
    TARGET_GUILD_ID,
    THEME_GOLD,
    THEME_PRIMARY,
)
from .economy import (
    get_balance,
    load_scoins,
    pending_buyins,
    pending_redemptions,
    process_daily_claim,
    update_balance,
)
from .helpers import (
    coins_to_usd,
    deny_if_wrong_channel,
    format_wallet,
    is_gambler,
    progress_to_shop,
    safe_reply,
)
from .views import GambleHubView, build_gamble_hub_embed

build_lobby_embed = build_gamble_hub_embed
CasinoLobby = GambleHubView


class DuelAcceptView(discord.ui.View):
    """Legacy PvP duel — preserved for backward compatibility."""

    def __init__(self, p1: discord.Member, p2: discord.Member, amount: int):
        super().__init__(timeout=60)
        self.p1 = p1
        self.p2 = p2
        self.amount = amount

    @discord.ui.button(label="ACCEPT DUEL", style=discord.ButtonStyle.danger, emoji="⚔️")
    async def accept(self, button, interaction: discord.Interaction):
        if interaction.user.id != self.p2.id:
            return
        p1_id, p2_id = str(self.p1.id), str(self.p2.id)
        if get_balance(p1_id) < self.amount or get_balance(p2_id) < self.amount:
            return await interaction.response.send_message(
                "❌ Someone went broke during the wait.", ephemeral=True
            )

        update_balance(p1_id, -self.amount)
        update_balance(p2_id, -self.amount)
        winner = random.choice([self.p1, self.p2])
        loser = self.p2 if winner == self.p1 else self.p1
        win_amt = self.amount * 2
        update_balance(str(winner.id), win_amt)

        embed = discord.Embed(
            title="🩸 DUEL FINISHED",
            description=(
                f"🏆 **Winner:** {winner.mention}\n"
                f"💀 **Loser:** {loser.mention}\n"
                f"💰 **Won:** {win_amt:,} 🪙"
            ),
            color=THEME_GOLD,
        )
        self.clear_items()
        await interaction.response.edit_message(view=self, embed=embed)


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
        description="Open the VIP Casino Hub — games, buy-in & Steam redeem",
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
        name="claim",
        description=f"Claim your daily {DAILY_CLAIM_AMOUNT:,} Coins stipend",
        guild_ids=[TARGET_GUILD_ID],
        default_member_permissions=discord.Permissions.none(),
    )
    @commands.has_role(GAMBLER_ROLE_ID)
    async def claim(self, ctx: ApplicationContext):
        if await deny_if_wrong_channel(ctx):
            return
        if not is_gambler(ctx.author):
            return await safe_reply(ctx, "🚫 Access denied.", ephemeral=True)

        ok, message, balance = process_daily_claim(str(ctx.author.id))
        color = THEME_GOLD if ok else THEME_PRIMARY
        embed = discord.Embed(
            title="💰 Daily Stipend",
            description=(
                f"{message}\n\n"
                f"Balance: {format_wallet(balance)}\n"
                f"{progress_to_shop(balance)}"
            ),
            color=color,
        )
        await safe_reply(ctx, embed=embed, ephemeral=True)

    @claim.error
    async def claim_error(self, ctx: ApplicationContext, error: discord.DiscordException):
        if isinstance(error, commands.MissingRole):
            await safe_reply(
                ctx,
                "🚫 **Access Denied** — Member clearance required.",
                ephemeral=True,
            )

    @discord.slash_command(
        name="duel",
        description="Challenge a member to a Coin duel",
        guild_ids=[TARGET_GUILD_ID],
        default_member_permissions=discord.Permissions.none(),
    )
    @commands.has_role(GAMBLER_ROLE_ID)
    async def duel(self, ctx: ApplicationContext, opponent: discord.Member, amount: str):
        if await deny_if_wrong_channel(ctx):
            return
        if not is_gambler(ctx.author):
            return await safe_reply(ctx, "🚫 Access denied.", ephemeral=True)
        if amount == "all":
            bet = get_balance(str(ctx.author.id))
        else:
            try:
                bet = int(amount)
            except ValueError:
                return await safe_reply(ctx, "❌ Invalid amount.", ephemeral=True)

        embed = discord.Embed(
            title="⚔️ DUEL",
            description=f"{ctx.author.mention} vs {opponent.mention}\nPot: {bet * 2:,} 🪙",
            color=discord.Color.red(),
        )
        await safe_reply(
            ctx,
            content=opponent.mention,
            embed=embed,
            view=DuelAcceptView(ctx.author, opponent, bet),
        )

    @duel.error
    async def duel_error(self, ctx: ApplicationContext, error: discord.DiscordException):
        if isinstance(error, commands.MissingRole):
            await safe_reply(
                ctx,
                "🚫 **Access Denied** — Member clearance required.",
                ephemeral=True,
            )

    @discord.slash_command(
        name="buyin",
        description="Open Casino Hub — PayPal buy-in ($1–$5)",
        guild_ids=[TARGET_GUILD_ID],
        default_member_permissions=discord.Permissions.none(),
    )
    @commands.has_role(GAMBLER_ROLE_ID)
    async def buyin(self, ctx: ApplicationContext):
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

    @buyin.error
    async def buyin_error(self, ctx: ApplicationContext, error: discord.DiscordException):
        if isinstance(error, commands.MissingRole):
            await safe_reply(
                ctx,
                "🚫 **Access Denied** — Member clearance required.",
                ephemeral=True,
            )

    @discord.slash_command(
        name="shop",
        description="Open Casino Hub — Steam redeem & PayPal buy-in",
        guild_ids=[TARGET_GUILD_ID],
        default_member_permissions=discord.Permissions.none(),
    )
    @commands.has_role(GAMBLER_ROLE_ID)
    async def shop(self, ctx: ApplicationContext):
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

    @shop.error
    async def shop_error(self, ctx: ApplicationContext, error: discord.DiscordException):
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
        name="wallet",
        description="Check Coin balance and Steam shop progress",
        guild_ids=[TARGET_GUILD_ID],
        default_member_permissions=discord.Permissions.none(),
    )
    @commands.has_role(GAMBLER_ROLE_ID)
    async def wallet(self, ctx: ApplicationContext, user: Option(discord.User, required=False)):
        if await deny_if_wrong_channel(ctx):
            return
        if not is_gambler(ctx.author):
            return await safe_reply(ctx, "🚫 Access denied.", ephemeral=True)
        target = user or ctx.author
        bal = get_balance(str(target.id))
        desc = f"**{target.display_name}:** {format_wallet(bal)}"
        if target.id == ctx.author.id:
            desc += f"\n{progress_to_shop(bal)}"
        await safe_reply(ctx, desc)

    @wallet.error
    async def wallet_error(self, ctx: ApplicationContext, error: discord.DiscordException):
        if isinstance(error, commands.MissingRole):
            await safe_reply(
                ctx,
                "🚫 **Access Denied** — Member clearance required.",
                ephemeral=True,
            )

    @discord.slash_command(
        name="give_scoins",
        description="Owner: grant Coins to a member",
        guild_ids=[TARGET_GUILD_ID],
        default_member_permissions=discord.Permissions.none(),
    )
    @owner_only()
    async def give_scoins(self, ctx: ApplicationContext, user: discord.Member, amount: int):
        new_bal = update_balance(str(user.id), amount)
        await safe_reply(
            ctx,
            f"✅ Granted **{amount:,}** 🪙 to {user.mention}. New balance: **{new_bal:,}**.",
            ephemeral=True,
        )

    @give_scoins.error
    async def give_scoins_error(self, ctx: ApplicationContext, error: discord.DiscordException):
        if isinstance(error, commands.CheckFailure):
            await safe_reply(
                ctx,
                "🚫 Owner authorization required.",
                ephemeral=True,
            )
