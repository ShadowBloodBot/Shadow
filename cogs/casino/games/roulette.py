# cogs/casino/games/roulette.py — European Roulette engine

import asyncio
import random

import discord
from discord.ui import Modal, Select, TextInput, View

from ..announcements import maybe_announce_win
from ..constants import ROULETTE_RED, THEME_GOLD, THEME_LOSS, THEME_PRIMARY, THEME_WIN
from ..economy import get_balance, record_stat, update_balance
from ..helpers import WagerPickerView, coins_to_usd, format_coins, parse_wager


BET_OPTIONS = [
    discord.SelectOption(label="Red", description="1:1 payout", value="red", emoji="🔴"),
    discord.SelectOption(label="Black", description="1:1 payout", value="black", emoji="⚫"),
    discord.SelectOption(label="Even", description="1:1 payout", value="even", emoji="2️⃣"),
    discord.SelectOption(label="Odd", description="1:1 payout", value="odd", emoji="1️⃣"),
    discord.SelectOption(label="Low (1–18)", description="1:1 payout", value="low", emoji="⬇️"),
    discord.SelectOption(label="High (19–36)", description="1:1 payout", value="high", emoji="⬆️"),
    discord.SelectOption(label="Straight Number", description="35:1 payout — pick 0–36", value="straight", emoji="🎯"),
]


def _wheel_color(number: int) -> str:
    if number == 0:
        return "green"
    return "red" if number in ROULETTE_RED else "black"


def _color_emoji(number: int) -> str:
    color = _wheel_color(number)
    if color == "green":
        return "🟢"
    if color == "red":
        return "🔴"
    return "⚫"


def _evaluate_bet(bet_type: str, target: int | None, result: int) -> tuple[bool, float]:
    if bet_type == "straight":
        return result == target, 35.0
    if result == 0:
        return False, 0.0
    if bet_type == "red":
        return result in ROULETTE_RED, 1.0
    if bet_type == "black":
        return result not in ROULETTE_RED, 1.0
    if bet_type == "even":
        return result % 2 == 0, 1.0
    if bet_type == "odd":
        return result % 2 == 1, 1.0
    if bet_type == "low":
        return 1 <= result <= 18, 1.0
    if bet_type == "high":
        return 19 <= result <= 36, 1.0
    return False, 0.0


class StraightNumberModal(Modal):
    def __init__(self, balance: int, bet_type: str, on_ready):
        super().__init__(title="Straight Number Bet"[:45])
        self.balance = balance
        self.bet_type = bet_type
        self.on_ready = on_ready
        self.add_item(TextInput(label="Wager — 10 Coins = 1¢"[:45], placeholder="10, 50, 100, or 'all'"))
        self.add_item(TextInput(label="Number (0–36)"[:45], placeholder="e.g. 17", min_length=1, max_length=2))

    async def callback(self, interaction: discord.Interaction):
        amount, err = parse_wager(self.children[0].value, self.balance)
        if err:
            return await interaction.response.send_message(err, ephemeral=True)
        try:
            target = int(self.children[1].value.strip())
        except ValueError:
            return await interaction.response.send_message("❌ Invalid number.", ephemeral=True)
        if not 0 <= target <= 36:
            return await interaction.response.send_message("❌ Pick 0–36.", ephemeral=True)
        await self.on_ready(interaction, amount, self.bet_type, target)


class RouletteWagerModal(Modal):
    def __init__(self, balance: int, bet_type: str, on_ready):
        super().__init__(title="Roulette Wager"[:45])
        self.balance = balance
        self.bet_type = bet_type
        self.on_ready = on_ready
        self.add_item(TextInput(label="Wager — 10 Coins = 1¢"[:45], placeholder="10, 50, 100, or 'all'"))

    async def callback(self, interaction: discord.Interaction):
        amount, err = parse_wager(self.children[0].value, self.balance)
        if err:
            return await interaction.response.send_message(err, ephemeral=True)
        await self.on_ready(interaction, amount, self.bet_type, None)


class RouletteBetSelect(Select):
    def __init__(self, balance: int):
        super().__init__(
            placeholder="Choose your bet type…",
            min_values=1,
            max_values=1,
            options=BET_OPTIONS,
        )
        self.balance = balance

    async def callback(self, interaction: discord.Interaction):
        bet_type = self.values[0]
        if bet_type == "straight":
            await interaction.response.send_modal(
                StraightNumberModal(self.balance, bet_type, spin_roulette)
            )
        else:
            await interaction.response.send_modal(
                RouletteWagerModal(self.balance, bet_type, spin_roulette)
            )


class RouletteLobbyView(View):
    def __init__(self, balance: int):
        super().__init__(timeout=120)
        self.add_item(RouletteBetSelect(balance))


async def spin_roulette(
    interaction: discord.Interaction,
    amount: int,
    bet_type: str,
    target: int | None,
) -> None:
    user_id = str(interaction.user.id)
    update_balance(user_id, -amount)
    record_stat(user_id, "roulette_spins")

    bet_label = bet_type.replace("_", " ").title()
    if bet_type == "straight":
        bet_label = f"Straight **{target}**"

    spin_embed = discord.Embed(
        title="🎡 European Roulette",
        description=(
            "━━━━━━━━━━━━━━━━━━\n"
            "🌀 **The wheel is spinning…**\n"
            "`▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓`\n"
            f"Your bet: **{bet_label}** — {format_coins(amount)}"
        ),
        color=THEME_PRIMARY,
    )
    await interaction.response.send_message(embed=spin_embed, ephemeral=True)

    await asyncio.sleep(1.2)
    tick = random.randint(0, 36)
    mid_embed = discord.Embed(
        title="🎡 European Roulette",
        description=(
            "━━━━━━━━━━━━━━━━━━\n"
            f"⚡ Ball crossing… `{tick}`\n"
            f"Your bet: **{bet_label}** — {format_coins(amount)}"
        ),
        color=THEME_GOLD,
    )
    try:
        await interaction.edit_original_response(embed=mid_embed)
    except Exception:
        pass

    await asyncio.sleep(1.4)
    result = random.randint(0, 36)
    won, multiplier = _evaluate_bet(bet_type, target, result)
    emoji = _color_emoji(result)

    if won:
        payout = int(amount * (multiplier + 1))
        profit = payout - amount
        update_balance(user_id, payout)
        record_stat(user_id, "total_won", profit)
        color = THEME_WIN
        outcome = f"✅ **Winner!** Payout {format_coins(payout)} (+{profit:,} profit)"
        flags: dict = {}
        headline = f"Hit **{bet_label}** on {result}!"
        if bet_type == "straight":
            flags["roulette_straight"] = True
            headline = f"Straight **{target}** hits {result}!"
        await maybe_announce_win(
            interaction.client,
            interaction.user,
            "Roulette",
            profit,
            payout,
            amount,
            headline,
            flags=flags,
        )
    else:
        record_stat(user_id, "total_lost", amount)
        color = THEME_LOSS
        outcome = f"❌ **No hit.** Lost {format_coins(amount)}."

    final_embed = discord.Embed(
        title="🎡 European Roulette — Result",
        description=(
            "━━━━━━━━━━━━━━━━━━\n"
            f"{emoji} **Ball landed on {result}**\n\n"
            f"{outcome}\n\n"
            f"Balance: {format_coins(get_balance(user_id))}"
        ),
        color=color,
    )
    final_embed.set_footer(text=f"Bet: {bet_label} • Wager: {amount:,} 🪙")
    try:
        await interaction.edit_original_response(embed=final_embed)
    except Exception:
        pass
