import discord
from analytics import post_webhook_log
from config import WEBHOOK_URL
from ai_suggestions import suggest_action, get_severity_score

class TwoFactorBanModal(discord.ui.Modal):
    def __init__(self, member):
        super().__init__(title="Confirm Ban")
        self.member = member
        self.code_input = discord.ui.TextInput(label="Type CONFIRM to ban this user", required=True)
        self.add_item(self.code_input)

    async def on_submit(self, interaction: discord.Interaction):
        if self.code_input.value.strip().upper() == "CONFIRM":
            await self.member.ban(reason="Manual ban from Shadow Bot")
            await interaction.response.send_message(f"✅ {self.member.mention} banned.", ephemeral=True)
            await post_webhook_log(WEBHOOK_URL, f"[2FA Ban] {self.member} banned by {interaction.user.name}")
        else:
            await interaction.response.send_message("❌ Confirmation failed. User not banned.", ephemeral=True)

class ModQueueView(discord.ui.View):
    def __init__(self, flagged_members):
        super().__init__(timeout=120)
        self.flagged_members = sorted(flagged_members, key=get_severity_score, reverse=True)[:25]
        self.options = [
            discord.SelectOption(label=f"{member.name} (S:{get_severity_score(member)})", value=str(member.id), description=suggest_action(member)) 
            for member in self.flagged_members
        ]
        self.select = discord.ui.Select(placeholder="Review flagged users", options=self.options)
        self.select.callback = self.select_callback
        self.add_item(self.select)

    async def select_callback(self, interaction: discord.Interaction):
        member_id = int(self.select.values[0])
        member = interaction.guild.get_member(member_id)
        action = suggest_action(member)
        embed = discord.Embed(title="Moderation Suggestion", description=f"User: {member.mention}")
        embed.add_field(name="Suggested Action", value=action)
        embed.add_field(name="Severity", value=str(get_severity_score(member)))
        embed.add_field(name="Joined", value=member.joined_at.strftime('%Y-%m-%d'))
        await interaction.response.send_message(embed=embed, view=BanConfirmButton(member), ephemeral=True)

class BanConfirmButton(discord.ui.View):
    def __init__(self, member):
        super().__init__(timeout=30)
        self.member = member

    @discord.ui.button(label="Ban with 2FA", style=discord.ButtonStyle.danger)
    async def confirm(self, button, interaction):
        modal = TwoFactorBanModal(self.member)
        await interaction.response.send_modal(modal)
