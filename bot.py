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

    flagged = []
    flags = load_flags()

    try:
        members = []
        async for member in interaction.guild.fetch_members(limit=None):
            members.append(member)
    except Exception:
        members = [m for m in interaction.guild.members if not m.bot]

    batch_size = 50
    delay_sec = 2

    total = len(members)
    scanned = 0

    for i in range(0, total, batch_size):
        batch = members[i:i + batch_size]
        for member in batch:
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

        scanned += len(batch)
        await progress_msg.edit(content=f"🔄 Scanning... `{scanned}/{total}` checked. `{len(flagged)}` flagged.")
        await bot.wait_until_ready()
        await discord.utils.sleep_until(discord.utils.utcnow() + discord.utils.timedelta(seconds=delay_sec))

    save_flags(flags)

    if flagged:
        await progress_msg.edit(content=f"🚨 Scan complete. `{len(flagged)}` user(s) flagged and added to the Mod Queue.")
    else:
        await progress_msg.edit(content="✅ Scan complete. No flagged users found.")
