# Shadow Bot - Elite Dyno Competitor

Instructions for Railway deployment and slash command setup.
💬 SLASH COMMANDS
/shadow
Opens the elite persistent moderation control panel
This panel lets moderators:

View flagged users

Approve / Kick / Timeout

Use dropdowns with severity and user info

All within a beautiful, persistent UI

/kick @user [reason]
Kicks a member with an optional reason
✅ Logs to webhook and database
✅ DM sent to user

/ban @user [reason]
Bans a member with optional reason
✅ Logs to webhook
✅ DM sent to user

/timeout @user [minutes] [reason]
Temporarily timeouts a user
✅ Accepts duration in minutes
✅ Logs action and reason

/warn @user [reason]
Sends a warning to a user
✅ Case is logged
✅ DM sent to user with reason

/scan
AI-scans all server members
✅ Flags users with suspicious:

Bio content

PFP status

Account age

Spammy usernames
✅ Adds them to the Mod Queue
✅ Sends update to mod thread/channel
