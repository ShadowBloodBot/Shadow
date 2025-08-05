# storage.py

import json
import os
import threading

STORAGE_FILE = "flagged_users.json"
LOCK = threading.Lock()


def _load_data() -> dict:
    if not os.path.exists(STORAGE_FILE):
        return {}
    with open(STORAGE_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def _save_data(data: dict):
    with LOCK:
        with open(STORAGE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)


def add_flagged_user(user_id: int, score: int, reason: str):
    data = _load_data()
    data[str(user_id)] = {"score": score, "reason": reason}
    _save_data(data)


def get_flagged_users() -> dict:
    return _load_data()


def clear_flag(user_id: int):
    data = _load_data()
    data.pop(str(user_id), None)
    _save_data(data)
