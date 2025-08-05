import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
from config import SHADOW_ROLE_ID
from ui import ShadowControlPanel
from moderation import auto_flag_new_members
from storage import save_flags

load_dotenv()

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"🌐 Synced {len(synced)} global slash command(s).")
    except Exception as e:
        print(f"❌ Slash sync failed: {e}")

def has_shadow_access(user: discord.Member) -> bool:
    allowed_names = ["Mover & Shaker"]
    if SHADOW_ROLE_ID in [role.id for role in user.roles]:
        return True
    if any(role.name in allowed_names for role in user.roles):
        return True
    return False

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
    flagged_ids = await auto_flag_new_members(interaction.guild)
    save_flags({uid: {"flagged_by": interaction.user.name} for uid in flagged_ids})

    if flagged_ids:
        await interaction.followup.send(f"🚨 Scan complete. {len(flagged_ids)} user(s) flagged and added to the Mod Queue.")
    else:
        await interaction.followup.send("✅ Scan complete. No flagged users found.")

if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if token:
        bot.run(token)
    else:
        print("❌ DISCORD_TOKEN not found in environment.")
