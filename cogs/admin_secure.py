# cogs/admin_secure.py
import discord
from discord.ext import commands
from discord import ApplicationContext

# --- CONSTANTS ---
THEME_PRIMARY = 0x2B0B35
# Architectural Rule: Single server only. Bind commands directly to the guild.
# Replace this with your actual Quinfall server ID.
TARGET_GUILD_ID = 123456789012345678 

class AdminSecureCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # =============================================================================
    # SECURE SLASH COMMAND EXAMPLES
    # =============================================================================

    @discord.slash_command(
        name="create_war",
        description="Create a Quinfall War Roster (Hidden).",
        guild_ids=[TARGET_GUILD_ID],
        default_member_permissions=discord.Permissions(administrator=True)
    )
    async def create_war(self, ctx: ApplicationContext):
        embed = discord.Embed(
            title="🛡️ System Protocol",
            description="War roster generation initialized successfully.",
            color=THEME_PRIMARY
        )
        await ctx.respond(embed=embed, ephemeral=True)

def setup(bot: commands.Bot):
    bot.add_cog(AdminSecureCog(bot))
