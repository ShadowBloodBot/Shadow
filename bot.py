import os
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

from ui import send_shadow_panel
from scan_command import Scan
from mod_commands import ModCommands
from events import EventHandlers

MOD_ROLE_ID = 955600547266822174

load_dotenv()

intents = discord.Intents.all()


class ShadowBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents,
            application_id=os.getenv("APPLICATION_ID"),
        )
        self.synced = False

    async def setup_hook(self):
        self.add_view(ModerationControlView())  # Ensure persistent view registration
        await self.add_cog(EventHandlers(self))
        await self.add_cog(Scan(self))
        await self.add_cog(ModCommands(self))


bot = ShadowBot()


# Global check for role locking all slash commands
@bot.tree.check
async def global_role_check(interaction: discord.Interaction) -> bool:
    return any(role.id == MOD_ROLE_ID for role in interaction.user.roles)


# Global command to open the panel
@bot.tree.command(name="shadow", description="Open the Shadow Moderation Panel.")
async def shadow(interaction: discord.Interaction):
    if not any(role.id == MOD_ROLE_ID for role in interaction.user.roles):
        await interaction.response.send_message("🚫 You don't have access to this panel.", ephemeral=True)
        return

    try:
        await send_shadow_panel(interaction.channel)
        await interaction.response.send_message("✅ Shadow panel deployed.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message("❌ Failed to deploy panel.", ephemeral=True)
        print("[ERROR] Panel deployment failed:", e)


@bot.event
async def on_ready():
    if not bot.synced:
        try:
            await bot.tree.sync()
            bot.synced = True
            print(f"[SYNC] Synced commands for: {bot.user}")
        except Exception as e:
            print(f"[ERROR] Sync failed: {e}")
    print(f"[READY] Logged in as {bot.user}")


if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise EnvironmentError("DISCORD_TOKEN not found in environment.")
    bot.run(token)
