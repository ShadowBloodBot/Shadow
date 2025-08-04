import discord
from discord.ext import commands
from discord import app_commands
from filters import get_severity_score, suggest_action, save_flagged_users, get_flagged_users
import asyncio

class ScanCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="scan", description="Scan server for flagged members")
    async def scan_server(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)

        guild = interaction.guild
        members = guild.members
        flagged = get_flagged_users()
        updated = 0

        for index, member in enumerate(members, 1):
            if member.bot:
                continue

            try:
                score = await get_severity_score(member, self.bot)  # ✅ fixed here
                if score >= 3:
                    flagged[str(member.id)] = {
                        "username": member.name,
                        "score": score,
                        "reason": suggest_action(member)
                    }
                    updated += 1
            except Exception as e:
                print(f"Scan error for {member.name}: {e}")
                continue

            # Throttle and status update every 250 members
            if index % 250 == 0:
                try:
                    await interaction.followup.send(
                        f"🔎 Scanned {index}/{len(members)} members...",
                        ephemeral=True
                    )
                except:
                    pass

            await asyncio.sleep(0.01)

        save_flagged_users(flagged)

        await interaction.followup.send(
            embed=discord.Embed(
                title="✅ Scan Complete",
                description=f"Scanned {len(members)} members.\nFlagged: {updated}",
                color=discord.Color.green()
            ),
            ephemeral=True
        )
