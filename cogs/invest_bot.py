import os
import json
import logging
import random
import re
import asyncio
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import discord
from discord import Option
from discord.ext import commands, tasks

from cogs.invest_data import (
    PROPERTIES,
    STRATEGIES,
    STRATEGIES_WEEK,
    DISCLAIMER,
    SYDNEY_DAILY_ROTATION,
    WEEKLY_DIGEST_LINES,
    strategy_embed_parts,
    strategy_for_today,
)
from cogs.invest_calculators import calc_negative_gearing, calc_refinance_check, fmt_currency
from cogs.invest_suburb_stats import get_store
from cogs.suburbs_database import db as suburbs_db, SUBURB_TO_STATE
from cogs.suburb_fetcher import build_suburb_profile

logger = logging.getLogger("ShadowSyn.InvestBot")

THEME = 0x2B0B35
GUILD_ID = 908659586536468540
TZ = ZoneInfo("Australia/Sydney")
PERSIST = Path(os.getenv("PERSIST_PATH", "/data"))
STATE_FILE = PERSIST / "invest_state.json"
PROFILES_FILE = PERSIST / "invest_profiles.json"

# Tier 2 qualification emojis
EMOJI_INTEREST = "\U0001f44d"       # 👍
EMOJI_STRATEGY = "\U0001f3af"       # 🎯
SURVEY_MAP = {
    "\U0001f3e0": "first_investor",
    "\U0001f504": "ppor_plus_investment",
    "\U0001f4b0": "refinance",
    "\U0001f517": "portfolio_builder",
}

LEAD_KEYWORDS = re.compile(
    r"\b(refinanc|interest rate|fixed rate|variable rate|pre-approval|preapproval|"
    r"serviceability|lmi|lvr|negative gearing|offset|broker|loan size|borrow)\b",
    re.I,
)

CONFIG_CHOICES = [
    "market",
    "strategies",
    "alerts",
    "strategy_seekers",
    "leads_mod",
    "bot_logs",
]


async def suburb_autocomplete(ctx: discord.AutocompleteContext):
    return suburbs_db.search(ctx.value or "", limit=15)


def _load_state() -> dict:
    default = {
        "market_channel_id": None,
        "strategies_channel_id": None,
        "alerts_channel_id": None,
        "strategy_seekers_channel_id": None,
        "leads_mod_channel_id": None,
        "bot_logs_channel_id": None,
        "strategy_role_id": None,
        "posted_properties": [],
        "strategy_index": 0,
        "sydney_rotation_index": 0,
        "last_market_date": None,
        "last_strategy_date": None,
        "last_digest_week": None,
        "last_alert_date": None,
        "suburb_baselines": {},
        "alert_threshold_pct": 2.0,
        "tracked_message_ids": [],
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


def _load_profiles() -> dict:
    if not PROFILES_FILE.exists():
        return {}
    try:
        with open(PROFILES_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"invest profiles load failed: {e}")
        return {}


def _save_profiles(profiles: dict):
    PERSIST.mkdir(parents=True, exist_ok=True)
    tmp = PROFILES_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(profiles, f, indent=2)
    tmp.replace(PROFILES_FILE)


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
    parts = strategy_embed_parts(item)
    embed = discord.Embed(
        title=parts["title"],
        description=parts["description"],
        colour=THEME,
    )
    for name, value in parts["fields"]:
        embed.add_field(name=name, value=value, inline=False)
    embed.set_footer(text=DISCLAIMER)
    return embed


def _suburb_embed(name: str, stats: dict, store) -> discord.Embed:
    score = store.hotspot_score(stats) if stats.get("median_price") else None
    label = store.hotspot_label(score) if score is not None else None
    growth = stats.get("growth_12m_pct")
    growth_str = f"{growth:+.1f}%" if growth is not None else "—"
    profile_type = stats.get("profile_type", "curated")
    embed = discord.Embed(
        title=f"🏘️ {stats.get('name', name)} — Market Intel",
        description="Indicative suburb snapshot for investor discussion.",
        colour=THEME,
    )
    if stats.get("median_price"):
        embed.add_field(name="Median house price", value=fmt_currency(stats["median_price"]), inline=True)
    else:
        embed.add_field(name="Median house price", value="—", inline=True)
    if stats.get("median_rent_weekly"):
        embed.add_field(name="Median rent", value=f"${stats['median_rent_weekly']}/wk", inline=True)
    else:
        embed.add_field(name="Median rent", value="—", inline=True)
    if stats.get("rental_yield_pct") is not None:
        embed.add_field(name="Gross rental yield", value=f"{stats['rental_yield_pct']}%", inline=True)
    embed.add_field(name="12m growth (indicative)", value=growth_str, inline=True)
    if stats.get("population"):
        embed.add_field(name="Population (ABS locality)", value=f"{stats['population']:,}", inline=True)
    if stats.get("median_income"):
        embed.add_field(name="Median income (ABS)", value=f"${stats['median_income']:,}/yr", inline=True)
    if stats.get("density_per_sqkm"):
        embed.add_field(name="Density", value=f"{stats['density_per_sqkm']}/sq km", inline=True)
    if stats.get("lga"):
        embed.add_field(name="LGA", value=str(stats["lga"])[:128], inline=True)
    if score is not None:
        embed.add_field(name="Investor hotspot score", value=f"{score}/100 — {label}", inline=False)
    if stats.get("price_note"):
        embed.add_field(name="Price data", value=stats["price_note"], inline=False)
    state = stats.get("state", SUBURB_TO_STATE.get(name.lower(), "NSW")).upper()
    slug = name.lower().replace(" ", "-")
    embed.add_field(
        name="Research",
        value=(
            f"[Domain suburb profile](https://www.domain.com.au/suburb-profile/{slug}-{state.lower()})\n"
            f"Profile: {profile_type} | {stats.get('source', 'Indicative model')}"
        ),
        inline=False,
    )
    embed.set_footer(text=DISCLAIMER)
    return embed


def _fmt_cmp(va, vb, *, money=False, pct=False) -> tuple[str, str]:
    def fmt(v):
        if v is None:
            return "—"
        if money:
            return fmt_currency(float(v))
        if pct:
            return f"{float(v):+.1f}%"
        if isinstance(v, float):
            return f"{v:,.1f}"
        return f"{int(v):,}"

    return fmt(va), fmt(vb)


def _compare_embed(a: dict, b: dict, store) -> discord.Embed:
    sa, sb = store.hotspot_score(a), store.hotspot_score(b)
    embed = discord.Embed(
        title=f"⚖️ {a['name']} vs {b['name']}",
        description="Side-by-side indicative comparison for discussion.",
        colour=THEME,
    )
    rows = [
        ("Median price", * _fmt_cmp(a.get("median_price"), b.get("median_price"), money=True)),
        ("12m growth", * _fmt_cmp(a.get("growth_12m_pct"), b.get("growth_12m_pct"), pct=True)),
        ("Gross yield", * _fmt_cmp(a.get("rental_yield_pct"), b.get("rental_yield_pct"), pct=True)),
        ("Population", * _fmt_cmp(a.get("population"), b.get("population"))),
        ("Median income", * _fmt_cmp(a.get("median_income"), b.get("median_income"), money=True)),
        ("Hotspot score", str(sa), str(sb)),
    ]
    for label, va, vb in rows:
        embed.add_field(name=label, value=f"**{a['name']}:** {va}\n**{b['name']}:** {vb}", inline=False)
    embed.set_footer(text=DISCLAIMER)
    return embed


class InvestBotCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.state = _load_state()
        self.profiles = _load_profiles()
        self.store = get_store(PERSIST)
        self.daily_market.start()
        self.daily_strategies.start()
        self.weekly_digest.start()
        self.market_alerts.start()
        self.suburb_sync.start()

    async def _ensure_suburb_index(self):
        db_path = PERSIST / "suburbs.db"
        force = os.getenv("SUBURB_SYNC_ON_START", "").lower() in ("1", "true", "yes")
        if db_path.exists() and not force:
            return
        logger.info("suburbs.db missing — running first-time suburb sync")
        from scripts.sync_suburbs import main as sync_main

        code = await asyncio.to_thread(sync_main)
        if code == 0:
            suburbs_db.reload()
            logger.info("Suburb index ready after sync")
        else:
            logger.error("Suburb sync failed on startup — autocomplete will be limited")

    async def _resolve_suburb_stats(self, suburb_name: str, *, force_refresh: bool = False) -> dict | None:
        stats = None if force_refresh else self.store.lookup(suburb_name)
        has_prices = stats and stats.get("median_price") and stats.get("median_rent_weekly")
        if stats and has_prices:
            return stats

        record = suburbs_db.get_record(suburb_name)
        if not record:
            return stats

        profile = await build_suburb_profile(record, persist=PERSIST)
        if stats:
            for key, val in stats.items():
                if val is not None and profile.get(key) is None:
                    profile[key] = val

        if profile.get("median_price") or profile.get("median_rent_weekly"):
            self.store.cache_stats(profile, PERSIST)
        return profile

    def cog_unload(self):
        self.daily_market.cancel()
        self.daily_strategies.cancel()
        self.weekly_digest.cancel()
        self.market_alerts.cancel()
        self.suburb_sync.cancel()

    def _profile_key(self, user_id: int) -> str:
        return str(user_id)

    def _get_profile(self, user_id: int) -> dict:
        key = self._profile_key(user_id)
        if key not in self.profiles:
            self.profiles[key] = {
                "tags": [],
                "suburbs": [],
                "qualified": False,
                "last_engagement": None,
                "notes": [],
            }
        return self.profiles[key]

    def _touch_profile(self, user_id: int, *, suburb: str | None = None, tag: str | None = None):
        p = self._get_profile(user_id)
        p["last_engagement"] = datetime.now(TZ).isoformat()
        if suburb and suburb not in p["suburbs"]:
            p["suburbs"].append(suburb)
        if tag and tag not in p["tags"]:
            p["tags"].append(tag)
        _save_profiles(self.profiles)

    async def _channel(self, key: str):
        cid = self.state.get(key)
        if not cid:
            return None
        ch = self.bot.get_channel(cid) or await self.bot.fetch_channel(cid)
        return ch

    async def _log(self, text: str):
        ch = await self._channel("bot_logs_channel_id")
        if ch:
            try:
                await ch.send(f"`{datetime.now(TZ).strftime('%H:%M')}` {text}")
            except discord.Forbidden:
                logger.warning("bot_logs channel forbidden")

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
        msg1 = await ch.send(embed=_market_embed(rental))
        msg2 = await ch.send(embed=_market_embed(growth))
        for mid in (msg1.id, msg2.id):
            ids = self.state.get("tracked_message_ids", [])
            ids.append(mid)
            self.state["tracked_message_ids"] = ids[-50:]
        posted.extend([rental["id"], growth["id"]])
        self.state["posted_properties"] = posted[-40:]
        self.state["last_market_date"] = datetime.now(TZ).strftime("%Y-%m-%d")
        _save_state(self.state)

        idx = self.state.get("sydney_rotation_index", 0) % len(SYDNEY_DAILY_ROTATION)
        suburb_name = SYDNEY_DAILY_ROTATION[idx]
        stats = self.store.lookup(suburb_name)
        if stats:
            rot_msg = await ch.send(embed=_suburb_embed(suburb_name, stats, self.store))
            ids = self.state.get("tracked_message_ids", [])
            ids.append(rot_msg.id)
            self.state["tracked_message_ids"] = ids[-50:]
            self.state["sydney_rotation_index"] = idx + 1
            _save_state(self.state)

        logger.info(f"market daily posted to {ch.id}")
        return True

    async def post_strategy_daily(self) -> bool:
        ch = await self._channel("strategies_channel_id")
        if not ch:
            return False
        try:
            item = strategy_for_today()
        except ValueError as e:
            logger.error(f"daily strategy config error: {e}")
            return False
        embed = _strategy_embed(item)
        embed.set_footer(
            text=f"{DISCLAIMER} | Week {STRATEGIES_WEEK} · {datetime.now(TZ).strftime('%A')}"
        )
        await ch.send(embed=embed)
        self.state["last_strategy_date"] = datetime.now(TZ).strftime("%Y-%m-%d")
        self.state["strategies_week"] = STRATEGIES_WEEK
        _save_state(self.state)
        logger.info(f"daily strategy posted to {ch.id} (week {STRATEGIES_WEEK})")
        return True

    async def post_weekly_digest(self) -> bool:
        ch = await self._channel("strategies_channel_id") or await self._channel("market_channel_id")
        if not ch:
            return False
        lines = "\n".join(f"• {line}" for line in WEEKLY_DIGEST_LINES)
        embed = discord.Embed(
            title="📰 Weekly Market Digest",
            description=lines,
            colour=THEME,
        )
        embed.set_footer(text=DISCLAIMER)
        await ch.send(embed=embed)
        self.state["last_digest_week"] = datetime.now(TZ).strftime("%G-W%V")
        _save_state(self.state)
        return True

    async def check_market_alerts(self) -> int:
        ch = await self._channel("alerts_channel_id") or await self._channel("market_channel_id")
        if not ch:
            return 0
        threshold = float(self.state.get("alert_threshold_pct", 2.0))
        baselines: dict = self.state.setdefault("suburb_baselines", {})
        sent = 0
        for key, stats in self.store.iter_stats():
            name = stats.get("name", key.title())
            median = float(stats["median_price"])
            growth = float(stats.get("growth_12m_pct", 0))
            prev = baselines.get(key)
            if prev is not None:
                pct_change = ((median - prev) / prev) * 100 if prev else 0
                if abs(pct_change) >= threshold or abs(growth) >= threshold:
                    direction = "down" if growth < 0 else "up"
                    moment = "potential buyer moment" if growth < 0 else "momentum to research"
                    embed = discord.Embed(
                        title=f"🔔 Market Alert — {name}",
                        description=(
                            f"**{name}** median indicative **{direction} {abs(growth):.1f}%** (12m) — {moment}.\n"
                            f"Median: {fmt_currency(median)} | Yield: {stats['rental_yield_pct']}%"
                        ),
                        colour=0xE67E22,
                    )
                    embed.set_footer(text=DISCLAIMER)
                    await ch.send(embed=embed)
                    sent += 1
            baselines[key] = median
        self.state["suburb_baselines"] = baselines
        self.state["last_alert_date"] = datetime.now(TZ).strftime("%Y-%m-%d")
        _save_state(self.state)
        return sent

    async def _flag_lead(self, guild: discord.Guild, member: discord.Member, reason: str):
        p = self._get_profile(member.id)
        p["qualified"] = True
        p["notes"].append(f"{datetime.now(TZ).isoformat()}: {reason}")
        _save_profiles(self.profiles)

        mod = await self._channel("leads_mod_channel_id")
        if mod:
            tags = ", ".join(p["tags"]) or "none"
            suburbs = ", ".join(p["suburbs"][-5:]) or "none"
            content = (
                f"🎯 **@needs-follow-up** — {member.mention}\n"
                f"**Reason:** {reason}\n"
                f"**Tags:** {tags}\n"
                f"**Suburb interests:** {suburbs}\n"
                f"**Last engagement:** {p.get('last_engagement', 'n/a')}"
            )
            try:
                thread = await mod.create_thread(
                    name=f"lead-{member.display_name}"[:100],
                    content=content,
                    auto_archive_duration=10080,
                )
                await thread.send(
                    f"[discussion] Lead thread for {member.mention}. "
                    "Review conversation history and reach out privately if appropriate."
                )
            except discord.Forbidden:
                await mod.send(content)
        await self._log(f"Lead flagged: {member} — {reason}")

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
    async def daily_strategies(self):
        today = datetime.now(TZ).strftime("%Y-%m-%d")
        if self.state.get("last_strategy_date") == today:
            return
        await self.post_strategy_daily()

    @daily_strategies.before_loop
    async def _wait_daily_strategies(self):
        await self.bot.wait_until_ready()

    @tasks.loop(time=time(hour=8, minute=30, tzinfo=TZ))
    async def weekly_digest(self):
        now = datetime.now(TZ)
        if now.weekday() != 0:
            return
        week = now.strftime("%G-W%V")
        if self.state.get("last_digest_week") == week:
            return
        await self.post_weekly_digest()

    @weekly_digest.before_loop
    async def _wait_digest(self):
        await self.bot.wait_until_ready()

    @tasks.loop(time=time(hour=11, minute=0, tzinfo=TZ))
    async def market_alerts(self):
        today = datetime.now(TZ).strftime("%Y-%m-%d")
        if self.state.get("last_alert_date") == today:
            return
        await self.check_market_alerts()

    @market_alerts.before_loop
    async def _wait_alerts(self):
        await self.bot.wait_until_ready()

    @tasks.loop(time=time(hour=3, minute=0, tzinfo=TZ))
    async def suburb_sync(self):
        """Weekly refresh of AU suburb index on Railway /data volume."""
        if datetime.now(TZ).weekday() != 6:
            return
        from scripts.sync_suburbs import main as sync_main

        code = await asyncio.to_thread(sync_main)
        if code == 0:
            suburbs_db.reload()
            logger.info("Weekly suburb sync completed")

    @suburb_sync.before_loop
    async def _wait_suburb_sync(self):
        await self.bot.wait_until_ready()
        await self._ensure_suburb_index()

    # ------------------------------------------------------------------ Tier 1
    @discord.slash_command(
        name="suburb",
        description="Market intel — median, growth, yield, hotspot score",
        guild_ids=[GUILD_ID],
    )
    async def suburb(self, ctx, suburb_name: Option(str, autocomplete=suburb_autocomplete)):
        await ctx.defer()
        stats = await self._resolve_suburb_stats(suburb_name)
        if not stats:
            state = SUBURB_TO_STATE.get(suburb_name.lower(), "nsw").upper()
            slug = suburb_name.lower().replace(" ", "-")
            await ctx.followup.send(
                embed=discord.Embed(
                    title=f"🏘️ {suburb_name}",
                    description=(
                        f"No match for **{suburb_name}** in the AU locality index.\n"
                        "Check spelling — try a nearby official locality name."
                    ),
                    colour=THEME,
                )
                .add_field(
                    name="Research",
                    value=f"[Search Domain](https://www.domain.com.au/suburb-profile/{slug}-{state.lower()})",
                    inline=False,
                )
                .set_footer(text=DISCLAIMER),
            )
            return
        self._touch_profile(ctx.author.id, suburb=stats.get("name", suburb_name))
        await self._log(f"`/suburb` {ctx.author} → {suburb_name}")
        await ctx.followup.send(embed=_suburb_embed(suburb_name, stats, self.store))

    @discord.slash_command(
        name="compare",
        description="Side-by-side suburb investment comparison",
        guild_ids=[GUILD_ID],
    )
    async def compare(
        self,
        ctx,
        suburb1: Option(str, autocomplete=suburb_autocomplete),
        suburb2: Option(str, autocomplete=suburb_autocomplete),
    ):
        await ctx.defer()
        a = await self._resolve_suburb_stats(suburb1)
        b = await self._resolve_suburb_stats(suburb2)
        if not a or not b:
            missing = []
            if not a:
                missing.append(suburb1)
            if not b:
                missing.append(suburb2)
            await ctx.followup.send(
                f"No stats for: **{', '.join(missing)}**. Try suburbs in the daily rotation first.",
                ephemeral=True,
            )
            return
        self._touch_profile(ctx.author.id, suburb=a["name"])
        self._touch_profile(ctx.author.id, suburb=b["name"])
        await self._log(f"`/compare` {ctx.author} → {suburb1} vs {suburb2}")
        await ctx.followup.send(embed=_compare_embed(a, b, self.store))

    @discord.slash_command(
        name="neggear",
        description="Negative gearing discussion calculator",
        guild_ids=[GUILD_ID],
    )
    async def neggear(
        self,
        ctx,
        property_price: Option(float, "Purchase price ($)", min_value=50000),
        rent_weekly: Option(float, "Weekly rent ($)", min_value=0),
        mortgage_rate: Option(float, "Interest rate (%)", min_value=0.1, max_value=20),
        marginal_tax_rate: Option(float, "Marginal tax rate (%)", default=37, required=False),
    ):
        await ctx.defer()
        r = calc_negative_gearing(property_price, rent_weekly, mortgage_rate, marginal_tax_rate_pct=marginal_tax_rate)
        embed = discord.Embed(
            title="📉 Negative Gearing — Discussion Model",
            description="Tax planning discussion numbers only — not a tax return.",
            colour=THEME,
        )
        embed.add_field(name="Loan (80% LVR assumed)", value=fmt_currency(r.loan_amount), inline=True)
        embed.add_field(name="Annual rent", value=fmt_currency(r.annual_rent), inline=True)
        embed.add_field(name="Annual interest", value=fmt_currency(r.annual_interest), inline=True)
        embed.add_field(name="Holding costs (est.)", value=fmt_currency(r.annual_holding_costs), inline=True)
        embed.add_field(name="Depreciation (est.)", value=fmt_currency(r.annual_depreciation), inline=True)
        embed.add_field(name="Pre-tax cashflow", value=fmt_currency(r.pre_tax_cashflow), inline=True)
        embed.add_field(name="Taxable loss", value=fmt_currency(r.taxable_loss), inline=True)
        embed.add_field(name=f"Tax benefit @ {r.marginal_rate_pct:.0f}%", value=fmt_currency(r.tax_benefit), inline=True)
        embed.add_field(name="After-tax cashflow", value=fmt_currency(r.after_tax_cashflow), inline=True)
        embed.set_footer(text=DISCLAIMER)
        self._touch_profile(ctx.author.id, tag="calculator_neggear")
        await self._log(f"`/neggear` {ctx.author} price={property_price}")
        await ctx.followup.send(embed=embed)

    @discord.slash_command(
        name="refi_check",
        description="Refinance eligibility discussion check",
        guild_ids=[GUILD_ID],
    )
    async def refi_check(
        self,
        ctx,
        current_rate: Option(float, "Current rate (%)", min_value=0.1),
        equity_pct: Option(float, "Equity (%)", min_value=0, max_value=100),
        income: Option(float, "Gross annual income ($)", min_value=0),
        property_value: Option(float, "Property value ($)", default=800000, required=False),
    ):
        await ctx.defer()
        r = calc_refinance_check(current_rate, equity_pct, income, property_value=property_value)
        embed = discord.Embed(
            title="🔄 Refinance Check — Discussion Model",
            description="Educational guidance only — talk to a broker for strategy.",
            colour=THEME,
        )
        embed.add_field(name="Loan balance (est.)", value=fmt_currency(r.loan_balance), inline=True)
        embed.add_field(name="Current repayment/mo", value=fmt_currency(r.current_monthly), inline=True)
        embed.add_field(name=f"Indicative market rate", value=f"{r.indicative_new_rate_pct:.2f}%", inline=True)
        embed.add_field(name="Market repayment/mo", value=fmt_currency(r.market_monthly), inline=True)
        embed.add_field(name="Monthly saving (est.)", value=fmt_currency(r.monthly_saving), inline=True)
        embed.add_field(name="Annual saving (est.)", value=fmt_currency(r.annual_saving), inline=True)
        if r.break_even_months:
            embed.add_field(
                name="Break-even on switch costs",
                value=f"~{r.break_even_months:.0f} months (assuming $1,500 switching)",
                inline=False,
            )
        embed.add_field(name="Serviceability (discussion)", value=r.serviceability_note, inline=False)
        embed.set_footer(text=DISCLAIMER)
        self._touch_profile(ctx.author.id, tag="calculator_refi")
        await self._log(f"`/refi_check` {ctx.author} rate={current_rate}% equity={equity_pct}%")
        await ctx.followup.send(embed=embed)

    # ------------------------------------------------------------------ Admin / config
    @discord.slash_command(
        name="invest_config",
        description="Bind invest bot channels — run inside target channel",
        guild_ids=[GUILD_ID],
        default_member_permissions=discord.Permissions(administrator=True),
    )
    async def invest_config(
        self,
        ctx,
        feed: Option(str, "Channel purpose", choices=CONFIG_CHOICES),
        strategy_role: Option(discord.Role, "Role for 🎯 qualification", required=False),
    ):
        key_map = {
            "market": "market_channel_id",
            "strategies": "strategies_channel_id",
            "alerts": "alerts_channel_id",
            "strategy_seekers": "strategy_seekers_channel_id",
            "leads_mod": "leads_mod_channel_id",
            "bot_logs": "bot_logs_channel_id",
        }
        self.state[key_map[feed]] = ctx.channel.id
        if strategy_role:
            self.state["strategy_role_id"] = strategy_role.id
        _save_state(self.state)
        await ctx.respond(f"✅ **{feed}** linked to this channel.", ephemeral=True)
        await self._log(f"Config: {feed} → #{ctx.channel.name} by {ctx.author}")

    @discord.slash_command(
        name="invest_post_now",
        description="Admin: trigger a feed post immediately",
        guild_ids=[GUILD_ID],
        default_member_permissions=discord.Permissions(administrator=True),
    )
    async def invest_post_now(
        self,
        ctx,
        feed: Option(str, choices=["market", "strategies", "digest", "alerts"]),
    ):
        await ctx.defer(ephemeral=True)
        if feed == "market":
            ok = await self.post_market_daily()
        elif feed == "strategies":
            ok = await self.post_strategy_daily()
        elif feed == "digest":
            ok = await self.post_weekly_digest()
        else:
            n = await self.check_market_alerts()
            ok = n >= 0
            await ctx.followup.send(f"✅ Alerts check done ({n} posted)." if ok else "❌ No alert channel.", ephemeral=True)
            return
        await ctx.followup.send("✅ Posted." if ok else "❌ Channel not configured.", ephemeral=True)

    @discord.slash_command(
        name="invest_survey_post",
        description="Admin: post qualification survey in this channel",
        guild_ids=[GUILD_ID],
        default_member_permissions=discord.Permissions(administrator=True),
    )
    async def invest_survey_post(self, ctx):
        embed = discord.Embed(
            title="Tell us your situation (react to describe)",
            description=(
                "🏠 First investor\n"
                "🔄 Current PPOR + investment\n"
                "💰 Looking to refinance\n"
                "🔗 Building portfolio\n\n"
                "One reaction per user — builds your profile for strategy discussion."
            ),
            colour=THEME,
        )
        embed.set_footer(text=DISCLAIMER)
        msg = await ctx.channel.send(embed=embed)
        for emoji in SURVEY_MAP:
            await msg.add_reaction(emoji)
        await ctx.respond("✅ Survey posted.", ephemeral=True)

    @discord.slash_command(
        name="invest_flag_lead",
        description="Admin: flag a member as qualified lead",
        guild_ids=[GUILD_ID],
        default_member_permissions=discord.Permissions(administrator=True),
    )
    async def invest_flag_lead(
        self,
        ctx,
        member: Option(discord.Member),
        reason: Option(str, default="Manual flag", required=False),
    ):
        await self._flag_lead(ctx.guild, member, reason)
        await ctx.respond(f"✅ Flagged {member.mention}.", ephemeral=True)

    # ------------------------------------------------------------------ Tier 2 reactions
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild or guild.id != GUILD_ID:
            return

        emoji = str(payload.emoji)
        tracked = payload.message_id in self.state.get("tracked_message_ids", [])

        if emoji == EMOJI_INTEREST and tracked:
            member = guild.get_member(payload.user_id) or await guild.fetch_member(payload.user_id)
            try:
                dm = await member.create_dm()
                await dm.send(
                    "Want personalised mortgage strategy **discussion** insights? "
                    f"React {EMOJI_STRATEGY} on the post in the server, or visit #strategy-seekers."
                )
            except discord.Forbidden:
                pass
            self._touch_profile(payload.user_id, tag="reacted_interest")
            await self._log(f"👍 interest: {member}")

        elif emoji == EMOJI_STRATEGY:
            member = guild.get_member(payload.user_id) or await guild.fetch_member(payload.user_id)
            role_id = self.state.get("strategy_role_id")
            if role_id:
                role = guild.get_role(role_id)
                if role:
                    try:
                        await member.add_roles(role, reason="Invest bot strategy qualification")
                    except discord.Forbidden:
                        logger.warning("Cannot assign strategy role")
            seekers = self.state.get("strategy_seekers_channel_id")
            if seekers:
                try:
                    ch = guild.get_channel(seekers) or await guild.fetch_channel(seekers)
                    await ch.send(
                        f"{member.mention} joined strategy discussion — "
                        "introduce yourself when ready. [discussion]"
                    )
                except discord.Forbidden:
                    pass
            self._touch_profile(payload.user_id, tag="strategy_seeker")
            await self._flag_lead(guild, member, "Reacted 🎯 for strategy discussion")

        elif emoji in SURVEY_MAP:
            tag = SURVEY_MAP[emoji]
            ch_id = self.state.get("strategy_seekers_channel_id")
            if ch_id and payload.channel_id != ch_id:
                return
            self._touch_profile(payload.user_id, tag=tag)
            member = guild.get_member(payload.user_id) or await guild.fetch_member(payload.user_id)
            await self._log(f"Survey {tag}: {member}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild or message.guild.id != GUILD_ID:
            return
        if not LEAD_KEYWORDS.search(message.content):
            return
        if len(message.content) < 20:
            return
        has_numbers = bool(re.search(r"\$?\d[\d,]{3,}", message.content))
        if has_numbers or "?" in message.content:
            self._touch_profile(message.author.id, tag="chat_finance_question")
            await self._flag_lead(
                message.guild,
                message.author,
                f"Finance keyword thread in #{message.channel.name}",
            )


def setup(bot):
    bot.add_cog(InvestBotCog(bot))
    logger.info("InvestBotCog online — mortgage broker discussion suite")
