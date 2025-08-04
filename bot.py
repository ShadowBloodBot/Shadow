import discord
import os
from discord.ext import commands
from dotenv import load_dotenv

from events import EventHandlers
from moderation import handle_mass_action, handle_shadowmute
from storage import load_flags, save_flags
from scan_command import ScanCommands
from ui import ShadowControlPanel

load_dotenv()

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# ✅ Modern async-safe startup hook
class ShadowBot(commands.Bot):
    async def setup_hook(self):
        await self.add_cog(EventHandlers(self))
        await self.add_cog(ScanCommands(self))
        try:
            synced = await self.tree.sync()
            print(f"✅ Synced {len(synced)} global slash commands.")
        except Exception as e:
            print(f"❌ Slash sync failed: {e}")

# Replace default bot with subclassed version
bot = ShadowBot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")

@bot.tree.command(name="shadow", description="Open the Shadow moderation panel")
async def open_shadow_panel(interaction: discord.Interaction):
    try:
        view = ShadowControlPanel(bot, interaction.user)
        await interaction.response.send_message("🧩 Opening Shadow Panel...", view=view, ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to open panel: {e}", ephemeral=True)

if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("❌ DISCORD_TOKEN is not set in the environment.")
    bot.run(token)
