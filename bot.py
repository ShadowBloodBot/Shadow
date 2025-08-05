import discord
import os
from dotenv import load_dotenv
from config import ALLOWED_ROLE_IDS, MOD_QUEUE_THREAD_ID
from ui import ShadowControlPanel
from filters import ai_flag_user
from mod_queue import ModQueueView

load_dotenv()

class ShadowBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(intents=intents)
        self.tree = discord.app_commands.CommandTree(self)

    async def setup_hook(self):

        # ===== /shadow =====
        @self.tree.command(name="shadow", description="Open the Shadow Moderation Panel")
        async def shadow(interaction: discord.Interaction):
            user_roles = [role.id for role in interaction.user.roles]
            print(f"[DEBUG] ALLOWED_ROLE_IDS: {ALLOWED_ROLE_IDS}")
            print(f"[DEBUG] USER ROLES: {user_roles}")
            if not any(role_id in user_roles for role_id in ALLOWED_ROLE_IDS):
                await interaction.response.send_message("🚫 You do not have permission to use this command.", ephemeral=True)
                return

            view = ShadowControlPanel(self, interaction.user)
            await interaction.response.send_message("🛡️ Launching Shadow Control Panel...", ephemeral=True)
            try:
                await interaction.channel.send(f"🛡️ {interaction.user.mention} activated the `/shadow` panel", view=view)
            except Exception as e:
                await interaction.followup.send("❌ Could not send panel to this channel.", ephemeral=True)
                print(f"[ERROR] {e}")

        # ===== /scan =====
        @self.tree.command(name="scan", description="Scan all members and flag suspicious ones.")
        @discord.app_commands.checks.has_permissions(administrator=True)
        async def scan(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            guild = interaction.guild
            members = [m async for m in guild.fetch_members(limit=None)]
            total = len(members)
            flagged = []

            try:
                mod_thread = await interaction.client.fetch_channel(MOD_QUEUE_THREAD_ID)
            except Exception as e:
                await interaction.followup.send("❌ Mod queue thread not found or inaccessible.", ephemeral=True)
                print(f"[ERROR] Cannot fetch mod thread: {e}")
                return

            await interaction.edit_original_response(content=f"🔍 Scanning {total} members...")

            for i, member in enumerate(members):
                if member.bot:
                    continue
                try:
                    if await ai_flag_user(member):
                        flagged.append(member)
                except Exception as e:
                    print(f"[SCAN ERROR] {member}: {e}")
                if i % 100 == 0:
                    await interaction.edit_original_response(content=f"🔎 Scanned {i}/{total}...")

            if not flagged:
                await interaction.edit_original_response(content="✅ Scan complete. No suspicious users flagged.")
            else:
                await interaction.edit_original_response(content=f"⚠️ Scan complete. {len(flagged)} users flagged.")
                try:
                    await mod_thread.send("📥 Auto-Scan Flagged Members", view=ModQueueView(flagged))
                except Exception as e:
                    print(f"[THREAD ERROR] {e}")

        await self.tree.sync()
        print("[SYNC] Slash commands registered.")

bot = ShadowBot()

@bot.event
async def on_ready():
    print(f"[READY] Logged in as {bot.user} (ID: {bot.user.id})")

if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise ValueError("❌ DISCORD_TOKEN not set in environment.")
    bot.run(token)
