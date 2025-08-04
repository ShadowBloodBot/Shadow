import os
import discord
from datetime import datetime

# ✅ Get the webhook URL from Railway environment variables
webhook_url = os.getenv("WEBHOOK_URL")
webhook = discord.SyncWebhook.from_url(webhook_url) if webhook_url else None

# 📜 Save actions to log file
def log_audit(action_type, user_id, actor=None, reason=None):
    timestamp = datetime.utcnow().isoformat()
    log_entry = f"[{timestamp}] ACTION: {action_type} | USER: {user_id}"
    if actor:
        log_entry += f" | BY: {actor}"
    if reason:
        log_entry += f" | REASON: {reason}"

    try:
        with open("audit.log", "a") as f:
            f.write(log_entry + "\n")
    except Exception as e:
        print(f"Failed to write audit log: {e}")

# 🧾 Send webhook log to Discord mod channel
def log_action_with_webhook(action_type, user_id, guild, reason=None):
    if not webhook:
        print("Webhook URL not set.")
        return

    try:
        embed = discord.Embed(
            title=f"🛡️ Moderation Event: {action_type}",
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="User ID", value=str(user_id), inline=False)
        embed.add_field(name="Server", value=guild.name, inline=False)
        if reason:
            embed.add_field(name="Reason", value=reason, inline=False)

        embed.set_footer(text="ShadowBot Logging System")
        webhook.send(embed=embed)
    except Exception as e:
        print(f"Failed to send webhook log: {e}")
