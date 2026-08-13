# cogs/utility.py
import json
import logging
import random
from pathlib import Path

import discord
from discord.ext import commands
from discord import Option, Interaction
from discord.ui import Modal, TextInput, View, Button

from cogs.guild_registry import REGISTERED_GUILD_IDS, has_admin_shadow, is_owner, PERSIST_ROOT
from cogs.utils import safe_reply

logger = logging.getLogger("ShadowSyn.Utility")

# --- CONSTANTS & IDS ---
THEME_PRIMARY = 0x2B0B35
OWNER_ID = 482463400929263627

# --- PERSISTENCE ---
try:
    PERSIST_ROOT.mkdir(parents=True, exist_ok=True)
except Exception:
    pass

HASTE_FACTS_STORE = PERSIST_ROOT / "haste_facts.json"

DEFAULT_HASTE_FACTS = [
    "Haste is a man lover", "Haste feeds knights to spearmen", "Haste is the potato peeler",
    "Haste hates women", "Haste loves fat chicks", "Haste would die for brightwood, bro",
    "Haste is a fitzroy enjoyer", "Haste used to get feudal in 3mins... used to",
    "Haste goes Pro scout", "Haste is in a good mood. Jks.", "Haste loves dating paki protestors",
    "Haste is a lefty greeny", "Haste has no dps", "Haste has beef with a dev of a game with sub 1000 players",
    "Haste cant afford ranger gear so he blames the dev", "Haste thinks Maya is fat",
    "Haste was MIA in Shadow Until Jed showed up", "Everyone prefers Haste over Boet",
    "Everyone likes it when Haste has a break down", "Everyone is scared Haste might get bashed at his restaurant",
    "Haste earns 70k a year and that gives Blood anxiety", "Haste Likes using a bow",
    "Haste doesn't have the muscle mass to carry a real life weapon.",
    "Haste never let go of New world.", "Haste only played Vrising cause he thought the outfits were cute."
]


def _atomic_write(file_path: Path, data):
    try:
        content = json.dumps(list(data) if isinstance(data, set) else data, indent=2)
        temp_path = file_path.with_suffix(".tmp")
        temp_path.write_text(content, encoding="utf-8")
        temp_path.replace(file_path)
    except Exception as e:
        logger.error("Persistence Error [%s]: %s", file_path.name, e)


def admin_only():
    def predicate(ctx):
        gid = ctx.guild.id if ctx.guild else None
        return has_admin_shadow(getattr(ctx, "author", None), gid)

    return commands.check(predicate)


def owner_only():
    def predicate(ctx):
        return ctx.author.id == OWNER_ID

    return commands.check(predicate)


def _resolve_member(interaction: discord.Interaction) -> discord.Member | None:
    user = interaction.user
    if isinstance(user, discord.Member):
        return user
    member = getattr(interaction, "member", None)
    if isinstance(member, discord.Member):
        return member
    return None


async def _toggle_claim_role(interaction: discord.Interaction, role_id: int) -> None:
    """Member-safe claim/remove for claim_role_* buttons."""
    if interaction.response.is_done():
        return

    guild = interaction.guild
    if guild is None:
        return await safe_reply(interaction, "❌ Use this inside the server.", ephemeral=True)

    member = _resolve_member(interaction)
    if member is None:
        return await safe_reply(
            interaction,
            "❌ Could not resolve your member profile. Rejoin and try again.",
            ephemeral=True,
        )

    role = guild.get_role(role_id)
    if role is None:
        return await safe_reply(
            interaction, "❌ This role no longer exists on the server.", ephemeral=True
        )

    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=True)

    try:
        if role in member.roles:
            await member.remove_roles(role, reason="ShadowSyn role_button toggle")
            msg = f"➖ You have removed the **{role.name}** role."
        else:
            await member.add_roles(role, reason="ShadowSyn role_button toggle")
            msg = f"✅ You have claimed the **{role.name}** role."
        await interaction.followup.send(msg, ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send(
            "❌ I lack permissions to assign this role.", ephemeral=True
        )
    except Exception as exc:
        logger.error("claim_role toggle failed for %s / role %s: %s", member.id, role_id, exc)
        await interaction.followup.send(f"⚠️ Error: {exc}", ephemeral=True)


# --- UI COMPONENTS ---
class EasyEmbedModal(Modal):
    def __init__(self, channel, edit_msg=None):
        super().__init__(title="Edit Embed" if edit_msg else "Create Custom Embed")
        self.channel = channel
        self.edit_msg = edit_msg
        pre_title = edit_msg.embeds[0].title if edit_msg and edit_msg.embeds else ""
        pre_desc = edit_msg.embeds[0].description if edit_msg and edit_msg.embeds else ""
        pre_foot = (
            edit_msg.embeds[0].footer.text
            if edit_msg and edit_msg.embeds and edit_msg.embeds[0].footer
            else ""
        )
        pre_col = (
            str(hex(edit_msg.embeds[0].color.value)).replace("0x", "#")
            if edit_msg and edit_msg.embeds and edit_msg.embeds[0].color
            else ""
        )
        self.add_item(TextInput(label="Title", placeholder="Embed Title...", value=pre_title, required=True))
        self.add_item(
            TextInput(
                label="Description",
                placeholder="Main content...",
                value=pre_desc,
                style=discord.InputTextStyle.paragraph,
                required=True,
            )
        )
        self.add_item(
            TextInput(
                label="Footer (Optional)",
                placeholder="Small text at bottom...",
                value=pre_foot,
                required=False,
            )
        )
        self.add_item(
            TextInput(label="Color (Hex)", placeholder="#2B0B35", value=pre_col, required=False)
        )

    async def callback(self, interaction: Interaction):
        title = self.children[0].value
        desc = self.children[1].value
        footer = self.children[2].value
        color_raw = self.children[3].value
        try:
            color = int(color_raw.replace("#", ""), 16) if color_raw else THEME_PRIMARY
        except Exception:
            color = THEME_PRIMARY
        embed = discord.Embed(title=title, description=desc, color=color)
        if footer:
            embed.set_footer(text=footer)
        if self.edit_msg:
            await self.edit_msg.edit(embed=embed)
            await interaction.response.send_message("✅ Embed Updated!", ephemeral=True)
        else:
            await self.channel.send(embed=embed)
            await interaction.response.send_message("✅ Embed Sent!", ephemeral=True)


class PersistentRoleView(View):
    def __init__(self, role: discord.Role):
        super().__init__(timeout=None)
        self.role_id = role.id
        btn = Button(
            label=f"Toggle {role.name}",
            style=discord.ButtonStyle.primary,
            custom_id=f"claim_role_{role.id}",
            emoji="🏷️",
        )
        btn.callback = self._claim_callback
        self.add_item(btn)

    async def _claim_callback(self, interaction: discord.Interaction):
        await _toggle_claim_role(interaction, self.role_id)


class UtilityCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_haste_facts = []
        self._load_data()

    def _load_data(self):
        if HASTE_FACTS_STORE.exists():
            try:
                self.active_haste_facts = json.loads(HASTE_FACTS_STORE.read_text(encoding="utf-8"))
            except Exception:
                self.active_haste_facts = list(DEFAULT_HASTE_FACTS)
        else:
            self.active_haste_facts = list(DEFAULT_HASTE_FACTS)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        custom_id = (interaction.data or {}).get("custom_id", "")
        if not custom_id.startswith("claim_role_"):
            return
        if interaction.response.is_done():
            return
        try:
            role_id = int(custom_id.replace("claim_role_", "", 1))
        except ValueError:
            return
        await _toggle_claim_role(interaction, role_id)

    @discord.slash_command(
        name="role_button",
        description="Deploy a persistent button for users to claim a role",
        guild_ids=REGISTERED_GUILD_IDS,
        default_member_permissions=discord.Permissions(manage_roles=True),
    )
    @admin_only()
    async def role_button(
        self, ctx, role: Option(discord.Role, description="Select the role to attach to the button")
    ):
        if not ctx.guild:
            return await ctx.respond("⛔ Guild context required.", ephemeral=True)

        bot_member = ctx.guild.me
        if bot_member is None:
            return await ctx.respond("❌ Bot unavailable.", ephemeral=True)

        if role.is_default():
            return await ctx.respond("❌ Can't attach @everyone to a claim button.", ephemeral=True)
        if role.managed:
            return await ctx.respond(
                "❌ That role is managed (integration/boost) and can't be assigned.",
                ephemeral=True,
            )
        if role.position >= bot_member.top_role.position:
            return await ctx.respond(
                f"❌ **{role.name}** is above my top role — I can't assign it.",
                ephemeral=True,
            )
        if (
            not is_owner(ctx.author)
            and isinstance(ctx.author, discord.Member)
            and role.position >= ctx.author.top_role.position
        ):
            return await ctx.respond(
                f"❌ **{role.name}** is at or above your top role.",
                ephemeral=True,
            )

        embed = discord.Embed(
            title="🏷️ Role Assignment",
            description=f"Click the button below to claim or remove the {role.mention} role.",
            color=THEME_PRIMARY,
        )
        view = PersistentRoleView(role)
        await ctx.respond("✅ Deploying role button...", ephemeral=True)
        await ctx.channel.send(embed=embed, view=view)
        self.bot.add_view(view)

    @role_button.error
    async def role_button_error(self, ctx, error: discord.DiscordException):
        if isinstance(error, commands.CheckFailure):
            return await safe_reply(ctx, "🚫 Admin clearance required.", ephemeral=True)
        logger.error("role_button error: %s", error)
        await safe_reply(ctx, f"⚠️ Error: {error}", ephemeral=True)

    @discord.slash_command(
        name="send_custom",
        description="Send a clean embed message",
        guild_ids=REGISTERED_GUILD_IDS,
        default_member_permissions=discord.Permissions(manage_messages=True),
    )
    @admin_only()
    async def send_custom(self, ctx, channel: Option(discord.TextChannel, required=False)):
        target = channel or ctx.channel
        await ctx.send_modal(EasyEmbedModal(target))

    @send_custom.error
    async def send_custom_error(self, ctx, error: discord.DiscordException):
        if isinstance(error, commands.CheckFailure):
            return await safe_reply(ctx, "🚫 Admin clearance required.", ephemeral=True)

    @discord.slash_command(
        name="edit_custom",
        description="Edit an existing bot embed",
        guild_ids=REGISTERED_GUILD_IDS,
        default_member_permissions=discord.Permissions(manage_messages=True),
    )
    @admin_only()
    async def edit_custom(
        self, ctx, message_id: str, channel: Option(discord.TextChannel, required=False)
    ):
        target_channel = channel or ctx.channel
        try:
            msg = await target_channel.fetch_message(int(message_id))
            if msg.author != self.bot.user:
                return await ctx.respond("❌ I can only edit my own messages.", ephemeral=True)
            await ctx.send_modal(EasyEmbedModal(target_channel, edit_msg=msg))
        except Exception as e:
            await ctx.respond(f"❌ Error finding message: {e}", ephemeral=True)

    @edit_custom.error
    async def edit_custom_error(self, ctx, error: discord.DiscordException):
        if isinstance(error, commands.CheckFailure):
            return await safe_reply(ctx, "🚫 Admin clearance required.", ephemeral=True)

    @discord.slash_command(
        name="haste",
        description="Random Haste Fact",
        guild_ids=REGISTERED_GUILD_IDS,
    )
    async def haste(self, ctx):
        if not self.active_haste_facts:
            return await safe_reply(ctx, "No facts yet.")
        await safe_reply(ctx, f"🍌 **Fact:** {random.choice(self.active_haste_facts)}")

    @discord.slash_command(
        name="morehaste",
        description="Add Haste Fact",
        guild_ids=REGISTERED_GUILD_IDS,
        default_member_permissions=discord.Permissions(manage_messages=True),
    )
    @admin_only()
    async def morehaste(self, ctx, fact: str):
        self.active_haste_facts.append(fact)
        _atomic_write(HASTE_FACTS_STORE, self.active_haste_facts)
        await safe_reply(ctx, "✅ Added.")

    @morehaste.error
    async def morehaste_error(self, ctx, error: discord.DiscordException):
        if isinstance(error, commands.CheckFailure):
            return await safe_reply(ctx, "🚫 Admin clearance required.", ephemeral=True)


def setup(bot):
    bot.add_cog(UtilityCog(bot))
