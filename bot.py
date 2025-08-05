import discord
import os
from dotenv import load_dotenv
from config import SHADOW_ROLE_ID
from ui import ShadowControlPanel

load_dotenv()

class ShadowBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(intents=intents)
        self.tree = discord.app_commands.CommandTree(self)

    async def setup_hook(self):
        # Register /shadow command
        @self.tree.command(name="shadow", description="Open the Shadow Moderation Panel")
        async def shadow(interaction: discord.Interaction):
            if SHADOW_ROLE_ID not in [role.id for role in interaction.user.roles]:
                await interaction.response.send_message("🚫 You do not have permission to use this command.", ephemeral=True)
                return

            view = ShadowControlPanel(self, interaction.user)
            await interaction.response.send_message("🛡️ Launching Shadow Control Panel...", ephemeral=True)
            try:
                await interaction.channel.send(f"🛡️ {interaction.user.mention} activated the `/shadow` panel", view=view)
            except Exception as e:
                print(f"[ERROR] Couldn't post panel: {e}")
                await interaction.followup.send("❌ Failed to launch panel.", ephemeral=True)

        # Sync the command tree to all guilds
        await self.tree.sync()
        print("[SYNC] Slash commands registered.")


bot = ShadowBot()

@bot.event
async def on_ready():
    print(f"[READY] Logged in as {bot.user} (ID: {bot.user.id})")

if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise ValueError("❌ DISCORD_TOKEN not set in .env or Railway.")
    bot.run(token)
