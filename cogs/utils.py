# cogs/utils.py — Shared bot utilities

import logging

logger = logging.getLogger("ShadowSyn.Utils")


async def safe_reply(ctx_or_inter, *args, **kwargs):
    """Send a reply via ApplicationContext.respond or Interaction.response, falling back to followup."""
    try:
        if hasattr(ctx_or_inter, "respond"):
            return await ctx_or_inter.respond(*args, **kwargs)
        if hasattr(ctx_or_inter, "response"):
            if not ctx_or_inter.response.is_done():
                return await ctx_or_inter.response.send_message(*args, **kwargs)
            return await ctx_or_inter.followup.send(*args, **kwargs)
    except Exception as exc:
        logger.warning("safe_reply failed: %s", exc)
        return None
