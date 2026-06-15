# cogs/casino/views.py — ShadowSyn /gamble hub (games + buy-in + redeem)

import discord
from discord import ButtonStyle
from discord.ui import Button, Select, View

from .buyin import BuyInTierSelect, paypal_tier_url
from .constants import (
    BUYIN_PAYMENT_URL,
    BUYIN_TIERS,
    CASINO_FLOOR_TITLE,
    CASINO_OPEN_HUB_ID,
    DAILY_CLAIM_AMOUNT,
    LEADERBOARD_METRICS,
    MEMBER_TENURE_DAYS,
    REDEEM_MAX_PER_MONTH,
    SHOP_MIN_COINS,
    SHOP_TIERS,
    THEME_GOLD,
    THEME_PRIMARY,
    THEME_WIN,
)
from .economy import (
    claim_status,
    get_balance,
    player_stats,
    process_daily_claim,
    top_by_metric,
)
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
    embed.set_footer(
        text="/gamble or the pinned floor panel · Refresh updates balance"
    )
    embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
    return embed


def build_casino_floor_embed(guild_id: int | None = None) -> discord.Embed:
    casino_mention = casino_channel_mention(guild_id)
    embed = discord.Embed(
        title=CASINO_FLOOR_TITLE,
        description=(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "**Season 1 VIP Casino** · Shared wallet across ShadowMain & ShadowBackup\n"
            f"📍 {casino_mention}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "🃏 **Blackjack** · 🎡 **Roulette** · 🏦 **Vault Heist**\n"
            "Daily stipend · PayPal buy-in · Steam redeem shop\n\n"
            "Hit **Open Hub** for your private casino panel — games, wallet, stats & leaderboard."
        ),
        color=THEME_PRIMARY,
    )
    embed.set_footer(text="ShadowSyn VIP Casino · Member clearance required")
    return embed


def build_player_stats_embed(user: discord.User) -> discord.Embed:
    stats = player_stats(str(user.id))
    net = stats["net"]
    net_line = (
        f"**+{net:,}** 🪙 ({coins_to_usd(net)}) profit"
        if net > 0
        else f"**{net:,}** 🪙 ({coins_to_usd(abs(net))}) loss"
        if net < 0
        else "**Even** — break even"
    )
    best = stats["best_win"]
    best_line = (
        f"**{best:,}** 🪙 ({coins_to_usd(best)})"
        if best > 0
        else "_No recorded wins yet_"
    )
    embed = discord.Embed(
        title="📊 My Casino Stats",
        description=(
            f"Balance: {format_wallet(stats['balance'])}\n"
            f"Net P/L: {net_line}\n\n"
            f"🃏 Blackjack hands: **{stats['blackjack_hands']:,}**\n"
            f"🎡 Roulette spins: **{stats['roulette_spins']:,}**\n"
            f"🏦 Vault heists: **{stats['vault_heists']:,}**\n"
            f"🎲 Total games: **{stats['games_played']:,}**\n\n"
            f"🏆 Biggest win: {best_line}\n\n"
            f"{progress_to_shop(stats['balance'])}"
        ),
        color=THEME_GOLD,
    )
    embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
    return embed


def _format_leaderboard_value(metric: str, value: int) -> str:
    if metric == "balance":
        return f"{value:,} 🪙 ({coins_to_usd(value)})"
    if metric in ("total_won", "net_profit"):
        sign = "+" if value > 0 else ""
        return f"{sign}{value:,} 🪙 ({coins_to_usd(abs(value))})"
    return f"{value:,} games"


def build_leaderboard_embed(metric: str = "balance") -> discord.Embed:
    label = LEADERBOARD_METRICS.get(metric, "Leaderboard")
    rows = top_by_metric(metric, 10)
    if not rows:
        desc = "No stats recorded yet."
    else:
        lines = [
            f"**{i}.** <@{uid}> — {_format_leaderboard_value(metric, val)}"
            for i, (uid, val) in enumerate(rows, 1)
        ]
        desc = "\n".join(lines)
    embed = discord.Embed(
        title=f"🏆 {label}",
        description=desc,
        color=THEME_GOLD,
    )
    embed.set_footer(text="Use the menu below to switch ranking")
    return embed


class LeaderboardMetricSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=label, value=key, default=(key == "balance"))
            for key, label in LEADERBOARD_METRICS.items()
        ]
        super().__init__(
            placeholder="Switch leaderboard…",
            options=options,
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        metric = self.values[0]
        for opt in self.options:
            opt.default = opt.value == metric
        await interaction.response.edit_message(
            embed=build_leaderboard_embed(metric),
            view=LeaderboardView(metric),
        )


class LeaderboardView(View):
    def __init__(self, metric: str = "balance"):
        super().__init__(timeout=120)
        self.metric = metric
        self.add_item(LeaderboardMetricSelect())


class CasinoFloorView(View):
    """Persistent floor panel — Open Hub handled in CasinoCog.on_interaction."""

    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(
            Button(
                label="Open Hub",
                style=ButtonStyle.primary,
                emoji="🎰",
                custom_id=CASINO_OPEN_HUB_ID,
            )
        )


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

    @discord.ui.button(label="My Stats", style=ButtonStyle.secondary, emoji="📊", row=3)
    async def my_stats(self, button, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=build_player_stats_embed(interaction.user),
            ephemeral=True,
        )

    @discord.ui.button(label="Leaderboard", style=ButtonStyle.secondary, emoji="🏆", row=3)
    async def leaderboard(self, button, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=build_leaderboard_embed("balance"),
            view=LeaderboardView("balance"),
            ephemeral=True,
        )

    @discord.ui.button(label="Refresh", style=ButtonStyle.secondary, emoji="🔄", row=3)
    async def refresh(self, button, interaction: discord.Interaction):
        await interaction.response.edit_message(
            embed=build_gamble_hub_embed(interaction.user),
            view=self._refresh_view(),
        )
