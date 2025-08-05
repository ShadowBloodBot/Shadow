@bot.tree.command(name="scan", description="Scan all members and flag suspicious ones")
async def scan(interaction: discord.Interaction):
    if not has_shadow_access(interaction.user):
        await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)
        return

    await interaction.response.send_message("🔍 Starting scan...", ephemeral=True)

    try:
        progress_msg = await interaction.channel.send("🔎 Scanning members... This may take a moment.")
    except discord.Forbidden:
        await interaction.followup.send("❌ Bot lacks permission to post updates.", ephemeral=True)
        return

    from filters import score_member
    flags = load_flags()
    flagged = []

    try:
        members = []
        async for m in interaction.guild.fetch_members(limit=None):
            members.append(m)
    except Exception:
        members = [m for m in interaction.guild.members if not m.bot]

    scanned = 0
    total = len(members)

    for member in members:
        scanned += 1

        try:
            user = await bot.fetch_user(member.id)
        except Exception:
            continue

        score, reason = score_member(member, user)

        if score >= 1:
            user_id = str(member.id)
            if user_id not in flags:
                flags[user_id] = {
                    "username": member.name,
                    "score": score,
                    "reason": reason
                }
                flagged.append(member.id)

        if scanned % 10 == 0 or scanned == total:
            await progress_msg.edit(content=f"🔄 Scanned `{scanned}/{total}` members — `{len(flagged)}` flagged.")

    save_flags(flags)

    if flagged:
        await progress_msg.edit(content=f"🚨 Scan complete. `{len(flagged)}` user(s) flagged and added to the Mod Queue.")
    else:
        await progress_msg.edit(content="✅ Scan complete. No flagged users found.")
