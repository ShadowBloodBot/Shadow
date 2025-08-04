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
        scanned = 0
        batch = 250

        try:
            members = list(interaction.guild.members)
            total = len(members)

            for i, member in enumerate(members, start=1):
                if member.bot:
                    continue

                scanned += 1
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

                # Send progress updates
                if scanned % batch == 0:
                    await interaction.followup.send(
                        f"📊 Scanned {scanned}/{total} members... `{count}` flagged so far.",
                        ephemeral=True
                    )

            await interaction.followup.send(
                embed=discord.Embed(
                    title="✅ Scan Complete",
                    description=f"Scanned `{scanned}` members.\nFlagged: `{count}` suspicious accounts.",
                    color=discord.Color.green()
                ),
                ephemeral=True
            )

        except Exception as e:
            await interaction.followup.send(f"❌ Scan failed: `{e}`", ephemeral=True)
