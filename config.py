import os

# === Load environment variables ===
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# === Role IDs with access to /shadow panel ===
# Replace with actual role IDs from your server
SHADOW_ROLE_ID = int(os.getenv("SHADOW_ROLE_ID", 0))
MOVER_SHAKER_ROLE_ID = int(os.getenv("MOVER_SHAKER_ROLE_ID", 0))

ALLOWED_ROLE_IDS = [SHADOW_ROLE_ID, MOVER_SHAKER_ROLE_ID]

# === Constants for moderation ===
MOD_QUEUE_THREAD_ID = int(os.getenv("MOD_QUEUE_THREAD_ID", 0))
