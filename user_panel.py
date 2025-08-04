import discord
from storage import log_audit, log_action_with_webhook

class MultiUserActionView(discord.ui.View):
    def __init__(self, members, moderator):
        super().__init__(timeout=60)
        self.members = members
        self.moderator = moderator
        self.selected = []

        options = [
            discord.SelectOption(label=member.name, value=str(member.id))
            for member in members[:25]
        ]
        self.select = discord.ui.Select(
            placeholder="Select users to moderate",
            options=options,
            min_values=1,
            max_values=len(options)
        )
        self.select.callback = self.select_callback
        self.add_item(self.select)

    async def select_callback(self, interaction: discord.Interaction):
        self.selected = [int(uid) for uid in interaction.data["values"]]
        self.clear_items()
        self.add_item(discord.ui.Button(label="Kick Selected", style=discord.ButtonStyle.danger))
        self.add_item(discord.ui.Button(label="Timeout Selected (10m)", style=discord.ButtonStyle.secondary))
        await interaction.response.edit_message(content="✅ Selected users. Choose an action:", view=self)

    @discord.ui.button(label="Kick Selected", style=discord.ButtonStyle.danger)
    async def kick_selected(self, button, interaction):
        count = 0
        for uid in self.selected:
            member = interaction.guild.get_member(uid)
            if member:
                try:
                    await member.kick(reason="Batch kick from panel")
                    log_audit("kick", uid, self.moderator)
                    log_action_with_webhook("kick", uid, self.moderator)
                    count += 1
                except:
                    continue
        await interaction.response.send_message(f"✅ Kicked {count} users.", ephemeral=True)

    @discord.ui.button(label="Timeout Selected (10m)", style=discord.ButtonStyle.secondary)
    async def timeout_selected(self, button, interaction):
        count = 0
        until = discord.utils.utcnow() + discord.timedelta(minutes=10)
        for uid in self.selected:
            member = interaction.guild.get_member(uid)
            if member:
                try:
                    await member.timeout(until, reason="Batch timeout from panel")
                    log_audit("timeout", uid, self.moderator)
                    log_action_with_webhook("timeout", uid, self.moderator)
                    count += 1
                except:
                    continue
        await interaction.response.send_message(f"⏱️ Timed out {count} users.", ephemeral=True)

async def view_user_sheet(interaction):
    try:
        members = [m for m in interaction.guild.members if not m.bot][:25]
        view = MultiUserActionView(members, interaction.user)
        await interaction.response.send_message("📋 Select users to moderate:", view=view, ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Failed to load user sheet: {e}", ephemeral=True)
