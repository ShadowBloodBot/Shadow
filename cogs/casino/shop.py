# cogs/casino/shop.py — Steam Wallet redemption shop

import discord
from discord import ButtonStyle
from discord.ui import Modal, Select, TextInput, View

from .constants import (
    BUYIN_TIERS,
    MEMBER_TENURE_DAYS,
    OWNER_ID,
    REDEEM_MAX_PER_MONTH,
    SHOP_MIN_COINS,
    SHOP_TIERS,
    STEAM_REDEEM_CHANNEL_ID,
    THEME_GOLD,
    THEME_PRIMARY,
    THEME_WARNING,
)
from .economy import (
    count_monthly_redemptions,
    create_redemption,
    get_balance,
    get_pending_redemption,
    redeem_cooldown_remaining,
    resolve_redemption,
)
from .helpers import coins_to_usd, deny_if_not_gambler, format_wallet, progress_to_shop
from .buyin import paypal_tier_url


def _tenure_ok(member: discord.Member) -> tuple[bool, str]:
    if not member.joined_at:
        return False, "Unable to verify membership tenure."
    import datetime

    age = discord.utils.utcnow() - member.joined_at
    required = datetime.timedelta(days=MEMBER_TENURE_DAYS)
    if age < required:
        days_left = (required - age).days
        return False, f"Account must be **{MEMBER_TENURE_DAYS} days** old. **{days_left}** day(s) remaining."
    return True, ""


def _redeem_blockers(member: discord.Member) -> str | None:
    ok, msg = _tenure_ok(member)
    if not ok:
        return msg
    if get_pending_redemption(member.id):
        return "You already have a **pending** redemption. Wait for admin review."
    cooldown = redeem_cooldown_remaining(str(member.id))
    if cooldown:
        from .helpers import format_countdown

        return f"Redemption cooldown: **{format_countdown(cooldown)}** remaining."
    if count_monthly_redemptions(str(member.id)) >= REDEEM_MAX_PER_MONTH:
        return f"Monthly limit reached (**{REDEEM_MAX_PER_MONTH}**/month)."
    if get_balance(str(member.id)) < SHOP_MIN_COINS:
        return f"Minimum shop balance: **{SHOP_MIN_COINS:,}** Coins ({coins_to_usd(SHOP_MIN_COINS)})."
    return None


class SteamIdModal(Modal):
    def __init__(self, tier: dict):
        super().__init__(title=f"Redeem {tier['label']}"[:45])
        self.tier = tier
        self.add_item(
            TextInput(
                label="Steam Friend Code or Profile URL"[:45],
                placeholder="https://steamcommunity.com/id/yourname",
                min_length=5,
                max_length=200,
            )
        )

    async def callback(self, interaction: discord.Interaction):
        member = interaction.user
        if not isinstance(member, discord.Member):
            return await interaction.response.send_message("❌ Guild only.", ephemeral=True)

        blocker = _redeem_blockers(member)
        if blocker:
            return await interaction.response.send_message(f"❌ {blocker}", ephemeral=True)

        cost = self.tier["coins"]
        if get_balance(str(member.id)) < cost:
            return await interaction.response.send_message("❌ Insufficient balance.", ephemeral=True)

        steam_id = self.children[0].value.strip()
        try:
            request = create_redemption(str(member.id), self.tier, steam_id)
        except ValueError as exc:
            return await interaction.response.send_message(f"❌ {exc}", ephemeral=True)

        embed = discord.Embed(
            title="🎁 Redemption Submitted",
            description=(
                f"**{self.tier['label']}** — {cost:,} Coins deducted.\n"
                f"Ticket: `{request['id']}`\n\n"
                "An admin will review and DM your Steam code.\n"
                "Denied requests are **refunded automatically**."
            ),
            color=THEME_GOLD,
        )
        embed.set_footer(text=f"New balance: {format_wallet(get_balance(str(member.id)))}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

        admin_embed = discord.Embed(
            title="🎁 Steam Redemption — Pending",
            description=(
                f"**Member:** {member.mention} (`{member.id}`)\n"
                f"**Tier:** {self.tier['label']}\n"
                f"**Cost:** {cost:,} 🪙 ({coins_to_usd(cost)})\n"
                f"**Steam:** {steam_id}\n"
                f"**Ticket:** `{request['id']}`"
            ),
            color=THEME_WARNING,
        )
        admin_view = RedemptionAdminView(request["id"], member.id, cost)

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


class RedeemTierSelect(Select):
    def __init__(self, balance: int, row: int = 2):
        options = []
        for tier in SHOP_TIERS:
            affordable = balance >= tier["coins"]
            options.append(
                discord.SelectOption(
                    label=tier["label"],
                    description=f"{tier['coins']:,} Coins — {'Available' if affordable else 'Need more Coins'}",
                    value=tier["id"],
                    emoji=tier["emoji"],
                )
            )
        super().__init__(
            placeholder="🎁 Redeem Steam Wallet…",
            min_values=1,
            max_values=1,
            options=options,
            row=row,
        )
        self._tiers = {t["id"]: t for t in SHOP_TIERS}

    async def callback(self, interaction: discord.Interaction):
        member = interaction.user
        if not isinstance(member, discord.Member):
            return await interaction.response.send_message("❌ Guild only.", ephemeral=True)

        tier = self._tiers[self.values[0]]
        if get_balance(str(member.id)) < tier["coins"]:
            return await interaction.response.send_message(
                f"❌ Need **{tier['coins']:,}** Coins. Balance: {format_wallet(get_balance(str(member.id)))}",
                ephemeral=True,
            )
        blocker = _redeem_blockers(member)
        if blocker:
            return await interaction.response.send_message(f"❌ {blocker}", ephemeral=True)

        await interaction.response.send_modal(SteamIdModal(tier))


ShopTierSelect = RedeemTierSelect


class ShopView(View):
    def __init__(self, balance: int):
        super().__init__(timeout=180)
        from .buyin import BuyInTierSelect

        self.add_item(BuyInTierSelect(row=0))
        self.add_item(RedeemTierSelect(balance, row=1))


class RedemptionAdminView(View):
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

    @discord.ui.button(label="Approve", style=ButtonStyle.success, emoji="✅")
    async def approve(self, button, interaction: discord.Interaction):
        if await self._guard(interaction):
            return
        req = resolve_redemption(self.request_id, True, interaction.user.id)
        if not req:
            return await interaction.response.send_message("❌ Ticket not found or already resolved.", ephemeral=True)

        self.clear_items()
        embed = interaction.message.embeds[0].copy() if interaction.message.embeds else discord.Embed()
        embed.color = THEME_GOLD
        embed.title = "✅ Steam Redemption — Approved"
        embed.description = (embed.description or "") + f"\n\nApproved by {interaction.user.mention}"
        await interaction.response.edit_message(embed=embed, view=self)

        user = interaction.client.get_user(self.user_id)
        if user:
            try:
                dm = discord.Embed(
                    title="✅ Steam Redemption Approved",
                    description=(
                        f"Your **${req['usd']}** Steam Wallet request (`{self.request_id}`) was approved.\n"
                        "Your code will arrive via DM from staff shortly."
                    ),
                    color=THEME_GOLD,
                )
                await user.send(embed=dm)
            except Exception:
                pass

    @discord.ui.button(label="Deny & Refund", style=ButtonStyle.danger, emoji="❌")
    async def deny(self, button, interaction: discord.Interaction):
        if await self._guard(interaction):
            return
        req = resolve_redemption(self.request_id, False, interaction.user.id)
        if not req:
            return await interaction.response.send_message("❌ Ticket not found or already resolved.", ephemeral=True)

        self.clear_items()
        embed = interaction.message.embeds[0].copy() if interaction.message.embeds else discord.Embed()
        embed.color = THEME_PRIMARY
        embed.title = "❌ Steam Redemption — Denied & Refunded"
        embed.description = (
            (embed.description or "")
            + f"\n\nDenied by {interaction.user.mention}\n**{self.coins:,}** Coins refunded."
        )
        await interaction.response.edit_message(embed=embed, view=self)

        user = interaction.client.get_user(self.user_id)
        if user:
            try:
                dm = discord.Embed(
                    title="❌ Steam Redemption Denied",
                    description=(
                        f"Request `{self.request_id}` was denied.\n"
                        f"**{self.coins:,}** Coins have been refunded to your wallet."
                    ),
                    color=THEME_PRIMARY,
                )
                await user.send(embed=dm)
            except Exception:
                pass


def build_shop_embed(user: discord.User, balance: int) -> discord.Embed:
    embed = discord.Embed(
        title="🛒 ShadowSyn Rewards Shop",
        description=(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"**Peg:** 10,000 Coins = $10 USD\n"
            f"**Minimum redemption:** {SHOP_MIN_COINS:,} Coins (${SHOP_MIN_COINS // 1000})\n\n"
            f"{progress_to_shop(balance)}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ),
        color=THEME_GOLD,
    )
    tier_lines = [
        f"{t['emoji']} **{t['label']}** — {t['coins']:,} 🪙"
        for t in SHOP_TIERS
    ]
    buyin_lines = [
        f"💵 [{t['label']}]({paypal_tier_url(t['usd'])}) — **{t['coins']:,}** 🪙"
        for t in BUYIN_TIERS
    ]
    embed.add_field(name="💵 Buy Coins (USD)", value="\n".join(buyin_lines), inline=False)
    embed.add_field(name="🎁 Redeem Steam Wallet", value="\n".join(tier_lines), inline=False)
    embed.add_field(
        name="Rules",
        value=(
            f"• {MEMBER_TENURE_DAYS}-day membership required\n"
            f"• {REDEEM_MAX_PER_MONTH} redemptions per month\n"
            "• 7-day cooldown between redemptions\n"
            "• 1 pending request at a time"
        ),
        inline=False,
    )
    embed.set_footer(text=f"Balance: {format_wallet(balance)}")
    embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
    return embed
