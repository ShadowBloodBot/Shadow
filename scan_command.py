# scan_command.py

import discord
from discord import app_commands
from discord.ext import commands
from datetime import timedelta
from filters import score_member, get_severity_score, suggest_action

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
        members = [m async for m in guild.fetch_members(limit=None)]
        total = len(members)

        try:
            mod_thread = await interaction.client.fetch_channel(MOD_QUEUE_THREAD_ID)
        except Exception as e:
            await interaction.followup.send("❌ Mod queue thread not found or inaccessible.", ephemeral=True)
            print(f"[ERROR] Cannot fetch mod thread: {e}")
            return

        await interaction.edit_original_response(content=f"🔍 Starting scan of {total} members...")

        for index, member in enumerate(members, start=1):
            try:
                if member.bot:
                    continue

                try:
                    user = await interaction.client.fetch_user(member.id)
                except Exception:
                    user = member  # fallback

                score, reason = score_member(member, user)
                if score >= 3:
                    flagged += 1
                    await mod_thread.send(
                        f"{get_severity_score(score)} **Flagged User:** {member.mention}\n"
                        f"Score: {score}\n"
                        f"Reason: {reason}\n"
                        f"Suggested Action: {suggest_action(score)}\n"
                        f"Account Created: <t:{int(member.created_at.timestamp())}:D>"
                    )

                if index % 50 == 0 or index == total:
                    await interaction.edit_original_response(
                        content=f"🔍 Scanned {index}/{total} members... Flagged: {flagged}"
                    )
                    await discord.utils.sleep_until(discord.utils.utcnow() + timedelta(seconds=1))

            except Exception as e:
                print(f"[ERROR] Failed to scan {member.name}: {e}")

        await interaction.edit_original_response(
            content=f"✅ Scan complete. Scanned {total} members. Total Flagged: **{flagged}**"
        )

    @app_commands.command(name="shadow", description="Open the Shadow moderation panel.")
    @app_commands.checks.has_permissions(administrator=True)
    async def shadow_panel(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            content="🧠 Opening the Shadow Moderation Panel...\nPlease check the Mod Queue for flagged users.",
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(Scan(bot))
