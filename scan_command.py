import discord
from discord import app_commands
from discord.ext import commands
from datetime import timedelta
from filters import score_member, get_severity_score, suggest_action
from storage import load_flags, save_flags

MOD_QUEUE_THREAD_ID = 1401792224500649994

class Scan(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="scan", description="Scan all members and flag suspicious ones.")
    @app_commands.checks.has_permissions(administrator=True)
    async def scan_members(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        flagged_ids = []
        flags = load_flags()

        try:
            members = [m async for m in guild.fetch_members(limit=None)]
        except Exception:
            members = [m for m in guild.members if not m.bot]

        total = len(members)

        try:
            mod_thread = await interaction.client.fetch_channel(MOD_QUEUE_THREAD_ID)
        except Exception as e:
            await interaction.followup.send("❌ Mod queue thread not found or inaccessible.", ephemeral=True)
            print(f"[ERROR] Cannot fetch mod thread: {e}")
            return

        try:
            await interaction.edit_original_response(content=f"🔍 Starting scan of {total} members...")
        except:
            pass

        for index, member in enumerate(members, start=1):
            try:
                if member.bot:
                    continue

                try:
                    user = await interaction.client.fetch_user(member.id)
                except:
                    user = member

                score, reason = score_member(member, user)

                if score >= 1:
                    user_id = str(member.id)
                    if user_id not in flags:
                        flags[user_id] = {
                            "username": member.name,
                            "score": score,
                            "reason": reason
                        }
                        flagged_ids.append(user.id)

                        await mod_thread.send(
                            f"{get_severity_score(score)} **Flagged User:** {member.mention}\n"
                            f"Score: {score}\n"
                            f"Reason: {reason}\n"
                            f"Suggested Action: {suggest_action(score)}\n"
                            f"Account Created: <t:{int(member.created_at.timestamp())}:D>"
                        )

                if index % 10 == 0 or index == total:
                    try:
                        await interaction.edit_original_response(
                            content=f"🔄 Scanned `{index}/{total}` members — `{len(flagged_ids)}` flagged."
                        )
                    except:
                        pass

                    await discord.utils.sleep_until(discord.utils.utcnow() + timedelta(seconds=1))

            except Exception as e:
                print(f"[ERROR] Failed to scan {member.name}: {e}")

        save_flags(flags)

        try:
            await interaction.edit_original_response(
                content=f"✅ Scan complete. `{total}` members scanned. Total Flagged: **{len(flagged_ids)}**"
            )
        except:
            pass

    @app_commands.command(name="shadow", description="Open the Shadow moderation panel.")
    @app_commands.checks.has_permissions(administrator=True)
    async def shadow_panel(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            content="🧠 Opening the Shadow Moderation Panel...\nPlease check the Mod Queue for flagged users.",
            ephemeral=True
        )

async def setup(bot):
    await bot.add_cog(Scan(bot))
