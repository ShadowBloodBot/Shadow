import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
from config import SHADOW_ROLE_ID
from ui import ShadowControlPanel
from moderation import auto_flag_new_members
from storage import save_flags, load_flags
from filters import get_severity_score

load_dotenv()

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

def has_shadow_access(user: discord.Member) -> bool:
    allowed_names = ["Mover & Shaker"]
    return SHADOW_ROLE_ID in [r.id for r in user.roles] or any(r.name in allowed_names for r in user.roles)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"🌐 Synced {len(synced)} global slash command(s).")
    except Exception as e:
        print(f"❌ Slash sync failed: {e}")

@bot.tree.command(name="shadow", description="Open the Shadow Moderation Panel")
async def shadow(interaction: discord.Interaction):
    if not has_shadow_access(interaction.user):
        await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)
        return

    view = ShadowControlPanel(bot, interaction.user)
    await interaction.response.send_message("🧠 Opening the Shadow Moderation Panel...\nPlease check the Mod Queue for flagged users.", ephemeral=True)
    try:
        await interaction.channel.send(f"🛡️ {interaction.user.mention} activated the `/shadow` panel.", view=view)
    except discord.Forbidden:
        await interaction.followup.send("❌ Could not post panel — missing permissions.", ephemeral=True)

@bot.tree.command(name="scan", description="Scan all members and flag suspicious ones")
async def scan(interaction: discord.Interaction):
    if not has_shadow_access(interaction.user):
        await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)
        return

    await interaction.response.send_message("🔍 Starting scan...", ephemeral=True)

    try:
        progress_msg = await interaction.channel.send("🔎 Scanning members... This may take a moment.")
    except discord.Forbidden:
        await interaction.followup.send("❌ Bot lacks permission to post updates.", ephemeral=True)
        return

    flagged = []
    flags = load_flags()

    try:
        members = []
        async for member in interaction.guild.fetch_members(limit=None):
            members.append(member)
    except Exception:
        members = [m for m in interaction.guild.members if not m.bot]

    batch_size = 50
    delay_sec = 2
    total = len(members)
    scanned = 0

    for i in range(0, total, batch_size):
        batch = members[i:i + batch_size]
        for member in batch:
            if member.bot:
                continue

            score = get_severity_score(bot, member)
            if score >= 3:
                user_id = str(member.id)
                if user_id not in flags:
                    flags[user_id] = {
                        "username": member.name,
                        "score": score,
                        "reason": "Flagged via scan"
                    }
                    flagged.append(member.id)

        scanned += len(batch)
        await progress_msg.edit(content=f"🔄 Scanning... `{scanned}/{total}` checked. `{len(flagged)}` flagged.")
        await bot.wait_until_ready()
        await discord.utils.sleep_until(discord.utils.utcnow() + discord.utils.timedelta(seconds=delay_sec))

    save_flags(flags)

    if flagged:
        await progress_msg.edit(content=f"🚨 Scan complete. `{len(flagged)}` user(s) flagged and added to the Mod Queue.")
    else:
        await progress_msg.edit(content="✅ Scan complete. No flagged users found.")

if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if token:
        bot.run(token)
    else:
        print("❌ DISCORD_TOKEN not found in environment.")
