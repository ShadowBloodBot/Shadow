import os
import re
import json
from typing import Optional

import discord
from discord import app_commands
from dotenv import load_dotenv

# ========= BASIC CONFIG =========
WEBHOOK_NAME_DEFAULT = "ShadowSyn"
WEBHOOK_AVATAR_DEFAULT = None  # optional avatar URL
WEBHOOK_CACHE_FILE = "webhooks.json"
CONFIG_FILE = "config.json"     # stores defaults for /send_welcome

# ========= ENV =========
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
ENV_WEBHOOK_URL = os.getenv("WEB_HOOKWELCOME")  # optional: direct webhook URL

if not TOKEN:
    raise RuntimeError("Missing DISCORD_TOKEN in environment")

# ========= CLIENT =========
intents = discord.Intents.default()
intents.message_content = False
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# ========= PERSISTENCE (webhook cache) =========
# { "<guild_id>": { "<channel_id>": { "url": "https://discord.com/api/webhooks/..." } } }
def load_cache() -> dict:
    try:
        with open(WEBHOOK_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # migrate old id/token -> url
            for g in list(data.keys()):
                for c in list(data[g].keys()):
                    entry = data[g][c]
                    if "url" not in entry and "id" in entry and "token" in entry:
                        data[g][c] = {"url": f"https://discord.com/api/webhooks/{entry['id']}/{entry['token']}"}
            return data
    except FileNotFoundError:
        return {}
    except Exception:
        return {}

def save_cache(cache: dict) -> None:
    try:
        with open(WEBHOOK_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)
    except Exception:
        pass

webhook_cache = load_cache()

def _store_hook(guild_id: int, channel_id: int, url: str):
    gk, ck = str(guild_id), str(channel_id)
    webhook_cache.setdefault(gk, {})
    webhook_cache[gk][ck] = {"url": url}
    save_cache(webhook_cache)

# ========= CONFIG (defaults for /send_welcome) =========
def load_cfg():
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def save_cfg(cfg: dict):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass

cfg = load_cfg()

# ========= HELPERS =========
async def get_or_create_webhook(
    channel: discord.TextChannel,
    name: str = WEBHOOK_NAME_DEFAULT,
    avatar_url: Optional[str] = WEBHOOK_AVATAR_DEFAULT,
) -> discord.Webhook:
    """Return a usable webhook for the channel, creating if needed. Caches by URL."""
    gk, ck = str(channel.guild.id), str(channel.id)

    # Try cached
    if gk in webhook_cache and ck in webhook_cache[gk]:
        url = webhook_cache[gk][ck].get("url")
        if url:
            try:
                return discord.Webhook.from_url(url, client=client)
            except Exception:
                pass  # fall through to repair

    # Try to find existing one by name
    try:
        hooks = await channel.webhooks()
        for h in hooks:
            if h.name == name and h.token and h.url:
                _store_hook(channel.guild.id, channel.id, h.url)
                return discord.Webhook.from_url(h.url, client=client)
    except discord.Forbidden:
        raise discord.Forbidden(channel, "I need **Manage Webhooks** in this channel.")
    except Exception:
        pass

    # Create new webhook
    try:
        hook = await channel.create_webhook(name=name, reason="ShadowSyn embed poster")
        _store_hook(channel.guild.id, channel.id, hook.url)
        return discord.Webhook.from_url(hook.url, client=client)
    except discord.Forbidden:
        raise discord.Forbidden(channel, "I need **Manage Webhooks** in this channel.")
    except Exception as e:
        raise RuntimeError(f"Failed creating webhook: {e}")

def parse_hex_color(value: Optional[str]) -> int:
    if not value:
        return 0x2b2d31
    value = value.strip().lstrip("#")
    try:
        return int(value, 16)
    except ValueError:
        return 0x2b2d31

def jump_url(guild_id: int, channel_id: int) -> str:
    return f"https://discord.com/channels/{guild_id}/{channel_id}"

def build_url_buttons(
    *,
    rules_link: Optional[str] = None,
    roles_link: Optional[str] = None,
    lobby_link: Optional[str] = None,
    invite_link: Optional[str] = None,
) -> discord.ui.View:
    view = discord.ui.View()
    if rules_link:
        view.add_item(discord.ui.Button(label="📜 Read Rules", url=rules_link))
    if roles_link:
        view.add_item(discord.ui.Button(label="🎭 Get Roles", url=roles_link))
    if lobby_link:
        view.add_item(discord.ui.Button(label="💬 Introduce Yourself", url=lobby_link))
    if invite_link:
        view.add_item(discord.ui.Button(label="🔗 Copy Invite", url=invite_link))
    return view

def welcome_embed(guild: Optional[discord.Guild], lobby_mention: str, self_roles_mention: str) -> discord.Embed:
    embed = discord.Embed(
        title="Welcome to ShadowSyn",
        description=(
            "👋 **Welcome to all our new members!**\n"
            "We’re thrilled to have you join our community! 🎉\n\n"
            "🎮 **What we play:**\n"
            "We’re into just about anything FPS or Survival, plus some RTS (and yes — Age of Empires IV is goated) and MMOs.\n\n"
            "💬 **Your first steps:**\n"
            f"Head over to **{lobby_mention}** and introduce yourself — let us know where you came from or what brought you here.\n"
            f"Tag **@Blood** to get your role (see {self_roles_mention}).\n\n"
            "Enjoy your stay! If you have any questions, **@Gravy** will love hearing you yap yap yap."
        ),
        color=0x5865F2
    )
    if guild and guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.set_footer(text="Shadow Syndicate • Welcome")
    return embed

# ========= THREAD RESOLUTION + AUTOCOMPLETE =========
THREAD_LINK_RE = re.compile(r"https?://(?:ptb\.|canary\.)?discord\.com/channels/(\d+)/(\d+)/(\d+)")

async def resolve_thread_from_input(guild: discord.Guild, thread_input: str) -> Optional[discord.Thread]:
    s = (thread_input or "").strip()

    # 1) Full link
    m = THREAD_LINK_RE.match(s)
    if m:
        g_id, parent_id, thread_id = map(int, m.groups())
        if g_id == guild.id:
            th = guild.get_thread(thread_id)
            if th:
                return th

    # 2) Raw numeric ID
    if s.isdigit():
        th = guild.get_thread(int(s))
        if th:
            return th

    # 3) Name search: active threads
    s_low = s.lower()
    for th in guild.threads:
        if s_low in th.name.lower():
            return th

    # 4) Recent archived per text channel
    for ch in guild.text_channels:
        try:
            async for th in ch.archived_threads(limit=50):
                if s_low in th.name.lower():
                    return th
        except Exception:
            continue

    return None

# ========= COMMANDS =========

@tree.command(name="setup_webhook", description="Create or reuse a 'ShadowSyn' webhook in a channel.")
@app_commands.describe(
    channel="Which channel should the webhook post in?",
    name="Custom sender name (default: ShadowSyn)",
    avatar_url="Avatar URL for the sender (optional)"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def setup_webhook(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    name: Optional[str] = WEBHOOK_NAME_DEFAULT,
    avatar_url: Optional[str] = WEBHOOK_AVATAR_DEFAULT,
):
    await interaction.response.defer(ephemeral=True)
    try:
        _ = await get_or_create_webhook(channel, name=name or WEBHOOK_NAME_DEFAULT, avatar_url=avatar_url)
        await interaction.followup.send(
            f"✅ Webhook ready in {channel.mention} as **{name or WEBHOOK_NAME_DEFAULT}**.",
            ephemeral=True
        )
    except discord.Forbidden as e:
        await interaction.followup.send(f"❌ {e}", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Failed: {e}", ephemeral=True)

# ---- SAVE DEFAULTS FOR /send_welcome ----
@tree.command(name="set_welcome_defaults", description="Save your welcome thread/channel + default links for /send_welcome.")
@app_commands.describe(
    welcome_thread="Your welcome thread (preferred).",
    welcome_channel="If not using a thread, the channel to post in.",
    lobby="Lobby/introductions channel",
    self_roles="Self-roles channel",
    rules="Rules channel",
    invite_url="Default invite link (optional)"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def set_welcome_defaults(
    interaction: discord.Interaction,
    welcome_thread: Optional[discord.Thread] = None,
    welcome_channel: Optional[discord.TextChannel] = None,
    lobby: Optional[discord.TextChannel] = None,
    self_roles: Optional[discord.TextChannel] = None,
    rules: Optional[discord.TextChannel] = None,
    invite_url: Optional[str] = None,
):
    if not welcome_thread and not welcome_channel:
        await interaction.response.send_message("❌ Pick a welcome **thread** or a **channel**.", ephemeral=True)
        return

    cfg.update({
        "guild_id": interaction.guild_id,
        "welcome_thread_id": welcome_thread.id if welcome_thread else None,
        "welcome_channel_id": welcome_channel.id if welcome_channel else None,
        "lobby_id": lobby.id if lobby else cfg.get("lobby_id"),
        "self_roles_id": self_roles.id if self_roles else cfg.get("self_roles_id"),
        "rules_id": rules.id if rules else cfg.get("rules_id"),
        "invite_url": invite_url if invite_url else cfg.get("invite_url"),
    })
    save_cfg(cfg)
    await interaction.response.send_message("✅ Defaults saved. Now `/send_welcome` works with no inputs.", ephemeral=True)

# ---- /send_welcome uses saved defaults, zero inputs ----
@tree.command(name="send_welcome", description="Post the welcome embed to your saved welcome thread/channel.")
@app_commands.describe(
    lobby="Override lobby (optional)",
    self_roles="Override self-roles (optional)",
    rules="Override rules (optional)",
    invite_url="Override invite link (optional)",
    sender_name="Override sender name (optional)",
    sender_avatar_url="Override sender avatar URL (optional)"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def send_welcome(
    interaction: discord.Interaction,
    lobby: Optional[discord.TextChannel] = None,
    self_roles: Optional[discord.TextChannel] = None,
    rules: Optional[discord.TextChannel] = None,
    invite_url: Optional[str] = None,
    sender_name: Optional[str] = None,
    sender_avatar_url: Optional[str] = None,
):
    await interaction.response.defer(ephemeral=True)

    if not cfg.get("welcome_thread_id") and not cfg.get("welcome_channel_id"):
        await interaction.followup.send("❌ No defaults set. Run `/set_welcome_defaults` once.", ephemeral=True)
        return

    g = interaction.guild
    thread = g.get_thread(cfg.get("welcome_thread_id")) if cfg.get("welcome_thread_id") else None
    channel = g.get_channel(cfg.get("welcome_channel_id")) if cfg.get("welcome_channel_id") else None

    if not thread and not channel:
        await interaction.followup.send("❌ Saved welcome destination not found. Re-run `/set_welcome_defaults`.", ephemeral=True)
        return

    lobby = lobby or g.get_channel(cfg.get("lobby_id"))
    self_roles = self_roles or g.get_channel(cfg.get("self_roles_id"))
    rules = rules or g.get_channel(cfg.get("rules_id"))
    invite_url = invite_url or cfg.get("invite_url")
    sender_name = sender_name or WEBHOOK_NAME_DEFAULT
    sender_avatar_url = sender_avatar_url or WEBHOOK_AVATAR_DEFAULT

    if not all([lobby, self_roles, rules]):
        await interaction.followup.send("❌ Missing default lobby/self-roles/rules. Set them via `/set_welcome_defaults`.", ephemeral=True)
        return

    embed = welcome_embed(g, lobby.mention, self_roles.mention)
    buttons = build_url_buttons(
        rules_link=jump_url(g.id, rules.id),
        roles_link=jump_url(g.id, self_roles.id),
        lobby_link=jump_url(g.id, lobby.id),
        invite_link=invite_url,
    )

    if thread:
        # forum threads cannot use webhooks
        if isinstance(thread.parent, discord.ForumChannel):
            await interaction.followup.send("❌ Saved welcome is a *forum* thread (no webhooks). Choose a text thread/channel.", ephemeral=True)
            return
        parent = thread.parent  # TextChannel
        hook = await get_or_create_webhook(parent, name=sender_name, avatar_url=sender_avatar_url)
        await hook.send(embed=embed, view=buttons, thread=thread,
                        username=sender_name, avatar_url=sender_avatar_url,
                        allowed_mentions=discord.AllowedMentions.none())
    else:
        hook = await get_or_create_webhook(channel, name=sender_name, avatar_url=sender_avatar_url)
        await hook.send(embed=embed, view=buttons,
                        username=sender_name, avatar_url=sender_avatar_url,
                        allowed_mentions=discord.AllowedMentions.none())

    await interaction.followup.send("✅ Welcome posted to your saved destination.", ephemeral=True)

# ---- Rules embed ----
@tree.command(name="send_rules", description="Post the rules embed via channel webhook.")
@app_commands.describe(
    channel="Where to post?",
    sender_name="Display name for the sender (default: ShadowSyn)",
    sender_avatar_url="Avatar URL for the sender (optional)",
    color_hex="Embed color hex (e.g. #2b2d31)"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def send_rules(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    sender_name: Optional[str] = WEBHOOK_NAME_DEFAULT,
    sender_avatar_url: Optional[str] = WEBHOOK_AVATAR_DEFAULT,
    color_hex: Optional[str] = "#2b2d31"
):
    await interaction.response.defer(ephemeral=True)
    try:
        hook = await get_or_create_webhook(channel, name=sender_name, avatar_url=sender_avatar_url)
        rules_text = (
            "Don’t be annoying, overly sensitive, or spammy. Avoid @mentioning or DMing people you don’t know, "
            "and no self‑promo unless approved. Keep personal info private, skip the hate speech "
            "(we’re not trying to get the Discord nuked), and absolutely no vegans, piracy, NSFW, or other shady content. "
            "Use common sense — it covers the rest."
        )
        embed = discord.Embed(
            title="Server Rules",
            description=rules_text,
            color=parse_hex_color(color_hex),
        )
        embed.set_footer(text="Shadow Syndicate • Rules")
        await hook.send(
            embed=embed,
            username=sender_name or WEBHOOK_NAME_DEFAULT,
            avatar_url=sender_avatar_url or WEBHOOK_AVATAR_DEFAULT,
            allowed_mentions=discord.AllowedMentions.none()
        )
        await interaction.followup.send(f"✅ Posted rules embed in {channel.mention}.", ephemeral=True)
    except discord.Forbidden as e:
        await interaction.followup.send(f"❌ {e}", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Failed: {e}", ephemeral=True)

# ---- Generic channel embed ----
@tree.command(name="send_embed", description="Post a custom embed via channel webhook.")
@app_commands.describe(
    channel="Where to post?",
    title="Embed title",
    description="Embed description (supports new lines)",
    color_hex="Color hex (e.g. #5865F2)",
    sender_name="Display name for the sender",
    sender_avatar_url="Avatar URL for the sender (optional)",
    image_url="Large image URL (optional)",
    thumbnail_url="Small thumbnail URL (optional)",
    footer="Footer text (optional)"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def send_embed(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    title: str,
    description: str,
    color_hex: Optional[str] = "#5865F2",
    sender_name: Optional[str] = WEBHOOK_NAME_DEFAULT,
    sender_avatar_url: Optional[str] = WEBHOOK_AVATAR_DEFAULT,
    image_url: Optional[str] = None,
    thumbnail_url: Optional[str] = None,
    footer: Optional[str] = None,
):
    await interaction.response.defer(ephemeral=True)
    try:
        hook = await get_or_create_webhook(channel, name=sender_name, avatar_url=sender_avatar_url)
        embed = discord.Embed(
            title=title[:256],
            description=description[:4000],
            color=parse_hex_color(color_hex),
        )
        if thumbnail_url:
            embed.set_thumbnail(url=thumbnail_url)
        if image_url:
            embed.set_image(url=image_url)
        if footer:
            embed.set_footer(text=footer[:2048])
        await hook.send(
            embed=embed,
            username=sender_name or WEBHOOK_NAME_DEFAULT,
            avatar_url=sender_avatar_url or WEBHOOK_AVATAR_DEFAULT,
            allowed_mentions=discord.AllowedMentions.none()
        )
        await interaction.followup.send(f"✅ Posted embed in {channel.mention}.", ephemeral=True)
    except discord.Forbidden as e:
        await interaction.followup.send(f"❌ {e}", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Failed: {e}", ephemeral=True)

# ---- /send_custom to a selected THREAD (string w/ autocomplete + link/ID resolve) ----
@tree.command(name="send_custom", description="Post a custom embed into a selected thread as ShadowSyn.")
@app_commands.describe(
    thread="Pick a thread, paste a thread link, or type to search",
    title="Embed title",
    description="Embed description (supports new lines)",
    color_hex="Color hex (e.g. #5865F2)",
    sender_name="Display name for the sender (default: ShadowSyn)",
    sender_avatar_url="Avatar URL for the sender (optional)",
    image_url="Large image URL (optional)",
    thumbnail_url="Small thumbnail URL (optional)",
    footer="Footer text (optional)"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def send_custom(
    interaction: discord.Interaction,
    thread: str,
    title: str,
    description: str,
    color_hex: Optional[str] = "#5865F2",
    sender_name: Optional[str] = WEBHOOK_NAME_DEFAULT,
    sender_avatar_url: Optional[str] = WEBHOOK_AVATAR_DEFAULT,
    image_url: Optional[str] = None,
    thumbnail_url: Optional[str] = None,
    footer: Optional[str] = None,
):
    """Accepts a thread ID/link/name with autocomplete; posts via parent text-channel webhook."""
    await interaction.response.defer(ephemeral=True)
    try:
        g = interaction.guild
        th = g.get_thread(int(thread)) if thread.isdigit() else await resolve_thread_from_input(g, thread)
        if not th:
            await interaction.followup.send("❌ Couldn't find that thread. Pick from suggestions or paste a valid thread link/ID.", ephemeral=True)
            return

        # webhooks only on text-channel threads
        if isinstance(th.parent, discord.ForumChannel):
            await interaction.followup.send("❌ Forum threads don’t support webhooks. Use a thread under a text channel.", ephemeral=True)
            return
        if not isinstance(th.parent, discord.TextChannel):
            await interaction.followup.send("❌ That thread’s parent isn’t a text channel.", ephemeral=True)
            return

        hook = await get_or_create_webhook(th.parent, name=sender_name, avatar_url=sender_avatar_url)

        embed = discord.Embed(
            title=title[:256],
            description=description[:4000],
            color=parse_hex_color(color_hex),
        )
        if thumbnail_url:
            embed.set_thumbnail(url=thumbnail_url)
        if image_url:
            embed.set_image(url=image_url)
        if footer:
            embed.set_footer(text=footer[:2048])

        await hook.send(
            embed=embed,
            thread=th,
            username=sender_name or WEBHOOK_NAME_DEFAULT,
            avatar_url=sender_avatar_url or WEBHOOK_AVATAR_DEFAULT,
            allowed_mentions=discord.AllowedMentions.none()
        )
        await interaction.followup.send(f"✅ Posted embed in thread **#{th.name}**.", ephemeral=True)

    except discord.Forbidden:
        await interaction.followup.send("❌ I need **Manage Webhooks** in the thread’s parent channel.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Failed: {e}", ephemeral=True)

# ---- Autocomplete for the 'thread' param on /send_custom ----
@send_custom.autocomplete("thread")
async def thread_autocomplete(interaction: discord.Interaction, current: str):
    results = []
    cur = (current or "").lower()

    # Active threads (up to ~50)
    for th in interaction.guild.threads[:50]:
        if not cur or cur in th.name.lower():
            parent = getattr(th, "parent", None)
            parent_name = f"#{parent.name}" if isinstance(parent, discord.TextChannel) else "#?"
            results.append(app_commands.Choice(name=f"{th.name} • {parent_name}", value=str(th.id)))
        if len(results) >= 22:
            break

    # Top-up with archived samples from first ~10 text channels
    if len(results) < 25:
        for ch in interaction.guild.text_channels[:10]:
            try:
                async for th in ch.archived_threads(limit=10):
                    if not cur or cur in th.name.lower():
                        results.append(app_commands.Choice(name=f"[archived] {th.name} • #{ch.name}", value=str(th.id)))
                        if len(results) >= 25:
                            break
            except Exception:
                continue
            if len(results) >= 25:
                break
    return results

# ========= ENV WEBHOOK SHORTCUTS =========
def env_hook() -> discord.Webhook:
    if not ENV_WEBHOOK_URL:
        raise RuntimeError("WEB_HOOKWELCOME not set")
    return discord.Webhook.from_url(ENV_WEBHOOK_URL, client=client)

@tree.command(name="send_welcome_url", description="Post the welcome embed (with buttons) using the WEB_HOOKWELCOME URL.")
@app_commands.describe(
    lobby="Channel for introductions",
    self_roles="Channel for self-roles",
    rules="Channel containing your rules",
    invite_url="Invite link to show on the button (optional)"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def send_welcome_url(
    interaction: discord.Interaction,
    lobby: discord.TextChannel,
    self_roles: discord.TextChannel,
    rules: discord.TextChannel,
    invite_url: Optional[str] = None,
):
    await interaction.response.defer(ephemeral=True)
    try:
        hook = env_hook()
        embed = welcome_embed(interaction.guild, lobby.mention, self_roles.mention)
        g_id = interaction.guild_id
        buttons = build_url_buttons(
            rules_link=jump_url(g_id, rules.id),
            roles_link=jump_url(g_id, self_roles.id),
            lobby_link=jump_url(g_id, lobby.id),
            invite_link=invite_url,
        )
        await hook.send(
            embed=embed,
            view=buttons,
            username=WEBHOOK_NAME_DEFAULT,
            avatar_url=WEBHOOK_AVATAR_DEFAULT,
            allowed_mentions=discord.AllowedMentions.none()
        )
        await interaction.followup.send("✅ Posted welcome card via env webhook.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Failed: {e}", ephemeral=True)

@tree.command(name="send_embed_url", description="Post a custom embed using the WEB_HOOKWELCOME URL.")
@app_commands.describe(
    title="Embed title",
    description="Embed description (supports new lines)",
    color_hex="Color hex (e.g. #5865F2)",
    image_url="Large image URL (optional)",
    thumbnail_url="Small thumbnail URL (optional)",
    footer="Footer text (optional)"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def send_embed_url(
    interaction: discord.Interaction,
    title: str,
    description: str,
    color_hex: Optional[str] = "#5865F2",
    image_url: Optional[str] = None,
    thumbnail_url: Optional[str] = None,
    footer: Optional[str] = None,
):
    await interaction.response.defer(ephemeral=True)
    try:
        hook = env_hook()
        embed = discord.Embed(
            title=title[:256],
            description=description[:4000],
            color=parse_hex_color(color_hex),
        )
        if thumbnail_url:
            embed.set_thumbnail(url=thumbnail_url)
        if image_url:
            embed.set_image(url=image_url)
        if footer:
            embed.set_footer(text=footer[:2048])

        await hook.send(
            embed=embed,
            username=WEBHOOK_NAME_DEFAULT,
            avatar_url=WEBHOOK_AVATAR_DEFAULT,
            allowed_mentions=discord.AllowedMentions.none()
        )
        await interaction.followup.send("✅ Posted embed via env webhook.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Failed: {e}", ephemeral=True)

# ========= STARTUP =========
@client.event
async def on_ready():
    try:
        await tree.sync()
        print(f"Synced {len(tree.get_commands())} slash commands.")
    except Exception as e:
        print(f"Command sync failed: {e}")
    print(f"Logged in as {client.user} (ID: {client.user.id})")

client.run(TOKEN)
