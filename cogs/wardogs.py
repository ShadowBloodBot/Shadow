# cogs/wardogs.py — /gold: Wardogs gold bar market value from wardogs.market
import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any

import aiohttp
import discord
from discord.ext import commands
from discord.ui import Button, View

from cogs.guild_registry import REGISTERED_GUILD_IDS, has_wardogs, is_registered_guild
from cogs.utils import safe_reply

logger = logging.getLogger("ShadowSyn.Wardogs")

THEME_PRIMARY = 0x2B0B35
MARKET_URL = "https://www.wardogs.market/"
VALUES_URL = "https://www.wardogs.market/values.json"
FETCH_TIMEOUT_SEC = 10
CACHE_TTL_SEC = 60
STALE_AFTER_SEC = 26 * 3600
HISTORY_DAYS = 7


def _fmt_money(value: Any) -> str:
    try:
        return f"${int(value):,}"
    except (TypeError, ValueError):
        return "—"


def _parse_updated(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _change_text(current: Any, previous: Any) -> str:
    try:
        cur = float(current)
        prev = float(previous)
    except (TypeError, ValueError):
        return "—"
    if prev <= 0:
        return "—"
    pct = (cur - prev) / prev * 100
    if pct > 0:
        return f"▲ +{abs(pct):,.1f}%"
    if pct < 0:
        return f"▼ {abs(pct):,.1f}%"
    return "— 0.0%"


def _history_line(payload: dict[str, Any]) -> str:
    history = payload.get("history") or {}
    points: dict[str, int] = {}
    if isinstance(history, dict):
        for key, val in history.items():
            # Site data is hand-edited upstream (seen: "2026-10-l0"); only accept real dates.
            try:
                if not isinstance(key, str):
                    continue
                datetime.strptime(key, "%Y-%m-%d")
                points[key] = int(val)
            except (TypeError, ValueError):
                continue
    updated = _parse_updated(payload.get("updated"))
    if updated is not None:
        try:
            points[updated.strftime("%Y-%m-%d")] = int(payload.get("current"))
        except (TypeError, ValueError):
            pass
    keys = sorted(points)[-HISTORY_DAYS:]
    if len(keys) < 2:
        return "—"
    return " → ".join(f"{int(k[5:7])}/{int(k[8:10])} {_fmt_money(points[k])}" for k in keys)


def build_gold_embed(payload: dict[str, Any], *, from_cache: bool = False) -> discord.Embed:
    current = payload.get("current")
    previous = payload.get("previous")
    updated = _parse_updated(payload.get("updated"))
    now = datetime.now(timezone.utc)
    stale = from_cache or updated is None or (now - updated).total_seconds() > STALE_AFTER_SEC

    title = "WARDOGS // Gold Market"
    if stale:
        title += " // LAST KNOWN VALUE"

    embed = discord.Embed(title=title, color=THEME_PRIMARY)
    embed.add_field(name="Today's Value", value=f"**{_fmt_money(current)}**", inline=False)
    embed.add_field(name="Yesterday", value=_fmt_money(previous), inline=True)
    embed.add_field(name="Change", value=_change_text(current, previous), inline=True)
    try:
        history_line = _history_line(payload)
    except Exception as exc:
        logger.warning("Wardogs history line skipped: %s", exc)
        history_line = "—"
    embed.add_field(name=f"Last {HISTORY_DAYS} days", value=history_line, inline=False)
    if updated is not None:
        embed.add_field(name="Updated", value=f"<t:{int(updated.timestamp())}:R>", inline=False)
    embed.set_footer(text="Gravy Loves Men")
    return embed


class GoldMarketView(View):
    def __init__(self) -> None:
        super().__init__(timeout=None)
        self.add_item(
            Button(
                label="Open Gold Market",
                style=discord.ButtonStyle.link,
                emoji="🪙",
                url=MARKET_URL,
            )
        )


class WardogsCog(commands.Cog):
    def __init__(self, bot: discord.Bot) -> None:
        self.bot = bot
        self._session: aiohttp.ClientSession | None = None
        self._cache: dict[str, Any] | None = None
        self._cache_at: float = 0.0
        self._lock = asyncio.Lock()

    def cog_unload(self) -> None:
        if self._session and not self._session.closed:
            self.bot.loop.create_task(self._session.close())

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _fetch_values(self) -> tuple[dict[str, Any] | None, bool]:
        """Return (payload, from_cache). Payload is None only if nothing is available."""
        async with self._lock:
            now = time.monotonic()
            if self._cache is not None and now - self._cache_at < CACHE_TTL_SEC:
                return self._cache, False
            try:
                session = await self._get_session()
                async with session.get(
                    VALUES_URL,
                    params={"t": str(int(time.time()))},
                    timeout=aiohttp.ClientTimeout(total=FETCH_TIMEOUT_SEC),
                    headers={"User-Agent": "ShadowSyn/1.0"},
                ) as resp:
                    if resp.status != 200:
                        raise RuntimeError(f"HTTP {resp.status}")
                    data = await resp.json(content_type=None)
                if not isinstance(data, dict) or "current" not in data:
                    raise RuntimeError("unexpected values.json shape")
                self._cache = data
                self._cache_at = now
                return data, False
            except Exception as exc:
                logger.warning("Wardogs gold fetch failed: %s", exc)
                if self._cache is not None:
                    return self._cache, True
                return None, False

    @discord.slash_command(
        name="gold",
        description="Today's Wardogs gold bar value",
        guild_ids=REGISTERED_GUILD_IDS,
    )
    async def gold(self, ctx: discord.ApplicationContext) -> None:
        if not ctx.guild or not is_registered_guild(ctx.guild.id):
            return await safe_reply(ctx, "⛔ Unregistered guild.", ephemeral=True)
        if not has_wardogs(ctx.author, ctx.guild.id):
            return await safe_reply(ctx, "🚫 Wardogs role required.", ephemeral=True)

        await ctx.defer()
        payload, from_cache = await self._fetch_values()
        if payload is None:
            return await ctx.followup.send(
                "❌ Could not reach wardogs.market right now. Try again shortly.",
                ephemeral=True,
            )
        try:
            embed = build_gold_embed(payload, from_cache=from_cache)
            await ctx.followup.send(embed=embed, view=GoldMarketView())
        except Exception as exc:
            logger.error("/gold failed to post: %s", exc)
            await ctx.followup.send(f"❌ Failed: {exc}", ephemeral=True)


def setup(bot: discord.Bot) -> None:
    bot.add_cog(WardogsCog(bot))
