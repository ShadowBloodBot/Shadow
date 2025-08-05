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
    print(f"✅ Logged in as {bot.user}.")

@bot.slash_command(name="shadow", description="Open the Shadow Moderation Panel")
async def shadow(ctx: discord.ApplicationContext):
    if SHADOW_ROLE_ID not in [role.id for role in ctx.author.roles]:
        await ctx.respond("❌ You do not have permission to use this command.", ephemeral=True)
        return

    view = ShadowControlPanel(bot, ctx.author)

    try:
        await ctx.respond("🧠 Opening the Shadow Moderation Panel...\nPlease check the Mod Queue for flagged users.", ephemeral=True)
        await ctx.send(f"🛡️ {ctx.author.mention} activated the `/shadow` panel.", view=view)
    except discord.Forbidden:
        await ctx.respond("❌ Bot lacks permission to send messages in this channel.", ephemeral=True)

if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if token:
        bot.run(token)
    else:
        print("❌ DISCORD_TOKEN not found in environment.")
