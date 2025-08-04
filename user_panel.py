import discord
from storage import log_audit, log_action_with_webhook

class UserActionView(discord.ui.View):
    def __init__(self, member, moderator):
        super().__init__(timeout=60)
        self.member = member
        self.moderator = moderator

    @discord.ui.button(label="Kick", style=discord.ButtonStyle.danger)
    async def kick(self, button, interaction):
        try:
            await self.member.kick(reason="Manual kick from Shadow panel")
            log_audit("kick", self.member.id, self.moderator)
            log_action_with_webhook("kick", self.member.id, self.moderator)
            await interaction.response.send_message(f"✅ {self.member.mention} has been kicked.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to kick: {e}", ephemeral=True)

    @discord.ui.button(label="Timeout 10m", style=discord.ButtonStyle.secondary)
    async def timeout(self, button, interaction):
        try:
            duration = discord.utils.utcnow() + discord.timedelta(minutes=10)
            await self.member.timeout(duration, reason="Timeout from Shadow panel")
            log_audit("timeout_10m", self.member.id, self.moderator)
            log_action_with_webhook("timeout_10m", self.member.id, self.moderator)
            await interaction.response.send_message(f"⏱️ {self.member.mention} has been timed out.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to timeout: {e}", ephemeral=True)

async def view_user_sheet(interaction):
    members = interaction.guild.members[:25]
    options = [
        discord.SelectOption(label=member.name, value=str(member.id))
        for member in members
    ]
    select = discord.ui.Select(placeholder="Select a user", options=options)

    async def select_callback(interaction2):
        user_id = int(select.values[0])
        member = interaction.guild.get_member(user_id)
        embed = discord.Embed(title="User Sheet", description=f"Details for {member.mention}")
        embed.add_field(name="ID", value=member.id)
        embed.add_field(name="Roles", value=", ".join([r.name for r in member.roles if r.name != "@everyone"]))
        embed.add_field(name="Joined", value=member.joined_at.strftime('%Y-%m-%d'))
        view = UserActionView(member, interaction.user)
        await interaction2.response.send_message(embed=embed, view=view, ephemeral=True)

    select.callback = select_callback
    view = discord.ui.View(timeout=60)
    view.add_item(select)
    await interaction.response.send_message("📋 Select a user to manage", view=view, ephemeral=True)
