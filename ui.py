import discord
from discord import ui
from discord.ext import tasks
from filters import get_severity_score
from storage import get_flagged_users
from log_utils import send_log

MOD_ROLE_ID = 955600547266822174


class ModerationDropdown(ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="View Mod Queue", value="queue", emoji="🔍", description="See all auto-flagged users"),
            discord.SelectOption(label="Active Timeouts", value="timeouts", emoji="⏳", description="View all currently timed-out users"),
            discord.SelectOption(label="Case Logs", value="logs", emoji="📋", description="Browse moderation history (coming soon)"),
            discord.SelectOption(label="Live Joins", value="live", emoji="🚨", description="Watch join events in real time (coming soon)"),
        ]
        super().__init__(
            placeholder="Choose a moderation view...",
            options=options,
            min_values=1,
            max_values=1,
            custom_id="mod_dropdown"  # ✅ Required for persistence
        )

    async def callback(self, interaction: discord.Interaction):
        if not any(role.id == MOD_ROLE_ID for role in interaction.user.roles):
            await interaction.response.send_message("🚫 You don't have permission to use this.", ephemeral=True)
            return

        selection = self.values[0]

        if selection == "queue":
            users = get_flagged_users()
            if not users:
                await interaction.response.send_message("✅ No users in the Mod Queue.", ephemeral=True)
                return

            embed = discord.Embed(title="🚨 Mod Queue", color=discord.Color.red())
            for user_id, data in users.items():
                embed.add_field(
                    name=f"<@{user_id}>",
                    value=f"Score: `{data['score']}`\nReason: {data['reason']}",
                    inline=False
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        elif selection == "timeouts":
            members = [m for m in interaction.guild.members if m.timed_out_until]
            embed = discord.Embed(title="⏳ Active Timeouts", color=discord.Color.orange())

            if not members:
                embed.description = "There are no members currently timed out."
            else:
                for m in members:
                    until = discord.utils.format_dt(m.timed_out_until, style='R')
                    embed.add_field(name=m.display_name, value=f"Until: {until}", inline=False)

            await interaction.response.send_message(embed=embed, ephemeral=True)

        elif selection == "logs":
            await interaction.response.send_message("🧾 Case Log Viewer coming soon.", ephemeral=True)

        elif selection == "live":
            await interaction.response.send_message("🚨 Live Join Feed coming soon.", ephemeral=True)


class RefreshPanelButton(ui.Button):
    def __init__(self):
        super().__init__(label="Refresh Panel", emoji="🔄", style=discord.ButtonStyle.secondary, custom_id="refresh_panel")

    async def callback(self, interaction: discord.Interaction):
        if not any(role.id == MOD_ROLE_ID for role in interaction.user.roles):
            await interaction.response.send_message("🚫 You don't have permission.", ephemeral=True)
            return

        await send_shadow_panel(interaction.channel, force=True)
        await interaction.response.send_message("🔁 Panel refreshed.", ephemeral=True)


class ScanNowButton(ui.Button):
    def __init__(self):
        super().__init__(label="Scan Now", emoji="👥", style=discord.ButtonStyle.danger, custom_id="scan_now")

    async def callback(self, interaction: discord.Interaction):
        if not any(role.id == MOD_ROLE_ID for role in interaction.user.roles):
            await interaction.response.send_message("🚫 You can't do this.", ephemeral=True)
            return

        await interaction.response.send_message("🛰️ Scan initiated...", ephemeral=True)
        await send_log(f"🛰️ {interaction.user.mention} triggered a manual scan.")


class CaseReviewButton(ui.Button):
    def __init__(self):
        super().__init__(label="Case Review", emoji="📋", style=discord.ButtonStyle.primary, custom_id="case_review")

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message("📋 Case Review coming soon.", ephemeral=True)


class SettingsButton(ui.Button):
    def __init__(self):
        super().__init__(label="Settings", emoji="⚙️", style=discord.ButtonStyle.success, custom_id="settings_btn")

    async def callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("⚠️ Only admins can access settings.", ephemeral=True)
            return

        await interaction.response.send_message("⚙️ Settings modal coming soon.", ephemeral=True)


class ModerationControlView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # ✅ Required for persistence
        self.add_item(ModerationDropdown())
        self.add_item(RefreshPanelButton())
        self.add_item(ScanNowButton())
        self.add_item(CaseReviewButton())
        self.add_item(SettingsButton())


async def send_shadow_panel(channel: discord.TextChannel, force: bool = False):
    try:
        flagged_count = len(get_flagged_users())
        timeout_count = len([m for m in channel.guild.members if m.timed_out_until])

        embed = discord.Embed(
            title="🛡️ Shadow Moderation Panel",
            description=(
                "Manage flagged users and automate moderation actions.\n"
                "Use the dropdown below to view Mod Queue or other moderation tools."
            ),
            color=discord.Color.from_rgb(138, 43, 226),
            timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text="Dyno Replacement Bot — Elite Tier")
        embed.add_field(name="👤 Flagged Users", value=f"`{flagged_count}` in queue", inline=True)
        embed.add_field(name="⏳ Active Timeouts", value=f"`{timeout_count}` users", inline=True)
        embed.add_field(name="🕵️ Auto-Scan", value="`ON`", inline=True)

        await channel.send(embed=embed, view=ModerationControlView())

    except Exception as e:
        print("[ERROR] Failed to send control panel:", e)
