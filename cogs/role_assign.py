# cogs/role_assign.py — Silhouette-tier assign-only role proxy (no Manage Roles required)

import logging

import discord
from discord import Option
from discord.ext import commands

from cogs.guild_registry import REGISTERED_GUILD_IDS, has_silhouette_tier, is_registered_guild

logger = logging.getLogger("ShadowSyn.RoleAssign")

THEME_PRIMARY = 0x2B0B35


def _can_assign_role(
    actor: discord.Member,
    role: discord.Role,
    bot_member: discord.Member,
) -> bool:
    if role.is_default() or role.managed:
        return False
    if role.position >= bot_member.top_role.position:
        return False
    if role.position >= actor.top_role.position:
        return False
    return True


class RoleAssignCog(commands.Cog):
    """Proxy add/remove role for Silhouette-tier staff without Manage Roles."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _deny_unauthorized(self, ctx: discord.ApplicationContext) -> bool:
        if not isinstance(ctx.author, discord.Member):
            return True
        if not has_silhouette_tier(ctx.author):
            return True
        return False

    async def _validate(
        self,
        ctx: discord.ApplicationContext,
        member: discord.Member,
        role: discord.Role,
    ) -> str | None:
        if not is_registered_guild(ctx.guild_id):
            return "This command is not available here."
        if self._deny_unauthorized(ctx):
            return "You need the **Silhouette** role (or admin tier) to assign roles."
        if member.bot:
            return "Can't assign roles to bots."
        bot_member = ctx.guild.me
        if bot_member is None:
            return "Bot unavailable."
        actor = ctx.author
        if not isinstance(actor, discord.Member):
            return "Invalid caller."
        if not _can_assign_role(actor, role, bot_member):
            return (
                f"You can't assign **{role.name}** — it must be below your top role "
                f"and below the bot's role."
            )
        return None

    @discord.slash_command(
        name="role_give",
        description="Add a role to a member (Silhouette tier — assign only).",
        guild_ids=REGISTERED_GUILD_IDS,
    )
    async def role_give(
        self,
        ctx: discord.ApplicationContext,
        member: Option(discord.Member, "Member to give the role to"),
        role: Option(discord.Role, "Role to add"),
    ):
        err = await self._validate(ctx, member, role)
        if err:
            return await ctx.respond(f"❌ {err}", ephemeral=True)

        if role in member.roles:
            return await ctx.respond(
                f"ℹ️ {member.mention} already has **{role.name}**.",
                ephemeral=True,
            )

        actor = ctx.author
        try:
            await member.add_roles(
                role,
                reason=f"Silhouette assign by {actor} ({actor.id})",
            )
        except discord.Forbidden:
            return await ctx.respond(
                "❌ I can't assign that role. Check my role hierarchy.",
                ephemeral=True,
            )
        except Exception as exc:
            logger.error("role_give failed: %s", exc)
            return await ctx.respond("❌ Assignment failed.", ephemeral=True)

        embed = discord.Embed(
            title="Role Added",
            description=f"Added **{role.name}** to {member.mention}.",
            color=THEME_PRIMARY,
        )
        embed.set_footer(text=f"By {actor.display_name}")
        await ctx.respond(embed=embed, ephemeral=True)

    @discord.slash_command(
        name="role_remove",
        description="Remove a role from a member (Silhouette tier — assign only).",
        guild_ids=REGISTERED_GUILD_IDS,
    )
    async def role_remove(
        self,
        ctx: discord.ApplicationContext,
        member: Option(discord.Member, "Member to remove the role from"),
        role: Option(discord.Role, "Role to remove"),
    ):
        err = await self._validate(ctx, member, role)
        if err:
            return await ctx.respond(f"❌ {err}", ephemeral=True)

        if role not in member.roles:
            return await ctx.respond(
                f"ℹ️ {member.mention} doesn't have **{role.name}**.",
                ephemeral=True,
            )

        actor = ctx.author
        try:
            await member.remove_roles(
                role,
                reason=f"Silhouette assign by {actor} ({actor.id})",
            )
        except discord.Forbidden:
            return await ctx.respond(
                "❌ I can't remove that role. Check my role hierarchy.",
                ephemeral=True,
            )
        except Exception as exc:
            logger.error("role_remove failed: %s", exc)
            return await ctx.respond("❌ Removal failed.", ephemeral=True)

        embed = discord.Embed(
            title="Role Removed",
            description=f"Removed **{role.name}** from {member.mention}.",
            color=THEME_PRIMARY,
        )
        embed.set_footer(text=f"By {actor.display_name}")
        await ctx.respond(embed=embed, ephemeral=True)


def setup(bot: commands.Bot):
    bot.add_cog(RoleAssignCog(bot))
