import discord
import os
from discord.ext import commands
from events import EventHandlers
from moderation import handle_mass_action, handle_shadowmute
from storage import load_flags, save_flags
from scan_command import ScanCommands
from ui import ShadowControlPanel
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# Setup complete message
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user.name}#{bot.user.discriminator}")
    try:
        synced = await bot.tree.sync()  # Global sync for slash commands
        print(f"✅ Synced {len(synced)} slash commands.")
    except Exception as e:
        print(f"❌ Slash command sync failed: {e}")

# Slash Command: /shadow
@bot.tree.command(name="shadow", description="Open the Shadow moderation panel")
async def open_shadow_panel(interaction: discord.Interaction):
    try:
        view = ShadowControlPanel(bot, interaction.user)
        await interaction.response.send_message("🧩 Opening Shadow Panel...", view=view, ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to open panel: {e}", ephemeral=True)

# Manual test command (optional)
@bot.command()
async def ping(ctx):
    await ctx.send("Pong!")

# Load core logic
async def setup_handlers():
    await bot.add_cog(EventHandlers(bot))
    await bot.add_cog(ScanCommands(bot))

bot.loop.create_task(setup_handlers())

# Run the bot
if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("❌ DISCORD_TOKEN is not set in the environment.")
    bot.run(token)
