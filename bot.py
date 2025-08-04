import discord
import os
from ui import ShadowControlPanel
from config import SHADOW_ROLE_ID

intents = discord.Intents.all()
bot = discord.Bot(intents=intents)  # ✅ Fixed: discord.Bot for slash commands

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}.")

@bot.slash_command(name="shadow", description="Open the Shadow Moderation Panel")
async def shadow(ctx: discord.ApplicationContext):
    if SHADOW_ROLE_ID not in [role.id for role in ctx.author.roles]:
        await ctx.respond("🚫 You do not have permission to use this command.", ephemeral=True)
        return

    view = ShadowControlPanel(bot, ctx.author)
    await ctx.respond("Launching Shadow Control Panel...", ephemeral=True)
    await ctx.channel.send(f"🛡️ {ctx.author.mention} activated the `/Shadow` panel", view=view)

if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))
