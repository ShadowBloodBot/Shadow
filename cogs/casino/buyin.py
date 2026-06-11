# cogs/casino/buyin.py — USD buy-in flow ($1–$5 → Coins)

import discord
from discord import ButtonStyle
from discord.ui import Modal, Select, TextInput, View

from .constants import (
    BUYIN_MAX_PENDING,
    BUYIN_MAX_PER_MONTH,
    BUYIN_PAYMENT_LABEL,
    BUYIN_PAYMENT_URL,
    BUYIN_TIERS,
    COINS_PER_USD,
    OWNER_ID,
    STEAM_REDEEM_CHANNEL_ID,
    THEME_GOLD,
    THEME_INFO,
    THEME_PRIMARY,
    THEME_WARNING,
)
from .economy import (
    count_monthly_buyins,
    create_buyin,
    get_balance,
    get_pending_buyin,
    resolve_buyin,
)
from .helpers import format_wallet


def paypal_tier_url(usd: int) -> str:
    """PayPal.me preset amount: https://paypal.me/ShadowSyn001/5"""
    return f"{BUYIN_PAYMENT_URL}/{usd}"


def _payment_instructions(usd: int, coins: int) -> str:
    pay_url = paypal_tier_url(usd)
    return (
        f"Send **${usd} USD** via **{BUYIN_PAYMENT_LABEL}**.\n"
        f"You receive **{coins:,} Coins** once approved.\n"
        f"**Pay here:** {pay_url}"
    )


class BuyInProofModal(Modal):
    def __init__(self, tier: dict):
        super().__init__(title=f"{tier['label']} — Submit Proof"[:45])
        self.tier = tier
        self.add_item(
            TextInput(
                label="PayPal transaction ID or note"[:45],
                placeholder="Txn ID, your Discord name in PayPal note…",
                min_length=3,
                max_length=120,
            )
        )

    async def callback(self, interaction: discord.Interaction):
        member = interaction.user
        if not isinstance(member, discord.Member):
            return await interaction.response.send_message("❌ Guild only.", ephemeral=True)

        if get_pending_buyin(str(member.id)):
            return await interaction.response.send_message(
                "❌ You already have a **pending buy-in**. Wait for admin review.",
                ephemeral=True,
            )
        if count_monthly_buyins(str(member.id)) >= BUYIN_MAX_PER_MONTH:
            return await interaction.response.send_message(
                f"❌ Monthly buy-in limit reached (**{BUYIN_MAX_PER_MONTH}**/month).",
                ephemeral=True,
            )

        payment_ref = self.children[0].value.strip()
        try:
            request = create_buyin(str(member.id), self.tier, payment_ref)
        except ValueError as exc:
            return await interaction.response.send_message(f"❌ {exc}", ephemeral=True)

        embed = discord.Embed(
            title="💵 Buy-In Submitted",
            description=(
                f"**{self.tier['label']}** → **{self.tier['coins']:,} Coins**\n"
                f"Ticket: `{request['id']}`\n"
                f"Reference: `{payment_ref}`\n\n"
                "Staff will verify your PayPal payment and credit your wallet.\n"
                "Do **not** submit duplicate tickets for the same payment."
            ),
            color=THEME_GOLD,
        )
        embed.set_footer(text=f"Current balance: {format_wallet(get_balance(str(member.id)))}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

        pay_url = paypal_tier_url(self.tier["usd"])
        admin_embed = discord.Embed(
            title="💵 Coin Buy-In — Pending",
            description=(
                f"**Member:** {member.mention} (`{member.id}`)\n"
                f"**Package:** {self.tier['label']} → **{self.tier['coins']:,}** 🪙\n"
                f"**Expected payment:** ${self.tier['usd']} USD\n"
                f"**PayPal link:** {pay_url}\n"
                f"**Reference:** `{payment_ref}`\n"
                f"**Ticket:** `{request['id']}`"
            ),
            color=THEME_WARNING,
        )
        admin_view = BuyInAdminView(request["id"], member.id, self.tier["coins"])

        channel = interaction.client.get_channel(STEAM_REDEEM_CHANNEL_ID)
        if channel:
            try:
                await channel.send(embed=admin_embed, view=admin_view)
                return
            except Exception:
                pass

        owner = interaction.client.get_user(OWNER_ID)
        if owner:
            try:
                await owner.send(embed=admin_embed, view=admin_view)
            except Exception:
                pass


class BuyInTierSelect(Select):
    def __init__(self, row: int = 0):
        options = [
            discord.SelectOption(
                label=tier["label"],
                description=f"${tier['usd']} → {tier['coins']:,} Coins",
                value=tier["id"],
                emoji=tier["emoji"],
            )
            for tier in BUYIN_TIERS
        ]
        super().__init__(
            placeholder="💵 Buy Coins with PayPal ($1–$5)…",
            min_values=1,
            max_values=1,
            options=options,
            row=row,
        )
        self._tiers = {t["id"]: t for t in BUYIN_TIERS}

    async def callback(self, interaction: discord.Interaction):
        tier = self._tiers[self.values[0]]
        pending = get_pending_buyin(str(interaction.user.id))
        if pending:
            return await interaction.response.send_message(
                f"❌ Pending buy-in `{pending['id']}` — wait for approval first.",
                ephemeral=True,
            )

        pay_url = paypal_tier_url(tier["usd"])
        info = discord.Embed(
            title=f"💵 {tier['label']}",
            description=(
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"{_payment_instructions(tier['usd'], tier['coins'])}\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "1. Tap **Pay on PayPal** below\n"
                "2. Complete payment\n"
                "3. Tap **Submit Proof** with your transaction ID"
            ),
            color=THEME_INFO,
        )
        info.set_footer(text=f"Rate: {COINS_PER_USD:,} Coins = $1 · ShadowSyn001 on PayPal")
        await interaction.response.send_message(
            embed=info,
            view=BuyInConfirmView(tier, pay_url),
            ephemeral=True,
        )


class BuyInConfirmView(View):
    def __init__(self, tier: dict, pay_url: str):
        super().__init__(timeout=300)
        self.tier = tier
        self.add_item(
            discord.ui.Button(
                label=f"Pay ${tier['usd']} on PayPal",
                style=ButtonStyle.link,
                url=pay_url,
                emoji="💳",
            )
        )

    @discord.ui.button(label="Submit Proof", style=ButtonStyle.success, emoji="✅")
    async def submit_proof(self, button, interaction: discord.Interaction):
        await interaction.response.send_modal(BuyInProofModal(self.tier))


class BuyInAdminView(View):
    def __init__(self, request_id: str, user_id: int, coins: int):
        super().__init__(timeout=None)
        self.request_id = request_id
        self.user_id = user_id
        self.coins = coins

    async def _guard(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != OWNER_ID:
            await interaction.response.send_message("🚫 Owner only.", ephemeral=True)
            return True
        return False

    @discord.ui.button(label="Approve & Credit", style=ButtonStyle.success, emoji="✅")
    async def approve(self, button, interaction: discord.Interaction):
        if await self._guard(interaction):
            return
        req = resolve_buyin(self.request_id, True, interaction.user.id)
        if not req:
            return await interaction.response.send_message(
                "❌ Ticket not found or already resolved.", ephemeral=True
            )

        self.clear_items()
        embed = interaction.message.embeds[0].copy() if interaction.message.embeds else discord.Embed()
        embed.color = THEME_GOLD
        embed.title = "✅ Coin Buy-In — Approved"
        embed.description = (
            (embed.description or "")
            + f"\n\nApproved by {interaction.user.mention}\n"
            f"**{self.coins:,}** Coins credited."
        )
        await interaction.response.edit_message(embed=embed, view=self)

        user = interaction.client.get_user(self.user_id)
        if user:
            try:
                dm = discord.Embed(
                    title="✅ Buy-In Approved",
                    description=(
                        f"Your **${req['usd']}** buy-in (`{self.request_id}`) was approved.\n"
                        f"**+{self.coins:,} Coins** added to your wallet.\n\n"
                        f"Balance: {format_wallet(get_balance(str(self.user_id)))}"
                    ),
                    color=THEME_GOLD,
                )
                await user.send(embed=dm)
            except Exception:
                pass

    @discord.ui.button(label="Deny", style=ButtonStyle.danger, emoji="❌")
    async def deny(self, button, interaction: discord.Interaction):
        if await self._guard(interaction):
            return
        req = resolve_buyin(self.request_id, False, interaction.user.id)
        if not req:
            return await interaction.response.send_message(
                "❌ Ticket not found or already resolved.", ephemeral=True
            )

        self.clear_items()
        embed = interaction.message.embeds[0].copy() if interaction.message.embeds else discord.Embed()
        embed.color = THEME_PRIMARY
        embed.title = "❌ Coin Buy-In — Denied"
        embed.description = (
            (embed.description or "") + f"\n\nDenied by {interaction.user.mention}"
        )
        await interaction.response.edit_message(embed=embed, view=self)

        user = interaction.client.get_user(self.user_id)
        if user:
            try:
                dm = discord.Embed(
                    title="❌ Buy-In Denied",
                    description=(
                        f"Buy-in `{self.request_id}` was denied.\n"
                        "If you already paid, contact staff with your PayPal transaction ID."
                    ),
                    color=THEME_PRIMARY,
                )
                await user.send(embed=dm)
            except Exception:
                pass


def build_buyin_embed(user: discord.User) -> discord.Embed:
    tier_lines = [
        f"{t['emoji']} [{t['label']}]({paypal_tier_url(t['usd'])}) → **{t['coins']:,}** 🪙"
        for t in BUYIN_TIERS
    ]
    embed = discord.Embed(
        title="💵 Buy Coins — PayPal",
        description=(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"**Rate:** {COINS_PER_USD:,} Coins = **$1 USD**\n"
            f"**PayPal:** [{BUYIN_PAYMENT_URL}]({BUYIN_PAYMENT_URL})\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=THEME_INFO,
    )
    embed.add_field(name="Packages", value="\n".join(tier_lines), inline=False)
    embed.add_field(
        name="How it works",
        value=(
            "1. Select a package below\n"
            "2. Tap **Pay on PayPal** → send exact amount\n"
            "3. **Submit Proof** with your PayPal transaction ID\n"
            "4. Staff approves → Coins credited instantly"
        ),
        inline=False,
    )
    embed.add_field(
        name="Limits",
        value=(
            f"• {BUYIN_MAX_PENDING} pending request at a time\n"
            f"• {BUYIN_MAX_PER_MONTH} approved buy-ins per month"
        ),
        inline=False,
    )
    embed.set_footer(text=f"Balance: {format_wallet(get_balance(str(user.id)))}")
    embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
    return embed


class BuyInView(View):
    def __init__(self, row: int = 0):
        super().__init__(timeout=180)
        self.add_item(BuyInTierSelect(row=row))
