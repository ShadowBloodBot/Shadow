# cogs/utility.py
import os
import json
import random
from pathlib import Path

import discord
from discord.ext import commands
from discord import Option, Interaction
from discord.ui import Modal, TextInput, View, Button

from cogs.guild_registry import REGISTERED_GUILD_IDS, is_owner, role_id

# --- CONSTANTS & IDS ---
THEME_PRIMARY = 0x2B0B35
OWNER_ID = 482463400929263627

# --- PERSISTENCE ---
PERSIST_ROOT = Path(os.getenv("PERSIST_PATH", "/data")).resolve()
try: PERSIST_ROOT.mkdir(parents=True, exist_ok=True)
except: PERSIST_ROOT = Path(".").resolve()

HASTE_FACTS_STORE = (PERSIST_ROOT / "haste_facts.json")

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
        temp_path.write_text(content, encoding='utf-8')
        temp_path.replace(file_path)
    except Exception as e:
        print(f"⚠️ Persistence Error [{file_path.name}]: {e}")

# --- HELPERS ---
def admin_only():
    def predicate(ctx):
        if is_owner(getattr(ctx, "author", None)):
            return True
        if not isinstance(ctx.author, discord.Member):
            return False
        admin_rid = role_id(ctx.guild.id, "admin_shadow")
        if admin_rid is None:
            return False
        return any(r.id == admin_rid for r in ctx.author.roles)
    return commands.check(predicate)

def owner_only():
    def predicate(ctx): return ctx.author.id == OWNER_ID
    return commands.check(predicate)

async def safe_reply(ctx_or_inter, *args, **kwargs):
    try:
        if hasattr(ctx_or_inter, 'respond'): return await ctx_or_inter.respond(*args, **kwargs)
        elif hasattr(ctx_or_inter, 'response'):
            if not ctx_or_inter.response.is_done(): return await ctx_or_inter.response.send_message(*args, **kwargs)
            else: return await ctx_or_inter.followup.send(*args, **kwargs)
    except: return None

# --- UI COMPONENTS ---
class EasyEmbedModal(Modal):
    def __init__(self, channel, edit_msg=None):
        super().__init__(title="Edit Embed" if edit_msg else "Create Custom Embed")
        self.channel = channel; self.edit_msg = edit_msg
        pre_title = edit_msg.embeds[0].title if edit_msg and edit_msg.embeds else ""
        pre_desc = edit_msg.embeds[0].description if edit_msg and edit_msg.embeds else ""
        pre_foot = edit_msg.embeds[0].footer.text if edit_msg and edit_msg.embeds and edit_msg.embeds[0].footer else ""
        pre_col = str(hex(edit_msg.embeds[0].color.value)).replace("0x", "#") if edit_msg and edit_msg.embeds and edit_msg.embeds[0].color else ""
        self.add_item(TextInput(label="Title", placeholder="Embed Title...", value=pre_title, required=True))
        self.add_item(TextInput(label="Description", placeholder="Main content...", value=pre_desc, style=discord.InputTextStyle.paragraph, required=True))
        self.add_item(TextInput(label="Footer (Optional)", placeholder="Small text at bottom...", value=pre_foot, required=False))
        self.add_item(TextInput(label="Color (Hex)", placeholder="#2B0B35", value=pre_col, required=False))
        
    async def callback(self, interaction: Interaction):
        title = self.children[0].value; desc = self.children[1].value; footer = self.children[2].value; color_raw = self.children[3].value
        try: color = int(color_raw.replace("#", ""), 16) if color_raw else THEME_PRIMARY
        except: color = THEME_PRIMARY
        embed = discord.Embed(title=title, description=desc, color=color)
        if footer: embed.set_footer(text=footer)
        if self.edit_msg:
            await self.edit_msg.edit(embed=embed); await interaction.response.send_message("✅ Embed Updated!", ephemeral=True)
        else:
            await self.channel.send(embed=embed); await interaction.response.send_message("✅ Embed Sent!", ephemeral=True)

class PersistentRoleView(View):
    def __init__(self, role: discord.Role):
        super().__init__(timeout=None)
        btn = Button(
            label=f"Toggle {role.name}", 
            style=discord.ButtonStyle.primary, 
            custom_id=f"claim_role_{role.id}",
            emoji="🏷️"
        )
        self.add_item(btn)

class UtilityCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_haste_facts = []
        self._load_data()

    def _load_data(self):
        if HASTE_FACTS_STORE.exists():
            try: self.active_haste_facts = json.loads(HASTE_FACTS_STORE.read_text())
            except: self.active_haste_facts = list(DEFAULT_HASTE_FACTS)
        else: self.active_haste_facts = list(DEFAULT_HASTE_FACTS)

    # --- STATELESS PERSISTENT LISTENER ---
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type == discord.InteractionType.component:
            custom_id = interaction.data.get("custom_id", "")
            if custom_id.startswith("claim_role_"):
                try:
                    role_id = int(custom_id.replace("claim_role_", ""))
                    role = interaction.guild.get_role(role_id)
                    
                    if not role:
                        return await safe_reply(interaction, "❌ This role no longer exists on the server.", ephemeral=True)
                    
                    if role in interaction.user.roles:
                        await interaction.user.remove_roles(role)
                        await safe_reply(interaction, f"➖ You have removed the **{role.name}** role.", ephemeral=True)
                    else:
                        await interaction.user.add_roles(role)
                        await safe_reply(interaction, f"✅ You have claimed the **{role.name}** role.", ephemeral=True)
                
                except discord.Forbidden:
                    await safe_reply(interaction, "❌ I lack permissions to assign this role.", ephemeral=True)
                except Exception as e:
                    await safe_reply(interaction, f"⚠️ Error: {e}", ephemeral=True)

    @discord.slash_command(
        name="role_button",
        description="Deploy a persistent button for users to claim a role",
        guild_ids=REGISTERED_GUILD_IDS,
    )
    @admin_only()
    async def role_button(self, ctx, role: Option(discord.Role, description="Select the role to attach to the button")):
        embed = discord.Embed(
            title="🏷️ Role Assignment",
            description=f"Click the button below to claim or remove the {role.mention} role.",
            color=THEME_PRIMARY
        )
        await safe_reply(ctx, "✅ Deploying role button...", ephemeral=True)
        await ctx.channel.send(embed=embed, view=PersistentRoleView(role))

    @discord.slash_command(
        name="send_custom",
        description="Send a clean embed message",
        guild_ids=REGISTERED_GUILD_IDS,
    )
    @admin_only()
    async def send_custom(self, ctx, channel: Option(discord.TextChannel, required=False)):
        target = channel or ctx.channel
        await ctx.send_modal(EasyEmbedModal(target))

    @discord.slash_command(
        name="edit_custom",
        description="Edit an existing bot embed",
        guild_ids=REGISTERED_GUILD_IDS,
    )
    @admin_only()
    async def edit_custom(self, ctx, message_id: str, channel: Option(discord.TextChannel, required=False)):
        target_channel = channel or ctx.channel
        try:
            msg = await target_channel.fetch_message(int(message_id))
            if msg.author != self.bot.user: return await ctx.respond("❌ I can only edit my own messages.", ephemeral=True)
            await ctx.send_modal(EasyEmbedModal(target_channel, edit_msg=msg))
        except Exception as e: await ctx.respond(f"❌ Error finding message: {e}", ephemeral=True)

    @discord.slash_command(
        name="haste",
        description="Random Haste Fact",
        guild_ids=REGISTERED_GUILD_IDS,
    )
    async def haste(self, ctx):
        if not self.active_haste_facts: return await safe_reply(ctx, "No facts yet.")
        await safe_reply(ctx, f"🍌 **Fact:** {random.choice(self.active_haste_facts)}")

    @discord.slash_command(
        name="morehaste",
        description="Add Haste Fact",
        guild_ids=REGISTERED_GUILD_IDS,
    )
    @admin_only()
    async def morehaste(self, ctx, fact: str):
        self.active_haste_facts.append(fact)
        _atomic_write(HASTE_FACTS_STORE, self.active_haste_facts)
        await safe_reply(ctx, "✅ Added.")

def setup(bot):
    bot.add_cog(UtilityCog(bot))
