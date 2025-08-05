import json
import os

FLAGGED_USERS_FILE = "flagged_users.json"

def _load_data():
    if not os.path.exists(FLAGGED_USERS_FILE):
        with open(FLAGGED_USERS_FILE, "w") as f:
            json.dump({}, f)
    with open(FLAGGED_USERS_FILE, "r") as f:
        return json.load(f)

def _save_data(data):
    with open(FLAGGED_USERS_FILE, "w") as f:
        json.dump(data, f, indent=4)

def add_flagged_user(guild_id: int, user_id: int, reason: str, severity: int):
    data = _load_data()
    guild_id = str(guild_id)
    user_id = str(user_id)
    if guild_id not in data:
        data[guild_id] = {}
    data[guild_id][user_id] = {"reason": reason, "severity": severity}
    _save_data(data)

def get_flagged_users(guild_id: int):
    data = _load_data()
    return data.get(str(guild_id), {})

def clear_flag(guild_id: int, user_id: int):
    data = _load_data()
    guild_id = str(guild_id)
    user_id = str(user_id)
    if guild_id in data and user_id in data[guild_id]:
        del data[guild_id][user_id]
        if not data[guild_id]:
            del data[guild_id]
        _save_data(data)
