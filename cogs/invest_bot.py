import os
import json
import logging
import random
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import discord
from discord import Option
from discord.ext import commands, tasks

from cogs.invest_data import PROPERTIES, STRATEGIES, DISCLAIMER
from cogs.suburbs_database import ALL_AUSTRALIAN_SUBURBS, SUBURB_TO_STATE

logger = logging.getLogger("ShadowSyn.InvestBot")

THEME = 0x2B0B35
GUILD_ID = 908659586536468540
TZ = ZoneInfo("Australia/Sydney")
PERSIST = Path(os.getenv("PERSIST_PATH", "/data"))
STATE_FILE = PERSIST / "invest_state.json"

async def suburb_autocomplete(ctx: discord.AutocompleteContext):
    q = (ctx.value or "").lower()
    hits = [s for s in ALL_AUSTRALIAN_SUBURBS if s.lower().startswith(q)]
    if len(hits) < 15:
        hits += [s for s in ALL_AUSTRALIAN_SUBURBS if q in s.lower() and s not in hits]
    return hits[:15]


def _load_state() -> dict:
    default = {
        "market_channel_id": None,
        "strategies_channel_id": None,
        "posted_properties": [],
        "strategy_index": 0,
        "last_market_date": None,
        "last_strategy_week": None,
    }
    if not STATE_FILE.exists():
        return default
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return {**default, **json.load(f)}
    except Exception as e:
        logger.error(f"invest state load failed: {e}")
        return default


def _save_state(state: dict):
    PERSIST.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    tmp.replace(STATE_FILE)


def _pick_property(pool_type: str, posted: list) -> dict | None:
    pool = [p for p in PROPERTIES if p["type"] == pool_type and p["id"] not in posted]
    if not pool:
        pool = [p for p in PROPERTIES if p["type"] == pool_type]
    return random.choice(pool) if pool else None


def _market_embed(prop: dict) -> discord.Embed:
    is_rental = prop["type"] == "rental"
    colour = 0x43B581 if is_rental else 0x3498DB
    tag = "Rental ROI Pick" if is_rental else "Growth Pick"
    embed = discord.Embed(
        title=f"{'📈' if is_rental else '🚀'} Market Daily — {tag}",
        description=prop["hook"],
        colour=colour,
    )
    embed.add_field(name="Suburb", value=f"{prop['suburb']}, {prop['state']}", inline=True)
    embed.add_field(name="Type", value=f"{prop['beds']}br {prop['ptype']}", inline=True)
    embed.add_field(name="Guide Price", value=f"${prop['price']:,}", inline=True)
    if is_rental:
        embed.add_field(name="Indicative Rent", value=f"${prop['rent_wk']}/wk", inline=True)
        embed.add_field(name="Gross Yield", value=f"{prop['yield']}%", inline=True)
    else:
        embed.add_field(name="5yr Growth (indicative)", value=f"{prop['growth_5y']}% p.a.", inline=True)
    search = prop["suburb"].replace(" ", "+")
    embed.add_field(
        name="Research",
        value=f"[Domain listings](https://www.domain.com.au/sale/{search.lower()}-{prop['state'].lower()}-*)",
        inline=False,
    )
    embed.set_footer(text=DISCLAIMER)
    return embed


def _strategy_embed(item: dict) -> discord.Embed:
    embed = discord.Embed(
        title=f"📋 Weekly Strategy — {item['title']}",
        description=item["body"],
        colour=THEME,
    )
    embed.add_field(name="Source", value=item["source"], inline=False)
    embed.add_field(name="Read more", value=item["link"], inline=False)
    embed.set_footer(text=DISCLAIMER)
    return embed


class InvestBotCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.state = _load_state()
        self.daily_market.start()
        self.weekly_strategies.start()

    def cog_unload(self):
        self.daily_market.cancel()
        self.weekly_strategies.cancel()

    async def _channel(self, key: str):
        cid = self.state.get(key)
        if not cid:
            return None
        ch = self.bot.get_channel(cid) or await self.bot.fetch_channel(cid)
        return ch

    async def post_market_daily(self) -> bool:
        ch = await self._channel("market_channel_id")
        if not ch:
            return False
        posted = self.state.get("posted_properties", [])
        rental = _pick_property("rental", posted)
        growth = _pick_property("growth", posted)
        if not rental or not growth:
            logger.warning("market pool empty")
            return False
        await ch.send(embed=_market_embed(rental))
        await ch.send(embed=_market_embed(growth))
        posted.extend([rental["id"], growth["id"]])
        self.state["posted_properties"] = posted[-40:]
        self.state["last_market_date"] = datetime.now(TZ).strftime("%Y-%m-%d")
        _save_state(self.state)
        logger.info(f"market daily posted to {ch.id}")
        return True

    async def post_strategy_weekly(self) -> bool:
        ch = await self._channel("strategies_channel_id")
        if not ch:
            return False
        idx = self.state.get("strategy_index", 0) % len(STRATEGIES)
        item = STRATEGIES[idx]
        await ch.send(embed=_strategy_embed(item))
        self.state["strategy_index"] = idx + 1
        self.state["last_strategy_week"] = datetime.now(TZ).strftime("%G-W%V")
        _save_state(self.state)
        logger.info(f"strategy posted to {ch.id}")
        return True

    @tasks.loop(time=time(hour=9, minute=0, tzinfo=TZ))
    async def daily_market(self):
        today = datetime.now(TZ).strftime("%Y-%m-%d")
        if self.state.get("last_market_date") == today:
            return
        await self.post_market_daily()

    @daily_market.before_loop
    async def _wait_daily(self):
        await self.bot.wait_until_ready()

    @tasks.loop(time=time(hour=10, minute=0, tzinfo=TZ))
    async def weekly_strategies(self):
        now = datetime.now(TZ)
        if now.weekday() != 0:
            return
        week = now.strftime("%G-W%V")
        if self.state.get("last_strategy_week") == week:
            return
        await self.post_strategy_weekly()

    @weekly_strategies.before_loop
    async def _wait_weekly(self):
        await self.bot.wait_until_ready()

    @discord.slash_command(name="suburb", description="Suburb investment snapshot", guild_ids=[GUILD_ID])
    async def suburb(self, ctx, suburb_name: Option(str, autocomplete=suburb_autocomplete)):
        await ctx.defer()
        state = SUBURB_TO_STATE.get(suburb_name.lower(), "nsw").upper()
        embed = discord.Embed(
            title=f"🏘️ {suburb_name} — Investment Snapshot",
            description=f"State: **{state}**\nUse Market daily for curated picks in this corridor.",
            colour=THEME,
        )
        embed.add_field(
            name="Research links",
            value=(
                f"[Domain — {suburb_name}](https://www.domain.com.au/suburb-profile/{suburb_name.lower().replace(' ', '-')}-{state.lower()})\n"
                f"[CoreLogic area profile](https://www.corelogic.com.au/)"
            ),
            inline=False,
        )
        embed.set_footer(text=DISCLAIMER)
        await ctx.followup.send(embed=embed)

    @discord.slash_command(
        name="invest_config",
        description="Bind Market or Strategies channel — run inside target channel",
        guild_ids=[GUILD_ID],
    )
    async def invest_config(
        self,
        ctx,
        feed: Option(str, "Which feed to bind", choices=["market", "strategies"]),
    ):
        key = "market_channel_id" if feed == "market" else "strategies_channel_id"
        self.state[key] = ctx.channel.id
        _save_state(self.state)
        label = "Market Daily (9am AEST)" if feed == "market" else "Strategies Weekly (Mon 10am AEST)"
        await ctx.respond(f"✅ **{label}** linked to this channel.", ephemeral=True)
        try:
            await ctx.channel.send(f"✅ Invest bot linked — **{label}**")
        except discord.Forbidden:
            pass

    @discord.slash_command(
        name="invest_post_now",
        description="Admin: trigger Market or Strategies post immediately",
        guild_ids=[GUILD_ID],
        default_member_permissions=discord.Permissions(administrator=True),
    )
    async def invest_post_now(
        self,
        ctx,
        feed: Option(str, choices=["market", "strategies"]),
    ):
        await ctx.defer(ephemeral=True)
        ok = await (self.post_market_daily() if feed == "market" else self.post_strategy_weekly())
        await ctx.followup.send("✅ Posted." if ok else "❌ Channel not configured. Run `/invest_config` first.", ephemeral=True)


def setup(bot):
    bot.add_cog(InvestBotCog(bot))
    logger.info("InvestBotCog online — market daily + strategies weekly")
