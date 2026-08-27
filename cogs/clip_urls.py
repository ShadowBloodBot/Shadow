"""Clip URL allowlist — no Discord imports (unit-testable)."""
from __future__ import annotations

import re
from urllib.parse import urlparse, urlunparse

MEDAL_HOST_RE = re.compile(r"^https://(?:www\.)?medal\.tv/", re.I)
MEDAL_CLIP_PATH_RE = re.compile(
    r"(?:"
    r"clip/[\w-]+"
    r"|clips/[\w-]+"
    r"|games/[\w-]+/clips?/[\w-]+"
    r")",
    re.I,
)
YOUTUBE_URL_RE = re.compile(
    r"^https://(?:www\.|m\.)?(?:"
    r"youtube\.com/watch\?v=[\w-]{11}(?:[&?][^\s]*)?"
    r"|youtu\.be/[\w-]{11}(?:[?&][^\s]*)?"
    r"|youtube\.com/shorts/[\w-]{11}(?:[?&][^\s]*)?"
    r"|youtube\.com/clip/[\w-]+(?:[?&][^\s]*)?"
    r"|youtube\.com/live/[\w-]{11}(?:[?&][^\s]*)?"
    r")$",
    re.I,
)
YOUTUBE_ID_RE = re.compile(
    r"(?:v=|youtu\.be/|shorts/)([\w-]{11})",
    re.I,
)
URL_IN_TEXT_RE = re.compile(r"https://[^\s<>]+", re.I)
DIRECT_VIDEO_EXT_RE = re.compile(r"\.(?:mp4|webm|mov|mkv)(?:$|\?)", re.I)

_TRAILING_PUNCT = ".,);]>}\"'"


def _strip_trailing_punct(url: str) -> str:
    return url.rstrip(_TRAILING_PUNCT)


def hostname(url: str) -> str:
    host = (urlparse(url.strip()).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if host.startswith("m.") and not host.startswith("medal."):
        host = host[2:]
    return host


def is_https_url(url: str) -> bool:
    if not url or not url.strip():
        return False
    parsed = urlparse(url.strip())
    return parsed.scheme == "https" and bool(parsed.netloc)


def _medal_path(url: str) -> str:
    return url.split("medal.tv/", 1)[-1].split("?")[0].strip("/")


def normalize_clip_url(url: str) -> str:
    """Trim whitespace and trailing punctuation; drop Medal tracking params."""
    url = _strip_trailing_punct((url or "").strip())
    if not MEDAL_HOST_RE.match(url):
        return url
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


def medal_content_id(url: str) -> str | None:
    path = _medal_path(normalize_clip_url(url))
    if not path:
        return None
    for pat in (
        r"games/[\w-]+/clips?/([\w-]+)$",
        r"clips?/([\w-]+)$",
    ):
        m = re.search(pat, path, re.I)
        if m:
            return m.group(1)
    return None


def is_valid_medal_url(url: str) -> bool:
    if not is_https_url(url):
        return False
    url = normalize_clip_url(url)
    if not MEDAL_HOST_RE.match(url):
        return False
    path = _medal_path(url)
    return bool(path and MEDAL_CLIP_PATH_RE.search(path))


def is_valid_youtube_url(url: str) -> bool:
    if not is_https_url(url):
        return False
    return bool(YOUTUBE_URL_RE.match(url.strip()))


def youtube_id(url: str) -> str | None:
    m = YOUTUBE_ID_RE.search(url)
    return m.group(1) if m else None


def is_valid_twitch_url(url: str) -> bool:
    if not is_https_url(url):
        return False
    host = hostname(url)
    path = urlparse(url).path or ""
    if host == "clips.twitch.tv":
        return bool(re.match(r"^/[\w-]+/?$", path))
    if host == "twitch.tv":
        return bool(re.search(r"/clip/[\w-]+", path, re.I))
    return False


def is_valid_tiktok_url(url: str) -> bool:
    if not is_https_url(url):
        return False
    host = hostname(url)
    path = urlparse(url).path or ""
    if host in {"vm.tiktok.com", "vt.tiktok.com"}:
        return bool(re.match(r"^/[\w-]+/?$", path))
    if host == "tiktok.com":
        return bool(
            re.search(r"/video/\d+", path, re.I)
            or re.search(r"/t/[\w-]+", path, re.I)
            or re.search(r"/@[\w.-]+/photo/\d+", path, re.I)
        )
    return False


def is_valid_streamable_url(url: str) -> bool:
    if not is_https_url(url):
        return False
    if hostname(url) != "streamable.com":
        return False
    path = (urlparse(url).path or "").strip("/")
    return bool(path) and "/" not in path


def is_valid_kick_url(url: str) -> bool:
    if not is_https_url(url):
        return False
    if hostname(url) != "kick.com":
        return False
    path = urlparse(url).path or ""
    return bool(re.search(r"/clips?/[\w-]+", path, re.I))


def is_valid_instagram_url(url: str) -> bool:
    if not is_https_url(url):
        return False
    host = hostname(url)
    if host not in {"instagram.com", "instagr.am"}:
        return False
    path = urlparse(url).path or ""
    return bool(re.search(r"/(?:reel|reels|p|tv)/[\w-]+", path, re.I))


def is_valid_reddit_url(url: str) -> bool:
    if not is_https_url(url):
        return False
    host = hostname(url)
    path = urlparse(url).path or ""
    if host == "v.redd.it":
        return bool(path.strip("/"))
    if host in {"reddit.com", "old.reddit.com"}:
        return bool(re.search(r"/r/[\w-]+/comments/", path, re.I))
    return False


def is_valid_twitter_url(url: str) -> bool:
    if not is_https_url(url):
        return False
    host = hostname(url)
    if host not in {"x.com", "twitter.com"}:
        return False
    path = urlparse(url).path or ""
    return bool(re.search(r"/status/\d+", path, re.I))


def is_discord_cdn_video_url(url: str) -> bool:
    if not is_https_url(url):
        return False
    host = hostname(url)
    if host not in {"cdn.discordapp.com", "media.discordapp.net"}:
        return False
    return is_direct_video_url(url)


def is_direct_video_url(url: str) -> bool:
    if not is_https_url(url):
        return False
    path = urlparse(url).path or ""
    return bool(DIRECT_VIDEO_EXT_RE.search(path))


def is_allowlisted_clip_url(url: str) -> bool:
    """Sync allowlist — no network. Generic og:video URLs are checked at publish time."""
    url = normalize_clip_url(url)
    return (
        is_valid_medal_url(url)
        or is_valid_youtube_url(url)
        or is_valid_twitch_url(url)
        or is_valid_tiktok_url(url)
        or is_valid_streamable_url(url)
        or is_valid_kick_url(url)
        or is_valid_instagram_url(url)
        or is_valid_reddit_url(url)
        or is_valid_twitter_url(url)
        or is_discord_cdn_video_url(url)
        or is_direct_video_url(url)
    )


def is_valid_clip_url(url: str) -> bool:
    return is_allowlisted_clip_url(url)


def clip_source(url: str) -> str:
    url = normalize_clip_url(url)
    if is_valid_youtube_url(url):
        return "youtube"
    if is_valid_medal_url(url):
        return "medal"
    if is_valid_twitch_url(url):
        return "twitch"
    if is_valid_tiktok_url(url):
        return "tiktok"
    if is_valid_streamable_url(url):
        return "streamable"
    if is_valid_kick_url(url):
        return "kick"
    if is_valid_instagram_url(url):
        return "instagram"
    if is_valid_reddit_url(url):
        return "reddit"
    if is_valid_twitter_url(url):
        return "twitter"
    if is_discord_cdn_video_url(url) or is_direct_video_url(url):
        return "file"
    return "link"


def extract_urls(text: str) -> list[str]:
    found: list[str] = []
    for raw in URL_IN_TEXT_RE.findall(text or ""):
        cleaned = normalize_clip_url(raw)
        if cleaned and cleaned not in found:
            found.append(cleaned)
    return found


def extract_og(html: str, prop: str) -> str | None:
    patterns = [
        rf'property="{prop}"[^>]+content="([^"]+)"',
        rf'content="([^"]+)"[^>]+property="{prop}"',
        rf"property='{prop}'[^>]+content='([^']+)'",
        rf'name="{prop}"[^>]+content="([^"]+)"',
    ]
    for pat in patterns:
        m = re.search(pat, html, re.I)
        if m:
            return m.group(1).strip()
    return None


def html_looks_like_video(html: str) -> bool:
    og_type = (extract_og(html, "og:type") or "").lower()
    if "video" in og_type:
        return True
    if extract_og(html, "og:video") or extract_og(html, "og:video:url"):
        return True
    twitter = (extract_og(html, "twitter:card") or "").lower()
    return twitter in {"player", "animated_gif"}
