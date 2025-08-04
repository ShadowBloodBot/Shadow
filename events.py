# events.py

import discord
from discord.ext import commands
from filters import score_member, get_severity_score, suggest_action

MOD_QUEUE_THREAD_ID = 1401792224500649994

class EventHandlers(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return

        try:
            user = await self.bot.fetch_user(member.id)
        except Exception:
            user = member  # fallback if API call fails

        score, reason = score_member(member, user)

        if score >= 3:
            severity = get_severity_score(score)
            suggested = suggest_action(score)

            try:
                mod_thread = await member.guild.fetch_channel(MOD_QUEUE_THREAD_ID)
                await mod_thread.send(
                    f"{severity} **New Member Flagged:** {member.mention}\n"
                    f"Score: {score}\n"
                    f"Reason: {reason}\n"
                    f"Suggested Action: {suggested}\n"
                    f"Account Created: <t:{int(member.created_at.timestamp())}:D>"
                )
            except Exception as e:
                print(f"[ERROR] Failed to post to mod queue: {e}")

        else:
            print(f"[INFO] New member {member.name} scored clean ({score})")

def register_events(bot):
    bot.add_cog(EventHandlers(bot))
