import discord
from discord.ui import View, Button
from storage import get_flagged_users

class ShadowControlPanel(View):
    def __init__(self, bot, user):
        super().__init__(timeout=None)
        self.bot = bot
        self.user = user

        self.add_item(Button(label="Mod Queue", style=discord.ButtonStyle.danger, custom_id="mod_queue"))

    @discord.ui.button(label="Mod Queue", style=discord.ButtonStyle.danger, custom_id="mod_queue_button")
    async def show_mod_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user:
            await interaction.response.send_message("❌ You are not authorized to use this panel.", ephemeral=True)
            return

        flagged = get_flagged_users()
        if not flagged:
            await interaction.response.send_message("✅ No flagged users currently in the queue.", ephemeral=True)
            return

        embed = discord.Embed(title="🚨 Mod Queue", color=discord.Color.red())
        for uid, info in flagged.items():
            embed.add_field(
                name=f"User ID: {uid}",
                value=f"Score: **{info['score']}**\nReason: {info['reason']}",
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)
