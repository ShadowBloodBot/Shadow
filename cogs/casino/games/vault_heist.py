# cogs/casino/games/vault_heist.py — Vault Heist (Crash) engine

import asyncio
import random

import discord
from discord.ui import Modal, TextInput

from ..constants import THEME_INFO, THEME_LOSS, THEME_WARNING, THEME_WIN, VAULT_HOUSE_MULTIPLIER
from ..economy import get_balance, record_stat, update_balance
from ..helpers import format_coins


class VaultHeistModal(Modal):
    def __init__(self, balance: int):
        super().__init__(title="Vault Heist Setup"[:45])
        self.balance = balance
        self.add_item(TextInput(label=f"Wager (Max {balance:,})"[:45], placeholder="Amount or 'all'"))
        self.add_item(
            TextInput(
                label="Cash-out multiplier (min 1.10x)"[:45],
                placeholder="e.g. 2.50",
                value="2.00",
            )
        )

    async def callback(self, interaction: discord.Interaction):
        raw = self.children[0].value.lower().strip()
        amount = self.balance if raw == "all" else None
        if amount is None:
            try:
                amount = int(raw.replace(",", ""))
            except ValueError:
                return await interaction.response.send_message("❌ Invalid wager.", ephemeral=True)
        try:
            target = float(self.children[1].value.replace(",", "."))
        except ValueError:
            return await interaction.response.send_message("❌ Invalid multiplier.", ephemeral=True)

        if amount <= 0 or amount > self.balance:
            return await interaction.response.send_message("❌ Invalid wager.", ephemeral=True)
        if target < 1.10:
            return await interaction.response.send_message("❌ Minimum cash-out is **1.10x**.", ephemeral=True)
        if target > 100:
            return await interaction.response.send_message("❌ Maximum cash-out is **100x**.", ephemeral=True)

        await run_vault_heist(interaction, amount, target)


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

    result_embed.set_footer(text="House edge ~3.5% • Set your target wisely")
    try:
        await interaction.edit_original_response(embed=result_embed)
    except Exception:
        pass
