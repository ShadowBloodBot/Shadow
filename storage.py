import aiosqlite

DB_NAME = "shadowbot.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS flagged_users (
            guild_id INTEGER,
            user_id INTEGER,
            score INTEGER,
            PRIMARY KEY (guild_id, user_id)
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS cases (
            case_id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            user_id INTEGER,
            mod_id INTEGER,
            action TEXT,
            reason TEXT,
            timestamp TEXT
        )
        """)
        await db.commit()

async def add_flagged_user(guild_id: int, user_id: int, score: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("REPLACE INTO flagged_users (guild_id, user_id, score) VALUES (?, ?, ?)", (guild_id, user_id, score))
        await db.commit()

async def fetch_flagged_users(guild_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT user_id, score FROM flagged_users WHERE guild_id = ?", (guild_id,))
        rows = await cursor.fetchall()
        return [{"user_id": row[0], "score": row[1]} for row in rows]

async def clear_flag(guild_id: int, user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM flagged_users WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
        await db.commit()

async def log_case(action: str, user: discord.Member, mod: discord.Member, reason: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO cases (guild_id, user_id, mod_id, action, reason, timestamp) VALUES (?, ?, ?, ?, ?, datetime('now'))",
            (user.guild.id, user.id, mod.id, action, reason)
        )
        await db.commit()
