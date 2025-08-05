import discord
from discord.ui import View, Button, Select
from discord import SelectOption
from moderation import handle_mass_action, handle_shadowmute
from user_panel import view_user_sheet
from ai_suggestions import get_severity_score
from analytics import get_bot_stats

class ShadowControlPanel(View):
    def __init__(self, bot, author):
        super().__init__(timeout=None)
        self.bot = bot
        self.author = author

        self.add_item(Button(label="Mass Ban", style=discord.ButtonStyle.danger, custom_id="mass_ban"))
        self.add_item(Button(label="ShadowMute", style=discord.ButtonStyle.secondary, custom_id="shadow_mute"))
        self.add_item(Button(label="Role Manager", style=discord.ButtonStyle.primary, custom_id="role_manager"))
        self.add_item(Button(label="User Panel", style=discord.ButtonStyle.secondary, custom_id="user_sheet"))
        self.add_item(Button(label="Flagged Users", style=discord.ButtonStyle.success, custom_id="flagged_list"))
        self.add_item(Button(label="Mod Queue", style=discord.ButtonStyle.red, custom_id="mod_queue"))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user == self.author

    async def on_error(self, interaction: discord.Interaction, error: Exception, item):
        await interaction.response.send_message("⚠️ An error occurred.", ephemeral=True)

    @discord.ui.button(label="Refresh Panel", style=discord.ButtonStyle.grey)
    async def refresh(self, button: Button, interaction: discord.Interaction):
        await interaction.response.edit_message(content="🔄 Refreshed panel.", view=self)

    @discord.ui.button(label="Analytics", style=discord.ButtonStyle.blurple)
    async def analytics(self, button: Button, interaction: discord.Interaction):
        stats = get_bot_stats(self.bot)
        embed = discord.Embed(title="📊 Bot Analytics")
        for key, val in stats.items():
            embed.add_field(name=key.capitalize(), value=str(val))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Search Users", style=discord.ButtonStyle.secondary)
    async def search(self, button: Button, interaction: discord.Interaction):
        from user_panel import SearchUserModal
        modal = SearchUserModal()
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Mod Queue", style=discord.ButtonStyle.red)
    async def mod_queue(self, button: Button, interaction: discord.Interaction):
        from mod_queue import ModQueueView
        flagged = [m for m in interaction.guild.members if not m.bot and get_severity_score(m) >= 3]
        if not flagged:
            await interaction.response.send_message("✅ No users currently in the mod queue.", ephemeral=True)
            return
        await interaction.response.send_message("📥 Reviewing Mod Queue", view=ModQueueView(flagged), ephemeral=True)
