# storage.py

import json
import os

FILE_PATH = "flagged_users.json"

def load_data():
    if not os.path.exists(FILE_PATH):
        return {}
    with open(FILE_PATH, "r") as f:
        return json.load(f)

def save_data(data):
    with open(FILE_PATH, "w") as f:
        json.dump(data, f, indent=2)

def get_flagged_users():
    return list(load_data().values())

def add_flagged_user(user_id, score, reason="Unknown"):
    data = load_data()
    data[str(user_id)] = {
        "user_id": user_id,
        "severity": score,
        "reason": reason
    }
    save_data(data)

def clear_flag(user_id):
    data = load_data()
    user_id = str(user_id)
    if user_id in data:
        del data[user_id]
        save_data(data)
