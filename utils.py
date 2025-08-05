import discord

def has_permission(member: discord.Member, perm: str) -> bool:
    perms = getattr(member.guild_permissions, perm, None)
    return perms is True

def format_case_embed(action: str, member: discord.Member, mod: discord.Member, reason: str) -> discord.Embed:
    return (
        discord.Embed(title=f"📝 Case Log – {action.title()}", color=discord.Color.orange())
        .add_field(name="Target", value=f"{member} ({member.id})", inline=False)
        .add_field(name="Moderator", value=f"{mod} ({mod.id})", inline=False)
        .add_field(name="Reason", value=reason or "No reason provided.", inline=False)
    )
