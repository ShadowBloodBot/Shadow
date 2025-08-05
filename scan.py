import discord
from discord import app_commands
from discord.ext import commands
from filters import score_member, get_severity_score, suggest_action
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
        members = [m async for m in guild.fetch_members(limit=None)]
        total = len(members)
        flagged = 0

        try:
            mod_thread = await interaction.client.fetch_channel(MOD_QUEUE_THREAD_ID)
        except Exception as e:
            await interaction.followup.send("❌ Mod queue thread not found or inaccessible.", ephemeral=True)
            print(f"[ERROR] Cannot fetch mod thread: {e}")
            return

        await interaction.edit_original_response(content=f"🔍 Scanning {total} members. Please wait...")

        for i, member in enumerate(members, start=1):
            await asyncio.sleep(0.5)  # Throttle to prevent rate limits and improve bio fetch chance
            score, reason = await score_member(member)
            if score >= 3:
                flagged += 1
                add_flagged_user(guild.id, member.id, reason, score)
                try:
                    await mod_thread.send(
                        f"🚩 **Flagged:** {member.mention} | Severity: **{score}**\n**Reason:** {reason}\nSuggested Action: `{suggest_action(score)}`"
                    )
                except Exception as e:
                    print(f"[ERROR] Could not post to mod queue: {e}")

            if i % 25 == 0 or i == total:
                try:
                    await interaction.edit_original_response(content=f"⏳ Scanned {i}/{total} members... Flagged: {flagged}")
                except:
                    pass

        await interaction.edit_original_response(content=f"✅ Scan complete. Flagged {flagged} members.")

async def setup(bot):
    await bot.add_cog(Scan(bot))
