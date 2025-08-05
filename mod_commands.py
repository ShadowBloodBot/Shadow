import discord
from discord.ext import commands
from discord import app_commands
from logging import send_log
from storage import log_case

class ModCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="kick", description="Kick a member from the server.")
    @app_commands.checks.has_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided."):
        try:
            await member.kick(reason=reason)
            await interaction.response.send_message(f"✅ {member} has been kicked.", ephemeral=True)
            await log_case("kick", member, interaction.user, reason)
        except Exception as e:
            await interaction.response.send_message("❌ Failed to kick member.", ephemeral=True)
            print(e)

    @app_commands.command(name="ban", description="Ban a member from the server.")
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided."):
        try:
            await member.ban(reason=reason)
            await interaction.response.send_message(f"✅ {member} has been banned.", ephemeral=True)
            await log_case("ban", member, interaction.user, reason)
        except Exception as e:
            await interaction.response.send_message("❌ Failed to ban member.", ephemeral=True)
            print(e)

    @app_commands.command(name="timeout", description="Timeout a member for X minutes.")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def timeout(self, interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str = "No reason provided."):
        try:
            until = discord.utils.utcnow() + discord.timedelta(minutes=minutes)
            await member.timeout(until, reason=reason)
            await interaction.response.send_message(f"🕓 {member} has been timed out for {minutes} minutes.", ephemeral=True)
            await log_case("timeout", member, interaction.user, f"{reason} ({minutes}m)")
        except Exception as e:
            await interaction.response.send_message("❌ Failed to timeout member.", ephemeral=True)
            print(e)

    @app_commands.command(name="warn", description="Warn a member.")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided."):
        try:
            await interaction.response.send_message(f"⚠️ {member.mention} has been warned: {reason}", ephemeral=True)
            await log_case("warn", member, interaction.user, reason)
        except Exception as e:
            await interaction.response.send_message("❌ Failed to warn member.", ephemeral=True)
            print(e)
