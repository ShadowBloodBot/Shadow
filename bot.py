# bot.py

import discord
import os
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
from ui import ModerationControlView
from scan import Scan
from events import EventHandlers

MOD_ROLE_ID = 955600547266822174  # Role allowed to access /shadow

intents = discord.Intents.all()

class ShadowBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        self.add_view(ModerationControlView())  # Persistent control panel
        self.tree.add_command(shadow_panel)     # Register slash command

        await self.add_cog(Scan(self))
        await self.add_cog(EventHandlers(self))

        try:
            await self.tree.sync()
            print("[SYNC] Slash commands synced.")
        except Exception as e:
            print(f"[SYNC ERROR] {e}")

# Slash command to open the Shadow moderation panel
@app_commands.command(name="shadow", description="Open the Shadow moderation panel.")
async def shadow_panel(interaction: discord.Interaction):
    if not any(role.id == MOD_ROLE_ID for role in interaction.user.roles):
        await interaction.response.send_message("🚫 You don't have permission to use this.", ephemeral=True)
        return

    try:
        await interaction.response.send_message("🛡️ Shadow Moderation Panel", view=ModerationControlView(), ephemeral=True)
    except Exception as e:
        print(f"[SHADOW CMD ERROR] {e}")
        await interaction.response.send_message("❌ Failed to open moderation panel.", ephemeral=True)

# Load .env and run
if __name__ == "__main__":
    load_dotenv()
    token = os.getenv("DISCORD_TOKEN")

    if not token:
        raise ValueError("DISCORD_TOKEN not found in environment.")

    bot = ShadowBot()
    bot.run(token)
