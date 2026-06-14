# cogs/casino/helpers.py — Shared casino utilities

import discord
from discord.ui import Modal, TextInput

from cogs.guild_registry import ch_id, resolve_channel, role_id, REGISTERED_GUILD_IDS

from .constants import (
    COINS_PER_CENT,
    COINS_PER_USD,
    MAX_BET,
    MIN_BET,
    QUICK_BETS,
    SHOP_MIN_COINS,
)
from .economy import get_balance


def casino_channel_id(guild_id: int | None) -> int | None:
    if guild_id is None:
        return None
    return ch_id(guild_id, "casino")


async def resolve_casino_channel(bot, guild_id: int | None):
    if guild_id is None:
        return None
    channel = await resolve_channel(bot, guild_id, "casino")
    return channel


def casino_channel_mention(guild_id: int | None) -> str:
    cid = casino_channel_id(guild_id)
    return f"<#{cid}>" if cid else "#casino"


def in_casino_channel(guild_id: int | None, channel_id: int | None) -> bool:
    expected = casino_channel_id(guild_id)
    return expected is not None and channel_id == expected


async def deny_if_wrong_channel(ctx_or_inter) -> bool:
    channel_id = getattr(ctx_or_inter, "channel_id", None)
    guild_id = getattr(ctx_or_inter, "guild_id", None)
    if channel_id is None and hasattr(ctx_or_inter, "channel"):
        channel_id = ctx_or_inter.channel.id
    if guild_id is None and hasattr(ctx_or_inter, "guild") and ctx_or_inter.guild:
        guild_id = ctx_or_inter.guild.id
    if in_casino_channel(guild_id, channel_id):
        return False

    msg = f"❌ All gambling commands are restricted to {casino_channel_mention(guild_id)}."
    if hasattr(ctx_or_inter, "respond"):
        await safe_reply(ctx_or_inter, msg, ephemeral=True)
    elif hasattr(ctx_or_inter, "response"):
        if not ctx_or_inter.response.is_done():
            await ctx_or_inter.response.send_message(msg, ephemeral=True)
        else:
            await ctx_or_inter.followup.send(msg, ephemeral=True)
    return True


def is_gambler(user, guild_id: int | None = None) -> bool:
    if not isinstance(user, discord.Member):
        return False
    gid = guild_id or (user.guild.id if user.guild else None)
    if gid is None:
        return False
    rid = role_id(gid, "member")
    if rid is None:
        return False
    return any(role.id == rid for role in user.roles)


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


def coins_to_usd(coins: int) -> str:
    return f"${coins / COINS_PER_USD:.2f}"


def format_coins(amount: int) -> str:
    return f"**{amount:,}** 🪙"


def format_wallet(amount: int) -> str:
    return f"**{amount:,}** 🪙 · {coins_to_usd(amount)}"


def progress_to_shop(balance: int, target: int = SHOP_MIN_COINS, width: int = 12) -> str:
    pct = min(balance / target, 1.0) if target else 0
    filled = int(pct * width)
    bar = "█" * filled + "░" * (width - filled)
    usd_left = max(0, target - balance) / COINS_PER_USD
    if balance >= target:
        return f"`{bar}` **100%** — Shop unlocked!"
    return (
        f"`{bar}` **{int(pct * 100)}%** toward ${target // COINS_PER_USD} Steam "
        f"({balance:,}/{target:,} · ${usd_left:.2f} to go)"
    )


def format_countdown(seconds: int) -> str:
    hours = seconds // 3600
    mins = (seconds % 3600) // 60
    if hours:
        return f"{hours}h {mins}m"
    return f"{mins}m"


def format_wager_label(coins: int) -> str:
    if coins < COINS_PER_USD:
        cents = coins // COINS_PER_CENT
        return f"{cents}¢"
    return coins_to_usd(coins)


def parse_wager(raw: str, balance: int) -> tuple[int | None, str | None]:
    text = raw.lower().strip()
    if text == "all":
        amount = balance - (balance % COINS_PER_CENT)
        if amount < MIN_BET:
            return None, f"Balance too low for a cent wager (min {MIN_BET} Coins / 1¢)."
        return amount, None
    try:
        amount = int(text.replace(",", "").replace("$", ""))
    except ValueError:
        return None, "❌ Enter a whole number of Coins, or `all`."

    if amount % COINS_PER_CENT != 0:
        return None, f"❌ Wagers must be in **cent steps** ({COINS_PER_CENT} Coins = 1¢)."
    if amount < MIN_BET:
        return None, f"❌ Minimum wager is **{MIN_BET} Coins (1¢)**."
    if amount > MAX_BET:
        return None, f"❌ Maximum wager is **{MAX_BET:,} Coins** ({coins_to_usd(MAX_BET)})."
    if amount > balance:
        return None, "❌ Insufficient balance."
    return amount, None


class BetAmountModal(Modal):
    def __init__(self, title: str, balance: int, callback_func):
        super().__init__(title=title[:45])
        self.balance = balance
        self.callback_func = callback_func
        self.add_item(
            TextInput(
                label=f"Wager in Coins — 10 = 1¢"[:45],
                placeholder="10, 50, 100, 250, or 'all'",
                min_length=1,
            )
        )

    async def callback(self, interaction: discord.Interaction):
        amount, err = parse_wager(self.children[0].value, self.balance)
        if err:
            return await interaction.response.send_message(err, ephemeral=True)
        await self.callback_func(interaction, amount)


class WagerPickerView(discord.ui.View):
    def __init__(self, balance: int, title: str, on_amount):
        super().__init__(timeout=120)
        self.balance = balance
        self.title = title
        self.on_amount = on_amount

        for coins in QUICK_BETS:
            if coins <= balance:
                btn = discord.ui.Button(
                    label=format_wager_label(coins),
                    style=discord.ButtonStyle.secondary,
                )
                btn.callback = self._make_quick_callback(coins)
                self.add_item(btn)

    def _make_quick_callback(self, coins: int):
        async def handler(interaction: discord.Interaction):
            await self.on_amount(interaction, coins)

        return handler

    @discord.ui.button(label="Custom", style=discord.ButtonStyle.primary, emoji="✏️", row=1)
    async def custom(self, button, interaction: discord.Interaction):
        await interaction.response.send_modal(
            BetAmountModal(self.title, self.balance, self.on_amount)
        )


def gambler_gate(interaction: discord.Interaction) -> bool:
    gid = interaction.guild.id if interaction.guild else None
    return is_gambler(interaction.user, gid)


async def deny_if_not_gambler(interaction: discord.Interaction) -> bool:
    if not gambler_gate(interaction):
        await interaction.response.send_message(
            "🚫 **Access Denied** — Member clearance required.",
            ephemeral=True,
        )
        return True
    return False
