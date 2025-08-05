import os
import discord
import aiohttp
from dotenv import load_dotenv
load_dotenv()

MOD_LOG_WEBHOOK = os.getenv("MOD_LOG_WEBHOOK")  # Optional

async def send_log(message: str):
    if not MOD_LOG_WEBHOOK:
        return
    try:
        async with aiohttp.ClientSession() as session:
            webhook = discord.Webhook.from_url(MOD_LOG_WEBHOOK, session=session)
            await webhook.send(message)
    except Exception as e:
        print(f"[LOG ERROR] Failed to send webhook log: {e}")
