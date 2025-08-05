import os
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

from ui import ModerationControlView
from scan import Scan
from events import EventHandlers
from filters import get_severity_score
from storage import get_flagged_users

# Load environment variables
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
APPLICATION_ID = os.getenv("APPLICATION_ID")
MOD_ROLE_ID = 955600547266822174

class ShadowBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=discord.Intents.all(),
            application_id=APPLICATION_ID
        )
        self.synced = False

    async def setup_hook(self):
        # Register persistent UI view (MUST have custom_ids and no timeout)
        self.add_view(ModerationControlView())

        # Register command Cogs
        await self.add_cog(EventHandlers(self))
        await self.add_cog(Scan(self))

        # Sync commands on startup
        if not self.synced:
            self.tree.copy_global_to(guild=None)  # Use global if you want server-wide
            await self.tree.sync()
            self.synced = True

bot = ShadowBot()

# Slash command: /shadow
@bot.tree.command(name="shadow", description="Open the Shadow Moderation Panel")
@app_commands.checks.has_role(MOD_ROLE_ID)
async def shadow(interaction: discord.Interaction):
    from ui import send_shadow_panel
    await interaction.response.defer(ephemeral=True)
    await send_shadow_panel(interaction.channel)
    await interaction.followup.send("🛡️ Shadow Panel sent to this channel.", ephemeral=True)

# Global error handler for all command check failures
@shadow.error
async def shadow_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.errors.MissingRole):
        await interaction.response.send_message("🚫 You don't have permission to use this.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ An error occurred.", ephemeral=True)
        print(f"[ERROR] /shadow: {error}")

# Run bot
if __name__ == "__main__":
    if not TOKEN:
        raise ValueError("DISCORD_TOKEN not set in .env")
    bot.run(TOKEN)
