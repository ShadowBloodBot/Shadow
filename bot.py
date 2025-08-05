import discord
import os
from discord.ext import commands
from dotenv import load_dotenv
from ui import ModerationControlView
from scan import Scan
from events import EventHandlers
from log_utils import setup_logging

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
APPLICATION_ID = os.getenv("APPLICATION_ID")

intents = discord.Intents.all()

class ShadowBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents,
            application_id=APPLICATION_ID
        )

    async def setup_hook(self):
        setup_logging()

        # Register persistent UI view
        self.add_view(ModerationControlView())

        # Register cogs
        await self.add_cog(EventHandlers(self))
        await self.add_cog(Scan(self))

        # Sync global commands
        try:
            await self.tree.sync()
            print("✅ Slash commands synced globally.")
        except Exception as e:
            print(f"[ERROR] Failed to sync commands: {e}")

        print("🛡️ ShadowBot is ready.")

bot = ShadowBot()

@bot.event
async def on_ready():
    print(f"🟢 Logged in as {bot.user} (ID: {bot.user.id})")


@bot.tree.command(name="shadow", description="Open the Shadow moderation control panel.")
async def shadow_panel(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator and not any(role.name == "Mover & Shaker" for role in interaction.user.roles):
        await interaction.response.send_message("🚫 You don’t have permission to use this.", ephemeral=True)
        return

    await interaction.response.send_message("🛠️ Sending moderation panel...", ephemeral=True)
    from ui import send_shadow_panel
    await send_shadow_panel(interaction.channel)


if __name__ == "__main__":
    if TOKEN is None:
        raise EnvironmentError("DISCORD_TOKEN is not set in the environment.")
    bot.run(TOKEN)
