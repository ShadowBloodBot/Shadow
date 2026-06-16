# cogs/sand/guide.py — ShadowSyn SAND: Raiders of Sophie knowledge bot

import logging

import discord
from discord import Option
from discord.ext import commands

from .query_engine import (
    BRAND_AUTHOR,
    format_craft_answer,
    format_materials_table,
    load_knowledge,
    truncate_for_discord,
    wiki_footer,
)

from cogs.guild_registry import REGISTERED_GUILD_IDS, ch_id, is_owner, role_id

logger = logging.getLogger("ShadowSyn.SAND")

THEME_PRIMARY = 0x2B0B35
OWNER_ID = 482463400929263627

CRAFT_EXAMPLES = [
    "time bomb",
    "1874 petros silenced",
    "1874 petros sniper",
    "armored jacket",
    "pristine",
]


def is_sand_member(user) -> bool:
    if is_owner(user):
        return True
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
    if is_owner(ctx.author):
        return False
    sand_id = ch_id(ctx.guild.id, "sand_general") if ctx.guild else None
    if sand_id and ctx.channel_id == sand_id:
        return False
    await safe_reply(
        ctx,
        f"🏜️ SAND commands live in <#{sand_id}> only.\n"
        f"Head there and try again — e.g. `/sand craft time bomb`",
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


def _build_craft_embed(result: dict, knowledge: dict) -> discord.Embed:
    if result.get("ok") is False:
        embed = _brand_embed(knowledge, f"❓ {result.get('title', 'Not found')}", result.get("subtitle", ""))
        suggestions = result.get("suggestions", [])
        if suggestions:
            lines = "\n".join(f"• **{name}** ({score}%)" for name, score in suggestions)
            embed.add_field(name="Did you mean?", value=lines, inline=False)
        embed.add_field(
            name="Try",
            value="\n".join(f"• `/sand craft {q}`" for q in CRAFT_EXAMPLES[:4]),
            inline=False,
        )
        return embed

    title = f"🔨 {result.get('title', 'SAND Craft')}"
    embed = _brand_embed(knowledge, title, result.get("subtitle", ""))

    if result.get("material_rows"):
        table = format_materials_table(result["material_rows"])
        embed.add_field(
            name="📋 Materials needed",
            value=f"```\n{truncate_for_discord(table, 1000)}\n```",
            inline=False,
        )
        if result.get("summary"):
            embed.add_field(name="📦 Total (full tree)", value=result["summary"], inline=False)

    direct = result.get("direct_rows")
    if direct and direct != result.get("material_rows"):
        direct_table = format_materials_table(direct)
        embed.add_field(
            name="⚙️ Direct recipe",
            value=f"```\n{truncate_for_discord(direct_table, 900)}\n```",
            inline=False,
        )

    craft = result.get("craft_chain") or []
    if craft:
        for i, step in enumerate(craft[:8], 1):
            embed.add_field(name=f"Step {i}", value=truncate_for_discord(step), inline=False)
    elif result.get("steps"):
        for i, step in enumerate(result["steps"][:12], 1):
            embed.add_field(name=f"Step {i}", value=truncate_for_discord(step), inline=False)

    if result.get("matched_item"):
        embed.add_field(name="📍 Item", value=result["matched_item"], inline=True)
    if result.get("intent_label"):
        embed.add_field(name="🎯 Type", value=result["intent_label"], inline=True)

    return embed


def _craftable_names(knowledge: dict) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for recipe in knowledge.get("recipes", []):
        name = recipe.get("output")
        if name and name not in seen:
            names.append(name)
            seen.add(name)
    for item in knowledge.get("items", []):
        name = item.get("name")
        if name and item.get("craft_recipe_text") and name not in seen:
            names.append(name)
            seen.add(name)
    return sorted(names, key=str.lower)


async def _craft_autocomplete(ctx: discord.AutocompleteContext):
    cog = ctx.cog
    if not cog or not getattr(cog, "knowledge", None):
        return []
    hints = ["pristine", "pristine turrets", *CRAFT_EXAMPLES]
    craftable = _craftable_names(cog.knowledge)
    current = (ctx.value or "").lower()
    if current:
        filtered_hints = [h for h in hints if current in h.lower()]
        filtered_items = [n for n in craftable if current in n.lower()]
    else:
        filtered_hints = hints
        filtered_items = craftable
    combined = filtered_hints + [n for n in filtered_items if n not in filtered_hints]
    return combined[:25]


class SandGuideCog(commands.Cog):
    """Intelligent SAND wiki + craft guide for ShadowSyn."""

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
        "SAND: Raiders of Sophie — craft recipes & Pristine turrets",
        guild_ids=REGISTERED_GUILD_IDS,
    )

    @sand.command(
        name="craft",
        description="Craft materials for an item, or list every Pristine turret variant",
    )
    async def sand_craft(
        self,
        ctx: discord.ApplicationContext,
        item: Option(
            str,
            "Item to craft (e.g. time bomb) — or type pristine for all Pristine variants",
            required=True,
            autocomplete=_craft_autocomplete,
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
            result = format_craft_answer(item, self.knowledge)
            embed = _build_craft_embed(result, self.knowledge)
            await safe_reply(ctx, embed=embed)
        except Exception as exc:
            logger.error("sand craft failed: %s", exc)
            await safe_reply(ctx, f"❌ Craft lookup failed — try rephrasing. ({exc})", ephemeral=True)

    @sand.command(name="help", description="SAND bot usage, examples, and tips")
    async def sand_help(self, ctx: discord.ApplicationContext):
        if await self._gate(ctx):
            return

        examples = "\n".join(f"• `/sand craft {q}`" for q in CRAFT_EXAMPLES)

        embed = _brand_embed(
            self.knowledge,
            "🏜️ ShadowSyn SAND Guide",
            "Craft recipes with full material breakdowns, plus every **Pristine** turret variant.",
        )
        embed.add_field(
            name="Commands",
            value=(
                "• `/sand craft <item>` — materials needed + craft steps\n"
                "• `/sand craft pristine` — list all Pristine turret variants\n"
                "• `/sand help` — this message"
            ),
            inline=False,
        )
        embed.add_field(name="Examples", value=examples, inline=False)
        embed.add_field(
            name="Tips",
            value=(
                "Materials show the **full tree** (e.g. Petros Sniper includes base Petros cost).\n"
                "Pristine turrets are **loot only** — use `/sand craft pristine` for the full list."
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
