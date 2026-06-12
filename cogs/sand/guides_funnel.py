# cogs/sand/guides_funnel.py — Rebrand SAND Follow crossposts into ShadowSyn guide embeds

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import aiohttp
import discord
from discord.ext import commands

logger = logging.getLogger("ShadowSyn.SAND.GuidesFunnel")

THEME_PRIMARY = 0x2B0B35
TARGET_GUILD_ID = 908659586536468540
GUIDES_CHANNEL_ID = 1514799420602978324
# Back-compat alias used in logs
GUIDES_THREAD_ID = GUIDES_CHANNEL_ID
SAND_GUILD_ID = 1192467643144355910
SAND_GUIDES_CHANNEL_ID = 1294462300027359343
SAND_GUIDES_URL = f"https://discord.com/channels/{SAND_GUILD_ID}/{SAND_GUIDES_CHANNEL_ID}"

PERSIST_DIR = Path(os.getenv("PERSIST_PATH", "/data"))
STATE_PATH = PERSIST_DIR / "sand_guides_funnel.json"

IMAGE_EXT = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"})


def clean_guide_body(body: str) -> list[str]:
    lines: list[str] = []
    for raw in (body or "").replace("\r", "").split("\n"):
        ln = raw.strip()
        if not ln or re.fullmatch(r"[\s,.;:\-–—]+", ln):
            continue
        ln = re.sub(r"^[-•*]\s*", "", ln)
        if ln:
            lines.append(ln)
    return lines


def merge_guide_body(description: str, fields: list[tuple[str, str]] | None = None) -> str:
    parts: list[str] = []
    if description and description.strip():
        parts.append(description.strip())
    for name, value in fields or []:
        if name and value:
            parts.append(f"{name}\n{value}")
        elif value:
            parts.append(value)
    return "\n".join(parts)


def format_guide_description(body: str) -> str:
    """Rewrite guide text as native embed markdown — bullets and bold section headers."""
    lines = clean_guide_body(body)
    if not lines:
        return ""

    blocks: list[str] = []
    for ln in lines:
        if ln.endswith(":") and len(ln) < 120:
            blocks.append(f"**{ln}**")
        else:
            blocks.append(f"• {ln}")
    return _truncate("\n".join(blocks), 4096)


def build_guide_payload(
    *,
    title: str,
    description: str = "",
    fields: list[tuple[str, str]] | None = None,
    image_files: list[discord.File] | None = None,
) -> tuple[discord.Embed, list[discord.File]]:
    """Native Discord embed with rewritten text; images attached separately."""
    display_title = title.replace("📜", "").strip() or "SAND Guide"
    if not title.startswith("📜"):
        display_title = f"📜 {display_title[:248]}"

    body = merge_guide_body(description, fields)
    embed = discord.Embed(
        title=display_title,
        description=format_guide_description(body) or None,
        color=THEME_PRIMARY,
    )
    embed.set_footer(text="SAND Guides · ShadowSyn")

    files = list(image_files or [])
    if files:
        embed.set_image(url=f"attachment://{files[0].filename}")
    return embed, files


def _atomic_write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def _truncate(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _is_image_url(url: str) -> bool:
    if not url or url.startswith("attachment://"):
        return False
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in IMAGE_EXT) or "/attachments/" in path


def _collect_image_urls(message: discord.Message) -> list[str]:
    seen: set[str] = set()
    urls: list[str] = []

    def add(url: str | None) -> None:
        if not url or url in seen or not _is_image_url(url):
            return
        seen.add(url)
        urls.append(url)

    for att in message.attachments:
        if att.content_type and att.content_type.startswith("image/"):
            add(att.url)
        elif att.filename and any(att.filename.lower().endswith(ext) for ext in IMAGE_EXT):
            add(att.url)

    for embed in message.embeds:
        if embed.image and embed.image.url:
            add(embed.image.url)
        if embed.thumbnail and embed.thumbnail.url:
            add(embed.thumbnail.url)

    return urls


def _extract_text(message: discord.Message) -> tuple[str, str, list[tuple[str, str]]]:
    """Return (title, description, fields)."""
    title = ""
    description = (message.content or "").strip()
    fields: list[tuple[str, str]] = []

    for embed in message.embeds:
        if embed.title and not title:
            title = embed.title.strip()
        if embed.description:
            chunk = embed.description.strip()
            if chunk:
                description = f"{description}\n\n{chunk}".strip() if description else chunk

        for field in embed.fields:
            name = (field.name or "").strip()
            value = (field.value or "").strip()
            if name and value:
                fields.append((name, value))

    if not title:
        if description:
            lines = [ln.strip() for ln in description.splitlines() if ln.strip()]
            title = _truncate(lines[0].lstrip("#").strip(), 240)
            if len(lines) > 1:
                description = "\n".join(lines[1:]).strip()
            else:
                description = ""
        else:
            title = "SAND Guide"

    if not title.startswith("📜"):
        title = f"📜 {title[:248]}"

    return title, description, fields


def _build_embed(message: discord.Message) -> tuple[str, str, list[tuple[str, str]]]:
    return _extract_text(message)


def build_guide_embed(
    *,
    title: str,
    description: str = "",
    fields: list[tuple[str, str]] | None = None,
    image_files: list[discord.File] | None = None,
) -> tuple[discord.Embed, list[discord.File]]:
    return build_guide_payload(
        title=title,
        description=description,
        fields=fields,
        image_files=image_files,
    )


class SandGuidesFunnelCog(commands.Cog):
    """Intercept Discord Follow webhook posts and republish as ShadowSyn-branded embeds."""

    def __init__(self, bot: discord.Bot):
        self.bot = bot
        self._session: aiohttp.ClientSession | None = None
        self._processing: set[int] = set()
        self._state = self._load_state()

    def cog_unload(self) -> None:
        if self._session and not self._session.closed:
            asyncio.create_task(self._session.close())

    def _load_state(self) -> dict:
        if STATE_PATH.exists():
            try:
                return json.loads(STATE_PATH.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.error("Corrupt sand guides funnel state: %s", exc)
        return {"processed_ids": []}

    def _save_state(self) -> None:
        ids = self._state.get("processed_ids", [])
        if len(ids) > 5000:
            ids = ids[-5000:]
        self._state["processed_ids"] = ids
        try:
            _atomic_write(STATE_PATH, self._state)
        except Exception as exc:
            logger.error("Failed to save sand guides funnel state: %s", exc)

    def _mark_processed(self, message_id: int) -> None:
        ids: list = self._state.setdefault("processed_ids", [])
        mid = str(message_id)
        if mid not in ids:
            ids.append(mid)
            self._save_state()

    def _already_processed(self, message_id: int) -> bool:
        return str(message_id) in self._state.get("processed_ids", [])

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _download_image(self, url: str, index: int) -> discord.File | None:
        try:
            session = await self._get_session()
            async with session.get(url) as resp:
                if resp.status != 200:
                    logger.warning("Image download failed (%s): %s", resp.status, url[:120])
                    return None
                data = await resp.read()
            name = Path(urlparse(url).path).name or f"guide_{index}.png"
            name = re.sub(r"[^\w.\-]", "_", name)
            if "." not in name:
                name = f"{name}.png"
            return discord.File(BytesIO(data), filename=name)
        except Exception as exc:
            logger.error("Image download error: %s", exc)
            return None

    async def _resolve_guides_destination(
        self, message: discord.Message
    ) -> discord.Thread | discord.TextChannel | None:
        channel = message.channel
        if channel.id == GUIDES_CHANNEL_ID:
            if isinstance(channel, (discord.Thread, discord.TextChannel)):
                return channel

        if isinstance(channel, discord.TextChannel):
            linked = self.bot.get_channel(GUIDES_CHANNEL_ID)
            if linked is None:
                try:
                    linked = await self.bot.fetch_channel(GUIDES_CHANNEL_ID)
                except Exception as exc:
                    logger.error("Could not resolve guides channel %s: %s", GUIDES_CHANNEL_ID, exc)
                    return None
            if isinstance(linked, discord.Thread) and linked.parent_id == channel.id:
                return linked
        return None

    async def _publish_branded(
        self,
        destination: discord.Thread | discord.TextChannel,
        message: discord.Message,
    ) -> None:
        image_files: list[discord.File] = []
        for i, url in enumerate(_collect_image_urls(message)[:10]):
            file = await self._download_image(url, i)
            if file:
                image_files.append(file)

        title, description, fields = _extract_text(message)
        embed, files = build_guide_payload(
            title=title,
            description=description,
            fields=fields,
            image_files=image_files,
        )
        await destination.send(embed=embed, files=files or None)

    async def _consume_webhook_post(self, message: discord.Message) -> None:
        if message.id in self._processing:
            return
        if self._already_processed(message.id):
            return

        destination = await self._resolve_guides_destination(message)
        if destination is None:
            return

        self._processing.add(message.id)
        try:
            await self._publish_branded(destination, message)
            try:
                await message.delete()
            except discord.Forbidden:
                logger.warning(
                    "Cannot delete raw follow message %s — need Manage Messages in guides thread",
                    message.id,
                )
            except discord.NotFound:
                pass
            self._mark_processed(message.id)
            logger.info("Rebranded SAND guide crosspost %s → channel %s", message.id, GUIDES_CHANNEL_ID)
        except Exception as exc:
            logger.error("Failed to rebrand guide message %s: %s", message.id, exc)
        finally:
            self._processing.discard(message.id)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None or message.guild.id != TARGET_GUILD_ID:
            return
        if not message.webhook_id:
            return
        if message.author and message.author.id == self.bot.user.id:
            return
        if message.type not in (discord.MessageType.default, discord.MessageType.reply):
            return

        destination = await self._resolve_guides_destination(message)
        if destination is None:
            return

        has_payload = bool(
            (message.content and message.content.strip())
            or message.embeds
            or message.attachments
        )
        if not has_payload:
            return

        await self._consume_webhook_post(message)


def setup(bot: discord.Bot) -> None:
    bot.add_cog(SandGuidesFunnelCog(bot))
