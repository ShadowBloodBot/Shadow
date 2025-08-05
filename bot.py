import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
from config import SHADOW_ROLE_ID
from ui import ShadowControlPanel

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

@bot.tree.command(name="shadow", description="Open the Shadow Moderation Panel")
async def shadow(interaction: discord.Interaction):
    if SHADOW_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)
        return

    view = ShadowControlPanel(bot, interaction.user)
    await interaction.response.send_message("🧠 Opening the Shadow Moderation Panel...\nPlease check the Mod Queue for flagged users.", ephemeral=True)
    try:
        await interaction.channel.send(f"🛡️ {interaction.user.mention} activated the `/shadow` panel.", view=view)
    except discord.Forbidden:
        await interaction.followup.send("❌ Could not post panel — missing permissions.", ephemeral=True)

if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if token:
        bot.run(token)
    else:
        print("❌ DISCORD_TOKEN not found in environment.")
