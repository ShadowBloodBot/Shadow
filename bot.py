import discord
import os
import asyncio
from discord.ext import commands
from dotenv import load_dotenv

from ui import ShadowControlPanel
from events import EventHandlers
from scan_command import ScanCommands

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} slash command(s).")
    except Exception as e:
        print(f"❌ Sync failed: {e}")


@bot.tree.command(name="shadow", description="Open the Shadow Moderation Panel")
async def shadow_panel(interaction: discord.Interaction):
    allowed_roles = ["Mover & Shaker"]
    if not any(role.name in allowed_roles for role in interaction.user.roles):
        await interaction.response.send_message("🚫 You do not have permission to use this command.", ephemeral=True)
        return

    try:
        await interaction.response.send_message(
            f"🔒 <@{interaction.user.id}> activated the `/shadow` panel",
            view=ShadowControlPanel(bot, interaction.user),
            ephemeral=True
        )
    except Exception as e:
        print(f"[ShadowPanel] Failed to open: {e}")
        await interaction.followup.send("❌ Failed to open Shadow Panel.", ephemeral=True)


async def main():
    async with bot:
        await bot.add_cog(EventHandlers(bot))
        await bot.add_cog(ScanCommands(bot))
        await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
