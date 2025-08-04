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

                # Optional mod-logs embed
                modlog = discord.utils.get(member.guild.text_channels, name="mod-logs")
                if modlog:
                    embed = discord.Embed(title="🚨 Auto-Flagged User Joined", color=discord.Color.red())
                    embed.add_field(name="User", value=f"{member.mention} (`{member.id}`)", inline=False)
                    embed.add_field(name="Severity Score", value=str(score))
                    embed.add_field(name="AI Suggestion", value=reason)
                    embed.set_footer(text="ShadowBot AI Flagging")
                    await modlog.send(embed=embed)
