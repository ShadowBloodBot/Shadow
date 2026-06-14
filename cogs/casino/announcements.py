# cogs/casino/announcements.py — Public big-win & jackpot feed in casino channel

import discord

from cogs.guild_registry import REGISTERED_GUILD_IDS

from .constants import (
    BIG_WIN_MIN_PROFIT,
    JACKPOT_MIN_PROFIT,
    THEME_GOLD,
    THEME_WIN,
)
from .helpers import coins_to_usd, format_coins, resolve_casino_channel


def classify_win(profit: int, wager: int, flags: dict | None = None) -> str | None:
    """Return 'jackpot', 'big', or None if not worth announcing."""
    if profit <= 0:
        return None

    flags = flags or {}

    if flags.get("blackjack_natural") and profit >= 50:
        return "jackpot"
    if flags.get("roulette_straight") and profit >= 50:
        return "jackpot"
    if flags.get("vault_multiplier", 0) >= 5.0 and profit >= 250:
        return "jackpot"

    if profit >= JACKPOT_MIN_PROFIT:
        return "jackpot"
    if profit >= BIG_WIN_MIN_PROFIT:
        return "big"
    return None


async def maybe_announce_win(
    bot: discord.Client,
    user: discord.User | discord.Member,
    game: str,
    profit: int,
    payout: int,
    wager: int,
    headline: str,
    *,
    flags: dict | None = None,
) -> None:
    tier = classify_win(profit, wager, flags)
    if not tier:
        return

    guild_id = user.guild.id if isinstance(user, discord.Member) and user.guild else None
    if guild_id is None:
        guild_id = REGISTERED_GUILD_IDS[0]

    channel = await resolve_casino_channel(bot, guild_id)
    if channel is None:
        return

    if tier == "jackpot":
        title = f"🎰 JACKPOT — {game}"
        color = THEME_GOLD
        banner = "━━━━━━━━━━━━━━━━━━\n✨ **JACKPOT HIT** ✨\n"
    else:
        title = f"💎 Big Win — {game}"
        color = THEME_WIN
        banner = "━━━━━━━━━━━━━━━━━━\n"

    embed = discord.Embed(
        title=title,
        description=(
            f"{banner}"
            f"{user.mention} — {headline}\n\n"
            f"Wager: {format_coins(wager)} · Payout: {format_coins(payout)}\n"
            f"Profit: **+{profit:,}** 🪙 ({coins_to_usd(profit)})"
        ),
        color=color,
    )
    embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
    embed.set_footer(text="ShadowSyn VIP Casino · Season 1")

    try:
        await channel.send(embed=embed)
    except Exception as exc:
        print(f"⚠️ Casino win announce send failed: {exc}")
