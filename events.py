import discord
from discord.ext import commands
from storage import init_db
from log_utils import send_log


class EventHandlers(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        try:
            await init_db()
            print("🗃️ Database initialized successfully.")
        except Exception as e:
            print(f"[ERROR] Failed to initialize database: {e}")
            await send_log(f"❌ Failed to initialize database: `{e}`")

        print(f"✅ Bot is ready: {self.bot.user} (ID: {self.bot.user.id})")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        from filters import score_member, get_severity_score, suggest_action
        from config import MOD_QUEUE_THREAD_ID

        score = await score_member(member)
        severity = get_severity_score(score)
        suggestion = suggest_action(severity)

        if severity > 0:
            try:
                thread = await member.guild.fetch_channel(MOD_QUEUE_THREAD_ID)
                await thread.send(
                    f"🚨 **New member flagged:** {member.mention}\n"
                    f"**Severity:** `{severity}`\n"
                    f"**Suggested Action:** {suggestion}"
                )
                await send_log(f"⚠️ Member `{member}` auto-scanned and flagged with severity {severity}.")
            except Exception as e:
                print(f"[ERROR] Could not post to mod queue: {e}")
                await send_log(f"❌ Could not post flagged member to mod queue: `{e}`")

