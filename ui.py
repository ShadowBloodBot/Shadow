# ui.py

import discord
from discord.ui import View, Button
from storage import get_flagged_users, clear_flag
from log_utils import send_log

class ModerationControlView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.refresh_button = Button(
            label="🔄 Refresh Mod Queue",
            style=discord.ButtonStyle.primary,
            custom_id="refresh_queue"
        )
        self.refresh_button.callback = self.refresh_mod_queue
        self.add_item(self.refresh_button)
        self.render_flagged_users()

    def render_flagged_users(self):
        # Clear everything and re-add refresh
        self.clear_items()
        self.add_item(self.refresh_button)

        flagged = get_flagged_users()
        if not flagged:
            self.add_item(Button(label="✅ No flagged users", disabled=True))
            return

        for user_data in flagged:
            user_id = user_data.get("user_id")
            severity = user_data.get("severity", 0)
            reason = user_data.get("reason", "Unknown")
            label = f"⚠️ {user_id} | Severity: {severity}"

            style = discord.ButtonStyle.danger if severity >= 3 else discord.ButtonStyle.secondary
            button = Button(label=label, style=style, custom_id=f"mod_action_{user_id}")

            async def callback(interaction: discord.Interaction, uid=user_id, sev=severity):
                if not interaction.guild:
                    await interaction.response.send_message("❌ Error: Guild context missing.", ephemeral=True)
                    return

                member = interaction.guild.get_member(uid)
                try:
                    if member:
                        await member.kick(reason="Auto-flagged by AI system")
                        await send_log(f"👢 {interaction.user.mention} kicked <@{uid}> (Severity {sev})")
                    else:
                        await send_log(f"⚠️ <@{uid}> was flagged but is no longer in the server.")

                    clear_flag(uid)
                    await interaction.response.edit_message(
                        content="✅ User processed and removed from queue.",
                        view=ModerationControlView()
                    )
                except discord.Forbidden:
                    await interaction.response.send_message("🚫 I don't have permission to kick that user.", ephemeral=True)
                except Exception as e:
                    await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

            button.callback = callback
            self.add_item(button)

    async def refresh_mod_queue(self, interaction: discord.Interaction):
        try:
            self.render_flagged_users()
            await interaction.response.edit_message(view=self)
        except Exception as e:
            print(f"[UI] Refresh error: {e}")
            await interaction.response.send_message("❌ Failed to refresh view.", ephemeral=True)
