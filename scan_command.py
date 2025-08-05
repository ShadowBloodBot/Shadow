import discord
from discord import app_commands
from discord.ext import commands
from filters import score_member, get_severity_score, suggest_action
from log_utils import send_log

MODERATOR_ROLE_ID = 955600547266822174
MOD_QUEUE_THREAD_ID = 1401792224500649994

class Scan(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="scan", description="Scan all members and flag suspicious ones.")
    @app_commands.checks.has_role(MODERATOR_ROLE_ID)
    async def scan_members(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        try:
            members = [m async for m in guild.fetch_members(limit=None)]
            total = len(members)
        except Exception as e:
            await interaction.followup.send("❌ Failed to fetch members.", ephemeral=True)
            await send_log(f"[SCAN ERROR] {e}")
            return

        flagged = 0
        try:
            mod_thread = await interaction.client.fetch_channel(MOD_QUEUE_THREAD_ID)
        except Exception as e:
            await interaction.followup.send("❌ Mod queue thread not found.", ephemeral=True)
            await send_log(f"[MOD THREAD ERROR] {e}")
            return

        await interaction.edit_original_response(content=f"🔍 Starting scan of {total} members...")

        for i, member in enumerate(members):
            try:
                score = score_member(member)
                if score >= 3:
                    flagged += 1
                    action = suggest_action(score)
                    await mod_thread.send(f"⚠️ **Flagged**: {member.mention} | Score: {score} | Suggestion: {action}")
            except Exception as e:
                await send_log(f"[SCAN MEMBER ERROR] {member.id}: {e}")

            if i % 25 == 0:
                await interaction.edit_original_response(content=f"🔎 Scanned {i}/{total} members...")

        await interaction.edit_original_response(content=f"✅ Scan complete. Flagged {flagged} members.")

    @scan_members.error
    async def scan_error(self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
        if isinstance(error, discord.app_commands.errors.MissingRole):
            await interaction.response.send_message("❌ You need the Moderator role to use this command.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Scan command failed.", ephemeral=True)
            await send_log(f"[SCAN COMMAND ERROR] {error}")
