# cogs/member_utils.py
import asyncio
import json
import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import discord
from discord import ButtonStyle, Interaction, Option, OptionChoice
from discord.ext import commands
from discord.ui import View, Button

# ==============================================================================
# TELEMETRY
# ==============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | [ShadowSyn] %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("ShadowSyn.MemberUtils")

# ==============================================================================
# CONSTANTS & IDS
# ==============================================================================
THEME_PRIMARY = 0x2B0B35
THEME_GOLD = 0xFFD700
THEME_SUCCESS = 0x57F287
MEMBER_ROLE_ID = 955600320287887400
TARGET_GUILD_ID = 908659586536468540
GUILD_TZ = ZoneInfo("Australia/Sydney")

MAX_REMINDERS_PER_USER = 5
BAR_WIDTH = 8

POLL_DURATIONS = {
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "24h": timedelta(hours=24),
    "3d": timedelta(days=3),
    "never": None,
}

RELATIVE_RE = re.compile(r"^(\d+)(m|h|d)$", re.I)
CLOCK_RE = re.compile(
    r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$",
    re.I,
)

# ==============================================================================
# PERSISTENCE
# ==============================================================================
PERSIST_ROOT = Path(os.getenv("PERSIST_PATH", "/data")).resolve()
try:
    PERSIST_ROOT.mkdir(parents=True, exist_ok=True)
except Exception:
    PERSIST_ROOT = Path(".").resolve()

STORE_PATH = PERSIST_ROOT / "member_utils.json"


def _atomic_write(file_path: Path, data):
    try:
        content = json.dumps(data, indent=2)
        temp_path = file_path.with_suffix(".tmp")
        temp_path.write_text(content, encoding="utf-8")
        temp_path.replace(file_path)
    except Exception as e:
        logger.error(f"Persistence error [{file_path.name}]: {e}")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _from_iso(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


# ==============================================================================
# HELPERS
# ==============================================================================
async def safe_reply(ctx_or_inter, *args, **kwargs):
    try:
        if hasattr(ctx_or_inter, "respond"):
            return await ctx_or_inter.respond(*args, **kwargs)
        if hasattr(ctx_or_inter, "response"):
            if not ctx_or_inter.response.is_done():
                return await ctx_or_inter.response.send_message(*args, **kwargs)
            return await ctx_or_inter.followup.send(*args, **kwargs)
    except Exception:
        return None


def member_only():
    def predicate(ctx):
        if not isinstance(ctx.author, discord.Member):
            return False
        return any(r.id == MEMBER_ROLE_ID for r in ctx.author.roles)

    return commands.check(predicate)


def _parse_relative(raw: str) -> timedelta | None:
    m = RELATIVE_RE.match(raw.strip().lower())
    if not m:
        return None
    amount = int(m.group(1))
    unit = m.group(2).lower()
    if unit == "m":
        return timedelta(minutes=amount)
    if unit == "h":
        return timedelta(hours=amount)
    if unit == "d":
        return timedelta(days=amount)
    return None


def _parse_at_time(raw: str) -> datetime | None:
    """Parse clock time in guild TZ; roll to tomorrow if already passed."""
    raw = raw.strip().lower().replace(" ", "")
    m = CLOCK_RE.match(raw)
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    meridiem = (m.group(3) or "").lower()
    if meridiem == "pm" and hour < 12:
        hour += 12
    elif meridiem == "am" and hour == 12:
        hour = 0
    elif not meridiem and hour > 23:
        return None
    now_local = _utc_now().astimezone(GUILD_TZ)
    target = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now_local:
        target += timedelta(days=1)
    return target.astimezone(timezone.utc)


def parse_when(raw: str) -> datetime | None:
    """Relative (30m) or clock (8pm, 20:30) → UTC datetime."""
    raw = raw.strip()
    delta = _parse_relative(raw)
    if delta:
        return _utc_now() + delta
    return _parse_at_time(raw)


def _parse_poll_options(raw: str) -> list[str]:
    seen: set[str] = set()
    options: list[str] = []
    for part in raw.split(","):
        opt = part.strip()
        if not opt:
            continue
        key = opt.lower()
        if key in seen:
            continue
        seen.add(key)
        options.append(opt[:80])
    return options


def _bar(pct: float) -> str:
    filled = round(pct / 100 * BAR_WIDTH)
    filled = max(0, min(BAR_WIDTH, filled))
    return "█" * filled + "░" * (BAR_WIDTH - filled)


def _poll_vote_counts(poll: dict) -> list[int]:
    options = poll.get("options", [])
    counts = [0] * len(options)
    for idx in poll.get("votes", {}).values():
        if 0 <= idx < len(counts):
            counts[idx] += 1
    return counts


def build_poll_embed(poll: dict, *, closed: bool = False) -> discord.Embed:
    question = poll.get("question", "Poll")
    options = poll.get("options", [])
    counts = _poll_vote_counts(poll)
    total = sum(counts)

    lines = []
    for i, opt in enumerate(options):
        pct = (counts[i] / total * 100) if total else 0
        lines.append(f"**{opt}**\n{_bar(pct)} `{pct:.0f}%` · {counts[i]} vote{'s' if counts[i] != 1 else ''}")

    status = "Closed" if closed or poll.get("closed") else "Live"
    color = THEME_PRIMARY if status == "Live" else THEME_GOLD
    embed = discord.Embed(
        title=f"📊 {question}",
        description="\n\n".join(lines) if lines else "*No options*",
        color=color,
    )

    creator_id = poll.get("creator_id")
    expires_at = poll.get("expires_at")
    footer_parts = [status, f"{total} total vote{'s' if total != 1 else ''}"]
    if creator_id:
        footer_parts.insert(0, f"By <@{creator_id}>")
    if expires_at and not poll.get("closed"):
        try:
            ts = int(_from_iso(expires_at).timestamp())
            footer_parts.append(f"Ends <t:{ts}:R>")
        except Exception:
            pass
    elif closed or poll.get("closed"):
        footer_parts.append("Final results")
    embed.set_footer(text=" · ".join(footer_parts))
    return embed


# ==============================================================================
# UI — POLL
# ==============================================================================
class PollView(View):
    def __init__(self, poll_id: str, options: list[str], *, closed: bool = False):
        super().__init__(timeout=None)
        if not closed:
            for i, opt in enumerate(options[:5]):
                self.add_item(Button(
                    label=opt[:80],
                    style=ButtonStyle.secondary,
                    custom_id=f"mpoll_vote_{poll_id}_{i}",
                ))
            self.add_item(Button(
                label="End Poll",
                style=ButtonStyle.danger,
                emoji="🛑",
                custom_id=f"mpoll_end_{poll_id}",
                row=1,
            ))


class CountdownView(View):
    def __init__(self, countdown_id: str, *, done: bool = False):
        super().__init__(timeout=None)
        if not done:
            self.add_item(Button(
                label="Cancel",
                style=ButtonStyle.danger,
                emoji="✖",
                custom_id=f"mcd_cancel_{countdown_id}",
            ))


# ==============================================================================
# CORE COG
# ==============================================================================
class MemberUtilsCog(commands.Cog):
    def __init__(self, bot: discord.Bot):
        self.bot = bot
        self.data: dict = {"polls": {}, "reminders": {}, "countdowns": {}}
        self._poll_tasks: dict[str, asyncio.Task] = {}
        self._reminder_tasks: dict[str, asyncio.Task] = {}
        self._countdown_tasks: dict[str, asyncio.Task] = {}
        self._load_data()

    def cog_unload(self):
        for tasks in (self._poll_tasks, self._reminder_tasks, self._countdown_tasks):
            for task in list(tasks.values()):
                task.cancel()

    # --------------------------------------------------------------------------
    # PERSISTENCE
    # --------------------------------------------------------------------------
    def _load_data(self):
        if STORE_PATH.exists():
            try:
                loaded = json.loads(STORE_PATH.read_text(encoding="utf-8"))
                self.data["polls"] = loaded.get("polls", {}) or {}
                self.data["reminders"] = loaded.get("reminders", {}) or {}
                self.data["countdowns"] = loaded.get("countdowns", {}) or {}
                logger.info(
                    f"Member utils loaded: {len(self.data['polls'])} polls, "
                    f"{len(self.data['reminders'])} reminders, "
                    f"{len(self.data['countdowns'])} countdowns."
                )
            except Exception as e:
                logger.error(f"Corruption in {STORE_PATH.name}: {e}")
                self.data = {"polls": {}, "reminders": {}, "countdowns": {}}
        else:
            logger.info("No member_utils store found. Initializing empty state.")

    def _save(self):
        _atomic_write(STORE_PATH, self.data)

    # --------------------------------------------------------------------------
    # RESTORE ON READY
    # --------------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_ready(self):
        try:
            for poll_id, poll in list(self.data.get("polls", {}).items()):
                if poll.get("closed"):
                    continue
                options = poll.get("options", [])
                view = PollView(poll_id, options, closed=False)
                self.bot.add_view(view)
                self._schedule_poll_expiry(poll_id)
            for cd_id, cd in list(self.data.get("countdowns", {}).items()):
                if cd.get("done"):
                    continue
                view = CountdownView(cd_id, done=False)
                self.bot.add_view(view)
                self._schedule_countdown(cd_id)
            for rid in list(self.data.get("reminders", {}).keys()):
                self._schedule_reminder(rid)
            logger.info("Member utils persistent views and timers restored.")
        except Exception as e:
            logger.error(f"Member utils on_ready restore failed: {e}")

    # --------------------------------------------------------------------------
    # INTERACTIONS
    # --------------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        custom_id = interaction.data.get("custom_id", "") if interaction.data else ""

        if custom_id.startswith("mpoll_vote_"):
            parts = custom_id.split("_")
            if len(parts) < 4:
                return
            poll_id = parts[2]
            try:
                option_idx = int(parts[3])
            except ValueError:
                return
            await self._handle_poll_vote(interaction, poll_id, option_idx)
            return

        if custom_id.startswith("mpoll_end_"):
            poll_id = custom_id.replace("mpoll_end_", "")
            await self._handle_poll_end(interaction, poll_id)
            return

        if custom_id.startswith("mcd_cancel_"):
            cd_id = custom_id.replace("mcd_cancel_", "")
            await self._handle_countdown_cancel(interaction, cd_id)

    async def _handle_poll_vote(self, interaction: Interaction, poll_id: str, option_idx: int):
        poll = self.data.get("polls", {}).get(poll_id)
        if not poll or poll.get("closed"):
            return await safe_reply(interaction, "❌ This poll is closed.", ephemeral=True)

        if not isinstance(interaction.user, discord.Member):
            return await safe_reply(interaction, "❌ Members only.", ephemeral=True)
        if not any(r.id == MEMBER_ROLE_ID for r in interaction.user.roles):
            return await safe_reply(
                interaction,
                "❌ Members only — grab Minion in the Hub first.",
                ephemeral=True,
            )

        uid = str(interaction.user.id)
        votes = poll.setdefault("votes", {})
        options = poll.get("options", [])
        if option_idx < 0 or option_idx >= len(options):
            return await safe_reply(interaction, "❌ Invalid option.", ephemeral=True)

        if votes.get(uid) == option_idx:
            del votes[uid]
            msg = f"Vote removed from **{options[option_idx]}**."
        else:
            votes[uid] = option_idx
            msg = f"Voted for **{options[option_idx]}**."

        self._save()

        try:
            embed = build_poll_embed(poll)
            await interaction.message.edit(embed=embed)
        except Exception as e:
            logger.warning(f"Poll embed update failed: {e}")

        await safe_reply(interaction, f"✅ {msg}", ephemeral=True)

    async def _handle_poll_end(self, interaction: Interaction, poll_id: str):
        poll = self.data.get("polls", {}).get(poll_id)
        if not poll:
            return await safe_reply(interaction, "❌ Poll not found.", ephemeral=True)

        if str(interaction.user.id) != str(poll.get("creator_id")):
            return await safe_reply(interaction, "❌ Only the poll creator can end it.", ephemeral=True)

        await self._close_poll(poll_id)
        await safe_reply(interaction, "✅ Poll closed.", ephemeral=True)

    async def _close_poll(self, poll_id: str):
        poll = self.data.get("polls", {}).get(poll_id)
        if not poll or poll.get("closed"):
            return

        poll["closed"] = True
        self._save()

        task = self._poll_tasks.pop(poll_id, None)
        if task:
            task.cancel()

        channel_id = poll.get("channel_id")
        if not channel_id:
            return
        try:
            channel = self.bot.get_channel(int(channel_id)) or await self.bot.fetch_channel(int(channel_id))
            msg = await channel.fetch_message(int(poll_id))
            embed = build_poll_embed(poll, closed=True)
            await msg.edit(embed=embed, view=None)
        except Exception as e:
            logger.warning(f"Could not finalize poll {poll_id}: {e}")

    def _schedule_poll_expiry(self, poll_id: str):
        poll = self.data.get("polls", {}).get(poll_id)
        if not poll or poll.get("closed") or not poll.get("expires_at"):
            return

        if poll_id in self._poll_tasks:
            self._poll_tasks[poll_id].cancel()

        async def _expiry():
            try:
                ends = _from_iso(poll["expires_at"])
                delay = (ends - _utc_now()).total_seconds()
                if delay > 0:
                    await asyncio.sleep(delay)
                await self._close_poll(poll_id)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"Poll expiry task failed for {poll_id}: {e}")

        self._poll_tasks[poll_id] = asyncio.create_task(_expiry())

    # --------------------------------------------------------------------------
    # REMINDERS
    # --------------------------------------------------------------------------
    def _user_reminder_count(self, user_id: str) -> int:
        return sum(
            1 for r in self.data.get("reminders", {}).values()
            if str(r.get("user_id")) == str(user_id)
        )

    def _schedule_reminder(self, reminder_id: str):
        reminder = self.data.get("reminders", {}).get(reminder_id)
        if not reminder:
            return

        if reminder_id in self._reminder_tasks:
            self._reminder_tasks[reminder_id].cancel()

        async def _fire():
            try:
                fire_at = _from_iso(reminder["fire_at"])
                delay = (fire_at - _utc_now()).total_seconds()
                if delay > 0:
                    await asyncio.sleep(delay)
                await self._deliver_reminder(reminder_id)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"Reminder task failed for {reminder_id}: {e}")

        self._reminder_tasks[reminder_id] = asyncio.create_task(_fire())

    async def _deliver_reminder(self, reminder_id: str):
        reminder = self.data.get("reminders", {}).pop(reminder_id, None)
        if not reminder:
            return
        self._save()
        self._reminder_tasks.pop(reminder_id, None)

        user_id = int(reminder["user_id"])
        note = reminder.get("note", "Reminder")
        where = reminder.get("where", "dm")

        try:
            user = await self.bot.fetch_user(user_id)
        except Exception as e:
            logger.warning(f"Reminder user fetch failed {user_id}: {e}")
            return

        embed = discord.Embed(
            title="⏰ Reminder",
            description=note,
            color=THEME_GOLD,
        )
        ts = int(_from_iso(reminder["fire_at"]).timestamp())
        embed.set_footer(text=f"Set for <t:{ts}:F>")

        try:
            if where == "here":
                channel_id = reminder.get("channel_id")
                if channel_id:
                    channel = self.bot.get_channel(int(channel_id)) or await self.bot.fetch_channel(int(channel_id))
                    await channel.send(content=user.mention, embed=embed)
            else:
                await user.send(embed=embed)
        except discord.Forbidden:
            logger.warning(f"Reminder delivery forbidden for user {user_id}")
        except Exception as e:
            logger.error(f"Reminder delivery failed for {reminder_id}: {e}")

    # --------------------------------------------------------------------------
    # COUNTDOWNS
    # --------------------------------------------------------------------------
    def build_countdown_embed(self, cd: dict) -> discord.Embed:
        title = cd.get("title", "Countdown")
        ends_at = cd.get("ends_at")
        done = cd.get("done", False)

        if done:
            return discord.Embed(
                title=f"✅ {title}",
                description="**Started!**",
                color=THEME_SUCCESS,
            )

        try:
            end_dt = _from_iso(ends_at)
            ts = int(end_dt.timestamp())
            remaining = (end_dt - _utc_now()).total_seconds()
        except Exception:
            return discord.Embed(title=title, description="Invalid time.", color=THEME_PRIMARY)

        if remaining <= 0:
            return discord.Embed(
                title=f"✅ {title}",
                description="**Started!**",
                color=THEME_SUCCESS,
            )

        mins = max(1, int(remaining // 60)) if remaining >= 60 else 0
        secs = int(remaining % 60)
        if mins:
            remain_str = f"{mins} minute{'s' if mins != 1 else ''} remaining"
        else:
            remain_str = f"{secs} second{'s' if secs != 1 else ''} remaining"

        embed = discord.Embed(
            title=f"⏳ {title}",
            description=f"Starts <t:{ts}:R>\n<t:{ts}:F>",
            color=THEME_PRIMARY,
        )
        embed.set_footer(text=remain_str)
        if cd.get("creator_id"):
            embed.add_field(name="Posted by", value=f"<@{cd['creator_id']}>", inline=True)
        return embed

    def _schedule_countdown(self, cd_id: str):
        cd = self.data.get("countdowns", {}).get(cd_id)
        if not cd or cd.get("done"):
            return

        if cd_id in self._countdown_tasks:
            self._countdown_tasks[cd_id].cancel()

        async def _loop():
            try:
                while True:
                    cd_now = self.data.get("countdowns", {}).get(cd_id)
                    if not cd_now or cd_now.get("done"):
                        break
                    try:
                        end_dt = _from_iso(cd_now["ends_at"])
                    except Exception:
                        break
                    remaining = (end_dt - _utc_now()).total_seconds()
                    if remaining <= 0:
                        await self._finish_countdown(cd_id)
                        break
                    await self._update_countdown_message(cd_id)
                    await asyncio.sleep(min(60, max(1, remaining)))
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"Countdown loop failed for {cd_id}: {e}")

        self._countdown_tasks[cd_id] = asyncio.create_task(_loop())

    async def _update_countdown_message(self, cd_id: str):
        cd = self.data.get("countdowns", {}).get(cd_id)
        if not cd:
            return
        channel_id = cd.get("channel_id")
        if not channel_id:
            return
        try:
            channel = self.bot.get_channel(int(channel_id)) or await self.bot.fetch_channel(int(channel_id))
            msg = await channel.fetch_message(int(cd_id))
            embed = self.build_countdown_embed(cd)
            await msg.edit(embed=embed)
        except Exception as e:
            logger.warning(f"Countdown embed update failed {cd_id}: {e}")

    async def _finish_countdown(self, cd_id: str):
        cd = self.data.get("countdowns", {}).get(cd_id)
        if not cd or cd.get("done"):
            return

        cd["done"] = True
        self._save()
        self._countdown_tasks.pop(cd_id, None)

        channel_id = cd.get("channel_id")
        if not channel_id:
            return
        try:
            channel = self.bot.get_channel(int(channel_id)) or await self.bot.fetch_channel(int(channel_id))
            msg = await channel.fetch_message(int(cd_id))
            embed = self.build_countdown_embed(cd)
            await msg.edit(embed=embed, view=None)

            ping_role_id = cd.get("ping_role_id")
            if ping_role_id:
                role = channel.guild.get_role(int(ping_role_id)) if channel.guild else None
                if role:
                    await channel.send(
                        content=f"{role.mention} **{cd.get('title', 'Event')}** has started!",
                        allowed_mentions=discord.AllowedMentions(roles=True),
                    )
        except Exception as e:
            logger.warning(f"Countdown finish failed {cd_id}: {e}")

    async def _handle_countdown_cancel(self, interaction: Interaction, cd_id: str):
        cd = self.data.get("countdowns", {}).get(cd_id)
        if not cd:
            return await safe_reply(interaction, "❌ Countdown not found.", ephemeral=True)
        if str(interaction.user.id) != str(cd.get("creator_id")):
            return await safe_reply(interaction, "❌ Only the creator can cancel.", ephemeral=True)

        self.data["countdowns"].pop(cd_id, None)
        self._save()
        task = self._countdown_tasks.pop(cd_id, None)
        if task:
            task.cancel()

        try:
            await interaction.message.delete()
        except Exception:
            pass
        await safe_reply(interaction, "✅ Countdown cancelled.", ephemeral=True)

    # --------------------------------------------------------------------------
    # SLASH — /poll
    # --------------------------------------------------------------------------
    @discord.slash_command(
        name="poll",
        description="Create a live button poll with results.",
        guild_ids=[TARGET_GUILD_ID],
    )
    @member_only()
    async def poll(
        self,
        ctx: discord.ApplicationContext,
        question: Option(str, "What are you asking?", max_length=200),
        option1: Option(str, "Choice 1", max_length=80),
        option2: Option(str, "Choice 2", max_length=80),
        option3: Option(str, "Choice 3", required=False, max_length=80),
        option4: Option(str, "Choice 4", required=False, max_length=80),
        option5: Option(str, "Choice 5", required=False, max_length=80),
        duration: Option(
            str,
            "How long the poll stays open",
            choices=[
                OptionChoice("1 hour", "1h"),
                OptionChoice("6 hours", "6h"),
                OptionChoice("24 hours", "24h"),
                OptionChoice("3 days", "3d"),
                OptionChoice("No expiry", "never"),
            ],
            default="24h",
        ),
    ):
        parsed: list[str] = []
        seen: set[str] = set()
        for opt in (option1, option2, option3, option4, option5):
            if not opt:
                continue
            cleaned = opt.strip()[:80]
            if not cleaned:
                continue
            key = cleaned.lower()
            if key in seen:
                continue
            seen.add(key)
            parsed.append(cleaned)

        if len(parsed) < 2:
            return await safe_reply(
                ctx,
                "❌ Fill in at least **option1** and **option2**.",
                ephemeral=True,
            )

        delta = POLL_DURATIONS.get(duration)
        expires_at = _iso(_utc_now() + delta) if delta else None

        await safe_reply(ctx, "📊 Posting poll...", ephemeral=True)

        poll_data = {
            "channel_id": str(ctx.channel_id),
            "creator_id": str(ctx.author.id),
            "question": question,
            "options": parsed,
            "votes": {},
            "expires_at": expires_at,
            "closed": False,
        }

        embed = build_poll_embed(poll_data)
        view = PollView("pending", parsed)

        try:
            msg = await ctx.channel.send(embed=embed, view=view)
        except Exception as e:
            logger.error(f"Poll post failed: {e}")
            return await safe_reply(ctx, f"❌ Could not post poll: {e}", ephemeral=True)

        poll_id = str(msg.id)
        poll_data["channel_id"] = str(ctx.channel_id)
        self.data.setdefault("polls", {})[poll_id] = poll_data
        self._save()

        view = PollView(poll_id, parsed)
        self.bot.add_view(view)
        try:
            await msg.edit(view=view)
        except Exception:
            pass

        self._schedule_poll_expiry(poll_id)

    @poll.error
    async def poll_error(self, ctx: discord.ApplicationContext, error: discord.DiscordException):
        if isinstance(error, commands.CheckFailure):
            await safe_reply(
                ctx,
                "❌ Members only — grab Minion in the Hub first.",
                ephemeral=True,
            )
        else:
            logger.error(f"poll error: {error}")
            await safe_reply(ctx, f"⚠️ Error: {error}", ephemeral=True)

    # --------------------------------------------------------------------------
    # SLASH — /remindme
    # --------------------------------------------------------------------------
    @discord.slash_command(
        name="remindme",
        description="Set a personal reminder.",
        guild_ids=[TARGET_GUILD_ID],
    )
    @member_only()
    async def remindme(
        self,
        ctx: discord.ApplicationContext,
        note: Option(str, "What to remind you about", max_length=200),
        in_time: Option(str, "Relative time, e.g. 30m or 2h", required=False, default=None),
        at: Option(str, "Clock time today, e.g. 8pm or 20:30", required=False, default=None),
        where: Option(
            str,
            "Where to deliver",
            choices=[
                OptionChoice("DM", "dm"),
                OptionChoice("This channel", "here"),
            ],
            default="dm",
        ),
    ):
        if not in_time and not at:
            return await safe_reply(
                ctx,
                "❌ Provide either **in** (e.g. `30m`) or **at** (e.g. `8pm`).",
                ephemeral=True,
            )
        if in_time and at:
            return await safe_reply(ctx, "❌ Use **in** or **at**, not both.", ephemeral=True)

        raw = (in_time or at).strip()
        fire_dt = parse_when(raw) if in_time else _parse_at_time(raw)
        if not fire_dt:
            return await safe_reply(
                ctx,
                "❌ Could not parse that time. Try `30m`, `2h`, `8pm`, or `20:30`.",
                ephemeral=True,
            )
        if fire_dt <= _utc_now():
            return await safe_reply(ctx, "❌ That time is already in the past.", ephemeral=True)

        uid = str(ctx.author.id)
        if self._user_reminder_count(uid) >= MAX_REMINDERS_PER_USER:
            return await safe_reply(
                ctx,
                f"❌ You already have **{MAX_REMINDERS_PER_USER}** active reminders.",
                ephemeral=True,
            )

        reminder_id = str(uuid.uuid4())
        self.data.setdefault("reminders", {})[reminder_id] = {
            "user_id": uid,
            "channel_id": str(ctx.channel_id),
            "note": note,
            "fire_at": _iso(fire_dt),
            "where": where,
        }
        self._save()
        self._schedule_reminder(reminder_id)

        ts = int(fire_dt.timestamp())
        await safe_reply(
            ctx,
            f"✅ Reminder set for <t:{ts}:F> (<t:{ts}:R>).",
            ephemeral=True,
        )

    @remindme.error
    async def remindme_error(self, ctx: discord.ApplicationContext, error: discord.DiscordException):
        if isinstance(error, commands.CheckFailure):
            await safe_reply(
                ctx,
                "❌ Members only — grab Minion in the Hub first.",
                ephemeral=True,
            )
        else:
            logger.error(f"remindme error: {error}")
            await safe_reply(ctx, f"⚠️ Error: {error}", ephemeral=True)

    # --------------------------------------------------------------------------
    # SLASH — /countdown
    # --------------------------------------------------------------------------
    @discord.slash_command(
        name="countdown",
        description="Post a live countdown for an event.",
        guild_ids=[TARGET_GUILD_ID],
    )
    @member_only()
    async def countdown(
        self,
        ctx: discord.ApplicationContext,
        title: Option(str, "Event name", max_length=100),
        when: Option(str, "When — 30m, 2h, 8pm, 20:30", max_length=20),
        ping: Option(discord.Role, "Role to ping when it starts", required=False, default=None),
    ):
        end_dt = parse_when(when)
        if not end_dt:
            return await safe_reply(
                ctx,
                "❌ Could not parse **when**. Try `30m`, `2h`, `8pm`, or `20:30`.",
                ephemeral=True,
            )
        if end_dt <= _utc_now():
            return await safe_reply(ctx, "❌ That time is already in the past.", ephemeral=True)

        await safe_reply(ctx, "⏳ Posting countdown...", ephemeral=True)

        cd_data = {
            "channel_id": str(ctx.channel_id),
            "creator_id": str(ctx.author.id),
            "title": title,
            "ends_at": _iso(end_dt),
            "ping_role_id": str(ping.id) if ping else None,
            "done": False,
        }

        embed = self.build_countdown_embed(cd_data)
        view = CountdownView("pending")

        try:
            msg = await ctx.channel.send(embed=embed, view=view)
        except Exception as e:
            logger.error(f"Countdown post failed: {e}")
            return await safe_reply(ctx, f"❌ Could not post countdown: {e}", ephemeral=True)

        cd_id = str(msg.id)
        self.data.setdefault("countdowns", {})[cd_id] = cd_data
        self._save()

        view = CountdownView(cd_id)
        self.bot.add_view(view)
        try:
            await msg.edit(view=view)
        except Exception:
            pass

        self._schedule_countdown(cd_id)

    @countdown.error
    async def countdown_error(self, ctx: discord.ApplicationContext, error: discord.DiscordException):
        if isinstance(error, commands.CheckFailure):
            await safe_reply(
                ctx,
                "❌ Members only — grab Minion in the Hub first.",
                ephemeral=True,
            )
        else:
            logger.error(f"countdown error: {error}")
            await safe_reply(ctx, f"⚠️ Error: {error}", ephemeral=True)


def setup(bot: discord.Bot):
    bot.add_cog(MemberUtilsCog(bot))
