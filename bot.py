import discord
import os
import asyncio
from discord.ext import commands
from dotenv import load_dotenv
from log_utils import send_log
from ui import ShadowControlPanel
from mod_commands import ModCommands
from scan_command import Scan
from events import EventHandlers

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
MODERATOR_ROLE_ID = 955600547266822174

class ShadowBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.add_cog(ModCommands(self))
        await self.add_cog(Scan(self))
        await self.add_cog(EventHandlers(self))
        self.tree.add_command(shadow_panel)
        await self.tree.sync()

@discord.app_commands.checks.has_role(MODERATOR_ROLE_ID)
@discord.app_commands.command(name="shadow", description="Open the Shadow moderation control panel.")
async def shadow_panel(interaction: discord.Interaction):
    panel = ShadowControlPanel(interaction.client)
    embed, view = await panel.build(interaction.channel)
    try:
        await interaction.response.send_message(embed=embed, view=view, ephemeral=False)
    except Exception as e:
        await send_log(f"[SHADOW PANEL ERROR] {e}")
        await interaction.followup.send("❌ Failed to load panel.", ephemeral=True)

@shadow_panel.error
async def shadow_panel_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    if isinstance(error, discord.app_commands.errors.MissingRole):
        await interaction.response.send_message("❌ You need the Moderator role to use this command.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ An error occurred.", ephemeral=True)
        await send_log(f"[SHADOW COMMAND ERROR] {error}")

if __name__ == "__main__":
    bot = ShadowBot()
    asyncio.run(bot.start(DISCORD_TOKEN))
