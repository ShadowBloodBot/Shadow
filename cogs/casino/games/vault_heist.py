# cogs/casino/games/vault_heist.py — Vault Heist (Crash) engine

import asyncio
import random

import discord
from discord.ui import Modal, TextInput, View

from ..constants import THEME_INFO, THEME_LOSS, THEME_PRIMARY, THEME_WARNING, THEME_WIN, VAULT_HOUSE_MULTIPLIER
from ..economy import get_balance, record_stat, update_balance
from ..helpers import WagerPickerView, coins_to_usd, format_coins


class VaultMultiplierModal(Modal):
    def __init__(self, bet: int):
        super().__init__(title="Vault Heist — Cash-Out"[:45])
        self.bet = bet
        self.add_item(
            TextInput(
                label="Cash-out multiplier (min 1.10x)"[:45],
                placeholder="e.g. 2.50",
                value="2.00",
            )
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            target = float(self.children[0].value.replace(",", "."))
        except ValueError:
            return await interaction.response.send_message("❌ Invalid multiplier.", ephemeral=True)
        if target < 1.10:
            return await interaction.response.send_message("❌ Minimum cash-out is **1.10x**.", ephemeral=True)
        if target > 100:
            return await interaction.response.send_message("❌ Maximum cash-out is **100x**.", ephemeral=True)
        await run_vault_heist(interaction, self.bet, target)


class VaultHeistSetupView(WagerPickerView):
    """Pick cent wager, then set cash-out multiplier."""

    def __init__(self, balance: int):
        super().__init__(balance, "Vault Heist", self._on_amount)

    async def _on_amount(self, interaction: discord.Interaction, amount: int):
        embed = discord.Embed(
            title="🏦 Vault Heist — Set Multiplier",
            description=(
                f"Wager locked: {format_coins(amount)} ({coins_to_usd(amount)})\n"
                "Tap **Launch Heist** to set your cash-out target."
            ),
            color=THEME_PRIMARY,
        )
        await interaction.response.send_message(
            embed=embed,
            view=_MultiplierOnlyView(amount),
            ephemeral=True,
        )


class _MultiplierOnlyView(View):
    def __init__(self, bet: int):
        super().__init__(timeout=120)
        self.bet = bet

    @discord.ui.button(label="Launch Heist", style=discord.ButtonStyle.danger, emoji="🏦")
    async def launch(self, button, interaction: discord.Interaction):
        await interaction.response.send_modal(VaultMultiplierModal(self.bet))


async def run_vault_heist(interaction: discord.Interaction, bet: int, target: float) -> None:
    user_id = str(interaction.user.id)
    update_balance(user_id, -bet)
    record_stat(user_id, "vault_heists")

    crash_point = round(VAULT_HOUSE_MULTIPLIER / (1.0 - random.random()), 2)

    phases = [
        (
            discord.Embed(
                title="🏦 Vault Heist — Infiltration",
                description=(
                    "━━━━━━━━━━━━━━━━━━\n"
                    "🕶️ **Team deployed.** Laser grid active.\n"
                    "`▰▰▰▰▰▰▰▱▱▱`  **1.00x**\n\n"
                    f"Target escape: **{target:.2f}x** • Wager: {format_coins(bet)}"
                ),
                color=THEME_INFO,
            ),
            1.0,
        ),
    ]

    if crash_point > 1.25:
        mid = round(1.0 + (min(crash_point, target) - 1.0) * random.uniform(0.35, 0.65), 2)
        phases.append(
            (
                discord.Embed(
                    title="🏦 Vault Heist — Extraction",
                    description=(
                        "━━━━━━━━━━━━━━━━━━\n"
                        "💨 **Vault breached!** Security closing in…\n"
                        f"`{'▰' * int(mid)}{'▱' * max(0, 10 - int(mid))}`  **{mid:.2f}x**\n\n"
                        f"Target escape: **{target:.2f}x** • Wager: {format_coins(bet)}"
                    ),
                    color=THEME_WARNING,
                ),
                1.3,
            )
        )

    await interaction.response.send_message(embed=phases[0][0], ephemeral=True)
    for embed, delay in phases[1:]:
        await asyncio.sleep(delay)
        try:
            await interaction.edit_original_response(embed=embed)
        except Exception:
            pass

    await asyncio.sleep(1.5)

    if crash_point >= target:
        payout = int(bet * target)
        profit = payout - bet
        update_balance(user_id, payout)
        record_stat(user_id, "total_won", profit)
        result_embed = discord.Embed(
            title="🏦 Vault Heist — Clean Getaway",
            description=(
                "━━━━━━━━━━━━━━━━━━\n"
                f"🚁 **Escaped at {crash_point:.2f}x!**\n"
                f"You cashed out at **{target:.2f}x** — {format_coins(payout)} secured.\n\n"
                f"Balance: {format_coins(get_balance(user_id))}"
            ),
            color=THEME_WIN,
        )
    else:
        record_stat(user_id, "total_lost", bet)
        result_embed = discord.Embed(
            title="🏦 Vault Heist — Lockdown",
            description=(
                "━━━━━━━━━━━━━━━━━━\n"
                f"🚨 **Alarm tripped at {crash_point:.2f}x!**\n"
                f"You needed **{target:.2f}x** — crew captured.\n"
                f"Lost {format_coins(bet)}.\n\n"
                f"Balance: {format_coins(get_balance(user_id))}"
            ),
            color=THEME_LOSS,
        )

    result_embed.set_footer(text="House edge ~3.5% • Grind from 1¢ wagers")
    try:
        await interaction.edit_original_response(embed=result_embed)
    except Exception:
        pass
