# cogs/admin_secure.py
import discord
from discord.ext import commands
from discord import ApplicationContext

# --- CONSTANTS ---
THEME_PRIMARY = 0x2B0B35

class AdminSecureCog(commands.Cog):
    """
    Demonstrates architectural implementation of native Discord Application Command Permissions
    to completely hide commands from unauthorized members within the command picker menu.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # =============================================================================
    # SECURE SLASH COMMAND EXAMPLES
    # =============================================================================

    @discord.slash_command(
        name="create_war",
        description="Create a Quinfall War Roster (Hidden from regular members).",
        # Hides the command from the / command menu for anyone lacking Administrator privileges
        default_member_permissions=discord.Permissions(administrator=True)
    )
    async def create_war(self, ctx: ApplicationContext):
        """Administrative command hidden natively from regular users."""
        embed = discord.Embed(
            title="🛡️ System Protocol",
            description="War roster generation initialized successfully.",
            color=THEME_PRIMARY
        )
        await ctx.respond(embed=embed, ephemeral=True)

    @discord.slash_command(
        name="invest_lead",
        description="Flag user as qualified lead (Hidden from regular members).",
        # Hides the command from the / command menu for anyone lacking Manage Guild privileges
        default_member_permissions=discord.Permissions(manage_guild=True)
    )
    async def invest_lead(self, ctx: ApplicationContext):
        """Administrative financial command hidden natively from regular users."""
        embed = discord.Embed(
            title="📈 System Protocol",
            description="Lead tracking system updated.",
            color=THEME_PRIMARY
        )
        await ctx.respond(embed=embed, ephemeral=True)

def setup(bot: commands.Bot):
    bot.add_cog(AdminSecureCog(bot))
