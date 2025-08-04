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

class ShadowBot(commands.Bot):
    async def setup_hook(self):
        await self.add_cog(EventHandlers(self))
        await self.add_cog(ScanCommands(self))
        print("✅ All Cogs loaded via setup_hook.")

bot = ShadowBot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"🔧 Synced {len(synced)} slash commands.")
    except Exception as e:
        print(f"❌ Sync failed: {e}")

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

# Start bot
if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))
