# cogs/audit_logs.py
import asyncio
import logging

import discord
from discord.ext import commands
from discord.ui import View, Button
from datetime import datetime, timezone

from cogs.guild_registry import has_admin_shadow, is_registered_guild, resolve_channel, resolve_role

logger = logging.getLogger("ShadowSyn.AuditLogs")

# --- CONSTANTS ---
THEME_PRIMARY = 0x2B0B35
THEME_LOSS = 0xF04747
THEME_WIN = 0x43B581
THEME_INFO = 0x3498DB


class MinionView(View):
    def __init__(self, target_member_id):
        super().__init__(timeout=None)
        self.target = target_member_id

        b = Button(label="Grant Minion", style=discord.ButtonStyle.success, emoji="✅",
                   custom_id=f"minion_grant_{target_member_id}")
        b.callback = self.grant
        self.add_item(b)

        profile_btn = Button(
            label="View Profile (App)",
            url=f"discord://-/users/{target_member_id}",
            style=discord.ButtonStyle.link,
            emoji="🔍",
        )
        self.add_item(profile_btn)

    async def grant(self, i: discord.Interaction):
        if not has_admin_shadow(i.user, i.guild.id if i.guild else None):
            return await i.response.send_message(
                "🚫 Admin clearance required.", ephemeral=True
            )
        try:
            m = i.guild.get_member(self.target)
            r = resolve_role(i.guild, "minion")
            if m and r:
                await m.add_roles(r)
                await i.response.send_message(
                    f"✅ Minion role granted to **{m.display_name}**.", ephemeral=True
                )
            else:
                await i.response.send_message(
                    "❌ Error: Member may have left or role is missing.", ephemeral=True
                )
        except discord.Forbidden:
            await i.response.send_message(
                "❌ Error: I lack permission to grant this role.", ephemeral=True
            )
        except Exception as e:
            await i.response.send_message(f"⚠️ Error: {e}", ephemeral=True)


class DepartureView(View):
    def __init__(self, target_member_id):
        super().__init__(timeout=None)
        profile_btn = Button(
            label="View Profile (App)",
            url=f"discord://-/users/{target_member_id}",
            style=discord.ButtonStyle.link,
            emoji="🔍",
        )
        self.add_item(profile_btn)


class AuditLogsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(MinionView(0))
        logger.info("AuditLogs: MinionView registered as persistent.")

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

            em = discord.Embed(
                title="🛬 New Arrival",
                description=f"Welcome to **{member.guild.name}**, {member.mention}!",
                color=THEME_PRIMARY,
            )
            em.set_thumbnail(url=avatar_url)
            em.add_field(name="👤 Username", value=f"`{member.name}`", inline=True)
            em.add_field(name="🆔 User ID", value=f"`{member.id}`", inline=True)
            em.add_field(name="📅 Account Created", value=f"<t:{created_ts}:R>", inline=False)

            await ch.send(embed=em, view=MinionView(member.id))
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
                async for entry in member.guild.audit_logs(limit=1, action=discord.AuditLogAction.kick):
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
            embed.add_field(name="🆔 User ID", value=f"`{member.id}`", inline=True)
            embed.add_field(name="📅 Account Created", value=f"<t:{created_ts}:R>", inline=False)
            if joined_ts:
                embed.add_field(name="📥 Joined Server", value=f"<t:{joined_ts}:R>", inline=True)

            embed.set_footer(text=f"User ID: {member.id}")

            await channel.send(embed=embed, view=DepartureView(member.id))
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
        deaf_mod_task = None

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
