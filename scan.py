# scan.py

import discord
from discord import app_commands
from discord.ext import commands
from filters import score_member, suggest_action
from storage import add_flagged_user
from log_utils import send_log

MOD_QUEUE_THREAD_ID = 1401792224500649994
MOD_ROLE_ID = 955600547266822174

class Scan(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="scan", description="Scan all members and flag suspicious ones.")
    async def scan_command(self, interaction: discord.Interaction):
        if not any(role.id == MOD_ROLE_ID for role in interaction.user.roles):
            await interaction.response.send_message("🚫 You don't have permission to use this.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        members = [m async for m in guild.fetch_members(limit=None)]
        total = len(members)
        flagged = 0

        await interaction.followup.send(f"🛰️ Starting scan of {total} members...", ephemeral=True)

        for i, member in enumerate(members):
            try:
                score, reason = score_member(member)
                if score >= 3:
                    add_flagged_user(member.id, score, reason)
                    flagged += 1

                # Progress every 250 members
                if i % 250 == 0 and i > 0:
                    await interaction.followup.send(f"🔍 Scanned {i}/{total} members...", ephemeral=True)

            except Exception as e:
                print(f"[SCAN ERROR] Member: {member} | {e}")

        await interaction.followup.send(f"✅ Scan complete. Flagged {flagged} member(s).", ephemeral=True)
        await send_log(f"🛰️ {interaction.user.mention} triggered a scan.\nFlagged: `{flagged}` members.")

