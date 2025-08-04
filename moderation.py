import discord
from storage import log_audit, log_action_with_webhook, load_flags, save_flags
from filters import get_severity_score


async def handle_mass_action(interaction, action="ban"):
    guild = interaction.guild
    members = [m for m in guild.members if not m.bot]
    count = 0

    for member in members:
        try:
            if action == "ban":
                await guild.ban(member, reason="Mass ban from Shadow Panel")
                log_audit("ban", member.id, interaction.user)
                log_action_with_webhook("ban", member.id, interaction.user)
                count += 1

            elif action == "kick":
                await guild.kick(member, reason="Mass kick from Shadow Panel")
                log_audit("kick", member.id, interaction.user)
                log_action_with_webhook("kick", member.id, interaction.user)
                count += 1

        except Exception:
            continue

    await interaction.response.send_message(f"✅ Mass `{action}` executed on {count} users.", ephemeral=True)


async def handle_shadowmute(interaction):
    shadowmute_role = discord.utils.get(interaction.guild.roles, name="ShadowMuted")
    if not shadowmute_role:
        shadowmute_role = await interaction.guild.create_role(name="ShadowMuted")

    for channel in interaction.guild.channels:
        try:
            await channel.set_permissions(shadowmute_role, send_messages=False, speak=False)
        except Exception:
            continue

    for member in interaction.guild.members:
        if not member.bot:
            try:
                await member.add_roles(shadowmute_role)
                log_audit("shadowmute", member.id, interaction.user)
                log_action_with_webhook("shadowmute", member.id, interaction.user)
            except Exception:
                continue

    await interaction.response.send_message("🔇 ShadowMute applied to all non-bot members.", ephemeral=True)


async def auto_flag_new_members(guild, bot):
    flagged = []
    flags = load_flags()

    for member in guild.members:
        if member.bot:
            continue

        score = get_severity_score(bot, member)
        if score >= 3:
            user_id = str(member.id)
            if user_id not in flags:
                flags[user_id] = {
                    "username": member.name,
                    "score": score,
                    "reason": "Flagged via scan"
                }
                flagged.append(member.id)

    save_flags(flags)
    return flagged
