import os
import json
import asyncio
from typing import Optional

import discord
from discord import app_commands
from dotenv import load_dotenv

# ========= CONFIG =========
WEBHOOK_NAME_DEFAULT = "ShadowSyn"
WEBHOOK_AVATAR_DEFAULT = None  # You can set a default avatar URL here if you want
WEBHOOK_CACHE_FILE = "webhooks.json"

# ========= ENV =========
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("Missing DISCORD_TOKEN in environment")

# ========= CLIENT =========
intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# ========= PERSISTENCE (webhook cache) =========
def load_cache() -> dict:
    try:
        with open(WEBHOOK_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
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

webhook_cache = load_cache()  # {guild_id: {channel_id: {"id": int, "token": str}}}

# ========= HELPERS =========
async def get_or_create_webhook(
    channel: discord.TextChannel,
    name: str = WEBHOOK_NAME_DEFAULT,
    avatar_url: Optional[str] = WEBHOOK_AVATAR_DEFAULT,
) -> discord.Webhook:
    """Return a usable webhook for the channel, creating if needed. Caches id/token."""
    guild_key = str(channel.guild.id)
    chan_key = str(channel.id)

    # Use cached webhook if it still exists
    if guild_key in webhook_cache and chan_key in webhook_cache[guild_key]:
        data = webhook_cache[guild_key][chan_key]
        try:
            return discord.Webhook.from_url(
                f"https://discord.com/api/webhooks/{data['id']}/{data['token']}",
                session=client.http._HTTPClient__session  # reuse internal session
            )
        except Exception:
            # Fall through to re-create if token invalid
            pass

    # Otherwise, try to find existing one by name
    try:
        hooks = await channel.webhooks()
        for h in hooks:
            if h.name == name and h.token:
                _store_hook(channel.guild.id, channel.id, h)
                return discord.Webhook.from_url(
                    h.url, session=client.http._HTTPClient__session
                )
    except discord.Forbidden:
        raise discord.Forbidden(channel, "I need **Manage Webhooks** in this channel.")
    except Exception:
        pass

    # Create a new webhook
    try:
        avatar_bytes = None
        if avatar_url:
            # discord.py will fetch avatar image if we pass bytes; keep it simple and omit.
            # Many servers prefer setting avatar later; name is enough for now.
            pass
        hook = await channel.create_webhook(name=name, reason="ShadowSyn embed poster")
    except discord.Forbidden:
        raise discord.Forbidden(channel, "I need **Manage Webhooks** in this channel.")
    except Exception as e:
        raise RuntimeError(f"Failed creating webhook: {e}")

    _store_hook(channel.guild.id, channel.id, hook)
    return discord.Webhook.from_url(hook.url, session=client.http._HTTPClient__session)

def _store_hook(guild_id: int, channel_id: int, hook: discord.Webhook | discord.PartialWebhook | discord.Webhook):
    guild_key = str(guild_id)
    chan_key = str(channel_id)
    webhook_cache.setdefault(guild_key, {})
    webhook_cache[guild_key][chan_key] = {"id": hook.id, "token": hook.token}
    save_cache(webhook_cache)

def parse_hex_color(value: Optional[str]) -> int:
    if not value:
        return 0x2b2d31  # Discord dark-ish default
    value = value.strip().lstrip("#")
    try:
        return int(value, 16)
    except ValueError:
        return 0x2b2d31

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
        hook = await get_or_create_webhook(channel, name=name or WEBHOOK_NAME_DEFAULT, avatar_url=avatar_url)
        await interaction.followup.send(
            f"✅ Webhook ready in {channel.mention} as **{name or WEBHOOK_NAME_DEFAULT}**.",
            ephemeral=True
        )
    except discord.Forbidden as e:
        await interaction.followup.send(f"❌ {e}", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Failed: {e}", ephemeral=True)

@tree.command(name="send_welcome", description="Post the ShadowSyn welcome embed to a channel via webhook.")
@app_commands.describe(
    channel="Where to post?",
    sender_name="Display name for the sender (default: ShadowSyn)",
    sender_avatar_url="Avatar URL for the sender (optional)"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def send_welcome(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    sender_name: Optional[str] = WEBHOOK_NAME_DEFAULT,
    sender_avatar_url: Optional[str] = WEBHOOK_AVATAR_DEFAULT,
):
    await interaction.response.defer(ephemeral=True)
    try:
        hook = await get_or_create_webhook(channel, name=sender_name, avatar_url=sender_avatar_url)

        embed = discord.Embed(
            title="Welcome to ShadowSyn",
            description=(
                "👋 **Welcome to all our new members!**\n"
                "We’re thrilled to have you join our community! 🎉\n\n"
                "🎮 **What we play:**\n"
                "We’re into just about anything FPS or Survival, plus some RTS (and yes — Age of Empires IV is goated) and MMOs.\n\n"
                "💬 **Your first steps:**\n"
                "Head over to **#lobby** and introduce yourself — let us know where you came from or what brought you here.\n"
                "Tag **@Blood** to get your role.\n\n"
                "Enjoy your stay! If you have any questions, **@Gravy** will love hearing you yap yap yap."
            ),
            color=0x5865F2
        )
        embed.set_footer(text="Shadow Syndicate • Welcome")
        embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild and interaction.guild.icon else discord.Embed.Empty)

        await hook.send(
            embed=embed,
            username=sender_name or WEBHOOK_NAME_DEFAULT,
            avatar_url=sender_avatar_url or WEBHOOK_AVATAR_DEFAULT,
            allowed_mentions=discord.AllowedMentions.none()
        )
        await interaction.followup.send(f"✅ Posted welcome embed in {channel.mention}.", ephemeral=True)

    except discord.Forbidden as e:
        await interaction.followup.send(f"❌ {e}", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Failed: {e}", ephemeral=True)

@tree.command(name="send_rules", description="Post the rules embed to a channel via webhook.")
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
            "Don’t be annoying, overly sensitive, or spammy. Avoid @mentioning or DMing people you don’t know, and no self‑promo unless approved. "
            "Keep personal info private, skip the hate speech (we’re not trying to get the Discord nuked), and absolutely no vegans, piracy, NSFW, or other shady content. "
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

@tree.command(name="send_embed", description="Post a custom embed via webhook.")
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
