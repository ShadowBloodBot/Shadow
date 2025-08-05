# scan.py

import discord
from discord.ext import commands
from discord import app_commands
from filters import get_severity_score, suggest_action
from storage import add_flagged_user
import asyncio

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

        try:
            members = [m async for m in guild.fetch_members(limit=None)]
        except Exception as e:
            await interaction.followup.send("❌ Failed to fetch members.", ephemeral=True)
            print(f"[ERROR] Fetching members failed: {e}")
            return

        total = len(members)

        try:
            mod_thread = await self.bot.fetch_channel(MOD_QUEUE_THREAD_ID)
        except Exception as e:
            await interaction.followup.send("❌ Mod queue thread not found or inaccessible.", ephemeral=True)
            print(f"[ERROR] Cannot fetch mod thread: {e}")
            return

        try:
            await interaction.edit_original_response(content=f"🔍 Starting scan of {total} members...")
        except Exception as e:
            print(f"[ERROR] Cannot edit original scan response: {e}")

        for idx, member in enumerate(members):
            try:
                score = await get_severity_score(member)
                if score >= 3:
                    reason = suggest_action(score)
                    add_flagged_user(member.id, score, reason)
                    await mod_thread.send(
                        f"🚨 **Flagged:** {member.mention} (Score: `{score}`)\nReason: `{reason}`"
                    )
                    flagged += 1
            except Exception as e:
                print(f"[ERROR] Scanning member {member.id}: {e}")

            if idx % 50 == 0:
                try:
                    await interaction.edit_original_response(
                        content=f"📊 Scanned {idx}/{total} members...\n🚩 Flagged so far: {flagged}"
                    )
                except:
                    pass

            await asyncio.sleep(0.1)

        await interaction.edit_original_response(
            content=f"✅ Scan complete: `{flagged}` members flagged out of `{total}`."
        )


async def setup(bot):
    await bot.add_cog(Scan(bot))
