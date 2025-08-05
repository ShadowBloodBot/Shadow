import discord
import logging
import os

LOG_CHANNEL_ID = int(os.getenv("MODERATION_LOG_CHANNEL_ID", 0))  # Set this in Railway

logger = logging.getLogger("shadowbot")
logger.setLevel(logging.INFO)
handler = logging.FileHandler(filename="moderation.log", encoding="utf-8", mode="a")
formatter = logging.Formatter("%(asctime)s:%(levelname)s:%(name)s: %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)


def setup_logging():
    discord.utils.setup_logging(level=logging.INFO, root=False)
    logger.info("Logging is configured.")


async def send_log(message: str, channel: discord.TextChannel = None):
    logger.info(message)
    if channel:
        try:
            await channel.send(f"🧾 `{message}`")
        except Exception as e:
            logger.error(f"Failed to send log message to Discord: {e}")
