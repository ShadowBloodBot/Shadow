# storage.py

import sqlite3
from typing import List, Optional, Tuple
import discord
import os
import datetime

DB_FILE = "shadow.db"


def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # Table for flagged users
    c.execute("""
        CREATE TABLE IF NOT EXISTS flagged_users (
            user_id TEXT PRIMARY KEY,
            username TEXT,
            discriminator TEXT,
            severity_score INTEGER,
            suggested_action TEXT,
            flagged_at TEXT
        )
    """)

    conn.commit()
    conn.close()


def save_flagged_user(user: discord.User, severity_score: int, suggested_action: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("""
        INSERT OR REPLACE INTO flagged_users (
            user_id, username, discriminator, severity_score, suggested_action, flagged_at
        ) VALUES (?, ?, ?, ?, ?, ?)
    """, (
        str(user.id),
        user.name,
        user.discriminator,
        severity_score,
        suggested_action,
        datetime.datetime.utcnow().isoformat()
    ))

    conn.commit()
    conn.close()


def get_flagged_users(min_score: int = 0) -> List[Tuple[str, str, str, int, str, str]]:
    """Returns a list of flagged users with optional minimum score filtering."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("""
        SELECT user_id, username, discriminator, severity_score, suggested_action, flagged_at
        FROM flagged_users
        WHERE severity_score >= ?
        ORDER BY severity_score DESC
    """, (min_score,))

    results = c.fetchall()
    conn.close()
    return results


async def send_log(message: str, channel: Optional[discord.TextChannel] = None):
    """Sends a message to a specified log channel and prints to console."""
    print(f"[LOG] {message}")
    if channel:
        try:
            await channel.send(f"📋 {message}")
        except Exception as e:
            print(f"[ERROR] Failed to send log to channel: {e}")


def get_flagged_user_by_id(user_id: int) -> Optional[Tuple[str, str, str, int, str, str]]:
    """Returns a single flagged user by Discord ID."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("""
        SELECT user_id, username, discriminator, severity_score, suggested_action, flagged_at
        FROM flagged_users
        WHERE user_id = ?
    """, (str(user_id),))

    result = c.fetchone()
    conn.close()
    return result
