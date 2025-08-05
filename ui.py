import discord
from discord.ui import View, Button
from ai_suggestions import get_severity_score
from mod_queue import ModQueueView

class ShadowControlPanel(View):
    def __init__(self, bot, author):
        super().__init__(timeout=None)
        self.bot = bot
        self.author = author

        self.add_item(Button(label="Mod Queue", style=discord.ButtonStyle.danger, custom_id="mod_queue"))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user == self.author

    async def on_error(self, interaction: discord.Interaction, error: Exception, item):
        await interaction.response.send_message("⚠️ An error occurred in the panel.", ephemeral=True)

    @discord.ui.button(label="Mod Queue", style=discord.ButtonStyle.red)
    async def mod_queue(self, button: Button, interaction: discord.Interaction):
        # Show members flagged by /scan from saved storage
        from storage import load_flags
        flagged_data = load_flags()
        flagged_ids = list(flagged_data.keys())
        flagged_members = [m for m in interaction.guild.members if str(m.id) in flagged_ids and not m.bot]

        if not flagged_members:
            await interaction.response.send_message("✅ No flagged users found in the Mod Queue.", ephemeral=True)
            return

        await interaction.response.send_message("📥 Reviewing Mod Queue", view=ModQueueView(flagged_members), ephemeral=True)
