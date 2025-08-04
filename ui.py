import discord
from discord.ui import View, Button
from moderation import handle_shadowmute
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
        return interaction.user == self.author

    async def on_button_click(self, interaction: discord.Interaction, custom_id: str):
        try:
            # If launching a modal, skip defer
            if custom_id in ["search", "user_sheet"]:
                await view_user_sheet(interaction)
                return

            await interaction.response.defer(ephemeral=True)

            if custom_id == "refresh":
                await interaction.edit_original_response(content="🔄 Refreshed panel.", view=self)

            elif custom_id == "analytics":
                stats = get_bot_stats(self.bot)
                embed = discord.Embed(title="📊 Bot Analytics")
                for key, val in stats.items():
                    embed.add_field(name=key.capitalize(), value=str(val))
                await interaction.followup.send(embed=embed, ephemeral=True)

            elif custom_id == "mod_queue":
                flagged = [m for m in interaction.guild.members if not m.bot][:25]
                await interaction.followup.send("📥 Reviewing Mod Queue", view=ModQueueView(flagged), ephemeral=True)

            elif custom_id == "role_manager":
                await launch_role_manager(interaction)

            elif custom_id == "flagged_list":
                users = load_flags()
                await interaction.followup.send(f"🚩 Flagged Users:\n{', '.join(users.keys())}", ephemeral=True)

        except Exception as e:
            try:
                await interaction.followup.send(f"⚠️ Error: {e}", ephemeral=True)
            except:
                pass

    async def on_error(self, interaction: discord.Interaction, error: Exception, item):
        try:
            await interaction.followup.send("❌ UI error occurred.", ephemeral=True)
        except:
            pass
