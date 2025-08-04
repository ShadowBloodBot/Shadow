import json
import os
from datetime import datetime
from config import WEBHOOK_URL
from analytics import post_webhook_log

FLAG_FILE = "shadow_flags.json"
AUDIT_LOG = "audit_log.json"
PROBATION_FILE = "probation.json"

def load_flags():
    if not os.path.exists(FLAG_FILE):
        return {}
    with open(FLAG_FILE, "r") as f:
        return json.load(f)

def save_flags(data):
    with open(FLAG_FILE, "w") as f:
        json.dump(data, f, indent=2)

def log_audit(action, user_id, moderator, reason=None):
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "action": action,
        "target_user": str(user_id),
        "moderator": moderator.name,
        "reason": reason or "No reason provided"
    }
    data = []
    if os.path.exists(AUDIT_LOG):
        with open(AUDIT_LOG, "r") as f:
            try:
                data = json.load(f)
            except:
                data = []
    data.append(log_entry)
    with open(AUDIT_LOG, "w") as f:
        json.dump(data, f, indent=2)

def log_action_with_webhook(action, user_id, moderator, reason=None):
    content = (
        f"🛡️ **Moderation Action**\n"
        f"• **Action:** {action}\n"
        f"• **User ID:** {user_id}\n"
        f"• **By:** {moderator.name}\n"
        f"• **Reason:** {reason or 'No reason provided'}\n"
        f"• **Time:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
    )
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(post_webhook_log(WEBHOOK_URL, content))
        else:
            loop.run_until_complete(post_webhook_log(WEBHOOK_URL, content))
    except Exception as e:
        print(f"Failed to send webhook: {e}")

def add_probation(user_id, reason):
    data = {}
    if os.path.exists(PROBATION_FILE):
        with open(PROBATION_FILE, "r") as f:
            try:
                data = json.load(f)
            except:
                data = {}
    data[str(user_id)] = {"reason": reason, "time": datetime.utcnow().isoformat()}
    with open(PROBATION_FILE, "w") as f:
        json.dump(data, f, indent=2)

def load_probation():
    if not os.path.exists(PROBATION_FILE):
        return {}
    with open(PROBATION_FILE, "r") as f:
        return json.load(f)
