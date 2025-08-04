import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

from ui import ShadowControlPanel
from role_manager import RoleManagerView
from moderation import handle_mass_action, handle_shadowmute
from analytics import post_webhook_log
from storage import log_audit
from events import EventHandlers
from scan_command import ScanCommands

load_dotenv()
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"🔧 Synced {len(synced)} slash commands.")
    except Exception as e:
        print(f"❌ Sync failed: {e}")

# /shadow command
@bot.tree.command(name="shadow", description="Open the Shadow Moderation Panel")
async def open_shadow_panel(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_guild and "Mover & Shaker" not in [role.name for role in interaction.user.roles]:
        await interaction.response.send_message("🚫 You do not have permission to use this command.", ephemeral=True)
        return

    await interaction.response.send_message(
        f"🛡️ {interaction.user.mention} activated the `/shadow` panel",
        view=ShadowControlPanel(),
        ephemeral=False
    )

# Register handler Cogs
async def setup_handlers():
    await bot.add_cog(EventHandlers(bot))
    await bot.add_cog(ScanCommands(bot))

bot.loop.create_task(setup_handlers())

# Run bot
if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))
