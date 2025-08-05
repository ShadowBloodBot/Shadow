import discord
from discord.ext import commands
from discord import app_commands
from log_utils import send_log
from storage import log_case

MODERATOR_ROLE_ID = 955600547266822174  # 🔒 Role required for all commands

class ModCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="kick", description="Kick a member from the server.")
    @app_commands.checks.has_permissions(kick_members=True)
    @app_commands.checks.has_role(MODERATOR_ROLE_ID)
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided."):
        try:
            await member.kick(reason=reason)
            await interaction.response.send_message(f"✅ {member} has been kicked.", ephemeral=True)
            await log_case("kick", member, interaction.user, reason)
            await send_log(f"👢 {interaction.user.mention} kicked {member.mention} – `{reason}`")
        except Exception as e:
            await interaction.response.send_message("❌ Failed to kick member.", ephemeral=True)
            await send_log(f"[KICK ERROR] {e}")

    @app_commands.command(name="ban", description="Ban a member from the server.")
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.checks.has_role(MODERATOR_ROLE_ID)
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided."):
        try:
            await member.ban(reason=reason)
            await interaction.response.send_message(f"✅ {member} has been banned.", ephemeral=True)
            await log_case("ban", member, interaction.user, reason)
            await send_log(f"🔨 {interaction.user.mention} banned {member.mention} – `{reason}`")
        except Exception as e:
            await interaction.response.send_message("❌ Failed to ban member.", ephemeral=True)
            await send_log(f"[BAN ERROR] {e}")

    @app_commands.command(name="timeout", description="Timeout a member for X minutes.")
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.checks.has_role(MODERATOR_ROLE_ID)
    async def timeout(self, interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str = "No reason provided."):
        try:
            until = discord.utils.utcnow() + discord.timedelta(minutes=minutes)
            await member.timeout(until, reason=reason)
            await interaction.response.send_message(f"🕓 {member} has been timed out for {minutes} minutes.", ephemeral=True)
            await log_case("timeout", member, interaction.user, f"{reason} ({minutes}m)")
            await send_log(f"🕓 {interaction.user.mention} timed out {member.mention} for {minutes}m – `{reason}`")
        except Exception as e:
            await interaction.response.send_message("❌ Failed to timeout member.", ephemeral=True)
            await send_log(f"[TIMEOUT ERROR] {e}")

    @app_commands.command(name="warn", description="Warn a member.")
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.checks.has_role(MODERATOR_ROLE_ID)
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided."):
        try:
            await interaction.response.send_message(f"⚠️ {member.mention} has been warned: {reason}", ephemeral=True)
            await log_case("warn", member, interaction.user, reason)
            await send_log(f"⚠️ {interaction.user.mention} warned {member.mention} – `{reason}`")
        except Exception as e:
            await interaction.response.send_message("❌ Failed to warn member.", ephemeral=True)
            await send_log(f"[WARN ERROR] {e}")

    @app_commands.command(name="purge", description="Delete messages in bulk from a channel.")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.has_role(MODERATOR_ROLE_ID)
    @app_commands.describe(limit="Number of messages to delete (max 100)", user="Optional: Only purge messages from this user")
    async def purge(self, interaction: discord.Interaction, limit: int, user: discord.User = None):
        await interaction.response.defer(ephemeral=True)

        if limit > 100:
            await interaction.followup.send("❌ Cannot delete more than 100 messages at once.", ephemeral=True)
            return

        def check(msg):
            return not user or msg.author.id == user.id

        try:
            deleted = await interaction.channel.purge(limit=limit, check=check)
            await interaction.followup.send(f"✅ Deleted {len(deleted)} messages.", ephemeral=True)

            if user:
                await send_log(f"🧹 {interaction.user.mention} purged {len(deleted)} messages from {user.mention} in <#{interaction.channel.id}>.")
            else:
                await send_log(f"🧹 {interaction.user.mention} purged {len(deleted)} messages in <#{interaction.channel.id}>.")
        except Exception as e:
            await interaction.followup.send("❌ Failed to purge messages.", ephemeral=True)
            await send_log(f"[PURGE ERROR] {e}")
