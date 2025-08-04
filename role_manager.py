async def launch_role_manager(interaction):
    guild = interaction.guild
    roles = [role for role in guild.roles if role.name != "@everyone"]
    options = [discord.SelectOption(label=role.name, value=str(role.id)) for role in roles[:25]]

    select = discord.ui.Select(placeholder="Select a role to assign/remove", options=options)
    
    async def select_callback(interaction2):
        role_id = int(select.values[0])
        role = discord.utils.get(guild.roles, id=role_id)
        count = 0
        for member in guild.members:
            if not member.bot:
                try:
                    if role not in member.roles:
                        await member.add_roles(role)
                        count += 1
                except:
                    continue
        await interaction2.response.send_message(f"✅ Role `{role.name}` assigned to {count} members.", ephemeral=True)

    select.callback = select_callback
    view = discord.ui.View(timeout=60)
    view.add_item(select)
    await interaction.response.send_message("🎚 Role Manager", view=view, ephemeral=True)
