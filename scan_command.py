import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from filters import get_severity_score, suggest_action
from storage import load_flags, save_flags
from analytics import log_action_with_webhook

MOD_QUEUE_THREAD_ID = 1401792224500649994  # Flag thread

class ScanCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="scan", description="Scan all members and flag suspicious ones")
    async def scan_members(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild = interaction.guild
        members = [m for m in guild.members if not m.bot]
        total = len(members)

        msg = await interaction.followup.send(f"🔍 Starting scan of {total} members...")

        flags = load_flags()
        flagged = 0
        threshold = 1  # now flag anyone scoring ≥ 1

        for i, member in enumerate(members, start=1):
            try:
                score = await get_severity_score(member, self.bot)
                reason = suggest_action(member)
                nickname = member.nick or member.name

                # Log score line (e.g., "[SCAN] Jack | Score: 2 | Reason: Suspicious")
                print(f"[SCAN] {nickname} | Score: {score} | Reason: {reason}")

                if score >= threshold:
                    user_id = str(member.id)
                    if user_id not in flags:
                        flags[user_id] = {
                            "username": member.name,
                            "score": score,
                            "reason": reason
                        }
                        flagged += 1

                        # Log to thread
                        thread = guild.get_thread(MOD_QUEUE_THREAD_ID)
                        if thread:
                            await thread.send(
                                f"🚩 **Flagged**: {member.mention} (`{member.id}`)\n"
                                f"Score: **{score}**\nReason: {reason}"
                            )

            except Exception as e:
                print(f"[ERROR] Scanning {member.name} failed: {e}")

            # Update progress every 25 members
            if i % 25 == 0 or i == total:
                try:
                    await msg.edit(content=f"🔍 Scanned {i}/{total} members... Flagged: {flagged}")
                except Exception:
                    pass

            await asyncio.sleep(0.1)  # prevent API spam

        save_flags(flags)
        await msg.edit(content=f"✅ Scan complete. Total Flagged: **{flagged}**")

async def setup(bot):
    await bot.add_cog(ScanCommands(bot))
