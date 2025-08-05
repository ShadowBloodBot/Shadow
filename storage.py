import json
import os

STORAGE_FILE = "flagged_users.json"

def init_db():
    if not os.path.exists(STORAGE_FILE):
        with open(STORAGE_FILE, "w") as f:
            json.dump([], f)

def get_flagged_users():
    try:
        with open(STORAGE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []

def add_flagged_user(user_id: int, severity: int, reason: str = "Unknown"):
    flagged = get_flagged_users()
    if not any(u["user_id"] == user_id for u in flagged):
        flagged.append({"user_id": user_id, "severity": severity, "reason": reason})
        with open(STORAGE_FILE, "w") as f:
            json.dump(flagged, f)

def clear_flag(user_id: int):
    flagged = get_flagged_users()
    flagged = [u for u in flagged if u["user_id"] != user_id]
    with open(STORAGE_FILE, "w") as f:
        json.dump(flagged, f)
