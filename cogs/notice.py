# cogs/notice.py — Elite notice system: game drops with a live squad counter
#
# /notice game  <steam_url>  → Steam-branded release poster + "I'm In" enlist button
# /notice event <title> <when> → wipe/beta/raid-night notice with Discord timestamps
# /notice psa   <text>       → slim branded one-liner
#
# The "I'm In" button grants the game role (auto-created + mirrored into the
# game-roles hub on both guilds) and live-edits a squad counter on the notice.

import asyncio
import json
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp
import discord
from discord import ButtonStyle, Option
from discord.ext import commands
from discord.ui import Button, Modal, TextInput, View

from cogs.game_roles import (
    _normalize_role_name,
    ephemeral_flash,
    ephemeral_flash_followup,
)
from cogs.guild_registry import (
    PERSIST_ROOT,
    REGISTERED_GUILD_IDS,
    SHADOW_BACKUP_GUILD_ID,
    SHADOW_MAIN_GUILD_ID,
    has_admin_shadow,
    is_registered_guild,
    resolve_channel,
)
from cogs.utils import safe_reply

logger = logging.getLogger("ShadowSyn.Notice")

THEME_PRIMARY = 0x2B0B35
ENLIST_PREFIX = "notice_enlist:"
STORE_PATH = PERSIST_ROOT / "notice_state.json"
MAX_NOTICES = 100
SQUAD_NAME_LIMIT = 20

STEAM_APPDETAILS_URL = "https://store.steampowered.com/api/appdetails"
STEAM_APP_RE = re.compile(r"store\.steampowered\.com/app/(\d+)")

# Joe's timezone — notices are written in AEST.
AEST = timezone(timedelta(hours=10))

GUILD_SCOPE_CHOICES = ["all", "main", "backup"]
PING_CHOICES = ["everyone", "here", "role", "none"]


# ==============================================================================
# PURE HELPERS (unit-testable, no Discord objects)
# ==============================================================================
def steam_appid(text: str) -> str | None:
    """Extract a Steam app id from a store URL or raw digits."""
    if not text:
        return None
    text = text.strip()
    match = STEAM_APP_RE.search(text)
    if match:
        return match.group(1)
    if text.isdigit():
        return text
    return None


def steam_store_url(appid: str) -> str:
    return f"https://store.steampowered.com/app/{appid}/"


def parse_steam_release_date(raw: str) -> datetime | None:
    """Steam gives locale strings like '21 Aug, 2026' — parse the common shapes."""
    if not raw:
        return None
    cleaned = raw.strip()
    for fmt in ("%d %b, %Y", "%b %d, %Y", "%d %B, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(cleaned, fmt).replace(hour=10, tzinfo=AEST)
        except ValueError:
            continue
    return None


def parse_when(raw: str) -> datetime | None:
    """Parse an event time string (AEST). Accepts unix ts or common date formats."""
    if not raw:
        return None
    cleaned = raw.strip()
    if cleaned.isdigit() and len(cleaned) == 10:
        try:
            return datetime.fromtimestamp(int(cleaned), tz=AEST)
        except (ValueError, OSError, OverflowError):
            return None
    now = datetime.now(AEST)
    for fmt in ("%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M", "%d/%m %H:%M"):
        try:
            parsed = datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
        if parsed.year == 1900:
            parsed = parsed.replace(year=now.year)
        parsed = parsed.replace(tzinfo=AEST)
        if fmt == "%d/%m %H:%M" and parsed < now:
            parsed = parsed.replace(year=now.year + 1)
        return parsed
    return None


def squad_field(enlisted: dict[str, str]) -> dict[str, str]:
    """Build the live squad counter field from the shared enlist map."""
    count = len(enlisted)
    name = f"⚔️ Squad — {count} locked in"
    if count == 0:
        return {"name": name, "value": "*Be the first — hit **I'm In**.*"}
    names = list(enlisted.values())
    shown = names[:SQUAD_NAME_LIMIT]
    value = " · ".join(f"**{n}**" for n in shown)
    if count > SQUAD_NAME_LIMIT:
        value += f" · +{count - SQUAD_NAME_LIMIT} more"
    return {"name": name, "value": value[:1024]}


def toggle_enlisted(notice: dict[str, Any], user_id: int, display_name: str) -> bool:
    """Flip a member in/out of the shared enlist map. Returns True if now enlisted."""
    enlisted = notice.setdefault("enlisted", {})
    key = str(user_id)
    if key in enlisted:
        del enlisted[key]
        return False
    enlisted[key] = display_name
    return True


def build_game_embed(
    meta: dict[str, Any],
    hype: str,
    enlisted: dict[str, str],
) -> discord.Embed:
    """Cinematic Steam release poster with the live squad counter."""
    description_parts: list[str] = []
    if hype:
        description_parts.append(
            "\n".join(f"> {line}" for line in hype.splitlines() if line.strip())
        )
    short = (meta.get("short_description") or "").strip()
    if short:
        description_parts.append(f"*{short[:280]}*")

    embed = discord.Embed(
        title=meta.get("name") or "Game Drop",
        url=meta.get("url"),
        description="\n\n".join(p for p in description_parts if p) or None,
        color=THEME_PRIMARY,
    )

    release_dt = parse_steam_release_date(meta.get("release_date") or "")
    if release_dt is not None:
        ts = int(release_dt.timestamp())
        release_value = f"<t:{ts}:D> · <t:{ts}:R>"
    else:
        release_value = meta.get("release_date") or "TBA"
    embed.add_field(name="Release", value=release_value, inline=True)
    embed.add_field(name="Price", value=meta.get("price") or "TBA", inline=True)
    genres = meta.get("genres") or []
    if genres:
        embed.add_field(name="Genres", value=", ".join(genres[:4]), inline=True)

    squad = squad_field(enlisted)
    embed.add_field(name=squad["name"], value=squad["value"], inline=False)

    if meta.get("header_image"):
        embed.set_image(url=meta["header_image"])
    embed.set_footer(text="ShadowSyn · I'm In = game role + squad ping")
    return embed


def build_event_embed(
    title: str,
    when_dt: datetime | None,
    when_raw: str,
    details: str | None,
    link: str | None,
) -> discord.Embed:
    lines: list[str] = []
    if details:
        lines.append(details.strip())
    if when_dt is not None:
        ts = int(when_dt.timestamp())
        lines.append(f"**When:** <t:{ts}:F> · <t:{ts}:R>")
    else:
        lines.append(f"**When:** {when_raw}")
    embed = discord.Embed(
        title=f"📅 {title}",
        url=link or None,
        description="\n\n".join(lines),
        color=THEME_PRIMARY,
    )
    embed.set_footer(text="ShadowSyn · Event Notice")
    return embed


def build_psa_embed(text: str) -> discord.Embed:
    embed = discord.Embed(
        description=f"📣 {text.strip()}",
        color=THEME_PRIMARY,
    )
    embed.set_footer(text="ShadowSyn Notice")
    return embed


def find_squad_field_index(embed: discord.Embed) -> int | None:
    for idx, field in enumerate(embed.fields):
        if (field.name or "").startswith("⚔️ Squad"):
            return idx
    return None


def _atomic_write(path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def _ping_content(ping: str, role_mention: str | None) -> str | None:
    if ping == "everyone":
        return "@everyone"
    if ping == "here":
        return "@here"
    if ping == "role":
        return role_mention
    return None


def _scope_guild_ids(scope: str) -> list[int]:
    if scope == "main":
        return [SHADOW_MAIN_GUILD_ID]
    if scope == "backup":
        return [SHADOW_BACKUP_GUILD_ID]
    return list(REGISTERED_GUILD_IDS)


# ==============================================================================
# UI COMPONENTS
# ==============================================================================
class NoticeActionView(View):
    """Persistent buttons on a notice — enlist toggle + Steam link."""

    def __init__(self, notice_key: str, steam_url: str | None = None):
        super().__init__(timeout=None)
        self.add_item(Button(
            label="I'm In",
            emoji="⚔️",
            style=ButtonStyle.success,
            custom_id=f"{ENLIST_PREFIX}{notice_key}",
            row=0,
        ))
        if steam_url:
            self.add_item(Button(
                label="Steam",
                style=ButtonStyle.link,
                url=steam_url,
                row=0,
            ))


class GameHypeModal(Modal):
    """Captures Joe's hype line before the notice ships — keeps his voice on it."""

    def __init__(
        self,
        cog: "NoticeCog",
        appid: str,
        ping: str,
        scope: str,
        role: discord.Role | None = None,
    ):
        super().__init__(title="Game Drop — add your hype line")
        self.cog = cog
        self.appid = appid
        self.ping = ping
        self.scope = scope
        self.role = role
        self.add_item(TextInput(
            label="Hype line (optional)",
            style=discord.InputTextStyle.long,
            placeholder="Yes we are gonna play. No soft cocks ty ❤️",
            required=False,
            max_length=600,
        ))

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        hype = (self.children[0].value or "").strip()
        await self.cog.post_game_notice(
            interaction, self.appid, hype, self.ping, self.scope, role=self.role
        )


# ==============================================================================
# CORE COG
# ==============================================================================
class NoticeCog(commands.Cog):
    def __init__(self, bot: discord.Bot):
        self.bot = bot
        self.session: aiohttp.ClientSession | None = None
        self._store: dict[str, Any] = {"notices": {}}
        self._locks: dict[str, asyncio.Lock] = {}
        self._load_store()

    # ── persistence ──
    def _load_store(self) -> None:
        if STORE_PATH.exists():
            try:
                loaded = json.loads(STORE_PATH.read_text(encoding="utf-8"))
                if isinstance(loaded, dict) and isinstance(loaded.get("notices"), dict):
                    self._store = loaded
            except Exception as exc:
                logger.error("Failed to load notice_state.json: %s", exc)

    def _save_store(self) -> None:
        try:
            _atomic_write(STORE_PATH, self._store)
        except Exception as exc:
            logger.error("Failed to save notice_state.json: %s", exc)

    def _prune_store(self) -> None:
        notices = self._store.get("notices", {})
        if len(notices) <= MAX_NOTICES:
            return
        ordered = sorted(
            notices.items(),
            key=lambda kv: str(kv[1].get("created_at") or ""),
        )
        for key, _ in ordered[: len(notices) - MAX_NOTICES]:
            notices.pop(key, None)

    def _lock_for(self, key: str) -> asyncio.Lock:
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    def cog_unload(self):
        if self.session and not self.session.closed:
            asyncio.create_task(self.session.close())

    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    # ── Steam metadata ──
    async def fetch_steam_meta(self, appid: str) -> dict[str, Any] | None:
        session = await self._get_session()
        try:
            async with session.get(
                f"{STEAM_APPDETAILS_URL}?appids={appid}&cc=au", timeout=15
            ) as resp:
                if resp.status != 200:
                    logger.warning("Steam appdetails %s returned %s", appid, resp.status)
                    return None
                payload = await resp.json()
        except Exception as exc:
            logger.error("Steam appdetails fetch failed for %s: %s", appid, exc)
            return None

        entry = (payload or {}).get(str(appid)) or {}
        if not entry.get("success"):
            return None
        data = entry.get("data") or {}

        price = "TBA"
        overview = data.get("price_overview") or {}
        if overview.get("final_formatted"):
            price = overview["final_formatted"]
        elif data.get("is_free"):
            price = "Free"

        release = data.get("release_date") or {}
        return {
            "appid": appid,
            "name": data.get("name"),
            "url": steam_store_url(appid),
            "header_image": data.get("header_image"),
            "short_description": data.get("short_description"),
            "genres": [g.get("description", "") for g in data.get("genres", []) if g],
            "release_date": release.get("date") or ("Coming soon" if release.get("coming_soon") else None),
            "price": price,
        }

    # ── game role plumbing (reuses the game-roles hub) ──
    async def _ensure_game_role(
        self,
        guild: discord.Guild,
        name: str,
        colour: discord.Colour | None = None,
    ) -> discord.Role | None:
        target = _normalize_role_name(name)
        roles = list(guild.roles)
        if len(roles) <= 1:
            try:
                roles = list(await guild.fetch_roles())
            except Exception:
                pass
        role = discord.utils.find(
            lambda r: _normalize_role_name(r.name) == target, roles
        )
        if role is not None:
            return role
        try:
            return await guild.create_role(
                name=name,
                colour=colour or discord.Colour(THEME_PRIMARY),
                mentionable=True,
                reason="ShadowSyn notice: game drop squad role",
            )
        except Exception as exc:
            logger.error("Could not create game role %s in guild %s: %s", name, guild.id, exc)
            return None

    async def _ensure_roles_all_guilds(
        self,
        name: str,
        preset_role: discord.Role | None = None,
    ) -> dict[int, discord.Role]:
        """Create/find the game role on every registered guild and hub it.

        When Joe hands us an existing role (preset_role), that exact role is
        used on its home guild and its name/colour drive the sister-guild copy.
        """
        game_cog = self.bot.get_cog("GameRolesCog")
        colour = preset_role.colour if preset_role is not None else None
        out: dict[int, discord.Role] = {}
        for gid in REGISTERED_GUILD_IDS:
            guild = self.bot.get_guild(gid)
            if guild is None:
                logger.warning("Guild %s unavailable for game role %s", gid, name)
                continue
            if preset_role is not None and preset_role.guild.id == gid:
                role = preset_role
            else:
                role = await self._ensure_game_role(guild, name, colour=colour)
            if role is None:
                continue
            out[gid] = role
            if game_cog is not None:
                try:
                    if game_cog._upsert_catalog_role(guild, role):
                        await game_cog._deploy_panel(guild)
                except Exception as exc:
                    logger.warning("Game-roles hub upsert failed for guild %s: %s", gid, exc)
        return out

    def _resolve_role_map(self, name: str) -> dict[int, discord.Role]:
        """Find an existing role by name on each guild — never creates or hubs it."""
        target = _normalize_role_name(name)
        out: dict[int, discord.Role] = {}
        for gid in REGISTERED_GUILD_IDS:
            guild = self.bot.get_guild(gid)
            if guild is None:
                continue
            role = discord.utils.find(
                lambda r: _normalize_role_name(r.name) == target, guild.roles
            )
            if role is not None:
                out[gid] = role
        return out

    # ── posting ──
    async def _dispatch_notice(
        self,
        *,
        embed: discord.Embed,
        ping: str,
        scope: str,
        view_factory=None,
        role_map: dict[int, discord.Role] | None = None,
    ) -> list[dict[str, str]]:
        """Send the notice to the notice channel of each in-scope guild."""
        posted: list[dict[str, str]] = []
        allowed = discord.AllowedMentions(everyone=True, roles=True, users=False)
        for gid in _scope_guild_ids(scope):
            channel = await resolve_channel(self.bot, gid, "notice")
            if channel is None:
                logger.warning("Notice channel missing in registry for guild %s", gid)
                continue
            role = (role_map or {}).get(gid)
            content = _ping_content(ping, role.mention if role else None)
            view = view_factory() if view_factory else None
            try:
                msg = await channel.send(
                    content=content,
                    embed=embed,
                    view=view,
                    allowed_mentions=allowed,
                )
            except Exception as exc:
                logger.error("Failed to post notice in guild %s: %s", gid, exc)
                continue
            posted.append({
                "guild_id": str(gid),
                "channel_id": str(channel.id),
                "message_id": str(msg.id),
            })
        return posted

    async def post_game_notice(
        self,
        interaction: discord.Interaction,
        appid: str,
        hype: str,
        ping: str,
        scope: str,
        role: discord.Role | None = None,
    ) -> None:
        meta = await self.fetch_steam_meta(appid)
        if meta is None or not meta.get("name"):
            return await interaction.followup.send(
                "❌ Steam wouldn't give up that game's details. Check the link and retry.",
                ephemeral=True,
            )

        # Joe's picked role wins; otherwise auto-match/create by the Steam title.
        role_name = role.name if role is not None else meta["name"]
        role_map = await self._ensure_roles_all_guilds(role_name, preset_role=role)
        if not role_map:
            return await interaction.followup.send(
                "❌ Could not create the game role on either guild. Check my role permissions.",
                ephemeral=True,
            )

        key = secrets.token_hex(4)
        enlisted: dict[str, str] = {}
        embed = build_game_embed(meta, hype, enlisted)

        posted = await self._dispatch_notice(
            embed=embed,
            ping=ping,
            scope=scope,
            view_factory=lambda: NoticeActionView(key, meta["url"]),
            role_map=role_map,
        )
        if not posted:
            return await interaction.followup.send(
                "❌ Couldn't post to any notice channel — is the `notice` registry key seeded?",
                ephemeral=True,
            )

        self._store.setdefault("notices", {})[key] = {
            "kind": "game",
            "label": meta["name"],
            "role_name": role_name,
            "appid": appid,
            "steam_url": meta["url"],
            "enlisted": enlisted,
            "roles": {str(gid): str(role.id) for gid, role in role_map.items()},
            "messages": posted,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._prune_store()
        self._save_store()

        await ephemeral_flash(
            interaction,
            f"✅ **{meta['name']}** drop is live on {len(posted)} guild(s).",
            seconds=1.5,
        )

    # ── squad counter ──
    async def _refresh_squad_embeds(self, notice: dict[str, Any]) -> None:
        squad = squad_field(notice.get("enlisted") or {})
        for record in notice.get("messages") or []:
            try:
                channel = self.bot.get_channel(int(record["channel_id"]))
                if channel is None:
                    channel = await self.bot.fetch_channel(int(record["channel_id"]))
                msg = await channel.fetch_message(int(record["message_id"]))
                if not msg.embeds:
                    continue
                embed = msg.embeds[0]
                idx = find_squad_field_index(embed)
                if idx is None:
                    embed.add_field(name=squad["name"], value=squad["value"], inline=False)
                else:
                    embed.set_field_at(idx, name=squad["name"], value=squad["value"], inline=False)
                await msg.edit(embed=embed)
            except Exception as exc:
                logger.warning(
                    "Squad counter refresh failed for message %s: %s",
                    record.get("message_id"),
                    exc,
                )

    async def _toggle_enlist(self, interaction: discord.Interaction, key: str) -> None:
        guild = interaction.guild
        member = interaction.user
        if guild is None or not isinstance(member, discord.Member):
            return await safe_reply(interaction, "❌ Use this inside the server.", ephemeral=True)
        if not is_registered_guild(guild.id):
            return

        notice = (self._store.get("notices") or {}).get(key)
        if notice is None:
            return await safe_reply(
                interaction, "❌ This notice has expired.", ephemeral=True
            )

        # ACK first — role REST + cross-guild edits exceed the 3s window.
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        async with self._lock_for(key):
            role_id_raw = (notice.get("roles") or {}).get(str(guild.id))
            role = guild.get_role(int(role_id_raw)) if role_id_raw else None
            if role is None:
                role = await self._ensure_game_role(
                    guild, notice.get("role_name") or notice.get("label") or ""
                )
                if role is not None:
                    notice.setdefault("roles", {})[str(guild.id)] = str(role.id)
            if role is None:
                await interaction.followup.send(
                    "❌ The squad role is missing and I couldn't recreate it. Tell an admin.",
                    ephemeral=True,
                )
                return

            enlisted_now = toggle_enlisted(notice, member.id, member.display_name)
            try:
                if enlisted_now:
                    await member.add_roles(role, reason="ShadowSyn notice: I'm In")
                else:
                    await member.remove_roles(role, reason="ShadowSyn notice: I'm out")
            except discord.Forbidden:
                # Roll back the map — role change failed.
                toggle_enlisted(notice, member.id, member.display_name)
                await interaction.followup.send(
                    "❌ I can't manage that role right now. Tell an admin.",
                    ephemeral=True,
                )
                return
            except Exception as exc:
                toggle_enlisted(notice, member.id, member.display_name)
                logger.error("Enlist role toggle failed for %s: %s", member.id, exc)
                await interaction.followup.send(
                    "⚠️ Something broke. Try again.", ephemeral=True
                )
                return

            self._save_store()
            await self._refresh_squad_embeds(notice)

        label = notice.get("label") or "the squad"
        if enlisted_now:
            await ephemeral_flash(
                interaction, f"⚔️ Locked in — **{label}** role granted."
            )
        else:
            await ephemeral_flash(
                interaction, f"👋 You're out — **{label}** role removed."
            )

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        custom_id = interaction.data.get("custom_id", "") if interaction.data else ""
        if custom_id.startswith(ENLIST_PREFIX):
            await self._toggle_enlist(interaction, custom_id[len(ENLIST_PREFIX):])

    # ==========================================================================
    # SLASH COMMANDS
    # ==========================================================================
    notice_group = discord.SlashCommandGroup(
        "notice",
        "ShadowSyn community notices — game drops, events, PSAs",
        guild_ids=REGISTERED_GUILD_IDS,
        default_member_permissions=discord.Permissions(administrator=True),
    )

    def _gate(self, ctx: discord.ApplicationContext) -> str | None:
        if not ctx.guild or not is_registered_guild(ctx.guild.id):
            return "⛔ Unregistered guild."
        if not has_admin_shadow(ctx.author, ctx.guild.id):
            return "🚫 Admin clearance required."
        return None

    @notice_group.command(
        name="game",
        description="Post a Steam-branded game drop with an I'm In squad button.",
    )
    async def notice_game(
        self,
        ctx: discord.ApplicationContext,
        steam_url: Option(str, "Steam store link (or app id)"),
        role: Option(
            discord.Role,
            "Your game role for the I'm In button (otherwise auto-matched by game name)",
            required=False,
            default=None,
        ),
        ping: Option(str, "Who to ping", choices=PING_CHOICES, default="everyone"),
        guild: Option(str, "Which guilds get it", choices=GUILD_SCOPE_CHOICES, default="all"),
    ):
        err = self._gate(ctx)
        if err:
            return await safe_reply(ctx, err, ephemeral=True)
        appid = steam_appid(steam_url)
        if appid is None:
            return await safe_reply(
                ctx,
                "❌ That doesn't look like a Steam store link. "
                "Expected `https://store.steampowered.com/app/<id>/...`.",
                ephemeral=True,
            )
        if role is not None and (role.is_default() or role.managed):
            return await safe_reply(
                ctx, "❌ That role can't be used as a squad role.", ephemeral=True
            )
        await ctx.send_modal(GameHypeModal(self, appid, ping, guild, role=role))

    @notice_group.command(
        name="event",
        description="Post a wipe/beta/raid-night notice with live countdown timestamps.",
    )
    async def notice_event(
        self,
        ctx: discord.ApplicationContext,
        title: Option(str, "Event title, e.g. RUST FORCE WIPE"),
        when: Option(str, "AEST time: YYYY-MM-DD HH:MM, DD/MM HH:MM, or unix ts"),
        details: Option(str, "Extra lines for the notice", required=False, default=None),
        link: Option(str, "Optional URL (event, store page, video)", required=False, default=None),
        ping: Option(str, "Who to ping", choices=PING_CHOICES, default="everyone"),
        role: Option(discord.Role, "Role to ping when ping=role", required=False, default=None),
        guild: Option(str, "Which guilds get it", choices=GUILD_SCOPE_CHOICES, default="all"),
    ):
        err = self._gate(ctx)
        if err:
            return await safe_reply(ctx, err, ephemeral=True)
        if ping == "role" and role is None:
            return await safe_reply(
                ctx, "❌ Pick a `role` when ping is set to role.", ephemeral=True
            )

        await ctx.defer(ephemeral=True)
        when_dt = parse_when(when)
        embed = build_event_embed(title, when_dt, when, details, link)

        role_map: dict[int, discord.Role] = {}
        if role is not None:
            role_map = self._resolve_role_map(role.name)

        posted = await self._dispatch_notice(
            embed=embed, ping=ping, scope=guild, role_map=role_map
        )
        if not posted:
            return await ctx.followup.send(
                "❌ Couldn't post to any notice channel.", ephemeral=True
            )
        note = "" if when_dt else " (time shown as raw text — unparsed)"
        await ephemeral_flash_followup(
            ctx, f"✅ Event notice live on {len(posted)} guild(s).{note}"
        )

    @notice_group.command(
        name="psa",
        description="Post a short branded community notice.",
    )
    async def notice_psa(
        self,
        ctx: discord.ApplicationContext,
        text: Option(str, "The notice text"),
        ping: Option(str, "Who to ping", choices=PING_CHOICES, default="none"),
        guild: Option(str, "Which guilds get it", choices=GUILD_SCOPE_CHOICES, default="all"),
    ):
        err = self._gate(ctx)
        if err:
            return await safe_reply(ctx, err, ephemeral=True)

        await ctx.defer(ephemeral=True)
        embed = build_psa_embed(text)
        posted = await self._dispatch_notice(embed=embed, ping=ping, scope=guild)
        if not posted:
            return await ctx.followup.send(
                "❌ Couldn't post to any notice channel.", ephemeral=True
            )
        await ephemeral_flash_followup(
            ctx, f"✅ PSA live on {len(posted)} guild(s)."
        )


def setup(bot: discord.Bot):
    bot.add_cog(NoticeCog(bot))
