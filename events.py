import discord
from discord.ext import commands
from filters import score_member
from storage import add_flagged_user
from log_utils import send_log

class EventHandlers(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"✅ Logged in as {self.bot.user}")
        from storage import init_db
        await init_db()

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        score = score_member(member)
        if score >= 3:
            await add_flagged_user(member.guild.id, member.id, score)
            print(f"[FLAG] {member} auto-flagged on join (score={score})")

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot:
            return
        content = message.content or "*[embed or attachment]*"
        log = f"🗑️ Message deleted in <#{message.channel.id}> by {message.author.mention}:\n```{content}```"
        await send_log(log)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.content == after.content or before.author.bot:
            return
        log = (
            f"✏️ Message edited in <#{before.channel.id}> by {before.author.mention}:\n"
            f"**Before:** ```{before.content}```\n**After:** ```{after.content}```"
        )
        await send_log(log)
