import discord
import os
import asyncio
from dotenv import load_dotenv
from config import ALLOWED_ROLE_IDS, MOD_QUEUE_THREAD_ID
from ui import ShadowControlPanel
from filters import ai_flag_user, get_severity_score
from mod_queue import ModQueueView

load_dotenv()

GUILD_ID = 908659586536468540  # ✅ Your confirmed server

class ShadowBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(intents=intents)
        self.tree = discord.app_commands.CommandTree(self)

    async def setup_hook(self):
        # === /shadow ===
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
                print(f"[ERROR] Could not send control panel: {e}")
                await interaction.followup.send("❌ Could not send panel.", ephemeral=True)

        # === Async scan worker runner ===
        async def asyncio_chunked_executor(tasks, max_concurrent=8):
            semaphore = asyncio.Semaphore(max_concurrent)
            results = []

            async def run_task(task_fn):
                async with semaphore:
                    try:
                        return await task_fn()
                    except Exception as e:
                        print(f"[SCAN ERROR] {e}")
                        return None

            await interaction.edit_original_response(content="🔄 Preparing scan...")
            chunks = [run_task(fn) for fn in tasks]
            return await asyncio.gather(*chunks, return_exceptions=False)

        # === /scan ===
        @self.tree.command(name="scan", description="Scan all members and flag suspicious ones.")
        @discord.app_commands.checks.has_permissions(administrator=True)
        async def scan(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            guild = interaction.guild
            members = [m async for m in guild.fetch_members(limit=None)]
            total = len(members)

            await interaction.edit_original_response(content=f"🔍 Scanning {total} members...")
            print(f"[SCAN] Starting scan of {total} members...")

            tasks = []

            for member in members:
                if member.bot:
                    continue

                async def scan_one(m=member):
                    try:
                        flagged = await ai_flag_user(m, self)
                        score = get_severity_score(m)
                        print(f"[SCAN] {m.name}#{m.discriminator} - Score: {score} | Flagged: {flagged}")
                        return m if flagged else None
                    except Exception as e:
                        print(f"[SCAN FAIL] {m}: {e}")
                        return None

                tasks.append(scan_one)

            results = await asyncio_chunked_executor(tasks, max_concurrent=8)
            flagged = [r for r in results if r is not None]

            if not flagged:
                await interaction.edit_original_response(content="✅ Scan complete. No suspicious users flagged.")
            else:
                await interaction.edit_original_response(
                    content=f"⚠️ Scan complete. {len(flagged)} users flagged."
                )
                try:
                    mod_thread = await interaction.client.fetch_channel(MOD_QUEUE_THREAD_ID)
                    await mod_thread.send("📥 Auto-Scan Flagged Members", view=ModQueueView(flagged))
                except Exception as e:
                    print(f"[FALLBACK] Could not post to MOD_QUEUE_THREAD_ID: {e}")
                    await interaction.followup.send(
                        "⚠️ Members flagged, but mod queue thread not found. Check `MOD_QUEUE_THREAD_ID` in your config.",
                        ephemeral=True
                    )

        await self.tree.sync(guild=discord.Object(id=GUILD_ID))
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
