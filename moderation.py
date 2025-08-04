import discord
from storage import log_audit
from filters import ai_flag_user

async def handle_mass_action(interaction, action="ban"):
    guild = interaction.guild
    members = [m for m in guild.members if not m.bot]
    count = 0
    if action == "ban":
        for member in members:
            try:
                await guild.ban(member, reason="Mass ban from Shadow Panel")
                log_audit("ban", member.id, interaction.user)
                count += 1
            except Exception:
                continue
        await interaction.response.send_message(f"✅ Mass ban executed on {count} users.", ephemeral=True)

async def handle_shadowmute(interaction):
    shadowmute_role = discord.utils.get(interaction.guild.roles, name="ShadowMuted")
    if not shadowmute_role:
        shadowmute_role = await interaction.guild.create_role(name="ShadowMuted")
    for channel in interaction.guild.channels:
        try:
            await channel.set_permissions(shadowmute_role, send_messages=False, speak=False)
        except:
            continue
    for member in interaction.guild.members:
        if not member.bot:
            try:
                await member.add_roles(shadowmute_role)
                log_audit("shadowmute", member.id, interaction.user)
            except:
                continue
    await interaction.response.send_message("🔇 ShadowMute applied to all non-bot members.", ephemeral=True)

async def auto_flag_new_members(guild):
    flagged = []
    for member in guild.members:
        if not member.bot and ai_flag_user(member):
            flagged.append(member.id)
    return flagged
