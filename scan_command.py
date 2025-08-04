import discord
from discord import app_commands
from discord.ext import commands

from filters import get_severity_score, suggest_action
from storage import load_flags, save_flags, log_audit, log_action_with_webhook

class ScanCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="scan", description="Scan all members for suspicious behavior")
    async def scan(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        flagged = load_flags()
        count = 0

        for member in interaction.guild.members:
            if member.bot:
                continue

            user_id = str(member.id)
            if user_id in flagged:
                continue

            score = get_severity_score(member)
            if score >= 3:
                reason = suggest_action(member)
                flagged[user_id] = {
                    "username": member.name,
                    "score": score,
                    "reason": reason
                }
                save_flags(flagged)
                log_audit("scan_flag", member.id, interaction.user, reason)
                log_action_with_webhook("scan_flag", member.id, interaction.user, reason)
                count += 1

        await interaction.followup.send(f"🔍 Scan complete. `{count}` member(s) were flagged.", ephemeral=True)
