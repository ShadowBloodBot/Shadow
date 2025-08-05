import discord
from discord.ext import commands
from discord import app_commands
from filters import score_member, suggest_action
from storage import add_flagged_user
from log_utils import send_log

MOD_ROLE_ID = 955600547266822174
MOD_QUEUE_THREAD_ID = 1401792224500649994


class Scan(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="scan", description="Scan all members and flag suspicious ones.")
    @app_commands.checks.has_role(MOD_ROLE_ID)
    async def scan_members(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        flagged = 0
        scanned = 0

        try:
            mod_thread = await self.bot.fetch_channel(MOD_QUEUE_THREAD_ID)
        except Exception as e:
            await interaction.followup.send("❌ Mod queue thread not found or inaccessible.", ephemeral=True)
            print(f"[ERROR] Mod thread fetch: {e}")
            return

        members = [m async for m in guild.fetch_members(limit=None)]
        total = len(members)

        await interaction.followup.send(f"🔍 Starting scan of `{total}` members. Progress will be shown here.", ephemeral=True)

        for member in members:
            scanned += 1

            if member.bot or member.system:
                continue

            score, reason = score_member(member)
            if score >= 3:
                flagged += 1
                add_flagged_user(member.id, score, reason)

                try:
                    await mod_thread.send(
                        f"🚨 **Flagged:** <@{member.id}> • Score: `{score}`\n🧠 Reason: {reason}\nSuggested action: `{suggest_action(score)}`"
                    )
                except Exception as e:
                    print(f"[ERROR] Failed to send to mod queue: {e}")

            # Yield control to avoid freezing
            if scanned % 25 == 0:
                try:
                    await interaction.edit_original_response(content=f"🔄 Scanned `{scanned}/{total}` members...\n🚩 Flagged so far: `{flagged}`")
                except:
                    pass
                await discord.utils.sleep_until(discord.utils.utcnow())

        await interaction.edit_original_response(content=f"✅ Finished scanning `{total}` members.\n🚩 Flagged total: `{flagged}`")


async def setup(bot):
    await bot.add_cog(Scan(bot))
