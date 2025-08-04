import discord
from discord.ext import commands
from filters import get_severity_score, suggest_action
from storage import load_flags, save_flags, log_audit, log_action_with_webhook

class EventHandlers(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return

        score = get_severity_score(member)
        if score >= 5:
            user_id = str(member.id)
            reason = suggest_action(member)
            flags = load_flags()

            if user_id not in flags:
                flags[user_id] = {
                    "username": member.name,
                    "score": score,
                    "reason": reason
                }
                save_flags(flags)
                log_audit("auto_flag", member.id, member.guild.me, reason=reason)
                log_action_with_webhook("auto_flag", member.id, member.guild.me, reason=reason)

                # Post to thread
                try:
                    thread = await member.guild.fetch_channel(1401792224500649994)
                    embed = discord.Embed(title="🚨 Auto-Flagged Member", color=discord.Color.red())
                    embed.add_field(name="User", value=f"{member.mention} (`{member.id}`)", inline=False)
                    embed.add_field(name="Severity Score", value=str(score))
                    embed.add_field(name="AI Suggestion", value=reason)
                    embed.set_footer(text="Flagged by ShadowBot AI")
                    await thread.send(embed=embed)
                except Exception as e:
                    print(f"[AI Flag] Failed to post to thread: {e}")
