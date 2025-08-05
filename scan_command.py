import discord
from discord import app_commands
from filters import ai_flag_user
from mod_queue import ModQueueView
from config import MOD_QUEUE_THREAD_ID

@app_commands.command(name="scan", description="Scan all members and flag suspicious ones.")
@app_commands.checks.has_permissions(administrator=True)
async def scan_command(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    members = [m async for m in guild.fetch_members(limit=None)]
    total = len(members)
    flagged = []

    try:
        mod_thread = await interaction.client.fetch_channel(MOD_QUEUE_THREAD_ID)
    except Exception as e:
        await interaction.followup.send("❌ Mod queue thread not found or inaccessible.", ephemeral=True)
        print(f"[ERROR] Cannot fetch mod thread: {e}")
        return

    await interaction.edit_original_response(content=f"🔍 Scanning {total} members...")

    for i, member in enumerate(members):
        if member.bot:
            continue
        try:
            if await ai_flag_user(member):
                flagged.append(member)
        except Exception as e:
            print(f"[SCAN ERROR] {member}: {e}")
        if i % 100 == 0:
            await interaction.edit_original_response(content=f"🔎 Scanned {i}/{total}...")

    if not flagged:
        await interaction.edit_original_response(content="✅ Scan complete. No suspicious users flagged.")
    else:
        await interaction.edit_original_response(content=f"⚠️ Scan complete. {len(flagged)} users flagged.")
        try:
            await mod_thread.send("📥 Auto-Scan Flagged Members", view=ModQueueView(flagged))
        except Exception as e:
            print(f"[THREAD ERROR] {e}")
