import json
import os
from datetime import datetime

FLAG_FILE = "shadow_flags.json"
AUDIT_LOG = "audit_log.json"

def load_flags():
    if not os.path.exists(FLAG_FILE):
        return {}
    with open(FLAG_FILE, "r") as f:
        return json.load(f)

def save_flags(data):
    with open(FLAG_FILE, "w") as f:
        json.dump(data, f, indent=2)

def log_audit(action, user_id, moderator):
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "action": action,
        "target_user": user_id,
        "moderator": moderator.name
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

from config import WEBHOOK_URL
from analytics import post_webhook_log

def log_action_with_webhook(action, user_id, moderator):
    content = f"[{datetime.utcnow().isoformat()}] Action: {action} | Target: {user_id} | By: {moderator.name}"
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(post_webhook_log(WEBHOOK_URL, content))
        else:
            loop.run_until_complete(post_webhook_log(WEBHOOK_URL, content))
    except Exception as e:
        print(f"Failed to send webhook: {e}")

PROBATION_FILE = "probation.json"

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
