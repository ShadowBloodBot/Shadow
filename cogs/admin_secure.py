# cogs/admin_secure.py
import discord
from discord.ext import commands

from cogs.guild_registry import (
    REGISTERED_GUILD_IDS,
    SHADOW_BACKUP_GUILD_ID,
    SHADOW_MAIN_GUILD_ID,
    load_registry,
    OWNER_ID,
)

THEME_PRIMARY = 0x2B0B35


class AdminSecureCog(commands.Cog):
    """Owner-only diagnostics for dual-guild ShadowSyn."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _is_owner(self, user: discord.User | discord.Member) -> bool:
        return user.id == OWNER_ID

    @discord.slash_command(
        name="guild_status",
        description="Owner: ShadowMain + ShadowBackup registry and connectivity.",
        guild_ids=REGISTERED_GUILD_IDS,
        default_member_permissions=discord.Permissions(administrator=True),
    )
    async def guild_status(self, ctx: discord.ApplicationContext):
        if not self._is_owner(ctx.author):
            return await ctx.respond("Owner only.", ephemeral=True)

        reg = load_registry(force=True)
        connected = {g.id for g in self.bot.guilds}
        lines = []
        for gid, label in (
            (SHADOW_MAIN_GUILD_ID, "ShadowMain"),
            (SHADOW_BACKUP_GUILD_ID, "ShadowBackup"),
        ):
            entry = reg.get("guilds", {}).get(str(gid), {})
            ch_count = len(entry.get("channels") or {})
            ro_count = len(entry.get("roles") or {})
            status = "connected" if gid in connected else "NOT IN CACHE"
            lines.append(f"**{label}** (`{gid}`) — {status} · {ch_count} channels · {ro_count} roles")

        embed = discord.Embed(title="Dual-Guild Status", color=THEME_PRIMARY)
        embed.description = "\n".join(lines)
        embed.set_footer(text="Shared economy/data on /data · guild-local panels/threads")
        await ctx.respond(embed=embed, ephemeral=True)

    @discord.slash_command(
        name="resync_guilds",
        description="Owner: re-sync slash commands to ShadowMain and ShadowBackup.",
        guild_ids=REGISTERED_GUILD_IDS,
        default_member_permissions=discord.Permissions(administrator=True),
    )
    async def resync_guilds(self, ctx: discord.ApplicationContext):
        if not self._is_owner(ctx.author):
            return await ctx.respond("Owner only.", ephemeral=True)
        await ctx.defer(ephemeral=True)
        try:
            await self.bot.sync_commands(guild_ids=REGISTERED_GUILD_IDS)
            await ctx.followup.send("Slash commands synced to ShadowMain + ShadowBackup.", ephemeral=True)
        except Exception as exc:
            await ctx.followup.send(f"Sync failed: {exc}", ephemeral=True)


def setup(bot: commands.Bot):
    bot.add_cog(AdminSecureCog(bot))
