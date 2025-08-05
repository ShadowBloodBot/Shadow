import discord
from discord.ui import View, Button, Select
from log_utils import send_log  # ✅ Fixed

class ShadowControlPanel:
    def __init__(self, bot: discord.Client):
        self.bot = bot

    async def build(self, channel: discord.abc.Messageable):
        embed = discord.Embed(
            title="🛡️ Shadow Moderation Panel",
            description="Manage flagged users and automate moderation actions.\nUse the dropdown below to view Mod Queue.",
            color=discord.Color.dark_purple()
        )
        embed.set_footer(text="Dyno Replacement Bot — Elite Tier")

        view = ShadowPanelView(self.bot)
        return embed, view

class ShadowPanelView(View):
    def __init__(self, bot: discord.Client):
        super().__init__(timeout=None)
        self.bot = bot
        self.add_item(ModQueueSelect())

class ModQueueSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="🧾 View Mod Queue", value="queue", description="See all auto-flagged users")
        ]
        super().__init__(placeholder="Choose a moderation view...", options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ You can't use this.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            from storage import fetch_flagged_users
            from filters import get_severity_score, suggest_action

            flagged = await fetch_flagged_users(interaction.guild.id)
            if not flagged:
                await interaction.followup.send("✅ No flagged users found.", ephemeral=True)
                return

            lines = []
            for user_data in flagged[:25]:
                user_id = user_data["user_id"]
                score = user_data["score"]
                member = interaction.guild.get_member(user_id)
                tag = member.mention if member else f"<@{user_id}>"
                severity = get_severity_score(user_data)
                action = suggest_action(score)
                lines.append(f"• {tag} — Score: `{score}` — {severity} → **{action}**")

            embed = discord.Embed(
                title="🚨 Mod Queue",
                description="\n".join(lines),
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            await send_log(f"[MOD QUEUE ERROR] {e}")
            await interaction.followup.send("❌ Failed to load mod queue.", ephemeral=True)
