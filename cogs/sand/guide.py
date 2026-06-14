# cogs/sand/guide.py — ShadowSyn SAND: Raiders of Sophie knowledge bot

import logging

import discord
from discord import Option
from discord.ext import commands

from .query_engine import (
    BRAND_AUTHOR,
    format_materials_table,
    format_query_answer,
    load_knowledge,
    suggest_closest_matches,
    truncate_for_discord,
    wiki_footer,
)

from cogs.guild_registry import REGISTERED_GUILD_IDS, ch_id, role_id

logger = logging.getLogger("ShadowSyn.SAND")

THEME_PRIMARY = 0x2B0B35
OWNER_ID = 482463400929263627

EXAMPLE_QUESTIONS = [
    "how do i get pristine cannons",
    "how many materials for 1874 petros sniper silenced",
    "storm dive dreadnaught loot",
    "fort raid time bombs",
    "where to farm triplet shotgun",
    "craft time bomb",
    "what do i need for armored jacket",
]


def is_sand_member(user) -> bool:
    if not isinstance(user, discord.Member):
        return False
    rid = role_id(user.guild.id, "member")
    if rid is None:
        return False
    return any(role.id == rid for role in user.roles)


async def safe_reply(ctx_or_inter, *args, **kwargs):
    try:
        if hasattr(ctx_or_inter, "respond"):
            return await ctx_or_inter.respond(*args, **kwargs)
        if hasattr(ctx_or_inter, "response"):
            if not ctx_or_inter.response.is_done():
                return await ctx_or_inter.response.send_message(*args, **kwargs)
            return await ctx_or_inter.followup.send(*args, **kwargs)
    except Exception as exc:
        logger.error("safe_reply failed: %s", exc)
        return None


async def deny_wrong_thread(ctx: discord.ApplicationContext) -> bool:
    sand_id = ch_id(ctx.guild.id, "sand_general") if ctx.guild else None
    if sand_id and ctx.channel_id == sand_id:
        return False
    await safe_reply(
        ctx,
        f"🏜️ SAND commands live in <#{sand_id}> only.\n"
        f"Head there and try again — e.g. `/sand query how do i get pristine cannons`",
        ephemeral=True,
    )
    return True


async def deny_wrong_role(ctx: discord.ApplicationContext) -> bool:
    if is_sand_member(ctx.author):
        return False
    await safe_reply(
        ctx,
        "🔒 You need the **Gambler** role to use SAND commands.\n"
        "Grab it from the casino hub, then come back to this thread.",
        ephemeral=True,
    )
    return True


def _brand_embed(knowledge: dict, title: str, subtitle: str = "") -> discord.Embed:
    embed = discord.Embed(title=title, color=THEME_PRIMARY)
    if subtitle:
        embed.description = subtitle
    embed.set_author(name=BRAND_AUTHOR)
    embed.set_footer(text=wiki_footer(knowledge))
    return embed


def _build_query_embed(result: dict, knowledge: dict) -> discord.Embed:
    if result.get("ok") is False:
        embed = _brand_embed(knowledge, f"❓ {result.get('title', 'Not found')}", result.get("subtitle", ""))
        suggestions = result.get("suggestions", [])
        if suggestions:
            lines = "\n".join(f"• **{name}** ({score}%)" for name, score in suggestions)
            embed.add_field(name="Did you mean?", value=lines, inline=False)
        embed.add_field(
            name="Try asking",
            value="\n".join(f"• `/sand query {q}`" for q in EXAMPLE_QUESTIONS[:3]),
            inline=False,
        )
        return embed

    title = f"🏜️ {result.get('title', 'SAND Guide')}"
    embed = _brand_embed(knowledge, title, result.get("subtitle", ""))

    steps = result.get("steps") or []
    if result.get("material_rows"):
        table = format_materials_table(result["material_rows"])
        embed.add_field(
            name="📋 Materials",
            value=f"```\n{truncate_for_discord(table, 1000)}\n```",
            inline=False,
        )
        if result.get("summary"):
            embed.add_field(name="📦 Total", value=result["summary"], inline=False)
        craft = result.get("craft_chain") or []
        for i, step in enumerate(craft[:8], 1):
            embed.add_field(name=f"Craft {i}", value=truncate_for_discord(step), inline=False)
    else:
        for i, step in enumerate(steps[:25], 1):
            embed.add_field(name=f"Step {i}", value=truncate_for_discord(step), inline=False)

    if result.get("matched_item"):
        embed.add_field(name="📍 Matched", value=result["matched_item"], inline=True)
    if result.get("intent_label"):
        embed.add_field(name="🎯 Topic", value=result["intent_label"], inline=True)

    return embed


async def _query_autocomplete(ctx: discord.AutocompleteContext):
    cog = ctx.cog
    if not cog or not getattr(cog, "knowledge", None):
        return []
    names = []
    seen = set()
    for item in cog.knowledge.get("items", []):
        n = item.get("name")
        if n and n not in seen:
            names.append(n)
            seen.add(n)
    current = (ctx.value or "").lower()
    filtered = [n for n in names if current in n.lower()] if current else names
    # Mix item names with example questions for autocomplete hints
    hints = [q for q in EXAMPLE_QUESTIONS if not current or current in q.lower()]
    combined = hints + [n for n in filtered if n not in hints]
    return combined[:25]


class SandGuideCog(commands.Cog):
    """Intelligent SAND wiki + guide Q&A for ShadowSyn."""

    def __init__(self, bot: discord.Bot):
        self.bot = bot
        self.knowledge: dict = {}
        self._load_kb()

    def _load_kb(self):
        try:
            self.knowledge = load_knowledge()
            logger.info(
                "SAND knowledge loaded: %d items, %d recipes",
                len(self.knowledge.get("items", [])),
                len(self.knowledge.get("recipes", [])),
            )
        except FileNotFoundError:
            logger.error("sand_knowledge.json missing — run sand-raiders-of-sophie/scripts/scrape_wiki.py")
            self.knowledge = {
                "items": [],
                "recipes": [],
                "acquisition_plans": [],
                "faq_intents": [],
                "item_aliases": {},
                "turret_tiers": [],
                "meta": {"sources": ["offline"]},
            }
        except Exception as exc:
            logger.error("Failed to load SAND knowledge: %s", exc)
            self.knowledge = {"meta": {"sources": ["error"]}}

    async def _gate(self, ctx: discord.ApplicationContext) -> bool:
        if await deny_wrong_thread(ctx):
            return True
        if await deny_wrong_role(ctx):
            return True
        return False

    sand = discord.SlashCommandGroup(
        "sand",
        "SAND: Raiders of Sophie — loot, craft & acquisition guide",
        guild_ids=REGISTERED_GUILD_IDS,
    )

    @sand.command(
        name="query",
        description="Ask anything about SAND — loot, craft, materials, forts, step-by-step",
    )
    async def sand_query(
        self,
        ctx: discord.ApplicationContext,
        question: Option(
            str,
            "e.g. how do i get pristine cannons / materials for time bomb",
            required=True,
            autocomplete=_query_autocomplete,
        ),
    ):
        if await self._gate(ctx):
            return
        if not self.knowledge.get("items"):
            return await safe_reply(
                ctx,
                "❌ Knowledge base empty. Admin: run `scrape_wiki.py` then redeploy Shadow on Railway.",
                ephemeral=True,
            )

        try:
            result = format_query_answer(question, self.knowledge)
            embed = _build_query_embed(result, self.knowledge)
            await safe_reply(ctx, embed=embed)
        except Exception as exc:
            logger.error("sand query failed: %s", exc)
            await safe_reply(ctx, f"❌ Query failed — try rephrasing. ({exc})", ephemeral=True)

    @sand.command(name="help", description="SAND bot usage, examples, and tips")
    async def sand_help(self, ctx: discord.ApplicationContext):
        if await self._gate(ctx):
            return

        examples = "\n".join(f"• `/sand query {q}`" for q in EXAMPLE_QUESTIONS)

        embed = _brand_embed(
            self.knowledge,
            "🏜️ ShadowSyn SAND Guide",
            "Ask **anything** about SAND in plain English — one command handles loot, craft, materials, and routes.",
        )
        embed.add_field(
            name="Commands",
            value=(
                "• `/sand query <question>` — answers everything (loot, materials, crafting, forts, Storm Dive)\n"
                "• `/sand help` — this message"
            ),
            inline=False,
        )
        embed.add_field(name="Example questions", value=examples, inline=False)
        embed.add_field(
            name="Tips",
            value=(
                "Ask naturally — `how many materials for time bomb`, `where to get triplet`, `pristine 80mm`.\n"
                "Fuzzy matching + craft chains (base → mod → final) are automatic."
            ),
            inline=False,
        )
        await safe_reply(ctx, embed=embed, ephemeral=True)

    @sand.command(name="reload", description="Owner: reload knowledge JSON from disk")
    async def sand_reload(self, ctx: discord.ApplicationContext):
        if await self._gate(ctx):
            return
        if ctx.author.id != OWNER_ID:
            return await safe_reply(ctx, "⛔ Owner only.", ephemeral=True)
        self._load_kb()
        count = len(self.knowledge.get("items", []))
        await safe_reply(ctx, f"✅ Reloaded knowledge base ({count} items).", ephemeral=True)


def setup(bot):
    bot.add_cog(SandGuideCog(bot))
