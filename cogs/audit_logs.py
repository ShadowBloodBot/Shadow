# cogs/audit_logs.py
import asyncio
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import discord
from discord.ext import commands
from discord.ui import View, Button

from cogs.guild_registry import (
    REGISTERED_GUILD_IDS,
    has_admin_shadow,
    is_registered_guild,
    resolve_channel,
    resolve_role,
)
from cogs.utils import safe_reply

logger = logging.getLogger("ShadowSyn.AuditLogs")

# --- CONSTANTS ---
THEME_PRIMARY = 0x2B0B35
THEME_LOSS = 0xF04747
THEME_WIN = 0x43B581
THEME_INFO = 0x3498DB

ARRIVAL_TITLE = "🛬 New Arrival"
PROFILE_FOOTER = "Click the @mention above to open profile"
ALLOWED_USER_MENTIONS = discord.AllowedMentions(users=True, roles=False, everyone=False)
_MINION_GRANT_RE = re.compile(r"^minion_grant_(\d+)$")
_USER_MENTION_RE = re.compile(r"<@!?(\d+)>")
_USER_ID_FIELD_RE = re.compile(r"`?(\d{17,20})`?")
_REPAIR_MARKER = "arrivals_profile_v2.done"
_ADMIN_FLASH_SECONDS = 1.5


def _persist_dir() -> Path:
    return Path(os.getenv("PERSIST_PATH", "/data"))


def _repair_marker_path() -> Path:
    return _persist_dir() / _REPAIR_MARKER


class MinionView(View):
    """Shell view for custom_id registration. Grant handling is owned by on_interaction."""

    def __init__(self, target_member_id: int):
        super().__init__(timeout=None)
        self.target = int(target_member_id)
        self.add_item(
            Button(
                label="Grant Minion",
                style=discord.ButtonStyle.success,
                emoji="✅",
                custom_id=f"minion_grant_{self.target}",
            )
        )


async def _grant_minion(i: discord.Interaction, target_id: int) -> None:
    if not i.guild or not has_admin_shadow(i.user, i.guild.id):
        return await safe_reply(i, "🚫 Admin clearance required.", ephemeral=True)
    try:
        if not i.response.is_done():
            await i.response.defer(ephemeral=True)
        m = i.guild.get_member(int(target_id))
        r = resolve_role(i.guild, "minion")
        if m and r:
            await m.add_roles(r)
            await i.followup.send(
                f"✅ Minion role granted to **{m.display_name}**.",
                ephemeral=True,
            )
        else:
            await i.followup.send(
                "❌ Error: Member may have left or role is missing.",
                ephemeral=True,
            )
    except discord.Forbidden:
        await safe_reply(i, "❌ Error: I lack permission to grant this role.", ephemeral=True)
    except Exception as e:
        await safe_reply(i, f"⚠️ Error: {e}", ephemeral=True)


def _build_arrival_embed(
    *,
    guild_name: str,
    mention: str,
    username: str,
    user_id: int,
    created_field: str,
    avatar_url: str | None,
) -> discord.Embed:
    em = discord.Embed(
        title=ARRIVAL_TITLE,
        description=f"Welcome to **{guild_name}**, {mention}!",
        color=THEME_PRIMARY,
    )
    if avatar_url:
        em.set_thumbnail(url=avatar_url)
    em.add_field(name="👤 Username", value=f"`{username}`", inline=True)
    em.add_field(name="📅 Account Created", value=created_field, inline=True)
    em.add_field(name="🆔 User ID", value=f"`{user_id}`", inline=False)
    em.set_footer(text=PROFILE_FOOTER)
    return em


def _extract_arrival_user_id(message: discord.Message) -> int | None:
    for row in message.components or []:
        for child in getattr(row, "children", []) or []:
            cid = getattr(child, "custom_id", None) or ""
            m = _MINION_GRANT_RE.match(cid)
            if m:
                return int(m.group(1))
            # Link-button leftovers have no custom_id; skip
    if message.content:
        m = _USER_MENTION_RE.search(message.content)
        if m:
            return int(m.group(1))
    if not message.embeds:
        return None
    emb = message.embeds[0]
    if emb.description:
        m = _USER_MENTION_RE.search(emb.description)
        if m:
            return int(m.group(1))
    for field in emb.fields:
        if "User ID" in (field.name or ""):
            m = _USER_ID_FIELD_RE.search(field.value or "")
            if m:
                return int(m.group(1))
    return None


def _field_map(embed: discord.Embed) -> dict[str, str]:
    out: dict[str, str] = {}
    for field in embed.fields:
        name = field.name or ""
        if "Username" in name:
            out["username"] = (field.value or "").strip("`")
        elif "Account Created" in name:
            out["created"] = field.value or "unknown"
        elif "User ID" in name:
            out["user_id"] = field.value or ""
    return out


async def _ephemeral_flash_followup(
    ctx: discord.ApplicationContext,
    content: str,
    *,
    seconds: float = _ADMIN_FLASH_SECONDS,
) -> None:
    try:
        msg = await ctx.followup.send(content, ephemeral=True, wait=True)
    except Exception as exc:
        logger.warning("arrivals repair flash failed: %s", exc)
        return
    try:
        await asyncio.sleep(seconds)
        await msg.delete()
    except Exception:
        pass


class AuditLogsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._auto_repair_started = False

    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(MinionView(0))
        logger.info("AuditLogs: MinionView registered as persistent.")
        if not self._auto_repair_started:
            self._auto_repair_started = True
            self.bot.loop.create_task(self._auto_repair_if_needed())

    async def _auto_repair_if_needed(self) -> None:
        await self.bot.wait_until_ready()
        marker = _repair_marker_path()
        try:
            if marker.exists():
                return
        except Exception:
            return
        await asyncio.sleep(5)
        total = 0
        for gid in REGISTERED_GUILD_IDS:
            try:
                n = await self._repair_guild_arrivals(gid, limit=200)
                total += n
            except Exception as exc:
                logger.error("Auto arrivals repair failed for guild %s: %s", gid, exc)
        try:
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(f"repaired={total}\n", encoding="utf-8")
        except Exception as exc:
            logger.warning("Could not write arrivals repair marker: %s", exc)
        logger.info("Arrivals auto-repair complete: %s message(s).", total)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        data = interaction.data or {}
        cid = data.get("custom_id") if isinstance(data, dict) else None
        if not isinstance(cid, str):
            return
        m = _MINION_GRANT_RE.match(cid)
        if not m:
            return
        await _grant_minion(interaction, int(m.group(1)))

    async def _get_mod(self, guild, action_type, target):
        await asyncio.sleep(1.5)
        try:
            now = datetime.now(timezone.utc)
            async for entry in guild.audit_logs(limit=3, action=action_type):
                if (now - entry.created_at).total_seconds() < 6:
                    if action_type in [
                        discord.AuditLogAction.member_move,
                        discord.AuditLogAction.member_disconnect,
                    ]:
                        return entry.user
                    if entry.target and entry.target.id == target.id:
                        return entry.user
        except Exception:
            pass
        return None

    async def _repair_one_arrival(self, message: discord.Message) -> bool:
        if not message.embeds:
            return False
        emb = message.embeds[0]
        if (emb.title or "") != ARRIVAL_TITLE:
            return False
        if message.author.id != self.bot.user.id:
            return False

        user_id = _extract_arrival_user_id(message)
        if user_id is None:
            return False

        fields = _field_map(emb)
        username = fields.get("username") or str(user_id)
        created = fields.get("created") or "unknown"
        mention = f"<@{user_id}>"
        guild_name = message.guild.name if message.guild else "ShadowSyn"
        avatar_url = emb.thumbnail.url if emb.thumbnail else None

        new_embed = _build_arrival_embed(
            guild_name=guild_name,
            mention=mention,
            username=username,
            user_id=user_id,
            created_field=created,
            avatar_url=avatar_url,
        )
        view = MinionView(user_id)
        await message.edit(
            content=mention,
            embed=new_embed,
            view=view,
            allowed_mentions=ALLOWED_USER_MENTIONS,
        )
        self.bot.add_view(view)
        return True

    async def _repair_guild_arrivals(self, guild_id: int, limit: int = 100) -> int:
        ch = await resolve_channel(self.bot, guild_id, "arrivals")
        if not ch:
            return 0
        edited = 0
        async for message in ch.history(limit=limit):
            try:
                if await self._repair_one_arrival(message):
                    edited += 1
                    await asyncio.sleep(0.35)
            except Exception as exc:
                logger.warning("Failed repairing arrival %s: %s", message.id, exc)
        return edited

    @discord.slash_command(
        name="arrivals_repair",
        description="Rewrite New Arrival cards for mention-first profiles (both layout + buttons).",
        guild_ids=REGISTERED_GUILD_IDS,
        default_member_permissions=discord.Permissions(administrator=True),
    )
    async def arrivals_repair(
        self,
        ctx: discord.ApplicationContext,
        limit: discord.Option(
            int,
            "How many recent arrivals messages to scan",
            required=False,
            default=100,
            min_value=1,
            max_value=500,
        ) = 100,
    ):
        if not ctx.guild or not is_registered_guild(ctx.guild.id):
            return await safe_reply(ctx, "⛔ Unregistered guild.", ephemeral=True)
        if not has_admin_shadow(ctx.author, ctx.guild.id):
            return await safe_reply(ctx, "🚫 Admin clearance required.", ephemeral=True)

        await ctx.defer(ephemeral=True)
        try:
            edited = await self._repair_guild_arrivals(ctx.guild.id, limit=int(limit))
            await _ephemeral_flash_followup(
                ctx,
                f"✅ Repaired **{edited}** New Arrival card(s) (scanned {limit}).",
            )
        except Exception as exc:
            logger.error("arrivals_repair failed: %s", exc)
            await ctx.followup.send(f"❌ Repair failed: {exc}", ephemeral=True)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        if not is_registered_guild(member.guild.id):
            return
        try:
            ch = await resolve_channel(self.bot, member.guild.id, "arrivals")
            if not ch:
                return

            created_ts = int(member.created_at.timestamp())
            avatar_url = (
                member.display_avatar.url if member.display_avatar else member.default_avatar.url
            )
            em = _build_arrival_embed(
                guild_name=member.guild.name,
                mention=member.mention,
                username=member.name,
                user_id=member.id,
                created_field=f"<t:{created_ts}:R>",
                avatar_url=avatar_url,
            )
            view = MinionView(member.id)
            await ch.send(
                content=member.mention,
                embed=em,
                view=view,
                allowed_mentions=ALLOWED_USER_MENTIONS,
            )
            self.bot.add_view(view)
        except Exception as e:
            logger.error("Exception in on_member_join routing: %s", e)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        if not is_registered_guild(member.guild.id):
            return
        try:
            channel = await resolve_channel(self.bot, member.guild.id, "departures")
            if not channel:
                return

            title = "👋 Member Left"
            description = f"{member.mention} has left **{member.guild.name}**."
            color = THEME_LOSS
            now = datetime.now(timezone.utc)

            try:
                async for entry in member.guild.audit_logs(limit=5, action=discord.AuditLogAction.kick):
                    if entry.target.id == member.id and (now - entry.created_at).total_seconds() < 10:
                        title = "🥾 Member Kicked"
                        description = (
                            f"{member.mention} was kicked from the server.\n"
                            f"**By:** {entry.user.mention} (`{entry.user.name}`)"
                        )
                        break
            except Exception:
                pass

            created_ts = int(member.created_at.timestamp())
            joined_ts = int(member.joined_at.timestamp()) if member.joined_at else None
            avatar_url = (
                member.display_avatar.url if member.display_avatar else member.default_avatar.url
            )

            embed = discord.Embed(title=title, description=description, color=color, timestamp=now)
            embed.set_thumbnail(url=avatar_url)
            embed.add_field(name="👤 Username", value=f"`{member.name}`", inline=True)
            embed.add_field(name="📅 Account Created", value=f"<t:{created_ts}:R>", inline=True)
            embed.add_field(name="🆔 User ID", value=f"`{member.id}`", inline=False)
            if joined_ts:
                embed.add_field(name="📥 Joined Server", value=f"<t:{joined_ts}:R>", inline=True)

            embed.set_footer(text=f"User ID: {member.id}")

            await channel.send(
                content=member.mention,
                embed=embed,
                allowed_mentions=ALLOWED_USER_MENTIONS,
            )
        except Exception as e:
            logger.error("Exception in on_member_remove routing: %s", e)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if not member.guild or not is_registered_guild(member.guild.id):
            return
        channel = await resolve_channel(self.bot, member.guild.id, "voice_audit")
        if not channel:
            return

        actions = []
        color = THEME_PRIMARY

        # Batch all audit-log lookups we need into concurrent tasks so we only
        # wait 1.5 s once instead of up to 1.5 s × N sequential calls.
        channel_mod_task = None
        mute_mod_task = None

        if before.channel != after.channel:
            if before.channel is None:
                pass  # join — no mod lookup needed
            elif after.channel is None:
                channel_mod_task = asyncio.ensure_future(
                    self._get_mod(member.guild, discord.AuditLogAction.member_disconnect, member)
                )
            else:
                channel_mod_task = asyncio.ensure_future(
                    self._get_mod(member.guild, discord.AuditLogAction.member_move, member)
                )

        if before.mute != after.mute or before.deaf != after.deaf:
            mute_mod_task = asyncio.ensure_future(
                self._get_mod(member.guild, discord.AuditLogAction.member_update, member)
            )

        # Await all outstanding tasks at once
        pending = [t for t in (channel_mod_task, mute_mod_task) if t is not None]
        if pending:
            await asyncio.gather(*pending)

        channel_mod = await channel_mod_task if channel_mod_task else None
        mute_deaf_mod = await mute_mod_task if mute_mod_task else None

        if before.channel != after.channel:
            if before.channel is None:
                actions.append(f"📥 Joined **{after.channel.name}**")
                color = THEME_WIN
            elif after.channel is None:
                mod_text = f"\n*(Disconnected by {channel_mod.mention})*" if channel_mod else ""
                actions.append(f"📤 Left **{before.channel.name}**{mod_text}")
                color = THEME_LOSS
            else:
                mod_text = f"\n*(Moved by {channel_mod.mention})*" if channel_mod else ""
                actions.append(
                    f"🔄 Moved: **{before.channel.name}** ➡️ **{after.channel.name}**{mod_text}"
                )
                color = THEME_INFO

        if before.mute != after.mute:
            mod_text = f" *(by {mute_deaf_mod.mention})*" if mute_deaf_mod else ""
            if after.mute:
                actions.append(f"🔇 Server Muted{mod_text}")
                color = THEME_LOSS
            else:
                actions.append(f"🔊 Server Unmuted{mod_text}")
                color = THEME_WIN

        if before.deaf != after.deaf:
            mod_text = f" *(by {mute_deaf_mod.mention})*" if mute_deaf_mod else ""
            if after.deaf:
                actions.append(f"🔕 Server Deafened{mod_text}")
                color = THEME_LOSS
            else:
                actions.append(f"🔔 Server Undeafened{mod_text}")
                color = THEME_WIN

        if before.self_mute != after.self_mute:
            if after.self_mute:
                actions.append("🎙️ Muted Mic (Self)")
            else:
                actions.append("🎙️ Unmuted Mic (Self)")

        if before.self_deaf != after.self_deaf:
            if after.self_deaf:
                actions.append("🎧 Deafened (Self)")
            else:
                actions.append("🎧 Undeafened (Self)")

        if actions:
            embed = discord.Embed(
                description="\n".join(actions),
                color=color,
                timestamp=datetime.now(timezone.utc),
            )
            embed.set_author(
                name=f"{member.display_name} Voice Update",
                icon_url=member.display_avatar.url if member.display_avatar else None,
            )
            embed.set_footer(text=f"User ID: {member.id}")
            try:
                await channel.send(embed=embed)
            except Exception:
                pass


def setup(bot):
    bot.add_cog(AuditLogsCog(bot))
