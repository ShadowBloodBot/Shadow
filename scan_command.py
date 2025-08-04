import discord
from discord.ext import commands
from filters import get_severity_score, suggest_action
from storage import load_flags, save_flags
import json
import asyncio

class ScanCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(name="scan", description="Scan all members and flag suspicious ones")
    async def scan(self, ctx: discord.ApplicationContext):
        await ctx.defer()

        guild = ctx.guild
        members = guild.members
        total = len(members)

        message = await ctx.respond(f"🔍 Starting scan of {total} members...")
        flagged_count = 0

        flags = load_flags()
        batch_size = 50

        for index, member in enumerate(members, start=1):
            if member.bot:
                continue

            try:
                score = get_severity_score(member, self.bot)
                reason = suggest_action(member)

                print(f"[SCAN] {member.display_name} | Score: {score} | Reason: {reason}")

                if score >= 1:  # TESTING THRESHOLD
                    user_id = str(member.id)

                    if user_id not in flags:
                        flags[user_id] = {
                            "username": member.name,
                            "score": score,
                            "reason": reason
                        }
                        flagged_count += 1

            except Exception as e:
                print(f"[ERROR] Failed to scan {member.display_name}: {e}")
                continue

            if index % batch_size == 0 or index == total:
                await message.edit_original_response(
                    content=f"🔍 Scanned {index}/{total} members... Flagged: {flagged_count}"
                )

        save_flags(flags)

        await message.edit_original_response(
            content=f"✅ Scan complete. Scanned {total} members. Flagged: {flagged_count}"
        )

def setup(bot):
    bot.add_cog(ScanCommands(bot))
