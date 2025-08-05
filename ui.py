import discord
from discord.ui import View, Button, Select, Modal, TextInput
from discord.ext import tasks
from filters import get_severity_score, suggest_action
from storage import fetch_flagged_users, clear_flag, log_case
from logging import send_log
import asyncio

class ShadowControlPanel:
    def __init__(self, bot):
        self.bot = bot
        self.view = None
        self.panel_message = None

    async def build(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🛡️ Shadow Mod Control Panel",
            description="Review flagged users and take action.",
            color=discord.Color.blurple()
        )
        embed.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)

        users = await fetch_flagged_users(interaction.guild.id)
        if not users:
            embed.add_field(name="✅ All Clear", value="No flagged users in the queue.", inline=False)
            return embed, View(timeout=None)

        member_options = []
        for u in users:
            member = interaction.guild.get_member(u["user_id"])
            if not member:
                continue
            label = f"{member.display_name} ({get_severity_score(u)}⚠️)"
            desc = suggest_action(u["score"])
            member_options.append(discord.SelectOption(label=label, description=desc, value=str(u["user_id"])))

        member_select = Select(placeholder="Select flagged user", options=member_options, custom_id="select_user")

        class ActionView(View):
            def __init__(self):
                super().__init__(timeout=None)
                self.selected_user_id = None

            @discord.ui.select(placeholder="Choose a user", options=member_options, custom_id="select_user")
            async def select_callback(self, select: Select, interaction: discord.Interaction):
                self.selected_user_id = int(select.values[0])
                member = interaction.guild.get_member(self.selected_user_id)
                embed = discord.Embed(
                    title=f"👤 {member.display_name}",
                    description=f"Severity: {get_severity_score({'score': 3})} – Suggested: {suggest_action(3)}",
                    color=discord.Color.gold()
                )
                embed.set_thumbnail(url=member.display_avatar.url)
                await interaction.response.edit_message(embed=embed, view=self)

            @discord.ui.button(label="✅ Approve", style=discord.ButtonStyle.success, custom_id="approve_btn")
            async def approve(self, button: Button, interaction: discord.Interaction):
                if not self.selected_user_id:
                    await interaction.response.send_message("Please select a user first.", ephemeral=True)
                    return
                await clear_flag(interaction.guild.id, self.selected_user_id)
                await interaction.response.send_message("✅ Flag cleared.", ephemeral=True)
                await send_log(f"{interaction.user.mention} approved {self.selected_user_id}")

            @discord.ui.button(label="🕓 Timeout", style=discord.ButtonStyle.secondary, custom_id="timeout_btn")
            async def timeout(self, button: Button, interaction: discord.Interaction):
                if not self.selected_user_id:
                    await interaction.response.send_message("Please select a user first.", ephemeral=True)
                    return
                member = interaction.guild.get_member(self.selected_user_id)

                class TimeoutModal(Modal, title="Timeout Duration"):
                    duration = TextInput(label="Enter duration in minutes", required=True)

                    async def on_submit(self, modal_interaction: discord.Interaction):
                        try:
                            minutes = int(self.duration.value)
                            await member.timeout(duration=discord.utils.utcnow() + discord.timedelta(minutes=minutes))
                            await modal_interaction.response.send_message(f"🕓 Timed out for {minutes} minutes.", ephemeral=True)
                            await log_case("timeout", member, interaction.user, f"Manual timeout via panel ({minutes}m)")
                        except Exception as e:
                            await modal_interaction.response.send_message("❌ Error applying timeout.", ephemeral=True)
                            print(e)

                await interaction.response.send_modal(TimeoutModal())

            @discord.ui.button(label="❌ Kick", style=discord.ButtonStyle.danger, custom_id="kick_btn")
            async def kick(self, button: Button, interaction: discord.Interaction):
                if not self.selected_user_id:
                    await interaction.response.send_message("Please select a user first.", ephemeral=True)
                    return
                member = interaction.guild.get_member(self.selected_user_id)
                try:
                    await member.kick(reason="Kicked via Shadow Panel")
                    await interaction.response.send_message("❌ Member kicked.", ephemeral=True)
                    await log_case("kick", member, interaction.user, "Manual kick via panel")
                except Exception as e:
                    await interaction.response.send_message("❌ Could not kick member.", ephemeral=True)
                    print(e)

        view = ActionView()
        return embed, view
