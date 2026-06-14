# cogs/casino/views.py — ShadowSyn /gamble hub (games + buy-in + redeem)

import discord
from discord import ButtonStyle
from discord.ui import View

from .buyin import BuyInTierSelect, paypal_tier_url
from .constants import (
    BUYIN_PAYMENT_URL,
    BUYIN_TIERS,
    DAILY_CLAIM_AMOUNT,
    MEMBER_TENURE_DAYS,
    REDEEM_MAX_PER_MONTH,
    SHOP_MIN_COINS,
    SHOP_TIERS,
    THEME_GOLD,
    THEME_PRIMARY,
    THEME_WIN,
)
from .economy import claim_status, get_balance, process_daily_claim, top_balances
from .games.blackjack import BlackjackView
from .games.roulette import RouletteLobbyView
from .games.vault_heist import VaultHeistSetupView
from .helpers import (
    WagerPickerView,
    casino_channel_mention,
    coins_to_usd,
    deny_if_not_gambler,
    format_countdown,
    format_wallet,
    in_casino_channel,
    progress_to_shop,
)
from .shop import RedeemTierSelect


def _guild_id_for_user(user: discord.User) -> int | None:
    if isinstance(user, discord.Member) and user.guild:
        return user.guild.id
    return None


def build_gamble_hub_embed(user: discord.User) -> discord.Embed:
    user_id = str(user.id)
    balance = get_balance(user_id)
    can_claim, remaining = claim_status(user_id)
    gid = _guild_id_for_user(user)
    casino_mention = casino_channel_mention(gid)
    claim_line = (
        f"✅ **Daily Claim** ready — +{DAILY_CLAIM_AMOUNT:,} Coins ({coins_to_usd(DAILY_CLAIM_AMOUNT)})"
        if can_claim
        else f"⏳ Daily claim in **{format_countdown(remaining)}** — use **Daily Claim** button"
    )

    games_block = (
        "🃏 **Blackjack** — 6:5 natural · double down\n"
        "🎡 **Roulette** — European single-zero\n"
        "🏦 **Vault Heist** — set your cash-out multiplier\n"
        "_Min bet **1¢** (10 Coins) · max $2.50/table_\n"
        "_Big wins & jackpots broadcast in this channel_"
    )
    buyin_block = "\n".join(
        f"• [{t['label']}]({paypal_tier_url(t['usd'])}) → **{t['coins']:,}** 🪙"
        for t in BUYIN_TIERS
    )
    redeem_block = "\n".join(
        f"• {t['emoji']} **{t['label']}** — {t['coins']:,} 🪙"
        for t in SHOP_TIERS
    )

    embed = discord.Embed(
        title="🎰 ShadowSyn VIP Casino Hub",
        description=(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "**Season 1** · 10,000 Coins = $10 · All actions below\n"
            f"📍 {casino_mention} only\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=THEME_PRIMARY,
    )
    embed.add_field(
        name="💳 Your Wallet",
        value=f"{format_wallet(balance)}\n{claim_line}",
        inline=False,
    )
    embed.add_field(
        name="🎲 Elite Tables",
        value=f"{games_block}\n\n*Tap a game button below*",
        inline=False,
    )
    embed.add_field(
        name="💵 Buy-In (PayPal)",
        value=(
            f"Pay via **[ShadowSyn001]({BUYIN_PAYMENT_URL})**\n"
            f"{buyin_block}\n\n*Use the **Buy Coins** dropdown*"
        ),
        inline=True,
    )
    embed.add_field(
        name="🎁 Redeem Steam",
        value=(
            f"{progress_to_shop(balance)}\n"
            f"Min **{SHOP_MIN_COINS:,}** 🪙 (${SHOP_MIN_COINS // 1000})\n\n"
            f"{redeem_block}\n\n"
            f"_{MEMBER_TENURE_DAYS}-day member · {REDEEM_MAX_PER_MONTH}/mo · 7-day cooldown_\n"
            "*Use the **Redeem Steam** dropdown*"
        ),
        inline=True,
    )
    embed.set_footer(text="/gamble opens this hub · Refresh updates balance")
    embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
    return embed


class GambleHubView(View):
    """Unified hub: games (buttons) + buy-in + redeem (dropdowns)."""

    def __init__(self, user: discord.User):
        super().__init__(timeout=300)
        balance = get_balance(str(user.id))
        self._user = user
        self.add_item(BuyInTierSelect(row=1))
        self.add_item(RedeemTierSelect(balance, row=2))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        gid = interaction.guild.id if interaction.guild else None
        if not in_casino_channel(gid, interaction.channel_id):
            await interaction.response.send_message(
                f"❌ All gambling is restricted to {casino_channel_mention(gid)}.",
                ephemeral=True,
            )
            return False
        if await deny_if_not_gambler(interaction):
            return False
        return True

    def _refresh_view(self) -> "GambleHubView":
        return GambleHubView(self._user)

    @discord.ui.button(label="Blackjack", style=ButtonStyle.primary, emoji="🃏", row=0)
    async def blackjack(self, button, interaction: discord.Interaction):
        balance = get_balance(str(interaction.user.id))

        async def start_game(inter, amount: int):
            view = BlackjackView(inter.user, amount)
            await inter.response.send_message(
                embed=view.generate_embed(), view=view, ephemeral=True
            )
            if view.game_over:
                await view.announce_if_notable(inter.client)

        embed = discord.Embed(
            title="🃏 Elite Blackjack",
            description=(
                f"Balance: {format_wallet(balance)}\n"
                "Pick a wager — **1¢** minimum (10 Coins)."
            ),
            color=THEME_PRIMARY,
        )
        await interaction.response.send_message(
            embed=embed,
            view=WagerPickerView(balance, "Elite Blackjack", start_game),
            ephemeral=True,
        )

    @discord.ui.button(label="Roulette", style=ButtonStyle.primary, emoji="🎡", row=0)
    async def roulette(self, button, interaction: discord.Interaction):
        balance = get_balance(str(interaction.user.id))
        embed = discord.Embed(
            title="🎡 European Roulette",
            description=(
                "Select your bet type from the menu below.\n"
                f"Balance: {format_wallet(balance)}\n"
                "Wagers from **1¢** (10 Coins)."
            ),
            color=THEME_PRIMARY,
        )
        await interaction.response.send_message(
            embed=embed,
            view=RouletteLobbyView(balance),
            ephemeral=True,
        )

    @discord.ui.button(label="Vault Heist", style=ButtonStyle.primary, emoji="🏦", row=0)
    async def vault_heist(self, button, interaction: discord.Interaction):
        balance = get_balance(str(interaction.user.id))
        embed = discord.Embed(
            title="🏦 Vault Heist",
            description=(
                f"Balance: {format_wallet(balance)}\n"
                "Pick a wager — **1¢** minimum (10 Coins)."
            ),
            color=THEME_PRIMARY,
        )
        await interaction.response.send_message(
            embed=embed,
            view=VaultHeistSetupView(balance),
            ephemeral=True,
        )

    @discord.ui.button(label="Daily Claim", style=ButtonStyle.success, emoji="💰", row=3)
    async def daily_claim(self, button, interaction: discord.Interaction):
        ok, message, balance = process_daily_claim(str(interaction.user.id))
        color = THEME_WIN if ok else THEME_PRIMARY
        embed = discord.Embed(
            title="💰 Daily Stipend",
            description=(
                f"{message}\n\n"
                f"Balance: {format_wallet(balance)}\n"
                f"{progress_to_shop(balance)}"
            ),
            color=color,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        if ok:
            try:
                await interaction.message.edit(
                    embed=build_gamble_hub_embed(interaction.user),
                    view=self._refresh_view(),
                )
            except Exception:
                pass

    @discord.ui.button(label="Wallet", style=ButtonStyle.secondary, emoji="💳", row=3)
    async def wallet(self, button, interaction: discord.Interaction):
        balance = get_balance(str(interaction.user.id))
        can_claim, remaining = claim_status(str(interaction.user.id))
        claim_info = (
            "Ready — tap **Daily Claim**"
            if can_claim
            else f"Resets in {format_countdown(remaining)}"
        )
        embed = discord.Embed(
            title="💳 Wallet",
            description=(
                f"Balance: {format_wallet(balance)}\n"
                f"Daily claim: {claim_info}\n\n"
                f"{progress_to_shop(balance)}"
            ),
            color=THEME_PRIMARY,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Leaderboard", style=ButtonStyle.secondary, emoji="🏆", row=3)
    async def leaderboard(self, button, interaction: discord.Interaction):
        rows = top_balances(10)
        if not rows:
            desc = "No wagers recorded yet."
        else:
            lines = [
                f"**{i}.** <@{uid}> — {bal:,} 🪙 ({coins_to_usd(bal)})"
                for i, (uid, bal) in enumerate(rows, 1)
            ]
            desc = "\n".join(lines)
        embed = discord.Embed(
            title="🏆 High-Roller Leaderboard",
            description=desc,
            color=THEME_GOLD,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Refresh", style=ButtonStyle.secondary, emoji="🔄", row=3)
    async def refresh(self, button, interaction: discord.Interaction):
        await interaction.response.edit_message(
            embed=build_gamble_hub_embed(interaction.user),
            view=self._refresh_view(),
        )
