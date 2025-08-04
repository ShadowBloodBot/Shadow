import discord
from discord.ext import commands
from discord import app_commands
from filters import get_severity_score, suggest_action, save_flagged_users, get_flagged_users
import asyncio
import traceback

class ScanCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="scan", description="Scan server for flagged members")
    async def scan_server(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)

        async def scan_logic():
            guild = interaction.guild
            members = guild.members
            flagged = get_flagged_users()
            updated = 0

            for index, member in enumerate(members, 1):
                if member.bot:
                    continue

                try:
                    score = await get_severity_score(member, self.bot)
                    if score >= 3:
                        flagged[str(member.id)] = {
                            "username": member.name,
                            "score": score,
                            "reason": suggest_action(member)
                        }
                        updated += 1
                except Exception as e:
                    print(f"[SCAN ERROR] {member.name} | {e}")
                    traceback.print_exc()
                    continue

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

        try:
            await asyncio.wait_for(scan_logic(), timeout=120)  # ⏱ 2-min timeout
        except asyncio.TimeoutError:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="❌ Scan Timed Out",
                    description="The scan took too long and was stopped.",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(
                embed=discord.Embed(
                    title="❌ Scan Failed",
                    description=f"Error: `{str(e)}`",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
