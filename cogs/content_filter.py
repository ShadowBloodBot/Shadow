# cogs/content_filter.py
import logging

import discord
from discord.ext import commands

from cogs.guild_registry import ch_id, is_registered_guild
from content_filter import is_protected_hub_panel, match_slurs, searchable_text

logger = logging.getLogger("ShadowSyn.ContentFilter")


class ContentFilterCog(commands.Cog):
    """Auto-delete slurs in Lobby and General-Open on ShadowMain and ShadowBackup."""

    def __init__(self, bot: discord.Bot):
        self.bot = bot

    def _filter_channel_ids(self, guild_id: int) -> set[int]:
        ids = set()
        for key in ("lobby", "general_open"):
            cid = ch_id(guild_id, key)
            if cid:
                ids.add(cid)
        return ids

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if not message.guild or not is_registered_guild(message.guild.id):
            return
        filter_ids = self._filter_channel_ids(message.guild.id)
        if message.channel.id not in filter_ids:
            return

        if message.embeds and is_protected_hub_panel(message.embeds[0].title or ""):
            return

        text = searchable_text(
            message.content or "",
            embeds=message.embeds,
            attachments=message.attachments,
        )
        terms = match_slurs(text)
        if not terms:
            return

        general_id = ch_id(message.guild.id, "general_open")
        channel_label = "general-open" if message.channel.id == general_id else "lobby"
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
