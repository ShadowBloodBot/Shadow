import os
import discord
from discord.ext import commands
from discord import app_commands
from ui import ShadowControlPanel
from moderation import handle_mass_action, handle_shadowmute
from scan_command import ScanCommands
from events import EventHandlers
from storage import load_flags
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

GUILD_ID = discord.Object(id=YOUR_GUILD_ID_HERE)  # Optional: restrict slash command registration

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    await tree.sync()
    print("🌐 Slash commands synced.")

# Fix: /shadow command now passes `bot` and `interaction.user`
@tree.command(name="shadow", description="Open the moderation panel")
@app_commands.checks.has_role("Mover & Shaker")
async def open_shadow_panel(interaction: discord.Interaction):
    await interaction.response.send_message(
        f"🛡️ {interaction.user.mention} activated the `/shadow` panel",
        view=ShadowControlPanel(bot, interaction.user),
        ephemeral=True
    )

# Attach all slash command groups
async def setup_handlers():
    await bot.add_cog(EventHandlers(bot))
    await bot.add_cog(ScanCommands(bot))

# Run async setup using setup_hook
class ShadowBot(commands.Bot):
    async def setup_hook(self):
        await setup_handlers()

if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise ValueError("DISCORD_TOKEN not set in environment variables.")
    bot = ShadowBot(command_prefix="!", intents=intents)
    tree = bot.tree
    bot.run(token)
