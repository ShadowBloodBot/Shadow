# cogs/game_roles.py — persistent gaming role self-serve hub (Steam Codes UX)

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

import discord
from discord import ButtonStyle, Option
from discord.ui import Button, View
from discord.ext import commands

from cogs.guild_registry import (
    PERSIST_ROOT,
    REGISTERED_GUILD_IDS,
    SHADOW_MAIN_GUILD_ID,
    ch_id,
    has_admin_shadow,
    is_registered_guild,
    resolve_channel,
    resolve_role,
)

logger = logging.getLogger("ShadowSyn.GameRoles")

THEME_PRIMARY = 0x2B0B35
PAGE_SIZE = 10
FLASH_SECONDS = 1.0
ADMIN_FLASH_SECONDS = 1.5

PANEL_TITLE = "🎮 Game Roles"
PANEL_BLURB = (
    "This is where you grab your **game roles**.\n\n"
    "Click **Manage My Games** to toggle what you play — "
    "your roles update instantly. Use **Prev / Next** to browse the list."
)

MANAGE_PREFIX = "game_roles_manage:"
PANEL_PREV_ID = "game_roles_panel_prev"
PANEL_NEXT_ID = "game_roles_panel_next"
TOGGLE_PREFIX = "game_roles_toggle:"
EPH_PREV_PREFIX = "game_roles_eph_prev:"
EPH_NEXT_PREFIX = "game_roles_eph_next:"

_REPO_DATA = Path(__file__).resolve().parents[1] / "data"
_persist_env = os.getenv("PERSIST_PATH", "").strip()
if _persist_env:
    STORE_PATH = Path(_persist_env).resolve() / "game_roles.json"
else:
    STORE_PATH = PERSIST_ROOT / "game_roles.json"
_REPO_STORE = _REPO_DATA / "game_roles.json"

DENYLIST_ROLE_IDS = frozenset({
    1283738820160000031,
    955600547266822174,
    960088893351415898,
    1403928804891693187,
    1214794734770323466,
    1447110148442030111,
})

DENYLIST_NAMES = frozenset({
    "@everyone",
    "everyone",
    "sensational shadow",
    "shadow",
    "mover & shaker",
    "mover and shaker",
    "🔥shadow",
    "silhouette",
    "shade",
    "major alcoholic boomer",
    "degenerate",
    "member",
    "minion",
    "bot",
    "rusty helper",
    "donate bot",
    "server booster",
    "t&l leadership",
    "t&l temp",
    "guest",
    "high t",
    "annoying",
    "bloods cum slut",
})

DEFAULT_GUILD_CFG: dict[str, Any] = {
    "channel_id": None,
    "panel_message_id": None,
    "panel_page": 0,
    "roles": [],
}


def _atomic_write(file_path: Path, data: Any) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = file_path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    temp_path.replace(file_path)


def _normalize_role_name(name: str) -> str:
    return (name or "").strip().lower()


def _is_denylisted(role: discord.Role, guild_id: int) -> bool:
    if role.id in DENYLIST_ROLE_IDS:
        return True
    if role.is_default():
        return True
    if role.managed:
        return True
    admin_rid = resolve_role(role.guild, "admin_shadow")
    if admin_rid and role.id == admin_rid.id:
        return True
    return _normalize_role_name(role.name) in DENYLIST_NAMES


async def safe_reply(ctx_or_inter, *args, **kwargs):
    try:
        if hasattr(ctx_or_inter, "respond"):
            return await ctx_or_inter.respond(*args, **kwargs)
        if hasattr(ctx_or_inter, "response"):
            if not ctx_or_inter.response.is_done():
                return await ctx_or_inter.response.send_message(*args, **kwargs)
            return await ctx_or_inter.followup.send(*args, **kwargs)
    except Exception:
        return None


async def ephemeral_flash(
    interaction: discord.Interaction,
    content: str,
    *,
    seconds: float = FLASH_SECONDS,
) -> None:
    """Brief ephemeral toast — auto-deletes so the picker stays uncluttered."""
    try:
        msg = await interaction.followup.send(content, ephemeral=True, wait=True)
    except Exception as exc:
        logger.warning("Ephemeral flash send failed: %s", exc)
        return
    try:
        await asyncio.sleep(seconds)
        await msg.delete()
    except Exception:
        pass


async def ephemeral_flash_reply(
    ctx: discord.ApplicationContext,
    content: str | None = None,
    *,
    embed: discord.Embed | None = None,
    seconds: float = ADMIN_FLASH_SECONDS,
) -> None:
    """Admin slash success/info toast — auto-deletes after 1.5s."""
    try:
        kwargs: dict[str, Any] = {"ephemeral": True, "wait": True}
        if embed is not None:
            msg = await ctx.respond(embed=embed, **kwargs)
        else:
            msg = await ctx.respond(content or "", **kwargs)
    except Exception as exc:
        logger.warning("Ephemeral flash reply failed: %s", exc)
        return
    try:
        await asyncio.sleep(seconds)
        await msg.delete()
    except Exception:
        pass


async def ephemeral_flash_followup(
    ctx: discord.ApplicationContext,
    content: str,
    *,
    seconds: float = ADMIN_FLASH_SECONDS,
) -> None:
    """Flash toast after ctx.defer() — auto-deletes after 1.5s."""
    try:
        msg = await ctx.followup.send(content, ephemeral=True, wait=True)
    except Exception as exc:
        logger.warning("Ephemeral flash followup failed: %s", exc)
        return
    try:
        await asyncio.sleep(seconds)
        await msg.delete()
    except Exception:
        pass


def _sorted_catalog(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(entries, key=lambda e: str(e.get("label") or "").lower())


class GameRolesPanelView(View):
    """Persistent hub panel — interactions handled in on_interaction."""

    def __init__(self, guild_id: int, page: int = 0, total_pages: int = 1):
        super().__init__(timeout=None)
        self.add_item(Button(
            label="Manage My Games",
            style=ButtonStyle.primary,
            emoji="🎮",
            custom_id=f"{MANAGE_PREFIX}{guild_id}",
            row=0,
        ))
        self.add_item(Button(
            label="Prev",
            style=ButtonStyle.secondary,
            emoji="◀",
            custom_id=PANEL_PREV_ID,
            disabled=page <= 0,
            row=1,
        ))
        self.add_item(Button(
            label="Next",
            style=ButtonStyle.secondary,
            emoji="▶",
            custom_id=PANEL_NEXT_ID,
            disabled=total_pages <= 1 or page >= total_pages - 1,
            row=1,
        ))


class GameRolesManageView(View):
    """Ephemeral paginated toggle buttons — one page, no dropdown rows."""

    def __init__(
        self,
        cog: "GameRolesCog",
        member: discord.Member,
        catalog: list[dict[str, Any]],
        page: int,
    ):
        super().__init__(timeout=300)
        self.cog = cog
        self.member = member
        self.catalog = catalog
        self.page = page
        self.total_pages = max(1, (len(catalog) + PAGE_SIZE - 1) // PAGE_SIZE)

        member_ids = {r.id for r in member.roles}
        start = page * PAGE_SIZE
        page_items = catalog[start:start + PAGE_SIZE]

        for idx, entry in enumerate(page_items):
            rid = int(entry["id"])
            label = str(entry.get("label") or "Role")[:80]
            has_role = rid in member_ids
            self.add_item(Button(
                label=label,
                style=ButtonStyle.success if has_role else ButtonStyle.secondary,
                custom_id=f"{TOGGLE_PREFIX}{rid}",
                row=idx // 5,
            ))

        nav_row = min(4, max(0, (len(page_items) + 4) // 5))
        self.add_item(Button(
            label="Prev",
            style=ButtonStyle.secondary,
            emoji="◀",
            custom_id=f"{EPH_PREV_PREFIX}{page}",
            disabled=page <= 0,
            row=nav_row,
        ))
        self.add_item(Button(
            label="Next",
            style=ButtonStyle.secondary,
            emoji="▶",
            custom_id=f"{EPH_NEXT_PREFIX}{page}",
            disabled=self.total_pages <= 1 or page >= self.total_pages - 1,
            row=nav_row,
        ))


class GameRolesCog(commands.Cog):
    def __init__(self, bot: discord.Bot):
        self.bot = bot
        self._store: dict[str, Any] = {}
        self._load_store()

    def _load_store(self) -> dict[str, Any]:
        source = STORE_PATH if STORE_PATH.exists() else _REPO_STORE
        data: dict[str, Any] = {}
        if source.exists():
            try:
                loaded = json.loads(source.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    data = loaded
            except Exception as exc:
                logger.error("Failed to load game_roles.json: %s", exc)

        if (
            STORE_PATH.exists()
            and _REPO_STORE.exists()
            and STORE_PATH.resolve() != _REPO_STORE.resolve()
        ):
            try:
                repo = json.loads(_REPO_STORE.read_text(encoding="utf-8"))
                if isinstance(repo, dict):
                    changed = False
                    for gid, repo_cfg in repo.items():
                        if not isinstance(repo_cfg, dict):
                            continue
                        repo_roles = repo_cfg.get("roles") or []
                        if not repo_roles:
                            continue
                        entry = data.setdefault(gid, dict(DEFAULT_GUILD_CFG))
                        if not entry.get("roles"):
                            entry["roles"] = repo_roles
                            changed = True
                        for key in ("channel_id", "panel_message_id"):
                            if not entry.get(key) and repo_cfg.get(key):
                                entry[key] = repo_cfg[key]
                                changed = True
                    if changed:
                        _atomic_write(STORE_PATH, data)
                        logger.info("Backfilled empty game_roles catalog from repo template.")
            except Exception as exc:
                logger.warning("game_roles repo backfill skipped: %s", exc)

        self._store = data
        return data

    def _save_store(self) -> None:
        _atomic_write(STORE_PATH, self._store)

    def _guild_store(self, guild_id: int) -> dict[str, Any]:
        key = str(guild_id)
        if key not in self._store:
            cfg = dict(DEFAULT_GUILD_CFG)
            cid = ch_id(guild_id, "game_roles")
            if cid:
                cfg["channel_id"] = str(cid)
            self._store[key] = cfg
        return self._store[key]

    def _catalog(self, guild_id: int, guild: discord.Guild | None = None) -> list[dict[str, Any]]:
        cfg = self._guild_store(guild_id)
        raw = cfg.get("roles") or []
        cleaned: list[dict[str, Any]] = []
        changed = False
        for entry in raw:
            if not entry.get("id"):
                changed = True
                continue
            if guild is not None:
                role = guild.get_role(int(entry["id"]))
                if role is None or _is_denylisted(role, guild_id):
                    changed = True
                    continue
            cleaned.append(entry)
        if changed and guild is not None:
            cfg["roles"] = cleaned
            self._save_store()
        return _sorted_catalog(cleaned)

    def _catalog_ids(self, guild_id: int, guild: discord.Guild | None = None) -> set[int]:
        return {int(e["id"]) for e in self._catalog(guild_id, guild) if e.get("id")}

    def _page_count(self, guild_id: int, guild: discord.Guild | None = None) -> int:
        catalog = self._catalog(guild_id, guild)
        if not catalog:
            return 1
        return max(1, (len(catalog) + PAGE_SIZE - 1) // PAGE_SIZE)

    def _clamp_page(self, guild_id: int, page: int, guild: discord.Guild | None = None) -> int:
        return max(0, min(page, self._page_count(guild_id, guild) - 1))

    def _current_panel_page(self, guild_id: int) -> int:
        try:
            return int(self._guild_store(guild_id).get("panel_page", 0))
        except (TypeError, ValueError):
            return 0

    def _set_panel_page(self, guild_id: int, page: int, guild: discord.Guild | None = None) -> None:
        self._guild_store(guild_id)["panel_page"] = self._clamp_page(guild_id, page, guild)

    def _page_slice(
        self,
        guild_id: int,
        page: int,
        guild: discord.Guild | None = None,
    ) -> list[dict[str, Any]]:
        catalog = self._catalog(guild_id, guild)
        start = page * PAGE_SIZE
        return catalog[start:start + PAGE_SIZE]

    def _role_entry(self, role: discord.Role) -> dict[str, Any]:
        return {
            "id": str(role.id),
            "label": role.name,
            "emoji": None,
            "sort": role.position,
        }

    def _column_block(self, items: list[dict[str, Any]]) -> str:
        if not items:
            return "—"
        return "\n".join(f"• **{e.get('label', '?')}**" for e in items)

    def build_panel_embed(
        self,
        guild_id: int,
        page: int | None = None,
        guild: discord.Guild | None = None,
    ) -> discord.Embed:
        if page is None:
            page = self._current_panel_page(guild_id)
        page = self._clamp_page(guild_id, page, guild)

        catalog = self._catalog(guild_id, guild)
        total = len(catalog)
        total_pages = self._page_count(guild_id, guild)
        page_items = self._page_slice(guild_id, page, guild)
        left_col = page_items[0::2]
        right_col = page_items[1::2]

        embed = discord.Embed(
            title=PANEL_TITLE,
            description=PANEL_BLURB,
            color=THEME_PRIMARY,
        )

        if total == 0:
            embed.add_field(
                name="📋 Games",
                value="*Nothing here yet — check back soon.*",
                inline=False,
            )
        else:
            embed.add_field(
                name="Games",
                value=self._column_block(left_col),
                inline=True,
            )
            embed.add_field(
                name="\u200b",
                value=self._column_block(right_col) if right_col else "—",
                inline=True,
            )
            embed.add_field(
                name="\u200b",
                value=f"**Page {page + 1}** of **{total_pages}** · **{total}** game{'s' if total != 1 else ''}",
                inline=False,
            )

        embed.set_footer(text="Sorted A → Z · Manage My Games to set yours")
        return embed

    def _can_manage_role(
        self,
        member: discord.Member,
        role: discord.Role,
        bot_member: discord.Member,
    ) -> bool:
        if role >= bot_member.top_role:
            return False
        if role.position >= member.top_role.position:
            return False
        return True

    def _build_seed_entries(self, guild: discord.Guild) -> list[dict[str, Any]]:
        minion = resolve_role(guild, "minion")
        if minion is None:
            return []
        entries: list[dict[str, Any]] = []
        for role in sorted(guild.roles, key=lambda r: -r.position):
            if role.position >= minion.position:
                continue
            if _is_denylisted(role, guild.id):
                continue
            entries.append(self._role_entry(role))
        return _sorted_catalog(entries)

    async def _ensure_catalog(self, guild: discord.Guild) -> list[dict[str, Any]]:
        catalog = self._catalog(guild.id, guild)
        if catalog:
            return catalog

        entries = self._build_seed_entries(guild)
        if not entries:
            return []

        cfg = self._guild_store(guild.id)
        cfg["roles"] = entries
        self._save_store()
        logger.info("Auto-seeded %d game roles for guild %s", len(entries), guild.id)

        try:
            await self._deploy_panel(guild)
        except Exception as exc:
            logger.warning("Panel refresh after auto-seed failed: %s", exc)

        return self._catalog(guild.id, guild)

    def _build_manage_embed(self, member: discord.Member, page: int) -> discord.Embed:
        hub_ids = self._catalog_ids(member.guild.id, member.guild)
        owned = [r.name for r in member.roles if r.id in hub_ids]
        owned_text = ", ".join(sorted(owned, key=str.lower)[:12]) if owned else "*None yet*"
        if len(owned) > 12:
            owned_text += f" … +{len(owned) - 12} more"

        total_pages = self._page_count(member.guild.id, member.guild)
        embed = discord.Embed(
            title="🎮 Manage My Games",
            description=(
                "Tap a game to **toggle** it on or off.\n"
                "Green = you have it · Grey = you don't."
            ),
            color=THEME_PRIMARY,
        )
        embed.add_field(name="Your games", value=owned_text, inline=False)
        embed.set_footer(
            text=f"Page {page + 1} of {total_pages} · ShadowSyn"
        )
        return embed

    async def _open_manage(self, interaction: discord.Interaction, page: int = 0):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await safe_reply(interaction, "❌ Use this inside the server.", ephemeral=True)

        member = interaction.user
        guild = interaction.guild
        if not is_registered_guild(guild.id):
            return

        catalog = await self._ensure_catalog(guild)
        if not catalog:
            return await safe_reply(
                interaction,
                "⚠️ No game roles are available right now. Check back later.",
                ephemeral=True,
            )

        page = self._clamp_page(guild.id, page, guild)
        view = GameRolesManageView(self, member, catalog, page)
        embed = self._build_manage_embed(member, page)
        await safe_reply(interaction, embed=embed, view=view, ephemeral=True)

    async def _refresh_manage(
        self,
        interaction: discord.Interaction,
        page: int,
    ):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return
        member = interaction.user
        catalog = self._catalog(member.guild.id, member.guild)
        page = self._clamp_page(member.guild.id, page, member.guild)
        view = GameRolesManageView(self, member, catalog, page)
        embed = self._build_manage_embed(member, page)
        try:
            await interaction.edit_original_response(embed=embed, view=view)
        except Exception as exc:
            logger.warning("Failed to refresh manage view: %s", exc)

    def _eph_page_from_interaction(self, interaction: discord.Interaction) -> int:
        msg = interaction.message
        if not msg:
            return 0
        for row in msg.components:
            for comp in row.children:
                cid = getattr(comp, "custom_id", "") or ""
                if cid.startswith(EPH_PREV_PREFIX) or cid.startswith(EPH_NEXT_PREFIX):
                    prefix = EPH_PREV_PREFIX if cid.startswith(EPH_PREV_PREFIX) else EPH_NEXT_PREFIX
                    try:
                        return int(cid[len(prefix):])
                    except ValueError:
                        pass
        return 0

    async def _toggle_role(self, interaction: discord.Interaction, role_id: int):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await safe_reply(interaction, "❌ Use this inside the server.", ephemeral=True)

        member = interaction.user
        guild = interaction.guild
        if not is_registered_guild(guild.id):
            return

        hub_ids = self._catalog_ids(guild.id, guild)
        if role_id not in hub_ids:
            return await safe_reply(interaction, "❌ That game isn't in the hub.", ephemeral=True)

        role = guild.get_role(role_id)
        if role is None:
            return await safe_reply(interaction, "❌ Role no longer exists.", ephemeral=True)

        bot_member = guild.me
        if bot_member is None:
            return await safe_reply(interaction, "❌ Bot unavailable.", ephemeral=True)

        if not self._can_manage_role(member, role, bot_member):
            return await safe_reply(
                interaction,
                f"❌ You can't assign **{role.name}** (above your tier).",
                ephemeral=True,
            )

        page = self._eph_page_from_interaction(interaction)

        had_role = role in member.roles
        try:
            if had_role:
                await member.remove_roles(role, reason="ShadowSyn Game Roles toggle")
                action = f"Removed **{role.name}**"
            else:
                await member.add_roles(role, reason="ShadowSyn Game Roles toggle")
                action = f"Added **{role.name}**"
        except discord.Forbidden:
            return await safe_reply(
                interaction,
                "❌ I can't assign that role right now. Tell an admin.",
                ephemeral=True,
            )
        except Exception as exc:
            logger.error("Toggle failed for %s: %s", member.id, exc)
            return await safe_reply(interaction, "⚠️ Something broke. Try again.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        member = guild.get_member(member.id) or member
        await self._refresh_manage(interaction, page)
        await ephemeral_flash(interaction, f"✅ {action}")

    async def _refresh_panel_message(
        self,
        channel: discord.abc.Messageable | None = None,
        *,
        page: int | None = None,
        guild_id: int | None = None,
    ):
        if channel is not None and getattr(channel, "guild", None):
            guild_id = channel.guild.id
        gid = guild_id or SHADOW_MAIN_GUILD_ID
        guild = self.bot.get_guild(gid)

        if page is not None:
            self._set_panel_page(gid, page, guild)
        else:
            self._set_panel_page(gid, self._current_panel_page(gid), guild)

        cfg = self._guild_store(gid)
        panel_id = cfg.get("panel_message_id")
        if not panel_id:
            return

        if channel is None:
            channel = await resolve_channel(self.bot, gid, "game_roles")
        if channel is None:
            return

        page_num = self._current_panel_page(gid)
        total_pages = self._page_count(gid, guild)
        view = GameRolesPanelView(gid, page_num, total_pages)
        embed = self.build_panel_embed(gid, page_num, guild)

        try:
            msg = await channel.fetch_message(int(panel_id))
            await msg.edit(embed=embed, view=view)
            self.bot.add_view(view)
            self._save_store()
        except discord.NotFound:
            logger.warning("Game roles panel %s not found for guild %s.", panel_id, gid)
        except Exception as exc:
            logger.error("Failed to refresh game roles panel: %s", exc)

    @commands.Cog.listener()
    async def on_ready(self):
        try:
            self._load_store()
            for gid in REGISTERED_GUILD_IDS:
                guild = self.bot.get_guild(gid)
                if guild is not None and not self._catalog(gid, guild):
                    entries = self._build_seed_entries(guild)
                    if entries:
                        cfg = self._guild_store(gid)
                        cfg["roles"] = entries
                        self._save_store()
                        logger.info(
                            "Startup seed: %d game roles for guild %s",
                            len(entries),
                            gid,
                        )
                        try:
                            await self._deploy_panel(guild)
                        except Exception as exc:
                            logger.warning("Panel refresh after startup seed: %s", exc)

                total = self._page_count(gid, guild)
                self.bot.add_view(GameRolesPanelView(gid, 0, total))
            logger.info("Game roles persistent views restored.")
        except Exception as exc:
            logger.error("Failed to restore game roles views on_ready: %s", exc)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        custom_id = interaction.data.get("custom_id", "") if interaction.data else ""

        if custom_id.startswith(MANAGE_PREFIX):
            await self._open_manage(interaction, page=0)
            return

        if custom_id == PANEL_PREV_ID:
            if not interaction.guild:
                return
            gid = interaction.guild.id
            new_page = self._clamp_page(gid, self._current_panel_page(gid) - 1, interaction.guild)
            try:
                await interaction.response.defer()
                await self._refresh_panel_message(interaction.channel, page=new_page, guild_id=gid)
            except Exception as exc:
                logger.error("Game roles panel prev failed: %s", exc)
            return

        if custom_id == PANEL_NEXT_ID:
            if not interaction.guild:
                return
            gid = interaction.guild.id
            new_page = self._clamp_page(gid, self._current_panel_page(gid) + 1, interaction.guild)
            try:
                await interaction.response.defer()
                await self._refresh_panel_message(interaction.channel, page=new_page, guild_id=gid)
            except Exception as exc:
                logger.error("Game roles panel next failed: %s", exc)
            return

        if custom_id.startswith(TOGGLE_PREFIX):
            try:
                role_id = int(custom_id[len(TOGGLE_PREFIX):])
            except ValueError:
                return
            await self._toggle_role(interaction, role_id)
            return

        if custom_id.startswith(EPH_PREV_PREFIX):
            try:
                page = int(custom_id[len(EPH_PREV_PREFIX):])
            except ValueError:
                page = 0
            try:
                await interaction.response.defer(ephemeral=True)
                await self._refresh_manage(interaction, page - 1)
            except Exception as exc:
                logger.error("Game roles eph prev failed: %s", exc)
            return

        if custom_id.startswith(EPH_NEXT_PREFIX):
            try:
                page = int(custom_id[len(EPH_NEXT_PREFIX):])
            except ValueError:
                page = 0
            try:
                await interaction.response.defer(ephemeral=True)
                await self._refresh_manage(interaction, page + 1)
            except Exception as exc:
                logger.error("Game roles eph next failed: %s", exc)

    def _validate_hub_role(self, guild: discord.Guild, role: discord.Role) -> str | None:
        if _is_denylisted(role, guild.id):
            return f"**{role.name}** is staff/special and cannot be in the hub."
        minion = resolve_role(guild, "minion")
        if minion and role.position >= minion.position:
            return f"**{role.name}** is at or above Minion tier."
        return None

    async def _find_existing_panel(self, channel: discord.abc.Messageable) -> discord.Message | None:
        if hasattr(channel, "pins"):
            try:
                pins = await channel.pins()
                for msg in pins:
                    if not msg.author or msg.author.id != self.bot.user.id:
                        continue
                    for row in msg.components:
                        for comp in row.children:
                            cid = getattr(comp, "custom_id", "") or ""
                            if cid.startswith(MANAGE_PREFIX):
                                return msg
            except Exception as exc:
                logger.warning("Could not scan pins for game roles panel: %s", exc)
        try:
            if hasattr(channel, "history"):
                async for msg in channel.history(limit=25):
                    if not msg.author or msg.author.id != self.bot.user.id:
                        continue
                    for row in msg.components:
                        for comp in row.children:
                            cid = getattr(comp, "custom_id", "") or ""
                            if cid.startswith(MANAGE_PREFIX):
                                return msg
        except Exception as exc:
            logger.warning("Could not scan history for game roles panel: %s", exc)
        return None

    async def _deploy_panel(self, guild: discord.Guild) -> discord.Message:
        channel = await resolve_channel(self.bot, guild.id, "game_roles")
        if channel is None:
            raise RuntimeError("game_roles channel not found in registry.")

        cfg = self._guild_store(guild.id)
        cfg["channel_id"] = str(channel.id)
        page = self._clamp_page(guild.id, self._current_panel_page(guild.id), guild)
        total_pages = self._page_count(guild.id, guild)
        embed = self.build_panel_embed(guild.id, page, guild)
        view = GameRolesPanelView(guild.id, page, total_pages)

        existing_id = cfg.get("panel_message_id")
        msg: discord.Message | None = None
        if existing_id:
            try:
                msg = await channel.fetch_message(int(existing_id))
            except Exception:
                msg = None
        if msg is None:
            msg = await self._find_existing_panel(channel)

        if msg is not None:
            await msg.edit(embed=embed, view=view)
        else:
            msg = await channel.send(embed=embed, view=view)
            try:
                await msg.pin()
            except Exception as exc:
                logger.warning("Could not pin game roles panel: %s", exc)

        cfg["panel_message_id"] = str(msg.id)
        cfg["panel_page"] = page
        self._save_store()
        self.bot.add_view(view)
        return msg

    @discord.slash_command(
        name="game_roles_deploy",
        description="Post or refresh the game roles panel in the game_roles channel.",
        guild_ids=REGISTERED_GUILD_IDS,
        default_member_permissions=discord.Permissions(administrator=True),
    )
    async def game_roles_deploy(self, ctx: discord.ApplicationContext):
        if not ctx.guild or not is_registered_guild(ctx.guild.id):
            return await safe_reply(ctx, "⛔ Unregistered guild.", ephemeral=True)
        if not has_admin_shadow(ctx.author, ctx.guild.id):
            return await safe_reply(ctx, "🚫 Admin clearance required.", ephemeral=True)

        await ctx.defer(ephemeral=True)
        try:
            msg = await self._deploy_panel(ctx.guild)
            ch = await resolve_channel(self.bot, ctx.guild.id, "game_roles")
            mention = ch.mention if ch else "game_roles channel"
            await ephemeral_flash_followup(
                ctx,
                f"✅ Panel live in {mention} · message `{msg.id}`",
            )
        except Exception as exc:
            logger.error("game_roles_deploy failed: %s", exc)
            await ctx.followup.send(f"❌ Deploy failed: {exc}", ephemeral=True)

    @discord.slash_command(
        name="game_roles_seed",
        description="Bootstrap hub catalog from gaming roles below Minion.",
        guild_ids=REGISTERED_GUILD_IDS,
        default_member_permissions=discord.Permissions(administrator=True),
    )
    async def game_roles_seed(self, ctx: discord.ApplicationContext):
        if not ctx.guild or not is_registered_guild(ctx.guild.id):
            return await safe_reply(ctx, "⛔ Unregistered guild.", ephemeral=True)
        if not has_admin_shadow(ctx.author, ctx.guild.id):
            return await safe_reply(ctx, "🚫 Admin clearance required.", ephemeral=True)

        minion = resolve_role(ctx.guild, "minion")
        if minion is None:
            return await safe_reply(ctx, "❌ Minion role not found.", ephemeral=True)

        await ctx.defer(ephemeral=True)
        try:
            cfg = self._guild_store(ctx.guild.id)
            entries = self._build_seed_entries(ctx.guild)
            cfg["roles"] = entries
            await asyncio.to_thread(self._save_store)

            try:
                await self._deploy_panel(ctx.guild)
            except Exception as exc:
                logger.warning("Panel refresh after seed failed: %s", exc)

            await ephemeral_flash_followup(
                ctx,
                f"✅ Seeded **{len(entries)}** gaming roles into the hub catalog.",
            )
        except Exception as exc:
            logger.exception("game_roles_seed failed")
            await ctx.followup.send(f"❌ Seed failed: {exc}", ephemeral=True)

    @discord.slash_command(
        name="game_roles_add",
        description="Add a role to the game roles hub catalog.",
        guild_ids=REGISTERED_GUILD_IDS,
        default_member_permissions=discord.Permissions(administrator=True),
    )
    async def game_roles_add(
        self,
        ctx: discord.ApplicationContext,
        role: Option(discord.Role, "Gaming role to add"),
    ):
        if not ctx.guild or not is_registered_guild(ctx.guild.id):
            return await safe_reply(ctx, "⛔ Unregistered guild.", ephemeral=True)
        if not has_admin_shadow(ctx.author, ctx.guild.id):
            return await safe_reply(ctx, "🚫 Admin clearance required.", ephemeral=True)

        err = self._validate_hub_role(ctx.guild, role)
        if err:
            return await safe_reply(ctx, f"❌ {err}", ephemeral=True)

        await ctx.defer(ephemeral=True)
        try:
            cfg = self._guild_store(ctx.guild.id)
            roles: list[dict[str, Any]] = list(cfg.get("roles") or [])
            if any(
                str(e.get("id")) == str(role.id)
                for e in roles
                if isinstance(e, dict)
            ):
                await ephemeral_flash_followup(
                    ctx,
                    f"ℹ️ **{role.name}** is already in the catalog.",
                )
                return

            roles.append(self._role_entry(role))
            cfg["roles"] = _sorted_catalog(roles)
            await asyncio.to_thread(self._save_store)

            try:
                await self._refresh_panel_message(guild_id=ctx.guild.id)
            except Exception as exc:
                logger.warning("Panel refresh after add failed: %s", exc)

            await ephemeral_flash_followup(
                ctx,
                f"✅ Added **{role.name}** to the hub ({len(roles)} total).",
            )
        except Exception as exc:
            logger.exception("game_roles_add failed")
            await ctx.followup.send(f"❌ Add failed: {exc}", ephemeral=True)

    @discord.slash_command(
        name="game_roles_remove",
        description="Remove a role from the hub catalog (does not strip from members).",
        guild_ids=REGISTERED_GUILD_IDS,
        default_member_permissions=discord.Permissions(administrator=True),
    )
    async def game_roles_remove(
        self,
        ctx: discord.ApplicationContext,
        role: Option(discord.Role, "Role to remove from catalog"),
    ):
        if not ctx.guild or not is_registered_guild(ctx.guild.id):
            return await safe_reply(ctx, "⛔ Unregistered guild.", ephemeral=True)
        if not has_admin_shadow(ctx.author, ctx.guild.id):
            return await safe_reply(ctx, "🚫 Admin clearance required.", ephemeral=True)

        await ctx.defer(ephemeral=True)
        try:
            cfg = self._guild_store(ctx.guild.id)
            roles: list[dict[str, Any]] = list(cfg.get("roles") or [])
            new_roles = [
                e for e in roles
                if isinstance(e, dict) and str(e.get("id")) != str(role.id)
            ]
            if len(new_roles) == len(roles):
                await ephemeral_flash_followup(
                    ctx,
                    f"ℹ️ **{role.name}** is not in the catalog.",
                )
                return

            cfg["roles"] = new_roles
            await asyncio.to_thread(self._save_store)

            try:
                await self._refresh_panel_message(guild_id=ctx.guild.id)
            except Exception as exc:
                logger.warning("Panel refresh after remove failed: %s", exc)

            await ephemeral_flash_followup(
                ctx,
                f"✅ Removed **{role.name}** from the hub ({len(new_roles)} remaining).",
            )
        except Exception as exc:
            logger.exception("game_roles_remove failed")
            await ctx.followup.send(f"❌ Remove failed: {exc}", ephemeral=True)

    @discord.slash_command(
        name="game_roles_list",
        description="List all roles in the game roles hub catalog.",
        guild_ids=REGISTERED_GUILD_IDS,
        default_member_permissions=discord.Permissions(administrator=True),
    )
    async def game_roles_list(self, ctx: discord.ApplicationContext):
        if not ctx.guild or not is_registered_guild(ctx.guild.id):
            return await safe_reply(ctx, "⛔ Unregistered guild.", ephemeral=True)
        if not has_admin_shadow(ctx.author, ctx.guild.id):
            return await safe_reply(ctx, "🚫 Admin clearance required.", ephemeral=True)

        catalog = self._catalog(ctx.guild.id, ctx.guild)
        if not catalog:
            return await safe_reply(ctx, "ℹ️ Catalog is empty. Run `/game_roles_seed`.", ephemeral=True)

        lines = [f"• {e.get('label', '?')} (`{e.get('id')}`)" for e in catalog]
        body = "\n".join(lines[:40])
        if len(lines) > 40:
            body += f"\n… and {len(lines) - 40} more"
        embed = discord.Embed(
            title=f"🎮 Hub catalog ({len(catalog)})",
            description=body,
            color=THEME_PRIMARY,
        )
        await safe_reply(ctx, embed=embed, ephemeral=True)


def setup(bot: discord.Bot):
    bot.add_cog(GameRolesCog(bot))
