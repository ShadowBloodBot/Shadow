import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
from ui import ShadowControlPanel
from config import SHADOW_ROLE_ID

load_dotenv()

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"[READY] Logged in as {bot.user} (ID: {bot.user.id})")

@bot.slash_command(name="shadow", description="Open the Shadow Moderation Panel")
async def shadow(ctx: discord.ApplicationContext):
    if SHADOW_ROLE_ID not in [role.id for role in ctx.author.roles]:
        await ctx.respond("🚫 You do not have permission to use this command.", ephemeral=True)
        return

    view = ShadowControlPanel(bot, ctx.author)
    await ctx.respond("🛡️ Launching Shadow Control Panel...", ephemeral=True)
    try:
        await ctx.channel.send(f"🛡️ {ctx.author.mention} activated the `/shadow` panel", view=view)
    except Exception as e:
        await ctx.respond("❌ Failed to launch panel in this channel.", ephemeral=True)
        print(f"[ERROR] Failed to send Shadow Control Panel: {e}")

if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise ValueError("❌ DISCORD_TOKEN is not set in the environment.")
    bot.run(token)
