import os

# === Load environment variables ===
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# === Role access control (update .env to match real IDs)
SHADOW_ROLE_ID = int(os.getenv("SHADOW_ROLE_ID", 0))
MOVER_SHAKER_ROLE_ID = int(os.getenv("MOVER_SHAKER_ROLE_ID", 0))
ALLOWED_ROLE_IDS = [SHADOW_ROLE_ID, MOVER_SHAKER_ROLE_ID]

# === Thread for mod-queue output
MOD_QUEUE_THREAD_ID = int(os.getenv("MOD_QUEUE_THREAD_ID", 0))
