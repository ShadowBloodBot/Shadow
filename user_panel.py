import discord

class SearchUserModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="Search User")
        self.search_input = discord.ui.TextInput(label="Username/ID contains...", required=True)
        self.add_item(self.search_input)

    async def on_submit(self, interaction: discord.Interaction):
        query = self.search_input.value.lower()
        matches = [m for m in interaction.guild.members if query in m.name.lower() or query in str(m.id)]
        if not matches:
            await interaction.response.send_message("❌ No users matched.", ephemeral=True)
            return
        embed = discord.Embed(title="🔍 Search Results")
        for m in matches[:10]:
            embed.add_field(name=m.name, value=f"ID: {m.id} | Joined: {m.joined_at.strftime('%Y-%m-%d')}", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def view_user_sheet(interaction):
    modal = SearchUserModal()
    await interaction.response.send_modal(modal)
