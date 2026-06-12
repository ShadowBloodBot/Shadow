"""
Import historical SAND guide posts from your logged-in Brave session into #sand-guides.

Brave (debugging):
  "C:\\Program Files\\BraveSoftware\\Brave-Browser\\Application\\brave.exe" --remote-debugging-port=9222

Open: https://discord.com/channels/1192467643144355910/1294462300027359343

Run:
  python scripts/sand_guides_import.py --dry-run
  python scripts/sand_guides_import.py --republish
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import aiohttp
import discord

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cogs.sand.guides_funnel import GUIDES_CHANNEL_ID, build_guide_payload  # noqa: E402

STATE_PATH = ROOT / "data" / "sand_guides_import.json"
SOURCE_URL = "https://discord.com/channels/1192467643144355910/1294462300027359343"
SOURCE_CHANNEL_ID = "1294462300027359343"

COLLECT_JS = """
(channelId) => {
  const out = [];
  const seen = new Set();
  for (const node of document.querySelectorAll('li[id^="chat-messages-"]')) {
    const parts = node.id.split("-");
    const messageId = parts[parts.length - 1];
    if (!/^\\d+$/.test(messageId) || seen.has(messageId)) continue;
    seen.add(messageId);

    const markup = node.querySelector('[id^="message-content-"] [class*="markup"]')
      || node.querySelector('[id^="message-content-"]');
    let content = markup ? (markup.innerText || "").trim() : "";

    let embedTitle = "";
    const titleCandidates = [];
    for (const a of node.querySelectorAll('[class*="embedTitle"]')) {
      const text = (a.textContent || "").trim();
      if (text) titleCandidates.push(text);
    }
    for (const a of node.querySelectorAll('a[href*="/channels/"]')) {
      const text = (a.textContent || "").trim();
      if (text && text.length <= 120 && !text.startsWith("http")) titleCandidates.push(text);
    }
    if (titleCandidates.length) {
      titleCandidates.sort((a, b) => a.length - b.length);
      embedTitle = titleCandidates[0];
    }

    let embedDesc = "";
    for (const block of node.querySelectorAll('[class*="embedDescription"]')) {
      const text = (block.textContent || "").trim();
      if (text) embedDesc += (embedDesc ? "\\n\\n" : "") + text;
    }

    const fields = [];
    for (const row of node.querySelectorAll('[class*="embedField"]')) {
      const name = row.querySelector('[class*="embedFieldName"]');
      const value = row.querySelector('[class*="embedFieldValue"]');
      const n = name ? (name.textContent || "").trim() : "";
      const v = value ? (value.textContent || "").trim() : "";
      if (n || v) fields.push({ name: n, value: v });
    }

    const images = [];
    for (const a of node.querySelectorAll(`a[href*="cdn.discordapp.com/attachments/${channelId}/"]`)) {
      if (a.href && !images.includes(a.href)) images.push(a.href);
    }

    let threadUrl = "";
    for (const a of node.querySelectorAll('a[href*="/channels/"]')) {
      const href = (a.href || "").split("?")[0];
      if (!href || href.includes("attachments")) continue;
      if (/\\/channels\\/\\d+\\/\\d+(\\/\\d+)?$/.test(href) && !href.endsWith("/" + channelId)) {
        threadUrl = a.href;
        break;
      }
    }

    if (!content && !embedTitle && !embedDesc && images.length === 0 && !threadUrl) continue;
    out.push({ messageId, content, embedTitle, embedDesc, fields, images, threadUrl });
  }
  return out;
}
"""

THREAD_BODY_JS = """
() => {
  const node = document.querySelector('li[id^="chat-messages-"]');
  if (!node) return "";
  const markup = node.querySelector('[id^="message-content-"] [class*="markup"]')
    || node.querySelector('[id^="message-content-"]');
  return markup ? (markup.innerText || "").trim() : "";
}
"""

SCROLL_JS = """
() => {
  const scroller = document.querySelector('[class*="messagesWrapper"] [class*="scroller"]')
    || document.querySelector('main [class*="scroller"]');
  if (!scroller) return { ok: false };
  const before = scroller.scrollTop;
  scroller.scrollTop = Math.max(0, before - scroller.clientHeight * 0.85);
  return { ok: true, before, after: scroller.scrollTop };
}
"""


def load_token() -> str:
    mcp = json.loads((ROOT / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
    return mcp["mcpServers"]["discord-admin"]["env"]["DISCORD_TOKEN"]



def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"imported": []}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(STATE_PATH)



MAX_TITLE_LEN = 80


def _short_title(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return ""
    if len(raw) <= MAX_TITLE_LEN:
        return raw
    for sep in (". ", " — ", " - ", ": "):
        if sep in raw:
            head = raw.split(sep)[0].strip()
            if 3 <= len(head) <= MAX_TITLE_LEN:
                return head
    return raw[: MAX_TITLE_LEN - 1].rsplit(" ", 1)[0] or raw[:MAX_TITLE_LEN]


def compose_guide(entry: dict) -> tuple[str, str, list[tuple[str, str]]]:
    raw_title = _short_title(entry.get("embedTitle") or "")
    content = (entry.get("content") or "").strip()
    embed_desc = (entry.get("embedDesc") or "").strip()
    thread_body = (entry.get("threadBody") or "").strip()

    title = raw_title
    if not title and content:
        lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
        if lines:
            title = _short_title(lines[0])
            content = "\n".join(lines[1:]).strip()

    if not title:
        title = "SAND Guide"
    if not title.startswith("📜"):
        title = f"📜 {title[:248]}"

    body_parts = []
    # If content repeats the title line, keep full content in the body hub.
    if content:
        if raw_title and content.startswith(raw_title):
            rest = content[len(raw_title) :].lstrip(" .:\n-")
            body_parts.append(rest if rest else content)
        elif content != raw_title:
            body_parts.append(content)
    if embed_desc and embed_desc not in body_parts:
        body_parts.append(embed_desc)
    if thread_body:
        body_parts.append(thread_body)

    description = "\n\n".join(p for p in body_parts if p).strip()

    fields: list[tuple[str, str]] = []
    for f in entry.get("fields") or []:
        name = (f.get("name") or "").strip()
        value = (f.get("value") or "").strip()
        if name and value:
            fields.append((name[:256], value[:1024]))

    return title, description, fields


async def purge_channel(session: aiohttp.ClientSession, token: str) -> int:
    """Delete every message the bot can reach in #sand-guides."""
    headers = {"Authorization": f"Bot {token}"}
    deleted = 0
    stagnant = 0
    while stagnant < 3:
        async with session.get(
            f"https://discord.com/api/v10/channels/{GUIDES_CHANNEL_ID}/messages?limit=100",
            headers=headers,
        ) as resp:
            msgs = await resp.json()
        if not isinstance(msgs, list) or not msgs:
            break
        batch_deleted = 0
        for m in msgs:
            async with session.delete(
                f"https://discord.com/api/v10/channels/{GUIDES_CHANNEL_ID}/messages/{m['id']}",
                headers=headers,
            ) as resp:
                if resp.status in (200, 204, 404):
                    deleted += 1
                    batch_deleted += 1
            await asyncio.sleep(0.4)
        stagnant = 0 if batch_deleted else stagnant + 1
    return deleted


async def enrich_thread_bodies(page, entries: list[dict]) -> None:
    for entry in entries:
        if entry.get("threadBody") or not entry.get("threadUrl"):
            continue
        title, desc, _ = compose_guide(entry)
        if desc:
            continue
        try:
            await page.goto(entry["threadUrl"], wait_until="domcontentloaded", timeout=90_000)
            await page.wait_for_timeout(2500)
            body = await page.evaluate(THREAD_BODY_JS)
            if body:
                entry["threadBody"] = body
        except Exception as exc:
            print(f"  thread scrape skip {entry.get('messageId')}: {exc}")
        await asyncio.sleep(0.5)
    if any(e.get("threadUrl") for e in entries):
        await page.goto(SOURCE_URL, wait_until="domcontentloaded", timeout=90_000)
        await page.wait_for_timeout(2000)


async def collect_from_browser(*, cdp: str, max_scrolls: int) -> list[dict]:
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(cdp)
        ctx = browser.contexts[0]
        page = None
        for p in ctx.pages:
            if SOURCE_CHANNEL_ID in p.url:
                page = p
                break
        if page is None:
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            await page.goto(SOURCE_URL, wait_until="domcontentloaded", timeout=120_000)

        await page.wait_for_timeout(5000)
        collected: dict[str, dict] = {}
        idle = 0
        for i in range(max_scrolls + 1):
            batch = await page.evaluate(COLLECT_JS, SOURCE_CHANNEL_ID)
            added = 0
            for item in batch:
                if item["messageId"] not in collected:
                    collected[item["messageId"]] = item
                    added += 1
            print(f"scroll {i}: guides {len(collected)} (+{added})")
            if i == max_scrolls:
                break
            scroll = await page.evaluate(SCROLL_JS)
            if not scroll.get("ok") or scroll.get("before") == scroll.get("after"):
                idle += 1
            else:
                idle = 0
            if idle >= 3:
                break
            await page.wait_for_timeout(1500)

        entries = sorted(collected.values(), key=lambda e: int(e["messageId"]))
        need_threads = [e for e in entries if e.get("threadUrl")]
        if need_threads:
            print(f"Fetching thread bodies for {len(need_threads)} guides...")
            await enrich_thread_bodies(page, entries)
        return entries


async def post_guide(session: aiohttp.ClientSession, token: str, entry: dict) -> None:
    title, description, fields = compose_guide(entry)
    image_files: list[discord.File] = []
    for i, url in enumerate(entry.get("images") or []):
        async with session.get(url) as resp:
            resp.raise_for_status()
            data = await resp.read()
        name = Path(urlparse(url).path).name or f"guide_{i}.png"
        name = re.sub(r"[^\w.\-]", "_", name)
        if "." not in name:
            name += ".png"
        image_files.append(discord.File(BytesIO(data), filename=name))

    embed, files = build_guide_payload(
        title=title,
        description=description,
        fields=fields,
        image_files=image_files,
    )

    payload = {"embeds": [embed.to_dict()]}
    form = aiohttp.FormData()
    form.add_field("payload_json", json.dumps(payload))
    for i, f in enumerate(files):
        f.fp.seek(0)
        form.add_field(
            f"files[{i}]",
            f.fp.read(),
            filename=f.filename,
            content_type="application/octet-stream",
        )

    headers = {"Authorization": f"Bot {token}"}
    url = f"https://discord.com/api/v10/channels/{GUIDES_CHANNEL_ID}/messages"
    async with session.post(url, headers=headers, data=form) as resp:
        text = await resp.text()
        if resp.status >= 400:
            raise RuntimeError(f"Post failed {resp.status}: {text[:400]}")


async def run(*, cdp: str, max_scrolls: int, dry_run: bool, republish: bool) -> None:
    token = load_token()

    if republish and not dry_run:
        async with aiohttp.ClientSession() as session:
            n = await purge_channel(session, token)
            print(f"Purged {n} messages from #sand-guides")
        save_state({"imported": []})

    entries = await collect_from_browser(cdp=cdp, max_scrolls=max_scrolls)
    if not entries:
        print("No guides found — open the SAND guides channel in debugging Brave.")
        return

    state = load_state()
    imported = set(state.get("imported", []))
    pending = entries if republish else [e for e in entries if e["messageId"] not in imported]
    print(f"Total scraped: {len(entries)}, to post: {len(pending)}")

    if dry_run:
        for e in pending[:20]:
            t, d, _ = compose_guide(e)
            print(f"  would post: {t} body={len(d)} chars imgs={len(e.get('images') or [])}")
        return

    async with aiohttp.ClientSession() as session:
        for i, entry in enumerate(pending, 1):
            try:
                await post_guide(session, token, entry)
                imported.add(entry["messageId"])
                state["imported"] = sorted(imported)
                save_state(state)
                t, d, _ = compose_guide(entry)
                print(f"[{i}/{len(pending)}] posted: {t} ({len(d)} chars)")
                await asyncio.sleep(1.5)
            except Exception as exc:
                print(f"[{i}/{len(pending)}] failed {entry['messageId']}: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cdp", default="http://localhost:9222")
    parser.add_argument("--max-scrolls", type=int, default=60)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--republish",
        action="store_true",
        help="Delete existing bot posts in #sand-guides and re-import all guides",
    )
    args = parser.parse_args()
    asyncio.run(
        run(
            cdp=args.cdp,
            max_scrolls=args.max_scrolls,
            dry_run=args.dry_run,
            republish=args.republish,
        )
    )


if __name__ == "__main__":
    main()
