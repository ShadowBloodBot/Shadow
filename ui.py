import discord
from discord.ui import View, Button
from mod_queue import ModQueueView
from storage import load_flags

class ShadowControlPanel(View):
    def __init__(self, bot, author):
        super().__init__(timeout=None)
        self.bot = bot
        self.author = author

        mod_queue_button = Button(label="Mod Queue", style=discord.ButtonStyle.red)
        mod_queue_button.callback = self.open_mod_queue
        self.add_item(mod_queue_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user == self.author

    async def on_error(self, interaction: discord.Interaction, error: Exception, item):
        await interaction.response.send_message("⚠️ An error occurred in the panel.", ephemeral=True)

    async def open_mod_queue(self, interaction: discord.Interaction):
        flagged_data = load_flags()
        flagged_ids = list(flagged_data.keys())
        flagged_members = [m for m in interaction.guild.members if str(m.id) in flagged_ids and not m.bot]

        if not flagged_members:
            await interaction.response.send_message("✅ No flagged users found in the Mod Queue.", ephemeral=True)
            return

        await interaction.response.send_message("📥 Reviewing Mod Queue", view=ModQueueView(flagged_members), ephemeral=True)
