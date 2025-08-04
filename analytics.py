import discord
import platform
from datetime import datetime

# Attempt to import psutil, fallback if not installed
try:
    import psutil
    USE_PSUTIL = True
except ImportError:
    USE_PSUTIL = False

def get_bot_stats(bot):
    stats = {
        "users": sum(1 for _ in bot.get_all_members()),
        "guilds": len(bot.guilds),
        "uptime": datetime.utcnow().isoformat(),
        "platform": platform.system(),
    }

    if USE_PSUTIL:
        stats["cpu"] = psutil.cpu_percent()
        stats["memory"] = psutil.virtual_memory().percent
    else:
        stats["cpu"] = "N/A"
        stats["memory"] = "N/A"

    return stats

async def post_webhook_log(webhook_url, content):
    try:
        webhook = discord.SyncWebhook.from_url(webhook_url)
        webhook.send(content)
    except Exception as e:
        print(f"Webhook error: {e}")
