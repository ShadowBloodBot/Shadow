import logging
import os
from datetime import datetime

LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, f"shadow_{datetime.utcnow().strftime('%Y-%m-%d')}.log")

def setup_logging(logger: logging.Logger):
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)

    logger.setLevel(logging.INFO)

    # Console handler
    console_handler = logging.StreamHandler()
    console_format = logging.Formatter("[%(asctime)s] %(levelname)s - %(message)s", datefmt="%H:%M:%S")
    console_handler.setFormatter(console_format)

    # File handler
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_format = logging.Formatter("[%(asctime)s] %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    file_handler.setFormatter(file_format)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

async def send_log(message: str, channel: discord.TextChannel = None):
    """
    Optionally send a log message to a Discord channel while always logging to file.
    """
    logging.getLogger("shadowbot").info(message)

    if channel:
        try:
            await channel.send(f"📝 {message}")
        except Exception as e:
            logging.getLogger("shadowbot").error(f"Failed to send log message to Discord: {e}")
