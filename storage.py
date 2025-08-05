import aiosqlite
import os
import asyncio

DB_PATH = "shadowbot.db"

# Run this once on startup to ensure tables exist
async def init_db():
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS flagged_users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    severity INTEGER,
                    reason TEXT,
                    flagged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS mod_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    action TEXT,
                    reason TEXT,
                    taken_by TEXT,
                    action_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.commit()
            print("✅ Database tables ensured.")
    except Exception as e:
        print(f"[ERROR] init_db(): {e}")
        raise

# Example function to add a flagged user
async def add_flagged_user(user_id: int, username: str, severity: int, reason: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO flagged_users (user_id, username, severity, reason) VALUES (?, ?, ?, ?)",
            (user_id, username, severity, reason)
        )
        await db.commit()

# Example function to log moderation actions
async def log_mod_action(user_id: int, action: str, reason: str, taken_by: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO mod_actions (user_id, action, reason, taken_by) VALUES (?, ?, ?, ?)",
            (user_id, action, reason, taken_by)
        )
        await db.commit()

# Optional: fetch flagged users
async def get_all_flagged_users():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM flagged_users") as cursor:
            return await cursor.fetchall()
