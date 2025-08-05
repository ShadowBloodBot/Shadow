import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

from mod_commands import ModCommands
from scan_command import Scan
from events import EventHandlers
from ui import ShadowControlPanel

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
APPLICATION_ID = os.getenv("APPLICATION_ID")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

class ShadowBot(commands.Bot):
    async def setup_hook(self):
        await self.add_cog(ModCommands(self))
        await self.add_cog(Scan(self))
        await self.add_cog(EventHandlers(self))
        self.tree.add_command(shadow_panel)
        await self.tree.sync()

@discord.app_commands.command(name="shadow", description="Open the Shadow moderation control panel.")
async def shadow_panel(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("❌ You don't have permission to use this.", ephemeral=True)
        return

    embed, view = await ShadowControlPanel(interaction.client).build(interaction)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

if __name__ == "__main__":
    bot = ShadowBot(command_prefix="!", intents=intents, application_id=APPLICATION_ID)
    import asyncio
    asyncio.run(bot.start(DISCORD_TOKEN))
