import discord
from discord.ext import commands
from discord import app_commands
from filters import get_severity_score, suggest_action
from storage import load_flags, save_flags

class ScanCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="scan", description="Scan all members and flag suspicious ones")
    async def scan(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild = interaction.guild
        members = guild.members
        total = len(members)

        message = await interaction.followup.send(f"🔍 Starting scan of {total} members...")
        flagged_count = 0
        flags = load_flags()

        for index, member in enumerate(members, start=1):
            if member.bot:
                continue

            try:
                score = get_severity_score(member, self.bot)
                reason = suggest_action(member)
                print(f"[SCAN] {member.display_name} | Score: {score} | Reason: {reason}")

                if score >= 1:  # TEMP TEST THRESHOLD
                    user_id = str(member.id)
                    if user_id not in flags:
                        flags[user_id] = {
                            "username": member.name,
                            "score": score,
                            "reason": reason
                        }
                        flagged_count += 1

            except Exception as e:
                print(f"[ERROR] Scanning {member.display_name} failed: {e}")
                continue

            if index % 50 == 0 or index == total:
                await message.edit(content=f"🔍 Scanned {index}/{total} members... Flagged: {flagged_count}")

        save_flags(flags)
        await message.edit(content=f"✅ Scan complete. {flagged_count} flagged out of {total} members.")

async def setup(bot: commands.Bot):
    await bot.add_cog(ScanCommands(bot))
