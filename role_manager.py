import discord
from discord.ui import View, Select
from discord import Interaction


class RoleManagerView(View):
    def __init__(self, roles: list[discord.Role], member: discord.Member):
        super().__init__(timeout=60)
        self.roles = roles
        self.member = member
        self.add_item(RoleDropdown(roles, member))


class RoleDropdown(Select):
    def __init__(self, roles: list[discord.Role], member: discord.Member):
        options = [
            discord.SelectOption(label=role.name, value=str(role.id))
            for role in roles if role < member.guild.me.top_role
        ]
        super().__init__(placeholder="Choose a role to assign/remove...", min_values=1, max_values=1, options=options)
        self.member = member

    async def callback(self, interaction: Interaction):
        role_id = int(self.values[0])
        role = interaction.guild.get_role(role_id)

        if role is None:
            await interaction.response.send_message("❌ Role not found.", ephemeral=True)
            return

        if role in self.member.roles:
            try:
                await self.member.remove_roles(role)
                await interaction.response.send_message(f"🔻 Removed role **{role.name}** from {self.member.mention}", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"❌ Failed to remove role: {e}", ephemeral=True)
        else:
            try:
                await self.member.add_roles(role)
                await interaction.response.send_message(f"🔺 Assigned role **{role.name}** to {self.member.mention}", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"❌ Failed to assign role: {e}", ephemeral=True)
