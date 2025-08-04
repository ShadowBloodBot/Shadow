import discord
from discord.utils import get
from storage import log_audit, log_action_with_webhook

class FilterUserModal(discord.ui.Modal, title="Filter Members"):
    search = discord.ui.TextInput(label="Username contains...", required=False, placeholder="Leave empty for all", max_length=50)
    join_range = discord.ui.TextInput(label="Joined within days (e.g. 1, 7, 30)", required=False, max_length=5)
    role_filter = discord.ui.TextInput(label="Role name (optional)", required=False, max_length=40)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            query = self.search.value.strip().lower()
            role_name = self.role_filter.value.strip()
            try:
                days = int(self.join_range.value.strip())
            except:
                days = None

            now = discord.utils.utcnow()
            members = []
            for m in interaction.guild.members:
                if m.bot:
                    continue
                if query and query not in m.name.lower() and query not in str(m.id):
                    continue
                if days:
                    delta = (now - m.joined_at).days
                    if delta > days:
                        continue
                if role_name and not get(m.roles, name=role_name):
                    continue
                members.append(m)

            if not members:
                await interaction.response.send_message("❌ No members matched your filter.", ephemeral=True)
                return

            view = MultiUserActionView(members, interaction.user)
            await interaction.response.send_message("✅ Select users to moderate:", view=view, ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(f"❌ Modal error: {e}", ephemeral=True)

class MultiUserActionView(discord.ui.View):
    def __init__(self, members, moderator):
        super().__init__(timeout=60)
        self.members = members
        self.moderator = moderator
        self.selected = []

        options = [discord.SelectOption(label=m.name, value=str(m.id)) for m in members[:25]]
        select = discord.ui.Select(placeholder="Select users", options=options, min_values=1, max_values=len(options))
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        self.selected = [int(uid) for uid in interaction.data["values"]]
        self.clear_items()
        self.add_item(discord.ui.Button(label="Kick Selected", style=discord.ButtonStyle.danger, custom_id="kick"))
        self.add_item(discord.ui.Button(label="Timeout Selected (10m)", style=discord.ButtonStyle.secondary, custom_id="timeout"))
        await interaction.response.edit_message(content="✅ Action options unlocked:", view=self)

    @discord.ui.button(label="Kick Selected", style=discord.ButtonStyle.danger, custom_id="kick")
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

    @discord.ui.button(label="Timeout Selected (10m)", style=discord.ButtonStyle.secondary, custom_id="timeout")
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
        await interaction.response.send_modal(FilterUserModal())
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to open modal: {e}", ephemeral=True)
