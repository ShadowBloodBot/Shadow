import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
APPLICATION_ID = os.getenv("APPLICATION_ID")
MOD_LOG_WEBHOOK = os.getenv("MOD_LOG_WEBHOOK")  # Optional for logging
MOD_QUEUE_THREAD_ID = int(os.getenv("MOD_QUEUE_THREAD_ID", 0))  # Optional thread/channel ID fallback
