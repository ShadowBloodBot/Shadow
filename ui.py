import discord
from discord.ui import View, Button
from moderation import handle_shadowmute  # still imported in case you use elsewhere
from role_manager import launch_role_manager
from user_panel import view_user_sheet
from filters import get_flagged_users
from storage import load_flags
from analytics import get_bot_stats
from mod_queue import ModQueueView

class ShadowControlPanel(View):
    def __init__(self, bot, author):
        super().__init__(timeout=None)
        self.bot = bot
        self.author = author

        self.add_item(Button(label="Refresh Panel", style=discord.ButtonStyle.grey, custom_id="refresh"))
        self.add_item(Button(label="Analytics", style=discord.ButtonStyle.blurple, custom_id="analytics"))
        self.add_item(Button(label="Search Users", style=discord.ButtonStyle.secondary, custom_id="search"))
        self.add_item(Button(label="Mod Queue", style=discord.ButtonStyle.red, custom_id="mod_queue"))
        self.add_item(Button(label="Role Manager", style=discord.ButtonStyle.primary, custom_id="role_manager"))
        self.add_item(Button(label="User Panel", style=discord.ButtonStyle.secondary, custom_id="user_sheet"))
        self.add_item(Button(label="Flagged Users", style=discord.ButtonStyle.success, custom_id="flagged_list"))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        await interaction.response.defer()
        await self.on_button_click(interaction, interaction.data["custom_id"])
        return False

    async def on_button_click(self, interaction: discord.Interaction, custom_id: str):
        if custom_id == "refresh":
            await interaction.response.edit_message(content="🔄 Refreshed panel.", view=self)

        elif custom_id == "analytics":
            stats = get_bot_stats(self.bot)
            embed = discord.Embed(title="📊 Bot Analytics")
            for key, val in stats.items():
                embed.add_field(name=key.capitalize(), value=str(val))
            await interaction.response.send_message(embed=embed, ephemeral=True)

        elif custom_id == "search":
            await view_user_sheet(interaction)

        elif custom_id == "mod_queue":
            flagged = [m for m in interaction.guild.members if not m.bot][:25]
            await interaction.response.send_message("📥 Reviewing Mod Queue", view=ModQueueView(flagged), ephemeral=True)

        elif custom_id == "role_manager":
            await launch_role_manager(interaction)

        elif custom_id == "user_sheet":
            await view_user_sheet(interaction)

        elif custom_id == "flagged_list":
            users = load_flags()
            await interaction.response.send_message(f"🚩 Flagged Users:\n{', '.join(users.keys())}", ephemeral=True)

    async def on_error(self, interaction: discord.Interaction, error: Exception, item):
        await interaction.response.send_message("⚠️ An error occurred during button click.", ephemeral=True)
