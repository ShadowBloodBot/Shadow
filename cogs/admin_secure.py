# cogs/admin_secure.py
import discord
from discord.ext import commands

# --- CONSTANTS ---
THEME_PRIMARY = 0x2B0B35
# Architectural Rule: Single server only. Bind commands directly to the guild.
TARGET_GUILD_ID = 908659586536468540


class AdminSecureCog(commands.Cog):
    """Template cog for admin-only commands hidden from members.

    Hiding is enforced per-command with
    default_member_permissions=discord.Permissions(administrator=True) —
    members without Administrator never see those commands in the picker.
    Register new hidden commands here with guild_ids=[TARGET_GUILD_ID].
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot


def setup(bot: commands.Bot):
    bot.add_cog(AdminSecureCog(bot))
