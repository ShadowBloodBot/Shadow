"""Shared slur detection for live moderation and ShadowAdmin cleanup scripts."""
import re

LOBBY_CHANNEL_ID = 974113723188912218
GENERAL_OPEN_CHANNEL_ID = 956725685014134785

FILTER_CHANNEL_IDS = frozenset({LOBBY_CHANNEL_ID, GENERAL_OPEN_CHANNEL_ID})

HUB_PANEL_TITLE = "Welcome -ShadowSyn-"

# Whole-word slurs + jew-prefix words (jew, jews, jewish) — excludes "jewelry".
SLUR_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("nigger", re.compile(r"\bniggers?\b", re.IGNORECASE)),
    ("faggot", re.compile(r"\bfaggots?\b", re.IGNORECASE)),
    ("jew", re.compile(r"\bjew(?!elry\b)\w*\b", re.IGNORECASE)),
]


def searchable_text(content: str, *, embeds=None, attachments=None) -> str:
    parts: list[str] = []
    if content:
        parts.append(content)
    for embed in embeds or []:
        if isinstance(embed, dict):
            for key in ("title", "description"):
                val = embed.get(key)
                if val:
                    parts.append(val)
            for field in embed.get("fields") or []:
                for key in ("name", "value"):
                    val = field.get(key)
                    if val:
                        parts.append(val)
        else:
            for attr in ("title", "description"):
                val = getattr(embed, attr, None)
                if val:
                    parts.append(str(val))
            for field in getattr(embed, "fields", None) or []:
                for attr in ("name", "value"):
                    val = getattr(field, attr, None)
                    if val:
                        parts.append(str(val))
    for attachment in attachments or []:
        filename = attachment.get("filename") if isinstance(attachment, dict) else getattr(attachment, "filename", None)
        if filename:
            parts.append(filename)
    return "\n".join(parts)


def match_slurs(text: str) -> list[str]:
    if not text or not text.strip():
        return []
    matched: list[str] = []
    for label, pattern in SLUR_PATTERNS:
        if pattern.search(text):
            matched.append(label)
    return matched


def is_protected_hub_panel(title: str | None) -> bool:
    return (title or "") == HUB_PANEL_TITLE
