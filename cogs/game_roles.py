# cogs/game_roles.py — persistent gaming role self-serve hub

import json
import logging
import os
from pathlib import Path
from typing import Any

import discord
from discord import ButtonStyle, Option
from discord.ui import Button, Select, View
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
SELECT_CHUNK = 25
OPEN_PREFIX = "game_roles_open:"

_REPO_DATA = Path(__file__).resolve().parents[1] / "data"
_persist_env = os.getenv("PERSIST_PATH", "").strip()
if _persist_env:
    STORE_PATH = Path(_persist_env).resolve() / "game_roles.json"
else:
    STORE_PATH = PERSIST_ROOT / "game_roles.json"
_REPO_STORE = _REPO_DATA / "game_roles.json"

# Staff / special roles — never hub-selectable (matched case-insensitively)
DENYLIST_NAMES = frozenset({
    "sensational shadow",
    "shadow",
    "mover & shaker",
    "mover and shaker",
    "🔥shadow",
    "silhouette",
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
})

DEFAULT_GUILD_CFG: dict[str, Any] = {
    "channel_id": str(ch_id(SHADOW_MAIN_GUILD_ID, "game_roles") or 1516222122211672084),
    "panel_message_id": None,
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


def _build_panel_embed(guild_id: int, role_count: int) -> discord.Embed:
    embed = discord.Embed(
        title="🎮 Game Roles",
        description=(
            "Pick every game you play — your Discord roles **sync instantly**.\n\n"
            "**How it works**\n"
            "1. Click **Choose Games** below\n"
            "2. Select all games you want (pre-filled with your current picks)\n"
            "3. Submit — added and removed automatically\n\n"
            "Staff roles (**Member**, **Silhouette**, **Shadow**, etc.) are assigned "
            "manually by admins and are not listed here."
        ),
        color=THEME_PRIMARY,
    )
    embed.set_footer(text=f"ShadowSyn • {role_count} game{'s' if role_count != 1 else ''} available")
    return embed


class GameRolesPanelView(View):
    """Persistent panel — open button handled in on_interaction."""

    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.add_item(Button(
            label="Choose Games",
            style=ButtonStyle.primary,
            emoji="🎮",
            custom_id=f"{OPEN_PREFIX}{guild_id}",
        ))


class GameRolesSyncSelect(Select):
    def __init__(
        self,
        cog: "GameRolesCog",
        member: discord.Member,
        catalog: list[dict[str, Any]],
        row: int,
    ):
        self.cog = cog
        self.member = member
        member_role_ids = {r.id for r in member.roles}
        options = []
        for entry in catalog:
            rid = int(entry["id"])
            label = str(entry.get("label") or "Role")[:100]
            opt = discord.SelectOption(
                label=label,
                value=str(rid),
                default=rid in member_role_ids,
            )
            emoji = entry.get("emoji")
            if emoji:
                try:
                    opt.emoji = emoji
                except Exception:
                    pass
            options.append(opt)
        super().__init__(
            placeholder=f"Games (row {row + 1}) — select all you play",
            min_values=0,
            max_values=len(options),
            options=options,
            row=row,
        )

    async def callback(self, interaction: discord.Interaction):
        view: GameRolesPickerView = self.view  # type: ignore[assignment]
        await view.cog._apply_sync(interaction, view)


class GameRolesPickerView(View):
    """Ephemeral multi-select picker — rebuilt per user on each open."""

    def __init__(
        self,
        cog: "GameRolesCog",
        member: discord.Member,
        catalog: list[dict[str, Any]],
    ):
        super().__init__(timeout=300)
        self.cog = cog
        self.member = member
        chunks = [
            catalog[i:i + SELECT_CHUNK]
            for i in range(0, len(catalog), SELECT_CHUNK)
        ]
        for row, chunk in enumerate(chunks[:5]):
            self.add_item(GameRolesSyncSelect(cog, member, chunk, row))

    def collect_desired_ids(self, hub_ids: set[int]) -> set[int]:
        """Union selections; untouched select rows keep the member's current hub roles."""
        desired: set[int] = set()
        member_role_ids = {r.id for r in self.member.roles}
        for child in self.children:
            if not isinstance(child, GameRolesSyncSelect):
                continue
            chunk_ids = {int(o.value) for o in child.options}
            if child.values:
                desired |= {int(v) for v in child.values}
            else:
                desired |= member_role_ids & chunk_ids
        return desired & hub_ids


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

    def _catalog(self, guild_id: int) -> list[dict[str, Any]]:
        cfg = self._guild_store(guild_id)
        roles = cfg.get("roles") or []
        return sorted(
            roles,
            key=lambda e: (-int(e.get("sort") or 0), str(e.get("label") or "").lower()),
        )

    def _catalog_ids(self, guild_id: int) -> set[int]:
        return {int(e["id"]) for e in self._catalog(guild_id) if e.get("id")}

    def _role_entry(self, role: discord.Role) -> dict[str, Any]:
        return {
            "id": str(role.id),
            "label": role.name,
            "emoji": None,
            "sort": role.position,
        }

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

    async def _apply_sync(self, interaction: discord.Interaction, view: GameRolesPickerView):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await safe_reply(interaction, "❌ Use this inside the server.", ephemeral=True)

        member = interaction.user
        guild = interaction.guild
        if not is_registered_guild(guild.id):
            return

        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        hub_ids = self._catalog_ids(guild.id)
        desired_ids = view.collect_desired_ids(hub_ids)
        current_ids = {r.id for r in member.roles} & hub_ids
        to_add_ids = desired_ids - current_ids
        to_remove_ids = current_ids - desired_ids

        bot_member = guild.me
        if bot_member is None:
            return await safe_reply(interaction, "❌ Bot member unavailable.", ephemeral=True)

        add_roles: list[discord.Role] = []
        remove_roles: list[discord.Role] = []
        skipped: list[str] = []

        for rid in to_add_ids:
            role = guild.get_role(rid)
            if role is None:
                continue
            if self._can_manage_role(member, role, bot_member):
                add_roles.append(role)
            else:
                skipped.append(f"+{role.name}")

        for rid in to_remove_ids:
            role = guild.get_role(rid)
            if role is None:
                continue
            if self._can_manage_role(member, role, bot_member):
                remove_roles.append(role)
            else:
                skipped.append(f"-{role.name}")

        try:
            if remove_roles:
                await member.remove_roles(
                    *remove_roles,
                    reason="ShadowSyn Game Roles sync",
                )
            if add_roles:
                await member.add_roles(
                    *add_roles,
                    reason="ShadowSyn Game Roles sync",
                )
        except discord.Forbidden:
            logger.error("Forbidden during game roles sync for %s", member.id)
            return await safe_reply(
                interaction,
                "❌ I can't assign those roles right now. Tell an admin.",
                ephemeral=True,
            )
        except Exception as exc:
            logger.error("Game roles sync failed for %s: %s", member.id, exc)
            return await safe_reply(interaction, "⚠️ Something broke. Try again.", ephemeral=True)

        lines: list[str] = []
        if add_roles:
            lines.append("**Added:** " + ", ".join(r.name for r in add_roles))
        if remove_roles:
            lines.append("**Removed:** " + ", ".join(r.name for r in remove_roles))
        if not add_roles and not remove_roles:
            lines.append("No changes — your games are already synced.")
        if skipped:
            lines.append("**Skipped** (above your tier): " + ", ".join(skipped))

        embed = discord.Embed(
            title="🎮 Roles synced",
            description="\n".join(lines),
            color=THEME_PRIMARY,
        )
        await safe_reply(interaction, embed=embed, ephemeral=True)

    async def _open_picker(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await safe_reply(interaction, "❌ Use this inside the server.", ephemeral=True)

        guild = interaction.guild
        member = interaction.user
        if not is_registered_guild(guild.id):
            return

        catalog = self._catalog(guild.id)
        if not catalog:
            return await safe_reply(
                interaction,
                "⚠️ Game catalog is empty. An admin needs to run `/game_roles_seed` first.",
                ephemeral=True,
            )

        picker = GameRolesPickerView(self, member, catalog)
        embed = discord.Embed(
            title="🎮 Choose your games",
            description=(
                "Select **every game you play**, then submit.\n"
                "Unselect a game to remove that role."
            ),
            color=THEME_PRIMARY,
        )
        await safe_reply(
            interaction,
            embed=embed,
            view=picker,
            ephemeral=True,
        )

    @commands.Cog.listener()
    async def on_ready(self):
        try:
            self._load_store()
            for gid_str, cfg in self._store.items():
                if cfg.get("panel_message_id"):
                    try:
                        self.bot.add_view(GameRolesPanelView(int(gid_str)))
                    except (TypeError, ValueError):
                        pass
            for gid in REGISTERED_GUILD_IDS:
                self.bot.add_view(GameRolesPanelView(gid))
            logger.info("Game roles persistent views restored.")
        except Exception as exc:
            logger.error("Failed to restore game roles views on_ready: %s", exc)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        custom_id = interaction.data.get("custom_id", "") if interaction.data else ""
        if not custom_id.startswith(OPEN_PREFIX):
            return
        await self._open_picker(interaction)

    def _validate_hub_role(self, guild: discord.Guild, role: discord.Role) -> str | None:
        if _is_denylisted(role, guild.id):
            return f"**{role.name}** is staff/special and cannot be in the hub."
        minion = resolve_role(guild, "minion")
        if minion and role.position >= minion.position:
            return f"**{role.name}** is at or above Minion tier."
        return None

    async def _find_existing_panel(self, channel: discord.abc.Messageable) -> discord.Message | None:
        """Reuse pinned panel if store has no message id yet."""
        fetch_channel = channel
        if hasattr(channel, "pins"):
            try:
                pins = await channel.pins()
                for msg in pins:
                    if not msg.author or msg.author.id != self.bot.user.id:
                        continue
                    for row in msg.components:
                        for comp in row.children:
                            cid = getattr(comp, "custom_id", "") or ""
                            if cid.startswith(OPEN_PREFIX):
                                return msg
            except Exception as exc:
                logger.warning("Could not scan pins for game roles panel: %s", exc)
        try:
            if hasattr(fetch_channel, "history"):
                async for msg in fetch_channel.history(limit=25):
                    if not msg.author or msg.author.id != self.bot.user.id:
                        continue
                    for row in msg.components:
                        for comp in row.children:
                            cid = getattr(comp, "custom_id", "") or ""
                            if cid.startswith(OPEN_PREFIX):
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
        catalog = self._catalog(guild.id)
        embed = _build_panel_embed(guild.id, len(catalog))
        view = GameRolesPanelView(guild.id)

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
        self._save_store()
        self.bot.add_view(GameRolesPanelView(guild.id))
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

        await safe_reply(ctx, "🛠️ Deploying game roles panel...", ephemeral=True)
        try:
            msg = await self._deploy_panel(ctx.guild)
            ch = await resolve_channel(self.bot, ctx.guild.id, "game_roles")
            mention = ch.mention if ch else "game_roles channel"
            await safe_reply(
                ctx,
                f"✅ Panel live in {mention} · message `{msg.id}`",
                ephemeral=True,
            )
        except Exception as exc:
            logger.error("game_roles_deploy failed: %s", exc)
            await safe_reply(ctx, f"❌ Deploy failed: {exc}", ephemeral=True)

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

        cfg = self._guild_store(ctx.guild.id)
        entries: list[dict[str, Any]] = []
        for role in sorted(ctx.guild.roles, key=lambda r: -r.position):
            if role.position >= minion.position:
                continue
            if _is_denylisted(role, ctx.guild.id):
                continue
            entries.append(self._role_entry(role))

        cfg["roles"] = entries
        self._save_store()

        if cfg.get("panel_message_id"):
            try:
                await self._deploy_panel(ctx.guild)
            except Exception as exc:
                logger.warning("Panel refresh after seed failed: %s", exc)

        await safe_reply(
            ctx,
            f"✅ Seeded **{len(entries)}** gaming roles into the hub catalog.",
            ephemeral=True,
        )

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

        cfg = self._guild_store(ctx.guild.id)
        roles: list[dict[str, Any]] = list(cfg.get("roles") or [])
        if any(int(e["id"]) == role.id for e in roles):
            return await safe_reply(ctx, f"ℹ️ **{role.name}** is already in the catalog.", ephemeral=True)

        roles.append(self._role_entry(role))
        cfg["roles"] = roles
        self._save_store()
        await safe_reply(
            ctx,
            f"✅ Added **{role.name}** to the hub ({len(roles)} total).",
            ephemeral=True,
        )

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

        cfg = self._guild_store(ctx.guild.id)
        roles: list[dict[str, Any]] = list(cfg.get("roles") or [])
        new_roles = [e for e in roles if int(e["id"]) != role.id]
        if len(new_roles) == len(roles):
            return await safe_reply(ctx, f"ℹ️ **{role.name}** is not in the catalog.", ephemeral=True)

        cfg["roles"] = new_roles
        self._save_store()
        await safe_reply(
            ctx,
            f"✅ Removed **{role.name}** from the hub ({len(new_roles)} remaining).",
            ephemeral=True,
        )

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

        catalog = self._catalog(ctx.guild.id)
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
