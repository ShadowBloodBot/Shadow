import discord
from discord.ext import commands
from discord import ui
from storage import load_flags

class ShadowControlPanel(discord.ui.View):
    def __init__(self, bot, user):
        super().__init__(timeout=None)
        self.bot = bot
        self.user = user

    @discord.ui.button(label="Mod Queue", style=discord.ButtonStyle.danger, custom_id="mod_queue")
    async def mod_queue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user:
            await interaction.response.send_message("Only the command invoker can use this panel.", ephemeral=True)
            return

        flagged = load_flags()
        if not flagged:
            await interaction.response.send_message("✅ No flagged users found.", ephemeral=True)
            return

        embed = discord.Embed(
            title="🧠 Mod Queue",
            description="These members were flagged by the Shadow AI system.",
            color=discord.Color.orange()
        )
        for user_id, info in flagged.items():
            embed.add_field(
                name=f"{info['username']} (ID: {user_id})",
                value=f"**Score**: {info['score']}\n**Reason**: {info['reason']}",
                inline=False
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)
