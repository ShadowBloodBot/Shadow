import discord
from discord.ext import commands
from discord import app_commands
from filters import score_member, suggest_action
from storage import add_flagged_user
import asyncio

MOD_QUEUE_THREAD_ID = 1401792224500649994  # Replace with your mod queue thread/channel ID

class Scan(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="scan", description="Scan all members and flag suspicious ones.")
    @app_commands.checks.has_permissions(administrator=True)
    async def scan(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        members = [m async for m in interaction.guild.fetch_members(limit=None)]
        flagged = 0

        try:
            for i, member in enumerate(members):
                score = score_member(member)
                if score >= 3:
                    await add_flagged_user(interaction.guild.id, member.id, score)
                    flagged += 1
                    await asyncio.sleep(0.1)  # prevent rate limit
                if i % 50 == 0:
                    await interaction.followup.send(f"Scanned {i}/{len(members)}...", ephemeral=True)

            await interaction.followup.send(f"✅ Scan complete. {flagged} users flagged.", ephemeral=True)
            thread = await interaction.client.fetch_channel(MOD_QUEUE_THREAD_ID)
            await thread.send(f"⚠️ {flagged} new members flagged. Review via `/shadow`.")
        except Exception as e:
            await interaction.followup.send("❌ Scan failed.", ephemeral=True)
            print(e)
