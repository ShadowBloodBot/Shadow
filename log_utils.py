# log_utils.py

import discord
import os
from dotenv import load_dotenv

load_dotenv()

LOG_CHANNEL_ID = int(os.getenv("MODERATION_LOG_CHANNEL", 0))

async def send_log(message: str, channel: discord.TextChannel = None):
    if channel:
        try:
            await channel.send(message)
            return
        except Exception as e:
            print(f"[LOG ERROR] {e}")

    if LOG_CHANNEL_ID:
        try:
            log_channel = channel.guild.get_channel(LOG_CHANNEL_ID) if channel else None
            if not log_channel and channel:
                log_channel = await channel.guild.fetch_channel(LOG_CHANNEL_ID)
            if log_channel:
                await log_channel.send(message)
        except Exception as e:
            print(f"[LOG CHANNEL ERROR] {e}")
    else:
        print(f"[LOG]: {message}")

async def log_case(action: str, target: discord.Member, moderator: discord.User, reason: str = "No reason provided."):
    embed = discord.Embed(
        title=f"🔎 Moderation Action: {action.capitalize()}",
        color=discord.Color.red() if action in ["kick", "ban"] else discord.Color.orange(),
        timestamp=discord.utils.utcnow()
    )
    embed.add_field(name="👤 Target", value=f"{target.mention} (`{target.id}`)", inline=True)
    embed.add_field(name="🛡️ Moderator", value=f"{moderator.mention} (`{moderator.id}`)", inline=True)
    embed.add_field(name="📄 Reason", value=reason, inline=False)
    embed.set_footer(text="ShadowBot Moderation System")

    if LOG_CHANNEL_ID:
        try:
            channel = await moderator.guild.fetch_channel(LOG_CHANNEL_ID)
            await channel.send(embed=embed)
        except Exception as e:
            print(f"[CASE LOG ERROR] {e}")
