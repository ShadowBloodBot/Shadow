# storage.py

import json
import os
from datetime import datetime
from typing import List, Dict

FLAG_STORE_FILE = "flagged_users.json"
LOG_FILE = "shadow_logs.txt"

def init_db():
    """Ensure the flagged users storage file exists."""
    if not os.path.exists(FLAG_STORE_FILE):
        with open(FLAG_STORE_FILE, "w") as f:
            json.dump({}, f)

def load_flags() -> Dict[str, dict]:
    """Load flagged users from the storage file."""
    if not os.path.exists(FLAG_STORE_FILE):
        init_db()
    try:
        with open(FLAG_STORE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def save_flags(flags: Dict[str, dict]):
    """Save the full flag dictionary to storage."""
    with open(FLAG_STORE_FILE, "w") as f:
        json.dump(flags, f, indent=2)

def flag_user(user_id: int, severity: int, reason: str = "Unspecified"):
    """Flag a user and store their details."""
    flags = load_flags()
    flags[str(user_id)] = {
        "user_id": user_id,
        "severity": severity,
        "reason": reason,
        "timestamp": datetime.utcnow().isoformat()
    }
    save_flags(flags)

def get_flagged_users() -> List[dict]:
    """Return all flagged users as a list of dicts."""
    return list(load_flags().values())

def clear_flag(user_id: int):
    """Remove a user from the flagged list."""
    flags = load_flags()
    user_id_str = str(user_id)
    if user_id_str in flags:
        del flags[user_id_str]
        save_flags(flags)

def get_flag(user_id: int) -> dict | None:
    """Get the flag data for a specific user."""
    return load_flags().get(str(user_id), None)

def log_action(message: str):
    """Append a timestamped message to the log file."""
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] {message}\n")
