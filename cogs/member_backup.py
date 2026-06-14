# cogs/member_backup.py
"""Member roster backup and disaster re-invite for Minion + Member role holders."""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import discord
from discord.ext import commands, tasks

from cogs.guild_registry import (
    REGISTERED_GUILD_IDS,
    SHADOW_BACKUP_GUILD_ID,
    SHADOW_MAIN_GUILD_ID,
    role_id,
)

logger = logging.getLogger("ShadowSyn.MemberBackup")

THEME_PRIMARY = 0x2B0B35
OWNER_ID = 482463400929263627
SYNC_GUILD_ID = SHADOW_MAIN_GUILD_ID

PERSIST_ROOT = Path(os.getenv("PERSIST_PATH", "/data")).resolve()
try:
    PERSIST_ROOT.mkdir(parents=True, exist_ok=True)
except Exception:
    PERSIST_ROOT = Path(".").resolve()

ROSTER_STORE = PERSIST_ROOT / "member_roster_backup.json"
SCHEMA_VERSION = 1
DM_PROBE_DELAY = 1.2

_DB_DEFAULTS = {
    "schema_version": SCHEMA_VERSION,
    "source_guild_id": str(SYNC_GUILD_ID),
    "last_full_sync": None,
    "members": {},
}


def _atomic_write(file_path: Path, data: dict) -> None:
    try:
        tmp_path = file_path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp_path.replace(file_path)
    except Exception as exc:
        logger.error("Persistence error [%s]: %s", file_path.name, exc)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_display_label(username: str, global_name: str | None, server_nick: str | None) -> str:
    username = username or "unknown"
    if server_nick:
        return f"{server_nick} (@{username})"
    if global_name:
        return f"{global_name} (@{username})"
    return f"@{username}"


def _admin_line(entry: dict) -> str:
    return f"{entry.get('display_label', '?')} · {entry.get('user_id', '?')}"


def _target_role_labels(member: discord.Member) -> list[str]:
    role_ids = {role.id for role in member.roles}
    labels: list[str] = []
    minion_rid = role_id(SYNC_GUILD_ID, "minion")
    member_rid = role_id(SYNC_GUILD_ID, "member")
    if minion_rid and minion_rid in role_ids:
        labels.append("minion")
    if member_rid and member_rid in role_ids:
        labels.append("member")
    return labels


def _member_identity(member: discord.Member) -> dict:
    username = member.name or "unknown"
    global_name = member.global_name
    server_nick = member.nick
    user_id = str(member.id)
    return {
        "user_id": user_id,
        "username": username,
        "global_name": global_name,
        "server_nick": server_nick,
        "display_label": _build_display_label(username, global_name, server_nick),
    }


class MemberBackupCog(commands.Cog):
    def __init__(self, bot: discord.Bot):
        self.bot = bot
        self.db = {k: (dict(v) if isinstance(v, dict) else v) for k, v in _DB_DEFAULTS.items()}
        self._load_data()

    def cog_load(self):
        if not self.daily_reconcile.is_running():
            self.daily_reconcile.start()

    def cog_unload(self):
        self.daily_reconcile.cancel()

    def _load_data(self) -> None:
        if not ROSTER_STORE.exists():
            return
        try:
            loaded = json.loads(ROSTER_STORE.read_text(encoding="utf-8"))
            for key in _DB_DEFAULTS:
                if key in loaded:
                    self.db[key] = loaded[key]
            if not isinstance(self.db.get("members"), dict):
                self.db["members"] = {}
        except Exception as exc:
            logger.error("Failed to load member roster — starting fresh: %s", exc)

    def _save(self) -> None:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "source_guild_id": str(self.db.get("source_guild_id") or SYNC_GUILD_ID),
            "last_full_sync": self.db.get("last_full_sync"),
            "members": self.db.get("members") or {},
        }
        _atomic_write(ROSTER_STORE, payload)

    def _is_owner(self, user: discord.User | discord.Member) -> bool:
        return user.id == OWNER_ID

    async def _require_owner(self, ctx: discord.ApplicationContext) -> bool:
        if not self._is_owner(ctx.author):
            await ctx.respond("Owner only.", ephemeral=True)
            return False
        return True

    def _get_entry(self, user_id: int | str) -> dict | None:
        members = self.db.setdefault("members", {})
        entry = members.get(str(user_id))
        return entry if isinstance(entry, dict) else None

    def _upsert_member(
        self,
        member: discord.Member,
        *,
        still_in_guild: bool = True,
        preserve_dm_on_refresh: bool = True,
    ) -> bool:
        if member.bot:
            return False

        roles = _target_role_labels(member)
        user_id = str(member.id)
        members = self.db.setdefault("members", {})
        now = _utc_now()
        existing = members.get(user_id) if isinstance(members.get(user_id), dict) else {}
        identity = _member_identity(member)

        if not roles:
            if user_id in members and still_in_guild:
                members[user_id] = {
                    **existing,
                    **identity,
                    "roles": [],
                    "still_in_guild": True,
                    "invite_eligible": False,
                    "last_updated": now,
                }
                return True
            return False

        dm_status = existing.get("dm_status", "unknown")
        invite_eligible = existing.get("invite_eligible", True)
        if preserve_dm_on_refresh and dm_status == "closed":
            invite_eligible = False

        members[user_id] = {
            **identity,
            "roles": roles,
            "still_in_guild": still_in_guild,
            "invite_eligible": bool(invite_eligible),
            "dm_status": dm_status,
            "dm_last_checked": existing.get("dm_last_checked"),
            "dm_last_error": existing.get("dm_last_error"),
            "first_recorded": existing.get("first_recorded") or now,
            "last_updated": now,
        }
        return True

    def _mark_left_guild(self, member: discord.Member) -> None:
        user_id = str(member.id)
        entry = self._get_entry(user_id)
        if not entry:
            return
        entry["still_in_guild"] = False
        entry["last_updated"] = _utc_now()
        identity = _member_identity(member)
        entry.update(identity)
        self._save()

    def _remove_entry(self, user_id: str) -> None:
        members = self.db.setdefault("members", {})
        members.pop(str(user_id), None)

    def _stats(self) -> dict:
        members = self.db.get("members") or {}
        stats = {
            "total_with_roles": 0,
            "minion_only": 0,
            "member_only": 0,
            "both_roles": 0,
            "invite_eligible": 0,
            "dm_closed": 0,
            "still_in_guild": 0,
            "left_guild": 0,
        }
        for entry in members.values():
            if not isinstance(entry, dict):
                continue
            roles = entry.get("roles") or []
            if not roles:
                continue
            stats["total_with_roles"] += 1
            has_minion = "minion" in roles
            has_member = "member" in roles
            if has_minion and has_member:
                stats["both_roles"] += 1
            elif has_minion:
                stats["minion_only"] += 1
            elif has_member:
                stats["member_only"] += 1
            if entry.get("still_in_guild", True):
                stats["still_in_guild"] += 1
            else:
                stats["left_guild"] += 1
            if entry.get("invite_eligible", True) and entry.get("dm_status") != "closed":
                stats["invite_eligible"] += 1
            if entry.get("dm_status") == "closed":
                stats["dm_closed"] += 1
        return stats

    async def _full_reconcile(self, guild: discord.Guild) -> dict:
        removed_invalid = 0
        updated = 0

        try:
            await guild.chunk(cache=True)
        except Exception as exc:
            logger.warning("Guild chunk failed during reconcile: %s", exc)

        seen_with_roles: set[str] = set()
        all_member_ids = {str(member.id) for member in guild.members if not member.bot}
        for member in guild.members:
            if member.bot:
                continue
            if self._upsert_member(member, still_in_guild=True):
                seen_with_roles.add(str(member.id))
                updated += 1

        members = self.db.setdefault("members", {})
        for user_id, entry in list(members.items()):
            if not isinstance(entry, dict):
                self._remove_entry(user_id)
                continue
            if entry.get("still_in_guild", True) and user_id not in all_member_ids:
                entry["still_in_guild"] = False
                entry["last_updated"] = _utc_now()

            if not entry.get("still_in_guild", True):
                try:
                    user = await self.bot.fetch_user(int(user_id))
                    if user.bot:
                        self._remove_entry(user_id)
                        removed_invalid += 1
                except discord.NotFound:
                    self._remove_entry(user_id)
                    removed_invalid += 1
                except Exception as exc:
                    logger.warning("Could not validate user %s: %s", user_id, exc)

        self.db["source_guild_id"] = str(guild.id)
        self.db["last_full_sync"] = _utc_now()
        self._save()
        stats = self._stats()
        stats["updated"] = updated
        stats["removed_invalid"] = removed_invalid
        return stats

    async def _apply_dm_result(self, user_id: str, success: bool, error: Exception | None = None) -> None:
        entry = self._get_entry(user_id)
        if not entry:
            return
        entry["dm_last_checked"] = _utc_now()
        if success:
            entry["dm_status"] = "reachable"
            entry["invite_eligible"] = True
            entry["dm_last_error"] = None
        else:
            code = getattr(error, "code", None)
            if isinstance(error, discord.NotFound) or code == 10013:
                self._remove_entry(user_id)
                return
            if code == 50007:
                entry["dm_status"] = "closed"
                entry["invite_eligible"] = False
                entry["dm_last_error"] = "Cannot send messages to this user"
            else:
                entry["dm_last_error"] = str(error) if error else "unknown_error"
        entry["last_updated"] = _utc_now()
        self._save()

    async def _send_probe_dm(self, user: discord.User, *, invite_url: str | None = None) -> tuple[bool, Exception | None]:
        embed = discord.Embed(
            title="ShadowSyn Community",
            color=THEME_PRIMARY,
        )
        if invite_url:
            embed.description = (
                "ShadowSyn is back. Use this invite to rejoin the community:\n"
                f"{invite_url}"
            )
        else:
            embed.description = "ShadowSyn roster check — ignore. No action needed."

        try:
            await user.send(embed=embed)
            return True, None
        except discord.Forbidden as exc:
            return False, exc
        except discord.NotFound as exc:
            return False, exc
        except Exception as exc:
            return False, exc

    def _iter_invite_targets(self, test_user_id: int | None = None) -> list[dict]:
        members = self.db.get("members") or {}
        targets: list[dict] = []
        for entry in members.values():
            if not isinstance(entry, dict):
                continue
            if not entry.get("roles"):
                continue
            if test_user_id is not None:
                if str(entry.get("user_id")) == str(test_user_id):
                    targets.append(entry)
                continue
            if not entry.get("invite_eligible", True):
                continue
            if entry.get("dm_status") == "closed":
                continue
            targets.append(entry)
        return targets

    @tasks.loop(hours=24)
    async def daily_reconcile(self):
        await self.bot.wait_until_ready()
        guild = self.bot.get_guild(SYNC_GUILD_ID)
        if guild is None:
            return
        try:
            stats = await self._full_reconcile(guild)
            logger.info(
                "Daily member roster reconcile: updated=%s removed_invalid=%s eligible=%s",
                stats.get("updated"),
                stats.get("removed_invalid"),
                stats.get("invite_eligible"),
            )
        except Exception as exc:
            logger.error("Daily member roster reconcile failed: %s", exc)

    @daily_reconcile.before_loop
    async def before_daily_reconcile(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if after.guild.id != SYNC_GUILD_ID or after.bot:
            return

        before_roles = set(_target_role_labels(before))
        after_roles = set(_target_role_labels(after))
        identity_changed = (
            before.name != after.name
            or before.global_name != after.global_name
            or before.nick != after.nick
        )

        if before_roles != after_roles or identity_changed:
            changed = self._upsert_member(after, still_in_guild=True)
            if changed or before_roles != after_roles:
                self._save()

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.guild.id != SYNC_GUILD_ID or member.bot:
            return
        roles = _target_role_labels(member)
        entry = self._get_entry(member.id)
        if not roles and not (entry and entry.get("roles")):
            return
        if not entry:
            self._upsert_member(member, still_in_guild=False)
        self._mark_left_guild(member)

    @discord.slash_command(
        name="backupmembers",
        description="Force a full Minion/Member roster backup sync.",
        guild_ids=REGISTERED_GUILD_IDS,
        default_member_permissions=discord.Permissions(administrator=True),
    )
    async def backupmembers(self, ctx: discord.ApplicationContext):
        if not await self._require_owner(ctx):
            return
        await ctx.defer(ephemeral=True)
        main_guild = self.bot.get_guild(SYNC_GUILD_ID)
        if main_guild is None:
            return await ctx.followup.send(
                "❌ ShadowMain is not available for roster sync.",
                ephemeral=True,
            )
        stats = await self._full_reconcile(main_guild)
        embed = discord.Embed(title="Member Roster Backup", color=THEME_PRIMARY)
        embed.add_field(name="Total with roles", value=str(stats["total_with_roles"]), inline=True)
        embed.add_field(name="Invite eligible", value=str(stats["invite_eligible"]), inline=True)
        embed.add_field(name="DM closed", value=str(stats["dm_closed"]), inline=True)
        embed.add_field(name="Minion only", value=str(stats["minion_only"]), inline=True)
        embed.add_field(name="Member only", value=str(stats["member_only"]), inline=True)
        embed.add_field(name="Both roles", value=str(stats["both_roles"]), inline=True)
        embed.add_field(name="Updated this sync", value=str(stats["updated"]), inline=True)
        embed.add_field(name="Invalid removed", value=str(stats["removed_invalid"]), inline=True)
        embed.set_footer(text=f"Saved to {ROSTER_STORE.name}")
        await ctx.followup.send(embed=embed, ephemeral=True)

    @discord.slash_command(
        name="memberbackupstats",
        description="Show saved Minion/Member roster stats.",
        guild_ids=REGISTERED_GUILD_IDS,
        default_member_permissions=discord.Permissions(administrator=True),
    )
    async def memberbackupstats(self, ctx: discord.ApplicationContext):
        if not await self._require_owner(ctx):
            return
        stats = self._stats()
        embed = discord.Embed(title="Member Roster Stats", color=THEME_PRIMARY)
        embed.add_field(name="Total with roles", value=str(stats["total_with_roles"]), inline=True)
        embed.add_field(name="Invite eligible", value=str(stats["invite_eligible"]), inline=True)
        embed.add_field(name="DM closed", value=str(stats["dm_closed"]), inline=True)
        embed.add_field(name="Still in guild", value=str(stats["still_in_guild"]), inline=True)
        embed.add_field(name="Left guild", value=str(stats["left_guild"]), inline=True)
        embed.add_field(
            name="Last full sync",
            value=str(self.db.get("last_full_sync") or "never"),
            inline=False,
        )
        await ctx.respond(embed=embed, ephemeral=True)

    @discord.slash_command(
        name="validateroster",
        description="Probe DM reachability for roster members (no invite links).",
        guild_ids=REGISTERED_GUILD_IDS,
        default_member_permissions=discord.Permissions(administrator=True),
    )
    async def validateroster(
        self,
        ctx: discord.ApplicationContext,
        test_user_id: discord.Option(
            str,
            "Optional single user ID to probe only",
            required=False,
            default=None,
        ),
    ):
        if not await self._require_owner(ctx):
            return
        await ctx.defer(ephemeral=True)

        parsed_test_id: int | None = None
        if test_user_id:
            try:
                parsed_test_id = int(test_user_id.strip())
            except ValueError:
                return await ctx.followup.send("Invalid test_user_id.", ephemeral=True)

        targets = self._iter_invite_targets(test_user_id=parsed_test_id)
        if not targets:
            return await ctx.followup.send("No roster targets to validate.", ephemeral=True)

        reachable = 0
        closed = 0
        invalid = 0
        failures: list[str] = []

        for entry in targets:
            user_id = entry["user_id"]
            try:
                user = await self.bot.fetch_user(int(user_id))
            except discord.NotFound:
                self._remove_entry(user_id)
                invalid += 1
                continue
            except Exception as exc:
                failures.append(f"{_admin_line(entry)} — fetch failed: {exc}")
                continue

            ok, err = await self._send_probe_dm(user, invite_url=None)
            await self._apply_dm_result(user_id, ok, err)
            if ok:
                reachable += 1
            elif isinstance(err, discord.NotFound) or getattr(err, "code", None) == 10013:
                invalid += 1
            elif getattr(err, "code", None) == 50007:
                closed += 1
                failures.append(f"{_admin_line(entry)} — DMs closed")
            else:
                failures.append(f"{_admin_line(entry)} — {err}")
            await asyncio.sleep(DM_PROBE_DELAY)

        embed = discord.Embed(title="Roster DM Validation", color=THEME_PRIMARY)
        embed.add_field(name="Probed", value=str(len(targets)), inline=True)
        embed.add_field(name="Reachable", value=str(reachable), inline=True)
        embed.add_field(name="DM closed", value=str(closed), inline=True)
        embed.add_field(name="Invalid removed", value=str(invalid), inline=True)
        if failures:
            sample = "\n".join(failures[:15])
            if len(failures) > 15:
                sample += f"\n... and {len(failures) - 15} more"
            embed.add_field(name="Manual follow-up", value=sample[:1024], inline=False)
        await ctx.followup.send(embed=embed, ephemeral=True)

    @discord.slash_command(
        name="inviteoldmembers",
        description="DM saved roster members an invite to rejoin (disaster recovery).",
        guild_ids=REGISTERED_GUILD_IDS,
        default_member_permissions=discord.Permissions(administrator=True),
    )
    async def inviteoldmembers(
        self,
        ctx: discord.ApplicationContext,
        max_age: discord.Option(
            int,
            "Invite expiry in hours (default 168 / 7 days)",
            required=False,
            default=168,
        ),
        max_uses: discord.Option(
            int,
            "Max uses (0 = unlimited)",
            required=False,
            default=0,
        ),
        test_user_id: discord.Option(
            str,
            "Optional single user ID to test before full send",
            required=False,
            default=None,
        ),
    ):
        if not await self._require_owner(ctx):
            return
        await ctx.defer(ephemeral=True)

        parsed_test_id: int | None = None
        if test_user_id:
            try:
                parsed_test_id = int(test_user_id.strip())
            except ValueError:
                return await ctx.followup.send("Invalid test_user_id.", ephemeral=True)

        targets = self._iter_invite_targets(test_user_id=parsed_test_id)
        if not targets:
            return await ctx.followup.send("No invite-eligible roster members found.", ephemeral=True)

        invite_kwargs = {
            "max_age": max(3600, int(max_age) * 3600),
            "unique": True,
        }
        if max_uses and max_uses > 0:
            invite_kwargs["max_uses"] = max_uses

        try:
            invite_guild = ctx.guild
            if invite_guild is None or invite_guild.id != SHADOW_BACKUP_GUILD_ID:
                backup = self.bot.get_guild(SHADOW_BACKUP_GUILD_ID)
                if backup is None:
                    return await ctx.followup.send(
                        "❌ ShadowBackup not available — run this from the backup guild.",
                        ephemeral=True,
                    )
                invite_guild = backup
            welcome = invite_guild.system_channel or next(
                (c for c in invite_guild.text_channels if c.permissions_for(invite_guild.me).create_instant_invite),
                None,
            )
            if welcome is None:
                return await ctx.followup.send(
                    "❌ No channel available to create a backup invite.",
                    ephemeral=True,
                )
            invite = await welcome.create_invite(**invite_kwargs)
        except Exception as exc:
            return await ctx.followup.send(f"Could not create invite: {exc}", ephemeral=True)

        sent = 0
        closed = 0
        invalid = 0
        other_failures: list[str] = []

        for entry in targets:
            user_id = entry["user_id"]
            try:
                user = await self.bot.fetch_user(int(user_id))
            except discord.NotFound:
                self._remove_entry(user_id)
                invalid += 1
                continue
            except Exception as exc:
                other_failures.append(f"{_admin_line(entry)} — fetch failed: {exc}")
                continue

            ok, err = await self._send_probe_dm(user, invite_url=invite.url)
            await self._apply_dm_result(user_id, ok, err)
            if ok:
                sent += 1
            elif isinstance(err, discord.NotFound) or getattr(err, "code", None) == 10013:
                invalid += 1
            elif getattr(err, "code", None) == 50007:
                closed += 1
                other_failures.append(f"{_admin_line(entry)} — DMs closed")
            else:
                other_failures.append(f"{_admin_line(entry)} — {err}")
            await asyncio.sleep(DM_PROBE_DELAY)

        embed = discord.Embed(title="Old Member Re-Invite", color=THEME_PRIMARY)
        embed.description = f"Invite link (manual fallback):\n{invite.url}"
        embed.add_field(name="Targeted", value=str(len(targets)), inline=True)
        embed.add_field(name="DM sent", value=str(sent), inline=True)
        embed.add_field(name="DM closed", value=str(closed), inline=True)
        embed.add_field(name="Invalid removed", value=str(invalid), inline=True)
        if other_failures:
            sample = "\n".join(other_failures[:15])
            if len(other_failures) > 15:
                sample += f"\n... and {len(other_failures) - 15} more"
            embed.add_field(name="Manual follow-up", value=sample[:1024], inline=False)
        await ctx.followup.send(embed=embed, ephemeral=True)


def setup(bot: discord.Bot):
    bot.add_cog(MemberBackupCog(bot))
