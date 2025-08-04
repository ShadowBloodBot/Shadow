import discord
import platform
import psutil
from datetime import datetime

def get_bot_stats(bot):
    stats = {
        "users": sum(1 for _ in bot.get_all_members()),
        "guilds": len(bot.guilds),
        "uptime": datetime.utcnow().isoformat(),
        "platform": platform.system(),
        "cpu": psutil.cpu_percent(),
        "memory": psutil.virtual_memory().percent
    }
    return stats

async def post_webhook_log(webhook_url, content):
    try:
        webhook = discord.SyncWebhook.from_url(webhook_url)
        webhook.send(content)
    except Exception as e:
        print(f"Webhook error: {e}")
