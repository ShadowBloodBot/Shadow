import discord
from discord.ext import commands
from discord import app_commands
import os
from ui import ShadowControlPanel
from events import EventHandlers

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

SHADOW_ROLE_NAMES = ["Mover & Shaker", "SHADOW"]

@bot.event
async def on_ready():
    await tree.sync()
    print(f"✅ Logged in as {bot.user}.")
    bot.add_cog(EventHandlers(bot))  # ✅ Load auto-flagging cog

@tree.command(name="shadow", description="Open the Shadow Moderation Panel")
async def shadow(interaction: discord.Interaction):
    user_roles = [role.name for role in interaction.user.roles]
    if not any(role in SHADOW_ROLE_NAMES for role in user_roles):
        await interaction.response.send_message("🚫 You do not have permission to use this command.", ephemeral=True)
        return

    view = ShadowControlPanel(bot, interaction.user)
    await interaction.response.send_message("Launching Shadow Control Panel...", ephemeral=True)
    await interaction.channel.send(
        f"🛡️ {interaction.user.mention} activated the `/shadow` panel", view=view
    )

if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))
