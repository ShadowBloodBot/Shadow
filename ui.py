import discord
from discord.ui import View, Button
from filters import get_flagged_users

class ModQueueView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ModQueueButton())

class ModQueueButton(Button):
    def __init__(self):
        super().__init__(label="Mod Queue", style=discord.ButtonStyle.danger)

    async def callback(self, interaction: discord.Interaction):
        try:
            flags = get_flagged_users()
            if not flags:
                await interaction.response.send_message("✅ Mod Queue is empty — no flagged users.", ephemeral=True)
                return

            embed = discord.Embed(title="🚨 ShadowBot Mod Queue", color=discord.Color.red())
            for user_id, data in flags.items():
                embed.add_field(
                    name=f"{data['username']} (`{user_id}`)",
                    value=f"**Score:** {data['score']}\n**AI Suggestion:** {data['reason']}",
                    inline=False
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            print(f"[Mod Queue] Failed to send: {e}")
            await interaction.response.send_message("❌ Failed to load Mod Queue.", ephemeral=True)


class ShadowControlPanel(View):
    def __init__(self, bot, user):
        super().__init__(timeout=None)
        self.bot = bot
        self.user = user
        self.add_item(ModQueueButton())
