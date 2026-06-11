# cogs/casino/helpers.py — Shared casino utilities

import discord
from discord.ui import Modal, TextInput

from .constants import COINS_PER_USD, CASINO_CHANNEL_ID, GAMBLER_ROLE_ID, MAX_BET, MIN_BET, SHOP_MIN_COINS
from .economy import get_balance


CASINO_CHANNEL_MENTION = f"<#{CASINO_CHANNEL_ID}>"


def in_casino_channel(channel_id: int | None) -> bool:
    return channel_id == CASINO_CHANNEL_ID


async def deny_if_wrong_channel(ctx_or_inter) -> bool:
    channel_id = getattr(ctx_or_inter, "channel_id", None)
    if channel_id is None and hasattr(ctx_or_inter, "channel"):
        channel_id = ctx_or_inter.channel.id
    if in_casino_channel(channel_id):
        return False

    msg = f"❌ All gambling commands are restricted to {CASINO_CHANNEL_MENTION}."
    if hasattr(ctx_or_inter, "respond"):
        await safe_reply(ctx_or_inter, msg, ephemeral=True)
    elif hasattr(ctx_or_inter, "response"):
        if not ctx_or_inter.response.is_done():
            await ctx_or_inter.response.send_message(msg, ephemeral=True)
        else:
            await ctx_or_inter.followup.send(msg, ephemeral=True)
    return True


def is_gambler(user) -> bool:
    if not isinstance(user, discord.Member):
        return False
    return any(role.id == GAMBLER_ROLE_ID for role in user.roles)


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


class BetAmountModal(Modal):
    def __init__(self, title: str, balance: int, callback_func):
        super().__init__(title=title[:45])
        self.balance = balance
        self.callback_func = callback_func
        self.add_item(
            TextInput(
                label=f"Wager ({coins_to_usd(balance)} avail)"[:45],
                placeholder="50, 100, 250, 500, or 'all'",
                min_length=1,
            )
        )

    async def callback(self, interaction: discord.Interaction):
        raw = self.children[0].value.lower().strip()
        if raw == "all":
            amount = self.balance
        else:
            try:
                amount = int(raw.replace(",", ""))
            except ValueError:
                return await interaction.response.send_message(
                    "❌ Enter a valid whole number.", ephemeral=True
                )

        if amount < MIN_BET:
            return await interaction.response.send_message(
                f"❌ Minimum wager is {MIN_BET:,} Coins ({coins_to_usd(MIN_BET)}).",
                ephemeral=True,
            )
        if amount > MAX_BET:
            return await interaction.response.send_message(
                f"❌ Maximum wager is {MAX_BET:,} Coins ({coins_to_usd(MAX_BET)}).",
                ephemeral=True,
            )
        if amount > self.balance:
            return await interaction.response.send_message(
                "❌ Insufficient balance.", ephemeral=True
            )
        await self.callback_func(interaction, amount)


def gambler_gate(interaction: discord.Interaction) -> bool:
    return is_gambler(interaction.user)


async def deny_if_not_gambler(interaction: discord.Interaction) -> bool:
    if not gambler_gate(interaction):
        await interaction.response.send_message(
            "🚫 **Access Denied** — Member clearance required.",
            ephemeral=True,
        )
        return True
    return False
