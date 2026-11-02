# cogs/server_tag.py — Member role follows this guild's server tag.
# Grant on equip, remove on an observed unequip. Never sweep people who
# simply are not wearing the tag.

import asyncio
import json
import logging
import os
from pathlib import Path

import discord
from discord.ext import commands

from cogs.guild_registry import (
    PERSIST_ROOT,
    REGISTERED_GUILD_IDS,
    has_admin_shadow,
    is_registered_guild,
    resolve_role,
)

logger = logging.getLogger("ShadowSyn.ServerTag")

_persist_env = os.getenv("PERSIST_PATH", "").strip()
if _persist_env:
    STORE_PATH = Path(_persist_env).resolve() / "server_tag.json"
else:
    STORE_PATH = PERSIST_ROOT / "server_tag.json"

SYNC_EDIT_INTERVAL = 1.1
CHUNK_TIMEOUT = 90.0
GRANT_REASON = "ShadowSyn server tag equipped"
REVOKE_REASON = "ShadowSyn server tag removed"


def payload_has_primary_guild(user: dict) -> bool:
    """Missing key is not 'tag off'. Explicit null is."""
    return isinstance(user, dict) and "primary_guild" in user


def wears_guild(primary_guild: dict | None, guild_id: int) -> bool:
    """True only when the tag is enabled for this exact guild."""
    if not isinstance(primary_guild, dict):
        return False
    if primary_guild.get("identity_enabled") is not True:
        return False
    raw_id = primary_guild.get("identity_guild_id")
    if raw_id is None:
        return False
    try:
        return int(raw_id) == int(guild_id)
    except (TypeError, ValueError):
        return False


def wears_target(primary_guild, guild_id: int) -> bool:
    """Dict from the gateway, or a py-cord PrimaryGuild. None is not wearing."""
    if primary_guild is None:
        return False
    if isinstance(primary_guild, dict):
        return wears_guild(primary_guild, guild_id)
    if getattr(primary_guild, "identity_enabled", None) is not True:
        return False
    raw_id = getattr(primary_guild, "identity_guild_id", None)
    if raw_id is None:
        return False
    try:
        return int(raw_id) == int(guild_id)
    except (TypeError, ValueError):
        return False


def decide_transition(was_holder: bool, wearing: bool) -> str:
    """grant, revoke, or noop. Not-a-holder who is not wearing is always noop."""
    if wearing and not was_holder:
        return "grant"
    if was_holder and not wearing:
        return "revoke"
    return "noop"


def _atomic_write(file_path: Path, data: dict) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = file_path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    temp_path.replace(file_path)


def _can_manage(guild: discord.Guild, role: discord.Role) -> bool:
    me = guild.me
    if me is None or role.is_default() or role.managed:
        return False
    return role.position < me.top_role.position


class ServerTagCog(commands.Cog):
    """Gives and takes the registry Member role as the server tag changes."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._holders: dict[str, set[str]] = {}
        self._io_lock = asyncio.Lock()
        self._user_locks: dict[int, asyncio.Lock] = {}
        self._load()

    def _user_lock(self, user_id: int) -> asyncio.Lock:
        lock = self._user_locks.get(user_id)
        if lock is None:
            lock = asyncio.Lock()
            self._user_locks[user_id] = lock
        return lock

    def _load(self) -> None:
        self._holders = {}
        if not STORE_PATH.exists():
            return
        try:
            raw = json.loads(STORE_PATH.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.error("Failed to load server tag holders: %s", exc)
            return
        guilds = raw.get("guilds") if isinstance(raw, dict) else None
        if not isinstance(guilds, dict):
            logger.error("server_tag.json has no guilds object. Starting empty.")
            return
        for gid, holders in guilds.items():
            if not isinstance(holders, list):
                continue
            self._holders[str(gid)] = {str(item) for item in holders}

    def _is_holder(self, guild_id: int, user_id: int) -> bool:
        return str(user_id) in self._holders.get(str(guild_id), set())

    async def _save(self) -> None:
        payload = {
            "guilds": {gid: sorted(uids) for gid, uids in self._holders.items()}
        }
        async with self._io_lock:
            try:
                _atomic_write(STORE_PATH, payload)
            except Exception as exc:
                logger.error("Failed to save server tag holders: %s", exc)

    async def _set_holder(self, guild_id: int, user_id: int, present: bool) -> None:
        bucket = self._holders.setdefault(str(guild_id), set())
        uid = str(user_id)
        if present:
            if uid in bucket:
                return
            bucket.add(uid)
        else:
            if uid not in bucket:
                return
            bucket.discard(uid)
        await self._save()

    async def _live_apply(self, member: discord.Member, wearing: bool) -> str:
        if member.bot:
            return "noop"
        action = decide_transition(self._is_holder(member.guild.id, member.id), wearing)
        if action == "noop":
            return "noop"
        role = resolve_role(member.guild, "member")
        if role is None or not _can_manage(member.guild, role):
            logger.error(
                "Cannot manage Member in guild %s for user %s.",
                member.guild.id,
                member.id,
            )
            return "error"
        try:
            if action == "grant":
                if role not in member.roles:
                    await member.add_roles(role, reason=GRANT_REASON)
                await self._set_holder(member.guild.id, member.id, True)
                logger.info(
                    "Granted Member to %s in guild %s.",
                    member.id,
                    member.guild.id,
                )
            else:
                if role in member.roles:
                    await member.remove_roles(role, reason=REVOKE_REASON)
                await self._set_holder(member.guild.id, member.id, False)
                logger.info(
                    "Removed Member from %s in guild %s.",
                    member.id,
                    member.guild.id,
                )
        except Exception as exc:
            logger.error(
                "Member role edit failed for %s in guild %s: %s",
                member.id,
                member.guild.id,
                exc,
            )
            return "error"
        return action

    async def _sync_grant(self, member: discord.Member) -> str:
        """Add-only. Records current wearers. Does not remove Member."""
        if member.bot:
            return "noop"
        role = resolve_role(member.guild, "member")
        if role is None or not _can_manage(member.guild, role):
            logger.error(
                "Cannot manage Member in guild %s during sync.",
                member.guild.id,
            )
            return "error"
        has_role = role in member.roles
        was = self._is_holder(member.guild.id, member.id)
        try:
            if not has_role:
                await member.add_roles(role, reason=GRANT_REASON)
                await self._set_holder(member.guild.id, member.id, True)
                logger.info(
                    "Sync granted Member to %s in guild %s.",
                    member.id,
                    member.guild.id,
                )
                return "grant"
            if not was:
                await self._set_holder(member.guild.id, member.id, True)
                logger.info(
                    "Sync recorded existing Member %s in guild %s.",
                    member.id,
                    member.guild.id,
                )
                return "recorded"
        except Exception as exc:
            logger.error(
                "Sync grant failed for %s in guild %s: %s",
                member.id,
                member.guild.id,
                exc,
            )
            return "error"
        return "noop"

    async def _member_for(
        self,
        guild: discord.Guild,
        user_id: int,
        *,
        fetch: bool,
    ) -> discord.Member | None:
        member = guild.get_member(user_id)
        if member is not None or not fetch:
            return member
        try:
            return await guild.fetch_member(user_id)
        except discord.NotFound:
            if self._is_holder(guild.id, user_id):
                await self._set_holder(guild.id, user_id, False)
                logger.info(
                    "Dropped tag holder %s — not in guild %s.",
                    user_id,
                    guild.id,
                )
            return None
        except Exception as exc:
            logger.error(
                "Failed to fetch member %s in guild %s: %s",
                user_id,
                guild.id,
                exc,
            )
            return None

    async def _reconcile_user(self, user_id: int, primary_guild, event_guild_id: int) -> None:
        for gid in REGISTERED_GUILD_IDS:
            guild = self.bot.get_guild(gid)
            if guild is None:
                continue
            fetch = gid == event_guild_id or self._is_holder(gid, user_id)
            member = await self._member_for(guild, user_id, fetch=fetch)
            if member is None:
                continue
            await self._live_apply(member, wears_target(primary_guild, gid))

    @commands.Cog.listener()
    async def on_raw_member_update(self, payload) -> None:
        guild_id = getattr(payload, "guild_id", None)
        if not is_registered_guild(guild_id):
            return
        data = getattr(payload, "data", None)
        user = data.get("user") if isinstance(data, dict) else None
        if not payload_has_primary_guild(user):
            return
        try:
            user_id = int(user.get("id") or payload.user_id)
        except (TypeError, ValueError, AttributeError):
            return
        async with self._user_lock(user_id):
            await self._reconcile_user(user_id, user.get("primary_guild"), int(guild_id))

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if member.bot or not is_registered_guild(member.guild.id):
            return
        primary_guild = getattr(member, "primary_guild", None)
        if primary_guild is None:
            return
        async with self._user_lock(member.id):
            await self._reconcile_user(member.id, primary_guild, member.guild.id)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        if not is_registered_guild(member.guild.id):
            return
        async with self._user_lock(member.id):
            if not self._is_holder(member.guild.id, member.id):
                return
            await self._set_holder(member.guild.id, member.id, False)
            logger.info(
                "Dropped tag holder %s after leave from guild %s.",
                member.id,
                member.guild.id,
            )

    async def _chunk_note(self, guild: discord.Guild) -> str | None:
        count = guild.member_count or 0
        if count and len(guild.members) >= int(count * 0.95):
            return None
        try:
            await asyncio.wait_for(guild.chunk(), timeout=CHUNK_TIMEOUT)
        except Exception as exc:
            logger.error("Member chunk failed for guild %s: %s", guild.id, exc)
        seen = len(guild.members)
        if count and seen < int(count * 0.95):
            return f"Member cache is short ({seen}/{count})."
        return None

    @discord.slash_command(
        name="tag_sync",
        description="Grant Member to people already wearing this server's tag. Does not remove.",
        guild_ids=REGISTERED_GUILD_IDS,
        default_member_permissions=discord.Permissions(administrator=True),
    )
    async def tag_sync(self, ctx: discord.ApplicationContext):
        if ctx.guild is None or not is_registered_guild(ctx.guild.id):
            await ctx.respond("This command is not available here.", ephemeral=True)
            return
        if not isinstance(ctx.author, discord.Member) or not has_admin_shadow(
            ctx.author, ctx.guild.id
        ):
            await ctx.respond("You need the SHADOW admin role.", ephemeral=True)
            return

        await ctx.defer(ephemeral=True)
        guild = ctx.guild
        note = await self._chunk_note(guild)

        parsed = 0
        wearers: list[discord.Member] = []
        for member in list(guild.members):
            if member.bot:
                continue
            primary_guild = getattr(member, "primary_guild", None)
            if primary_guild is None:
                continue
            parsed += 1
            if wears_target(primary_guild, guild.id):
                wearers.append(member)

        if parsed == 0:
            detail = "No parsed server tags in this guild. Nothing changed."
            if note:
                detail = f"{detail} {note}"
            await ctx.followup.send(detail, ephemeral=True)
            return

        granted = 0
        recorded = 0
        already = 0
        errors = 0
        for member in wearers:
            async with self._user_lock(member.id):
                result = await self._sync_grant(member)
            if result == "grant":
                granted += 1
                await asyncio.sleep(SYNC_EDIT_INTERVAL)
            elif result == "recorded":
                recorded += 1
            elif result == "error":
                errors += 1
            else:
                already += 1

        lines = [
            f"Parsed tags: **{parsed}**",
            f"Wearing this server: **{len(wearers)}**",
            f"Granted: **{granted}**",
            f"Recorded (already had Member): **{recorded}**",
            f"Already tracked: **{already}**",
        ]
        if errors:
            lines.append(f"Errors: **{errors}**")
        if note:
            lines.append(note)
        await ctx.followup.send("\n".join(lines), ephemeral=True)


def setup(bot: discord.Bot):
    bot.add_cog(ServerTagCog(bot))
