import discord
import os

WEBHOOK_URL = os.getenv("MODERATION_WEBHOOK_URL")

async def log_action_with_webhook(action_type: str, user_id: int, guild_id: int, reason: str = None):
    if not WEBHOOK_URL:
        print("[⚠️] Webhook URL not set in environment.")
        return

    try:
        webhook = discord.SyncWebhook.from_url(WEBHOOK_URL)

        embed = discord.Embed(
            title=f"🛡️ Moderation Action: {action_type.upper()}",
            color=discord.Color.red()
        )
        embed.add_field(name="User ID", value=str(user_id), inline=True)
        embed.add_field(name="Guild ID", value=str(guild_id), inline=True)
        if reason:
            embed.add_field(name="Reason", value=reason, inline=False)

        webhook.send(embed=embed, username="ShadowBot Logs")
    except Exception as e:
        print(f"[Webhook Logging Error] {e}")
