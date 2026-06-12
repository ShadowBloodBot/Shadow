# cogs/content_filter.py
import logging

import discord
from discord.ext import commands

from content_filter import (
    FILTER_CHANNEL_IDS,
    GENERAL_OPEN_CHANNEL_ID,
    LOBBY_CHANNEL_ID,
    is_protected_hub_panel,
    match_slurs,
    searchable_text,
)

logger = logging.getLogger("ShadowSyn.ContentFilter")

TARGET_GUILD_ID = 908659586536468540


class ContentFilterCog(commands.Cog):
    """Auto-delete slurs in Lobby and General-Open."""

    def __init__(self, bot: discord.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if not message.guild or message.guild.id != TARGET_GUILD_ID:
            return
        if message.channel.id not in FILTER_CHANNEL_IDS:
            return

        if message.embeds and is_protected_hub_panel(message.embeds[0].title):
            return

        text = searchable_text(
            message.content or "",
            embeds=message.embeds,
            attachments=message.attachments,
        )
        terms = match_slurs(text)
        if not terms:
            return

        channel_label = (
            "general-open" if message.channel.id == GENERAL_OPEN_CHANNEL_ID else "lobby"
        )
        try:
            await message.delete()
            logger.info(
                f"Deleted slur message {message.id} in {channel_label} "
                f"by {message.author.id} — matched: {', '.join(terms)}"
            )
        except discord.Forbidden:
            logger.error(
                f"Cannot delete slur message {message.id} in {channel_label} — missing permissions"
            )
        except discord.NotFound:
            pass
        except Exception as e:
            logger.error(f"Slur delete failed for {message.id}: {e}")


def setup(bot: discord.Bot):
    bot.add_cog(ContentFilterCog(bot))
