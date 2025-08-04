# scan_command.py

import discord
from discord import app_commands
from discord.ext import commands
from filters import score_member

MOD_QUEUE_THREAD_ID = 1401792224500649994

class Scan(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="scan", description="Scan all members and flag suspicious ones.")
    @app_commands.checks.has_permissions(administrator=True)
    async def scan_members(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        flagged = 0

        mod_thread = guild.get_thread(MOD_QUEUE_THREAD_ID)
        if not mod_thread:
            await interaction.followup.send("❌ Mod queue thread not found.", ephemeral=True)
            return

        for index, member in enumerate(guild.members, start=1):
            try:
                score, reason = score_member(member)
                if score >= 3:
                    flagged += 1
                    await mod_thread.send(
                        f"\n🚨 **Flagged User:** {member.mention}"
                        f"\nScore: {score}"
                        f"\nReason: {reason}"
                        f"\nSuggested Action: Kick or timeout"
                    )

                if index % 25 == 0:
                    await discord.utils.sleep_until(discord.utils.utcnow() + discord.utils.timedelta(seconds=1))

            except Exception as e:
                print(f"[ERROR] Failed to scan {member.name}: {e}")

        await interaction.followup.send(f"✅ Scan complete. Total Flagged: **{flagged}**", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Scan(bot))
