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
        self.clear_items()
        self.add_item(self.refresh_button)

        flagged = get_flagged_users()
        if not flagged:
            empty_btn = Button(label="✅ No flagged users", disabled=True)
            self.add_item(empty_btn)
            return

        for user_data in flagged:
            uid = user_data["user_id"]
            sev = user_data.get("severity", 0)
            reason = user_data.get("reason", "Unknown")
            label = f"⚠️ {uid} | Severity: {sev}"

            action_btn = Button(
                label=label,
                style=discord.ButtonStyle.danger if sev >= 3 else discord.ButtonStyle.secondary,
                custom_id=f"mod_action_{uid}"
            )

            async def action_callback(interaction: discord.Interaction, user_id=uid):
                try:
                    member = interaction.guild.get_member(user_id)
                    if member:
                        await member.kick(reason="Auto-flagged by AI system")
                        await send_log(f"👢 Kicked flagged user <@{user_id}> (Severity {sev})", channel=None)
                    else:
                        await send_log(f"⚠️ Tried to kick <@{user_id}> but they are no longer in the server", channel=None)

                    clear_flag(user_id)
                    await interaction.response.edit_message(content="✅ User processed and removed from queue.", view=ModerationControlView())
                except Exception as e:
                    await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

            action_btn.callback = action_callback
            self.add_item(action_btn)

    async def refresh_mod_queue(self, interaction: discord.Interaction):
        self.render_flagged_users()
        await interaction.response.edit_message(view=self)
