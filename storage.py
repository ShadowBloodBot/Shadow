import json
import os
from datetime import datetime

DATA_FILE = "flagged_users.json"
LOG_FILE = "mod_logs.json"

def ensure_file_exists(path, default_data):
    if not os.path.exists(path):
        with open(path, "w") as f:
            json.dump(default_data, f, indent=4)

# Ensure storage files exist
ensure_file_exists(DATA_FILE, {})
ensure_file_exists(LOG_FILE, [])

def get_flagged_users() -> dict:
    """Return all currently flagged users from the mod queue."""
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        print("[ERROR] Failed to load flagged users:", e)
        return {}

def add_flagged_user(user_id: int, score: int, reason: str):
    """Add a user to the flagged list."""
    flagged = get_flagged_users()
    flagged[str(user_id)] = {
        "score": score,
        "reason": reason,
        "timestamp": datetime.utcnow().isoformat()
    }
    with open(DATA_FILE, "w") as f:
        json.dump(flagged, f, indent=4)

def remove_flagged_user(user_id: int):
    """Remove a user from the flagged list."""
    flagged = get_flagged_users()
    if str(user_id) in flagged:
        del flagged[str(user_id)]
        with open(DATA_FILE, "w") as f:
            json.dump(flagged, f, indent=4)

async def log_case(action: str, user, mod, reason: str):
    """Append a moderation case log entry."""
    try:
        case = {
            "timestamp": datetime.utcnow().isoformat(),
            "action": action,
            "user_id": user.id,
            "user_tag": str(user),
            "mod_id": mod.id,
            "mod_tag": str(mod),
            "reason": reason
        }
        logs = []
        with open(LOG_FILE, "r") as f:
            logs = json.load(f)

        logs.append(case)

        with open(LOG_FILE, "w") as f:
            json.dump(logs, f, indent=4)

    except Exception as e:
        print("[ERROR] Failed to log moderation case:", e)
